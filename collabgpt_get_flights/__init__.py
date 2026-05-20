import logging
import asyncio

from azure.functions import TimerRequest
from datetime import datetime, timezone, timedelta

from collabgpt_lg.endpoints_base import DataEnhancerAPIBaseClass
from collabgpt_lg.endpoints import FlightsByID
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
def main(flightsTimer: TimerRequest) -> None:
    utc_timestamp = datetime.now(tz=timezone.utc)
    recent_interval = timedelta(hours=1, minutes=10)
    logger.info('Flight data ingestion function triggered at %s', utc_timestamp)
    retriever = FlightDataRetriever()
    retriever.retrieve(from_date=(utc_timestamp - recent_interval).isoformat(timespec='seconds')[:-6] + 'Z',
                       to_date=utc_timestamp.isoformat(timespec='seconds')[:-6]+'Z')
    uploader = IndexUploader(config.ai_search.url.flight_indexing, 'CHEVRON', logger)
    uploader.single_upload_with_retries(retriever.data, f'Recent data (the last {recent_interval})')
    return


class FlightDataRetriever(DataEnhancerAPIBaseClass):
    """Uses the Data Enhancer flights-last-updated-at-datetime endpoint to retrieve entries in a given time frame.
    """

    def __init__(self):
        super().__init__(org_state('CHEVRON'), supported_orgs=['CHEVRON'])
        self.url_endpoint = config.data_enhancer.url.flights_by_date
        self.data = []

    def retrieve(self, from_date: str, to_date: str):
        """Retrieve flights in the given timeframe and map their fields appropriately.
        Note that results are already processed as CollabGPT would, minimising processing on the AI Search side.
        Arguments have to be in limited ISO format: no seconds decimals and only Z as timezone: yyyy-mm-ddThh:mm:ssZ
        """
        flights = asyncio.run(self._send_request(params={'organization': 'CHEVRON', 'from': from_date, 'to': to_date}))
        if flights:
            api = FlightsByID(self.c)             # vv index true datetimes, not local ones
            self.data = [api._data_mapping(flight, localised_datetimes=False) for flight in flights]
        return self.data


# if __name__ == '__main__':
#     # vv removes the harmless but annoying "RuntimeError: Event loop is closed" errors
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     main(TimerRequest)


