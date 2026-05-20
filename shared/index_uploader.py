from time import sleep
from azure.functions import HttpResponse
from logging import Logger
from itertools import batched
from typing import Callable, Union

from collabgpt_lg.endpoints_base import AISearchBaseClass
from collabgpt_lg.utils import org_state


class IndexUploader(AISearchBaseClass):
    """Class to manage uploads to AI Search indexing endpoints, providing batching and retries.
    """

    def __init__(self, endpoint_url: str, org: str, logger: Logger):
        super().__init__(org_state(org), supported_orgs=[org])  # the org is for documentation in this case
        self.url_endpoint = endpoint_url
        self.logger = logger
        self.name = parts[1] if len(parts := endpoint_url.split('/')) > 1 else endpoint_url

    def single_upload_with_retries(self, data: list[dict], prefix: str, remove_no_data_entries: bool = True,
                                   retry_limit: int = 3, retry_delay: int = 3) -> HttpResponse:
        if isinstance(data, list) and remove_no_data_entries:
            old_n = len(data)
            data = [d for d in data if d and d != dict(status='no data available')]
            if len(data) != old_n:
                self.logger.info('%s entries with no data were removed before uploading to the indexer.', old_n - len(data))

        if not data:
            self.logger.warning('%s - No entries to send for indexing.', self.name)
            return HttpResponse(f'No entries to send for indexing', status_code=400)

        r = 1
        while r <= retry_limit:
            try:
                result = self._send_request(method='POST', verbose=False, json=data)  # str or raises error
                self.logger.info('%s - %s: %s entries uploaded to indexer.', self.name, prefix, len(data))
                return HttpResponse(f'{prefix}: {len(data)} entries to indexer.', status_code=200)
            except Exception as e:
                if r == retry_limit:
                    self.logger.error('%s - %s: %s attempts of sending entries to indexer failed: %s.', self.name, prefix, r, e)
                    return HttpResponse(f'{prefix}: {r} attempts of sending entries to indexer failed: {e}.',
                                        status_code=500)
                else:
                    self.logger.info('%s - %s: Attempt %s/%s of sending entries to indexer failed; '
                                'retrying after %s seconds. The error was the following: %s.',
                                self.name, prefix, r, retry_limit, retry_delay, e)
                    sleep(retry_delay)
            finally:
                r += 1

    def batched_upload(self, data_or_ids: Union[list[dict], list[str]], upload_batch_size: int = 200,
                       upload_retry_limit: int = 3, upload_retry_delay: int = 3,
                       ids_to_data: Callable = None) -> HttpResponse:
        """This function can upload already-retrieved entries or can look them up in the same batch loop using ids_to_data.
        If ids_to_data is given, then data_or_ids needs to contain ids to retrieve, batches of which will be passed to it.
        On failures, ids_to_data should not raise errors but instead return a dict with at most 1 entry
        (typically this is dict(status='No data available')).
        """
        if not data_or_ids:
            self.logger.error('%s - No data to upload or ids to retrieve.', self.name)
            return HttpResponse('No data to upload or ids to retrieve.', status_code=500)

        batches = list(batched(data_or_ids, upload_batch_size))

        self.logger.info(f'%s - Beginning %s upload of %s entries in %s batches of %s (last batch likely smaller).',
                         self.name, '' if ids_to_data is None else 'retrieval and', len(data_or_ids),
                         len(batches), upload_batch_size)

        successful_count = 0
        for i, batch in enumerate(batches, start=1):
            data = batch
            if ids_to_data is not None:
                self.logger.info('%s - Beginning retrieval of batch %s/%s of entries.', self.name, i, len(batches))
                data = ids_to_data(batch)
                self.logger.info('%s - Batch %s/%s: retrieved %s/%s of entries.',
                                 self.name, i, len(batches), len(data), len(batch))

            bad_data = [b for b, d in zip(batch, data) if d.get('status') == 'no data available']  # for inspection
            data = [d for d in data if d.get('status') != 'no data available']

            upload_response = self.single_upload_with_retries(data, f'Batch {i}/{len(batches)}',
                                                              retry_limit=upload_retry_limit, retry_delay=upload_retry_delay)
            successful_count += len(data) if upload_response.status_code == 200 else 0

        if successful_count == len(data_or_ids):
            self.logger.info('%s - Successfully retrieved and uploaded %s entries.', self.name, len(data_or_ids))
            return HttpResponse(f'Successfully retrieved and uploaded {len(data_or_ids)} entries.', status_code=200)
        elif successful_count > 0:
            self.logger.warning('%s - Retrieved and uploaded only %s out of %s entries.', self.name, successful_count, len(data_or_ids))
            return HttpResponse(f'Retrieved and uploaded only {successful_count} out of {len(data_or_ids)} entries.', status_code=500)
        else:
            self.logger.error('%s - Failed to upload any of the %s entries.', self.name, len(data_or_ids))
            return HttpResponse(f'Failed to upload any of the {len(data_or_ids)} entries.', status_code=500)


