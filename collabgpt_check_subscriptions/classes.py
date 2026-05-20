import re
import json
import logging

# Set up the logger before importing anything else from this package
logging.getLogger().setLevel(logging.INFO)
if not logging.getLogger().hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

from collabgpt_lg.graph_types import ConfigSchema
from collabgpt_lg.endpoints_base import LangFlowBaseClass

from shared.redis_cache import SpecificRedisCache
import config


class SubscriptionCache(SpecificRedisCache):
    """Read or write any of Subscription Redis cache sub-caches (SNAPSHOTS, TO_CLOSE, or PAST_NOTIFICATIONS)."""

    def __init__(self, sub_cache: str, org: str):
        assert sub_cache in ['SNAPSHOTS', 'TO_CLOSE', 'PAST_NOTIFICATIONS']
        cache_path = f'{config.redis.subscriptions}::{org}::{sub_cache}'
        super().__init__(org=org, cache_path=cache_path)


class SubscriptiontionAgent(LangFlowBaseClass):
    """Run the Subscription Agent."""

    def __init__(self, c: ConfigSchema):
        super().__init__(c, supported_orgs=['CHEVRON', 'ExxonMobilGuyana', 'Shell UK'])
        self.flow_id = config.langflow.subscription_agent

    async def query(self, sub_id: str, sub: dict, past_notifications: dict, new_data: dict, diff: dict, **kwargs):
        payload = dict(
            session_id='cgpt-' + re.sub(r'[@._]', '-', sub['createdByUserId']),
            tweaks={  # i.e. overrides to any input to any component in the flow
                # Very useful note on the keys of tweaks: they can be either the arbitrary name given to that node or
                # the one generated automatically (i.e. the generic name plus a few random chars, visible in the node or
                # when generating tweaks with the UI under Publish > API Access > Tweaks).
                'Inputs': {
                    'organisation': sub['organisation'],
                    'current_user_id': sub['createdByUserId'],
                    'entity_id': sub['entityId'].upper(),
                    'entity_type': sub['entityType'],
                    'sub_description': sub['description'],
                    'past_notifications': str(past_notifications),
                    'new_data': str(new_data),
                    'diff': str(diff)
                }
            }
        )
        response = None
        try:
            response = self._send_request(payload=payload)
            r = json.loads(response)
            return sub_id, r
        except Exception as e:
            logging.warning('Error in invoking (or parsing the response from) the Subscription Agent for payload.\n'
                            'Error: %s.\n\nPayload: %s\n\nResponse: %s', e, payload, response)
            return sub_id, dict(error=(sub['entityType'], e))


