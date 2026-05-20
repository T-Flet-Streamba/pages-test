import pandas as pd
from datetime import datetime, timedelta, time
from pymongo.mongo_client import MongoClient
from pymongo.collection import Collection
from collections import defaultdict
from copy import deepcopy
from typing import Union

import config


class CosmosDBs:
    """
    Wrapper for the Cosmos dbs (via pymongo); it abstracts both dev/live and main/cvx instances,
    making it easy to query collections and aggregate their outputs
    (since might want to query same ones in different databases depending on the region).
    Not an abstract class, but inheriting from it is encouraged in order to pre-package queries (e.g. through CosmosCollection).
    """
    def __init__(self, timeout=10000):
        """
        Initialise the database with the connection string depending on environment.
        """
        self.db_prefix = config.cosmos.db_prefix
        self.mongo_main = MongoClient(config.cosmos.main_db, serverSelectionTimeoutMS=timeout)
        self.mongo_cvx = MongoClient(config.cosmos.cvx_abu_db, serverSelectionTimeoutMS=timeout)

    def get_collection(self, db_suffix: str, collection: str, db_is_cvx = True) -> Collection:
        """
        Connect to the collection of the given suffix from the main or cvx Cosmos database (depending on db_is_cvx).
        (The dev/live Cosmos instance is determined by environment variable).
        """
        return (self.mongo_cvx if db_is_cvx else self.mongo_main)[self.db_prefix + db_suffix][collection]

    def query(self, collection: Union[Collection, str], query: dict, db_suffix: str = None, db_is_cvx = True) -> pd.DataFrame:
        """
        Query the given collection, returning a Pandas dataframe of results.
        Can specify the collection either as a Collection (from the .collection method) or with a name and db_suffix
        (note that db_is_cvx is True by default and only used if collection is a string).
        """
        if isinstance(collection, str):
            assert db_suffix, 'If the collection argument is a string, the method requires a db_suffix (note that db_is_cvx is True by default).'
            collection = self.get_collection(db_suffix=db_suffix, collection=collection, db_is_cvx=db_is_cvx)

        res = list(collection.find(query).sort('Start'))
        df = pd.json_normalize(res)  # json_normalize extracts nested objects
        return df


class CosmosCollection(CosmosDBs):
    """Wrapper for a single Cosmos collection (specified on instantiation).
    Allows optional caching of results (with fixed lifespan).
    The keys to the cache are the used method and then the query dictionaries cast to strings (because dicts are not hashable).
    The cache lifespan can be given in minutes or as a datetime.timedelta.
    Not an abstract class, but inheriting from it is encouraged in order to pre-package queries.
    """
    def __init__(self, db_suffix: str, collection: str, db_is_cvx = True,
                 cache_mins_or_delta: Union[int, timedelta] = 15):
        super().__init__()
        self.coll = self.get_collection(db_suffix=db_suffix, collection=collection, db_is_cvx=db_is_cvx)
        # Cache:         method -> str(query) -> (datetime, df)
        self.cache: dict[str, dict[str, tuple[datetime, pd.DataFrame]]] = defaultdict(dict)
        self.cache_lifespan = cache_mins_or_delta * 60 if isinstance(cache_mins_or_delta, int) else cache_mins_or_delta.total_seconds()

    def _clean_cache(self, cache_key: str):
        now = datetime.now()
        for query_tuple in list(self.cache[cache_key]):  # not .items because deleting entries
            if (now - self.cache[cache_key][query_tuple][0]).total_seconds() > self.cache_lifespan:
                del self.cache[cache_key][query_tuple]

    def coll_query(self, query: dict, cache_key: str = None, cache_by_field: str = None) -> pd.DataFrame:
        """Like CosmosDBs.query, but not taking collection arguments and possibly using a cache.
        To use the cache, pass a key to the cache_key argument; it is intended to be the calling method's name.
        If a field is given to cache_by_field (cache_key is still required),
        the query MUST be performing an '$in' operation for it;
        then results for each value of that field will be cached separately using "individual" queries as sub-keys
        (i.e. the original query but with single values instead of the '$in' operation).
        """
        if cache_key:
            self._clean_cache(cache_key)  # no need to check datetimes below vv because already cleaned
            now = datetime.now()
            if cache_by_field:
                if (field := query.get(cache_by_field)) and (vals := field.get('$in')):
                    # Same (str) queries as the full one, but with the $in operation replaced by single values
                    individual_keys = {v: str({**q, cache_by_field: v}) for v in vals if (q := deepcopy(query))}

                    individual_res = {}
                    if meth_cache := self.cache.get(cache_key):
                        # dict[individual value, tuple[datetime, dataframe]]
                        individual_res = {v: res for v, q in individual_keys.items() if (res := meth_cache.get(q))}

                    if vals_not_in_cache := list(set(vals).difference(individual_res.keys())):
                        query[cache_by_field]['$in'] = vals_not_in_cache
                        res_df = self.query(self.coll, query)
                        individual_res.update({
                            v: (now, pd.DataFrame() if res_df.empty else res_df[res_df[cache_by_field] == v])
                        for v in vals_not_in_cache})

                    # Update cache entries only if something was returned for those values
                    meth_cache.update({individual_keys[v]: t_df for v in vals if not (t_df := individual_res[v])[1].empty})
                    return pd.concat([df for _, df in individual_res.values()], axis=0)
                else:
                    raise ValueError(f"'{cache_by_field}' was used as the cache_by_field_instead value, "
                                     f"but there is no '$in' operation with it in the query.")
            else:
                query_id = str(query)  # dicts are not hashable, hence string keys; field order is guaranteed consistent
                if (meth_cache := self.cache.get(cache_key)) and (res := meth_cache.get(query_id)):
                    # If had not _clean_cache-ed, would also need: (now - res[0]).total_seconds() <= self.cache_lifespan
                    return res[1]
                else:
                    self.cache[cache_key][query_id] = (now, out := self.query(self.coll, query))
                    return out  # note: no update on unsuccessful calls
        else:
            return self.query(self.coll, query)


