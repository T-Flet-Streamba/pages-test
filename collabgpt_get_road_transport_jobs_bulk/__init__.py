import logging
import asyncio
from more_itertools import unique_everseen
from azure.functions import HttpRequest, HttpResponse
from datetime import datetime, timezone

from collabgpt_lg.endpoints_base import DataEnhancerAPIBaseClass
from collabgpt_lg.endpoints import RoadTransportJobsByID
from collabgpt_lg.utils import org_state

from shared.index_uploader import IndexUploader
from shared.slack import slack_logging

import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)


@slack_logging
def main(req: HttpRequest) -> HttpResponse:
    utc_timestamp = datetime.now(tz=timezone.utc)
    logger.info('Road transport data ingestion-from-summary function triggered at %s', utc_timestamp)
    handler = SummaryRoadTransportDataHandler(req.params.get('concurrent_requests_limit'))
    return handler.retrieve_and_upload(**{  # pass args only if present, and cast to int if numeric
        k: int(val) if isinstance(val, str) and val.isnumeric() else val
        for k in ['from_date', 'to_date', 'entries_limit', 'upload_batch_size']
        if (val := req.params.get(k))
    })


class SummaryRoadTransportDataHandler(DataEnhancerAPIBaseClass):
    """Uses the Data Enhancer Road Transport events endpoint to get the IDs of recently updated entries,
    then retrieves data for them with the by-ID endpoint and uses IndexUploader to upload them to the search index.
    """

    def __init__(self, concurrent_requests_limit: str = None):
        super().__init__(org_state('CHEVRON'), supported_orgs=['CHEVRON'])
        self.url_endpoint = config.data_enhancer.url.road_transports_by_date
        # NOTE: using the summary endpoint above and not /roadTransportJob/getByLastUpdatedTimestamp because the latter,
        #   although desirable since allowing arbitrary timeframes, returns enormous amounts of data even for a few days
        self.concurrent_requests_limit = int(concurrent_requests_limit) if concurrent_requests_limit else 30
        self.data = []
        self.uploader = IndexUploader(config.ai_search.url.road_transport_indexing, 'CHEVRON', logger)

    def retrieve_batch(self, ids: list[str]):
        return asyncio.run(self.get_data(ids, RoadTransportJobsByID, limit=len(ids),
                                         concurrent_requests_limit=self.concurrent_requests_limit, verbose=False,
                                         localised_datetimes=False))

    def retrieve_and_upload(self, from_date: str = None, to_date: str = None,
                            entries_limit: int = None, upload_batch_size: int = 100) -> HttpResponse:
        """Get road transport jobs data from the by-date summary endpoint.
        Note that results are already processed as CollabGPT would, minimising processing on the AI Search side.
        entries_limit determines how many entries will be retrieved/uploaded.
        """
        if not from_date or not to_date:
            logger.error(msg := 'Both from_date and to_date fields are required.')
            return HttpResponse(msg, status_code=500)

        summaries = asyncio.run(self._send_request(params=dict(
            organization='CHEVRON',
            start=from_date,
            end=to_date
        )))

        if summaries and (rtjs := summaries.get('roadTransportJobSummaries')):
            # Would use the summary data directly, but it lacks important fields: consignmentItems and events
            # I.e. the following two lines work but their outputs also lack those fields.
            # api = RoadTransportsByID()
            # self.data = [api._data_mapping(rtj) for rtj in rtjs]

            if not rtjs:
                logger.info(msg := 'No results from the endpoint for the given date range; nothing to index.')
                return HttpResponse(msg, status_code=200)

            # In case entries_limit is not None, sort by most recent entries first (.get lambda safer than itemgetter)
            rtjs = sorted(rtjs, key=lambda j: j.get('requestedDeliveryDateTime'), reverse=True)
            ids = list(unique_everseen(e['displayId'] for e in rtjs))[:entries_limit]

            return self.uploader.batched_upload(ids, upload_batch_size=upload_batch_size, ids_to_data=self.retrieve_batch)
        else:
            logger.error(msg := 'Could not retrieve the road transport jobs summary.')
            return HttpResponse(msg, status_code=500)


# if __name__ == '__main__':
#     # vv removes the harmless but annoying "RuntimeError: Event loop is closed" errors
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     out = main(HttpRequest(method='GET', url='', body='', params=dict(
#         from_date='2025-08-01',
#         to_date='2025-08-04',
#         concurrent_requests_limit='30',
#         entries_limit='100',
#         upload_batch_size=50
#     )))
#     print(out.status_code, out.get_body())


