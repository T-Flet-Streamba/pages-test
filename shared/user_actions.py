import time

from collabgpt_lg.graph_types import ConfigSchema
from collabgpt_lg.endpoints_base import UserActionsBaseClass

import config


class ActiveSubscriptions(UserActionsBaseClass):
    """Uses the User Actions API endpoint to retrieve or close active subscriptions (not filtered by users nor topics)."""

    def __init__(self, org: str):
        c = ConfigSchema(
            org=org,
            timezone=config.org_time_zones[org],
            llms={}
        )
        super().__init__(c, supported_orgs=['CHEVRON', 'ExxonMobilGuyana', 'Shell UK'])

    def retrieve(self, org: str = None, user: str = None, entity: str = None, max_attempts: int = 2) -> dict[str, dict]:
        """Retrieve all active subscriptions (all users, all entities if neither is specified).
        Retries on non-200 response; raises after all retries fail.
        """
        self.url_endpoint = config.user_actions.url.get_user_actions
        params = dict(
            actionTypes=['subscription'],
            closed=False
        )
        if org:
            params['organisation'] = org
        if user:
            params['createdByUserId'] = user
        if entity:
            params['entityId'] = entity

        for attempt in range(1, max_attempts + 1):
            response = self._send_request(json=params)
            if response is not None:  # needs to be `is not None` because 200-status responses can be {}
                if subs := response.get('actions'):
                    return {sub['_id']: dict(organisation=sub['organisation'], **sub['data'], description=sub['description']) for sub in subs}
                return {}
            if attempt < max_attempts:  # only sleep if not on the last attempt
                time.sleep(5)

        raise RuntimeError(f'Failed to retrieve active subscriptions ({max_attempts} attempts with non-200 status) for params {params}.')

    def close(self, subs: list[str]):
        """Close the given subscriptions. Returns ids of those successfully closed."""
        self.url_endpoint = config.user_actions.url.close_subscription
        closed = []
        for sub in subs:
            response = self._send_request(json=dict(id=sub))
            if response and response.get('success'):
                closed.append(sub)
        return closed


