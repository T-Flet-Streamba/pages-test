import json
import redis
from datetime import timedelta

import config


class Redis:
    def __init__(self, org: str):
        redis_connection_string = config.redis.connection_str
        if not redis_connection_string:
            raise ValueError("Redis connection string env var not set")

        self.org = org
        self.uc = redis.from_url(redis_connection_string)

    def del_entries(self, cache_path: str, keys: list[str], del_sub_keys = False) -> list[int]:
        """Returns the number of individual cache entries which were found and deleted for each given key.
        If del_sub_keys then the keys are treated as the stem from which to look for sub-keys to delete
        (they are treated as the terminal keys otherwise).
        """
        if del_sub_keys:
            return [self._del_bulk_data(f'{cache_path}::{key}', None) for key in keys]
        else:
            return [self._del_bulk_data(cache_path, keys)]

    def get_entries(self, cache_path: str, keys: list[str] = None, get_sub_keys = False, return_grouped_sub_keys = True) -> dict[str, dict | None]:
        """If keys is set to [] or None, then ALL key-values in the cache are returned.
        If get_sub_keys then the keys are treated as the stem from which to look for sub-keys to retrieve
        (they are treated as the terminal keys otherwise).
        Additionally, if return_grouped_sub_keys is also true, results are grouped by the given keys: key -> sub-keys.
        """
        keys = keys if keys else []
        try:  # vv the function ultimately called by the redis library already does a retry
            if get_sub_keys:
                all_keys = self._get_keys(cache_path, return_relative_keys=True)  # best for Redis to do a single fetch of all keys and filter them here
                sub_keys_by_stem = {stem: [key for key in all_keys if key.startswith(stem)] for stem in keys}
                data = self._get_bulk_data(cache_path, [sub_key for sub_keys in sub_keys_by_stem.values() for sub_key in sub_keys])
            else:
                data = self._get_bulk_data(cache_path, keys)
        except Exception as e:  # no need to be more specific
            return {k: None for k in keys}

        for key in data:
            try:
                decoded = data[key].decode('utf-8')  # the cache returns byte strings
                try:  # if JSON, convert to a Python object
                    data[key] = json.loads(decoded)
                except Exception:
                    data[key] = decoded  # fallback to plain string
            except Exception:
                data[key] = None  # fallback if decoding fails entirely

        if get_sub_keys and return_grouped_sub_keys:
            data = {stem: {key[len(stem)+2:]: data[key] for key in keys} for stem, keys in sub_keys_by_stem.items()}

        return data

    def set_entries(self, cache_path: str, keys_and_values: dict):  # friendly alias of the private method
        """Efficiently set multiple entries in a single interaction."""
        return self._set_bulk_data(cache_path, keys_and_values)

    def _del_bulk_data(self, cache_path: str, sub_keys: list[str] | None) -> int:
        """Remove data for each id under a specific base path (then '::id' for each entry).
        If sub_keys is set to [] or None, then ALL key-values "under" the cache_path are deleted.
        Returns the number of keys which were found and deleted.
        """
        if sub_keys:                     # vv following our convention of an empty layer (i.e. 2 colons in a row)
            keys = [f'{cache_path}::{sub_key}' for sub_key in sub_keys]
        else:  # ^^ vv in either case want the full keys, so either add or do not remove the stem
            keys = self._get_keys(cache_path)
        return self.uc.delete(*keys) if keys else 0

    def _get_keys(self, cache_path: str, return_relative_keys = False) -> list[str]:
        """Get all the keys "under" a specific Redis cache path.
        If return_relative_keys is True then the cache_path prefix is not included in the output strings.
        """
        keys = [k.decode('utf-8') for k in self.uc.keys(f'{cache_path}*')]  # bytestrings -> strings
        return [k[len(cache_path)+2:] for k in keys] if return_relative_keys else keys

    def _get_keys_by_scan(self, cache_path: str, return_relative_keys = False, max_batches = 10) -> list[str]:
        """Same as _get_keys but using SCAN instead of KEYS to be extra safe (not a blocking operation, so good for large results),
        but at the price of NOT guaranteeing that ALL results are returned; see https://redis.io/docs/latest/commands/scan/.
        Get all the keys "under" a specific Redis cache path.
        If return_relative_keys is True then the cache_path prefix is not included in the output strings.
        Use max_batches mostly as a safeguard against errors on the Redis side (causing an infinite loop by not updating the counter).
        """
        batch_counter, cursor, keys = 0, 0, set()
        while True:                     # vv index whence to pick up results        vv max batch size
            cursor, batch = self.uc.scan(cursor=cursor, match=f'{cache_path}*', count=100)
            keys.update(batch)  # a set because SCAN is stateless, so it is not impossible to get batch overlaps
            batch_counter += 1
            if cursor == 0 or batch_counter > max_batches:
                break
        keys = [k.decode('utf-8') for k in keys]  # bytestrings -> strings
        return [k[len(cache_path)+2:] for k in keys] if return_relative_keys else keys

    def _get_data(self, cache_path: str):
        """Get data from a specific Redis cache path
        """
        data_raw = self.uc.get(cache_path)
        if data_raw:
            try:
                decoded = data_raw.decode('utf-8')  # the cache returns byte strings
                try:  # if JSON, convert to a Python object
                    return json.loads(decoded)
                except Exception:
                    return decoded  # fallback to plain string
            except Exception:
                return None  # fallback if decoding fails entirely

    def _get_bulk_data(self, cache_path: str, sub_keys: list[str] = None) -> dict[str, str | None]:
        """Efficiently retrieve data for each id under a specific base path (then '::id' for each entry).
        If sub_keys is set to [] or None, then ALL key-values "under" the cache_path are returned.
        Returns a dict[key, cached value | None if not there].
        """
        sub_keys = sub_keys if sub_keys else []
        if sub_keys:                     # vv following our convention of an empty layer (i.e. 2 colons in a row)
            keys = [f'{cache_path}::{sub_key}' for sub_key in sub_keys]
        else:  # ^^ vv in either case want the full keys, so either add or do not remove the stem
            keys = self._get_keys(cache_path)
        results = self.uc.mget(keys)  # vv return only relative keys though
        return dict(zip(sub_keys if sub_keys else [k[len(cache_path)+2:] for k in keys], results))

    def _set_data(self, cache_path: str, data: str | dict | list, get=True, ttl=timedelta(days=180)):
        """Set data at a specific Redis cache path.
        If data is not a str it will be converted to JSON before uploading it.
        If get==True, the return value is the previous value of that cache path if it existed (or None if not).

        NOTE: by default this method sets a time-to-live of 180 days on created cache entries;
        can change this by passing a datetime.timedelta object to the ttl argument.
        """
        if not isinstance(data, str):
            data = json.dumps(data)
        return self.uc.set(cache_path, data, get=get, ex=ttl)

    def _set_bulk_data(self, cache_path: str, entries_by_id: dict[str, str | dict | list], ttl=timedelta(days=180)):
        """Efficiently set data for each key of entries_by_id at a specific base Redis cache path (then '::key' for each entry).
        If values of entries_by_id are not a str they will be converted to JSON before uploading them.

        NOTE: by default this method sets a time-to-live of 180 days on created cache entries;
        can change this by passing a datetime.timedelta object to the ttl argument.
        """
        pipe = self.uc.pipeline()
        for k, v in entries_by_id.items():
            if not isinstance(v, str):
                v = json.dumps(v)
            # vv following our convention of an empty layer (i.e. 2 colons in a row)
            pipe.set(f'{cache_path}::{k}', v, ex=ttl)
        statuses = pipe.execute()
        return dict(zip(entries_by_id.keys(), statuses))


class SpecificRedisCache(Redis):
    """Read or write a specific Redis cache (overrides the cache_path argument of the friendly methods of the Redis cache)."""

    def __init__(self, org: str, cache_path: str):
        super().__init__(org=org)
        self.cache_path = cache_path

    def del_entries(self, keys: list[str], del_sub_keys = False) -> list[int]:
        return super().del_entries(self.cache_path, keys=keys, del_sub_keys=del_sub_keys)

    def get_entries(self, keys: list[str] = None, get_sub_keys = False) -> dict[str, dict | None]:
        return super().get_entries(self.cache_path, keys=keys, get_sub_keys=get_sub_keys)

    def set_entries(self, keys_and_values: dict):
        return super().set_entries(self.cache_path, keys_and_values=keys_and_values)

    def get_keys(self) -> list[str]:
        return super()._get_keys(self.cache_path, return_relative_keys=True)


