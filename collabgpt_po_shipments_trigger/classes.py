from logging import Logger
import json
import re
import redis
import requests
from datetime import datetime, timedelta

import config


class FlowiseWrapper:
    def __init__(self, logger: Logger, workflow_id: str, workflow_name: str = None):
        """
        Class to wrap the various endpoints used in flowise workflows.
        """
        self._token = config.flowise.bearer_token
        self._auth_header = dict(Authorization=f'Bearer {self._token}')
        self._url_workflow_root = config.flowise.root_url
        self._workflow_id = workflow_id
        self._workflow_name = ' - '.join([type(self).__name__] + ([workflow_name] if workflow_name else []))
        self._logger = logger

    def _send_request(self, endpoint: str, method: str = None, **kwargs):
        method = method or 'GET'
        assert method in ['GET', 'POST']

        url = self._url_workflow_root + endpoint
        kwargs['headers'] = dict(kwargs.get('headers', {}), **self._auth_header)
        return requests.request(method=method, url=url, **kwargs)

    def get_workflow_sessions(self, all_workflows=False):
        """
        Return all sessions for the wrapped workflow or all of them.
        """
        r = self._send_request('/api/v1/chatflows/getAllFlowStates')
        if sessions := r.json():
            return sessions if all_workflows else [s for s in sessions if s.get('chatflowid') == self._workflow_id]

    def list_chatflows(self):
        r = self._send_request('/api/v1/chatflows/')
        return r.json()

    def start_workflow(self, session_id: str = None, _vars: dict = None, **kwargs):
        """
        Trigger the workflow; kwargs are passed directly to the json argument of the request.
        Likely kwargs: question=..., overrideConfig=dict(...).
        session_id is a shortcut for the kwarg overrideConfig=dict(sessionId=...).
        _vars is a shortcut for the kwarg overrideConfig=dict(vars=...), i.e. direct arguments to the flow.
        (The argument is called _vars and not vars in order to not shadow the built-in Python function).
        Note that vars.type and vars.userId are already filled in but can be overridden through kwargs.
        """
        kwargs['question'] = kwargs.get('question') or ''
        final_vars = dict(type='PythonAzureFunction', userId=self._workflow_name)
        final_vars.update(_vars or {})
        if shortcut_overrides := {k: v for k, v in dict(sessionId=session_id, vars=final_vars).items() if v}:
            kwargs['overrideConfig'] = kwargs.get('overrideConfig', {})
            for k, v in shortcut_overrides.items():  # admittedly too much for just two shortcuts, but forward-looking;
                if isinstance(v, dict):              # could make a separate recursive-safe-dictionary-update function
                    kwargs['overrideConfig'][k] = dict(kwargs['overrideConfig'].get(k, {}), **v)
                else:
                    kwargs['overrideConfig'][k] = v
        self._logger.info('%s triggered its workflow with the following arguments: %s', self._workflow_name, kwargs)
        r = self._send_request(f'/api/v1/prediction/{self._workflow_id}', method='POST', json=kwargs)
        return r.json()


class PoShipmentsTrigger:
    def __init__(self, logger: Logger):
        """
        Class to process the purchase orders data from redis.
        """
        self.data = None
        self._logger = logger

    def get_data(self):
        """
        Get all endorsed for collection from redis cache.
        """
        # get full data cache
        uc = redis.from_url(config.redis.connection_str)
        data_raw = uc.get(config.redis.cvx.endorsedforcollection)
        self.data = json.loads(data_raw)

        if not self.data:
            raise ValueError('No data found in cache')
        
        for po in self.data:
            if pr := po.get('priority'):
                po['priority'] = pr.strip()  # this is because 'Courier' values can have one or more trailing spaces

        self._logger.info('%s items found in cache', len(self.data))

    def get_overdue_items(self):
        """
        Returns POs which are overdue, sorted first by priority level, and then allocated date (oldest first).
        Necessary conditions on outputs (some from https://streamba.slack.com/archives/C026XKWLH6X/p1731945939441029):
            - 'shipmentDetails' is absent or empty
            - 'endorsedCollectionStatus' is 'Unknown', 'Assigned' or 'Pending Booking'
            - 'poNumber' is present and correctly formatted, i.e. \d+ (sometimes users write sentences or MRs in them)
            - 'allocatedAtDateTime' is older than the warning threshold for each 'priority'
              - 7 days for Sea, 1 day for P1, 2 days for P2 and P3, and 3 days for Courier (None values are ignored)
        """
        out = [po for po in self.data
               # if po.get('isOverdueForBooking')  # always for 48hrs; not varying by priority; might change
               if not po.get('shipmentDetails')
               if po.get('endorsedCollectionStatus', '') in ['Unknown', 'Assigned', 'Pending Booking']
               if (pon := po.get('poNumber')) and re.fullmatch(r'\d+', pon)]

        # Date filtering separated from the above to avoid creating allocated_dt for ALL entries in the cache
        for po in out:
            if allocated := po.get('allocatedAtDateTime'):
                po['allocated_dt'] = datetime.fromisoformat(allocated.replace('Z', '+00:00'))  # field used outside too

        threshold_days = {p: d for d, ps in {1: ['P1 Air'], 2: ['P2 Air', 'P3 Air'],
                                             3: ['Courier'], 7: ['Sea']}.items() for p in ps}
        thresholds = {p: (datetime.now() - timedelta(days=d)).timestamp() for p, d in threshold_days.items()}

        out = [po for po in out
               if (allocated_dt := po.get('allocated_dt')) and (allocated_ts := allocated_dt.timestamp())
               if (pr := po.get('priority')) and allocated_ts <= thresholds[pr]]

        for po in out:  # adding the used day thresholds to the outputs since useful to report
            po['threshold'] = f"{(d := threshold_days[po.get('priority')])} day{'s' if d > 1 else ''}"

        priority_order = {p: i for i, p in enumerate(['P1 Air', 'P2 Air', 'P3 Air', 'Courier', 'Sea'])}
        return sorted(out, key=lambda po: (priority_order[po.get('priority')], po['allocated_dt']))


