import logging
import asyncio

from azure.functions import HttpRequest, HttpResponse
from datetime import datetime, timezone

from collabgpt_get_flights import FlightDataRetriever
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
    logger.info('Bulk flight data ingestion function triggered at %s', utc_timestamp)
    retriever = FlightDataRetriever()
    retriever.retrieve(from_date=req.params.get('from'), to_date=req.params.get('to'))
    uploader = IndexUploader(config.ai_search.url.flight_indexing, 'CHEVRON', logger)
    upload_batch_size = int(passed) if (passed := req.params.get('upload_batch_size')) else 200
    return uploader.batched_upload(retriever.data, upload_batch_size=upload_batch_size)


# if __name__ == '__main__':
#     # vv removes the harmless but annoying "RuntimeError: Event loop is closed" errors
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     out = main(HttpRequest(method='GET', url='', body='', params={
#         'from': '2025-01-01',
#         'to': '2025-02-24',
#         'upload_batch_size': 30
#     }))
#     print(out.status_code, out.get_body())


