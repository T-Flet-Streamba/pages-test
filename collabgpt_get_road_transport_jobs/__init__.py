import json
import logging
import asyncio

from azure.functions import TimerRequest
from datetime import datetime, timezone, timedelta

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
def main(roadTransportJobsTimer: TimerRequest) -> None:
    utc_timestamp = datetime.now(tz=timezone.utc)
    recent_interval = timedelta(hours=1, minutes=10)
    logger.info('Road transport data ingestion function triggered at %s', utc_timestamp)
    retriever = RecentRoadTransportDataRetriever()
    retriever.retrieve(from_date=(utc_timestamp - recent_interval).isoformat(), to_date=utc_timestamp.isoformat())
    uploader = IndexUploader(config.ai_search.url.road_transport_indexing, 'CHEVRON', logger)
    uploader.single_upload_with_retries(retriever.data, f'Recent data (the last {recent_interval})')
    return


class RecentRoadTransportDataRetriever(DataEnhancerAPIBaseClass):
    """Uses the Data Enhancer Road Transport events endpoint to get the IDs of recently updated entries,
    and then retrieves data for them with the by-ID endpoint.
    """

    def __init__(self):
        super().__init__(org_state('CHEVRON'), supported_orgs=['CHEVRON'])
        self.url_endpoint = config.data_enhancer.url.road_transports_events
        self.data = []

    def retrieve(self, from_date: str, to_date: str):
        """Get road transports with events in the given timeframe and retrieve data for them.
        Note that results are already processed as CollabGPT would, minimising processing on the AI Search side.
        Arguments can be in any variety of ISO format.
        """
        recent_events = asyncio.run(self._send_request(
            method='POST',
            headers={'Content-Type': 'application/json'},
            data=json.dumps({'organization': 'CHEVRON', 'from': from_date, 'to': to_date})
        ))

        ids_with_updates = list(set(e['roadTransportJobId'] for e in recent_events))

        self.data = asyncio.run(self.get_data(ids_with_updates, RoadTransportJobsByID,
                                              limit=len(ids_with_updates), verbose=False,
                                              localised_datetimes=False))  # index true datetimes, not local ones
        return self.data


# if __name__ == '__main__':
#     # vv removes the harmless but annoying "RuntimeError: Event loop is closed" errors
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     main(TimerRequest)