class AISData(CosmosCollection):
    """Wrapper for the chevronvesselais Cosmos collection.
    """
    def __init__(self, cache_mins_or_delta: Union[int, timedelta] = 15):
        super().__init__('-cvx-abu-set2', 'chevronvesselais', cache_mins_or_delta=cache_mins_or_delta)

    def get_by_mmsi(self, mmsi: Union[str, list[str]]) -> dict:
        """
        Get the latest ais for the given vessel MMSI.
        """
        if not mmsi:
            return None
        recently = datetime.combine(datetime.now() - timedelta(weeks=2), time.min)  # midnight n weeks ago
        out = self.coll_query(
            dict(  # vv use the $in operator even for single values for consistency; no extra cost
                MmsiCode={'$in': [mmsi] if isinstance(mmsi, str) else mmsi},
                Timestamp={'$gte': recently}
            ),
            cache_key='get_by_mmsi',
            cache_by_field='MmsiCode'
        )
        if out.empty:
            return {}
        else:
            # Indices of the most recent row for each vessel
            max_indices = out.groupby('MmsiCode')['Timestamp'].idxmax()
            out = out.loc[max_indices].set_index('MmsiCode')
            return out.to_dict('index')



class Locations(CosmosCollection):
    """Wrapper for the chevronvesselais Cosmos collection.
    """
    def __init__(self, cache_mins_or_delta: Union[int, timedelta] = timedelta(weeks=52)):
        super().__init__('', 'locations', db_is_cvx=False, cache_mins_or_delta=cache_mins_or_delta)

    def coords_by_id(self, _id: str) -> Union[dict, None]:
        """
        Get the coordinates of the given location.
        """
        out = self.coll_query(dict(id=_id), cache_key='coords_by_id')
        return None if out.empty else (out.at[0, 'position.lat'], out.at[0, 'position.lng'])

    def coords_by_org(self, org: str) -> Union[tuple[dict, dict], None]:
        """
        Get the coordinates of all locations for the given organisation.
        """
        out = self.coll_query(dict(organization=org), cache_key='coords_by_org')
        if out.empty:
            return None
        else:
            coords = {row['id']: (row['position.lat'], row['position.lng']) for _, row in out.iterrows()}
            display_to_id = {row['displayName']: row['id'] for _, row in out.iterrows()}
            return coords, display_to_id


