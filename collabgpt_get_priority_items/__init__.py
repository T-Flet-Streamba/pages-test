import json
import logging
import redis

from azure.functions import TimerRequest
from datetime import datetime, timezone

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
def main(priorityitemstimer: TimerRequest) -> None:
    utc_timestamp = datetime.now(tz=timezone.utc).isoformat()
    logger.info('Priority data ingestion function triggered at %s', utc_timestamp)
    data = get_from_redis()
    uploader = IndexUploader(config.ai_search.url.priority_indexing, 'CHEVRON', logger)
    uploader.batched_upload(data, upload_batch_size=1000, upload_retry_limit=3, upload_retry_delay=3)
    return


def get_from_redis():
    """
    Get priority items from redis cache
    """
    # get redis connection string
    redis_connection_string = config.redis.connection_str
    if not redis_connection_string:
        raise ValueError("Redis connection string env var not set")

    redis_priority_items_cache_path = config.redis.cvx.priorityfreight
    if not redis_priority_items_cache_path:
        raise ValueError("Priority freight report data path env var not set")

    # connect to redis
    uc = redis.from_url(redis_connection_string)

    # get full data cache
    data_raw = uc.get(redis_priority_items_cache_path)
    data = json.loads(data_raw)

    if (n_items := len(data)) == 0:
        raise ValueError("No priority freight data found in redis cache")
    logger.info("%s priority items found in cache", n_items)

    return data


# if __name__ == '__main__':
#     main(TimerRequest)


