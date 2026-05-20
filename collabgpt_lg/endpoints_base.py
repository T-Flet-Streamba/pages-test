import logging
import asyncio
import requests
import re
import json
import pandas as pd
from urllib.parse import urljoin, quote
from requests.auth import HTTPBasicAuth
from aiohttp import ClientSession, TCPConnector

from abc import ABC, abstractmethod
from typing import Union

from collabgpt_lg.graph_types import ConfigSchema
from collabgpt_lg.utils import iso_dt_range, localise_dt

from shared.ids.all_regexes import REGEX_MAPPING, REGEX_ANTIMAPPING
from shared.redis_cache import SpecificRedisCache
import config



class VorURL:
    """Generate a VOR url for the given entity type."""
    @staticmethod
    def _core(_type: str, _id: str) -> str:
        _id_safe = quote(_id)
        return urljoin(config.customer_api.url.base, f'/supplychain#/{_type}/{_id_safe}')
    # functools.partialmethod would have been tidier here (e.g. container = partialmethod(_core, 'containerEvents'))
    # but at the price of the IDE treating methods as attributes (i.e. no automatic brackets insertion nor arg hints)
    def container(self, _id): return self._core('containerEvents', _id)
    def container_details(self, _id): return self._core('containerDetails', _id)
    def flight(self, _id): return self._core('airTransport/flights', _id)
    def helicopter(self, _id): return self._core('helicopters/flights', _id)
    def movement_request(self, _id): return self._core('movementRequest', _id)
    def request(self, _id): return self._core('request', _id)
    def road_transport_job(self, _id): return self._core('roadTransport/jobs', _id)
    def shipment(self, _id): return self._core('shipments', _id)
    def voyage(self, _id): return self._core('voyage', _id)
    def work_order(self, _id): return self._core('workOrders', _id)
    def enhanced_work_order(self, _id): return self._core('enhancedWorkOrders', _id)

    def parametrised(self, org: str, _id: str, _type: str | set[str] | list[str] = None) -> str:
        """Router for the other methods. Also attempts to guess if not given a type (it assigns one only if certain).
        Returns the empty string on failed cases (bad entity type or failed guesses).
        """
        if not _type or isinstance(_type, (set, list)):
            # Check whether _id is definitely of one type (restricted to candidate types if given)
            for _t, antipattern in REGEX_ANTIMAPPING[org].items():
                if _type and _t not in _type:
                    continue  # conversely, proceed with this _t if _type was None or if _t is in it
                if re.fullmatch(antipattern, _id):
                    return getattr(self, _t)(_id)  # returns on the first match since these regexes are type guarantees
        elif _type not in self.__dir__() or _type.startswith('_'):
            logging.warning('Requested VOR url type not found (the ID for it was %s): %s', _id, _type)
            return ''
        else:
            return getattr(self, _type)(_id)


class DataSource(ABC):
    """Abstract base for data sources (config, org validation, and data-packaging helpers)."""
    c: ConfigSchema
    supported_orgs: list[str]
    vor_url = VorURL()

    def set_config_and_orgs(self, c: ConfigSchema, supported_orgs: list[str]):
        """Verify that the org in the config is among those in supported_orgs, then set the homonymous fields."""
        if c['org'] in supported_orgs:
            self.c, self.supported_orgs = c, supported_orgs
        else:  # vv no need for logging; this will propagate up the chain to a log (and DO want to fail for this)
            raise ValueError(f"{type(self).__name__} does not support organisation '{c['org']}'. Supported orgs: {supported_orgs}.")

    def make_iso(self, dt_or_range: str) -> str:
        """Convert a datetime or ~ range to full ISO format (using the org's time zone if none is specified)."""
        return iso_dt_range(dt_or_range, self.c['timezone'])

    def localise_dates(self, data: dict, date_fields: list[str]) -> dict:
        """Localise ISO datetimes in the given fields."""
        return {k: localise_dt(v, self.c['timezone']) if k in date_fields and v else v for k, v in data.items()}

    async def get_data(
        self,
        data: Union[list[dict], list[str]],
        endpoint_class,
        concurrent_requests_limit: int = 20,
        limit: int = config.ai_behaviour.default_limit,
        verbose: bool = True,
        **kwargs
    ):
        """Get related data async; accepts either a list of ids or a list of dictionaries with an id field.
        kwargs are passed to the endpoint_class' .query method.
        """
        ids = data if data and isinstance(data[0], str) else [_id for item in data if (_id := item.get('id'))]
        async with ClientSession(connector=TCPConnector(limit=concurrent_requests_limit)) as session:
            api = endpoint_class(self.c, session)
            return await asyncio.gather(*[api.query(_id, verbose=verbose, **kwargs) for _id in ids[:limit]])

    def _df_and_details(self, data: list[dict]):
        """Convert the data to a dataframe with nested keys expanded out.
        The dataframe will be removed before any data passing into prompts;
        details about it will instead be let through: number of rows and names of columns.
        """
        # Convert top-layer fields containing lists to dictionaries with int indices
        #   Note: fields which make it to this stage as lists are assumed sensible to unnest
        if list_fields := set(k for d in data for k, v in d.items() if isinstance(v, list)):
            logging.info('%s produced the following fields containing lists: %s', type(self).__name__, list_fields)
        data = [{k: dict(enumerate(v)) if isinstance(v, list) else v for k, v in d.items()} for d in data]

        try:  # pd.json_normalize below flattens nested dicts (including lists converted above)
            df = pd.json_normalize(data)
        except Exception as e:  # no need to be more specific
            return f'{type(self).__name__} could not convert data to a DataFrame.\nError: {e}'

        return dict(n_rows=len(data), columns=list(df.columns), dataframe=df)

    def _package_data(self, top_results: list[dict], limit=config.ai_behaviour.default_limit,
                      applied_filters: dict = None, further_processing: str = None,
                      metadata: dict = None, all_results: list[dict] = None) -> dict:
        """Return only up to a limited number of results and convert the full dataset(s) to dataframes (to NOT pass to prompts).

        NOTE: the limit argument is only for reporting purposes, as this method is not responsible for limiting the data;
            it WILL limit it if it has to but will complain about it.
        """
        md, out = {}, {}  # metadata and output dictionaries; the order of their fields helps the LLM focus attention

        md.update(metadata or {})
        if further_processing:
            md['further_processing_is_required'] = further_processing
        else:
            if len(top_results) > limit:
                logging.warning('The data passed to %s._package_data is longer than the given limit of %s; '
                               'this should not happen (.get_data or a simple [:limit] should have handled it).',
                               type(self).__name__, limit)

            if all_results and len(all_results) > len(top_results):
                md['data_is_reduced'] = f'There are {len(all_results)} results, but only showing the first {limit} explicitly; ' \
                                        'ask the user to be more specific or use the full data for further processing.'

        md['applied_filters'] = {k: v for k, v in (applied_filters or {}).items() if v is not None if v != '*'}

        if top_results:
            out['TopResultsDataset'] = self._df_and_details(top_results)
        if all_results and len(all_results) > len(top_results):
            out['AllResultsDataset'] = self._df_and_details(all_results)
        if not top_results and not all_results:  # vv Avoid saying 'no data available' since that triggers retries
            out['system_message'] = 'No data found for these parameters using this tool; do not try them again.'
            if further_processing:
                md['further_processing_is_required'] = False

        out['MetaData'] = md
        if top_results:  # If present, keep the long data printout as the last dict entry
            out['TopResults'] = top_results[:limit]  # the limit is applied anyway even if warned about it
        return out


class AuthenticatedEndpoint(DataSource):
    """An abstract base class for API endpoints (adds auth and request behaviour)."""

    @abstractmethod
    def _generate_new_bearer_token(self):
        """Generate new access bearer token."""
        pass

    @abstractmethod
    def _send_request(self, **kwargs):
        """Send an authenticated request; keyword arguments are passed directly to the post."""
        pass

    def by_id_fallback(self, regex_name: str, endpoint_class, search_results: list[dict], params: dict) -> dict | None:
        """To be used if no by-description results are found: this function checks whether the query looks like
        the right kind of ID and if so it looks it up; it returns None otherwise.
        This method removes the need for a dedicated by-id tool or argument (which is a source of confusion for the AI).
        Also, it ensures IDs are looked up at their original source if it did not find references to them in the indexes.
        :param regex_name: the name of the regex (keys of REGEX_MAPPING) to check the query against,
            i.e. one of flight_id, movement_request, road_transport_job, shipment, voyage_cargo_manifest.
        :param endpoint_class: the by-id class matching the entity type (needs to be passed in because cannot be referenced here in the base class).
        """
        if (not search_results
            and (pattern := REGEX_MAPPING[self.c['org']].get(regex_name))
            and (_id := params.get('query', '') or params.get('search_term', ''))
            and re.fullmatch(pattern, _id)):
            return asyncio.run(endpoint_class(self.c).query(_id))


class CustomerAPIBaseClass(AuthenticatedEndpoint):
    """A base class for customer API endpoints."""

    def __init__(self, c: ConfigSchema, supported_orgs):
        self.set_config_and_orgs(c, supported_orgs)
        self.subscription_key = config.customer_api.subscription_keys[self.c['org']]
        self.url_base = config.customer_api.url.services
        self.url_endpoint = '/'
        self.bearer_token = ''
        self.auth_header = {}
        self._generate_new_bearer_token()
        self.auth_header = {
            'Ocp-Apim-Subscription-Key': self.subscription_key,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Bearer ' + self.bearer_token,
            'UseLocalTime': 'true' if self.c['org'] == 'CHEVRON' else 'false'
        }

    def _generate_new_bearer_token(self):
        post_url = f"https://login.microsoftonline.com/{config.customer_api.tenant_id}/oauth2/token"
        body = dict(
            resource=config.customer_api.api_resource_id,
            client_id=config.customer_api.client_id,
            client_secret=config.customer_api.client_secret,
            grant_type='client_credentials',
        )
        headers = {
            'Ocp-Apim-Subscription-Key': self.subscription_key,
            'Authorization': '',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        r = requests.post(url=post_url, data=body, headers=headers, timeout=None)

        if r.status_code == 200:
            self.bearer_token = r.json()['access_token']
            logging.info('Created a new customer API bearer token')
        else:
            raise ValueError(f'Failed to generate access token. Status code {r.status_code}')

    async def _send_request(self, method: str = None, session: ClientSession = None, verbose: bool = True,
                            path_variables: dict[str, str] = None, **kwargs):
        """Send an authenticated get request; keyword arguments besides session are passed directly to the get.
        The session argument is meant for the by-ID endpoints which get called repeatedly by by-description ones.
        The path_variables argument is for converting ':'-tagged variables in self.url_base to their values,
        e.g. if path_variables == dict(id='ME'), '/something/:id' will be converted to '/something/ME'.
        """
        if 'params' in kwargs:
            kwargs['params'] = {k: v for k, v in kwargs['params'].items() if v is not None}

        method = method or 'GET'
        assert method in ['GET', 'POST']

        endpoint = self.url_endpoint
        if path_variables:
            for var, val in path_variables.items():
                endpoint = re.sub(f':{var}', val, endpoint)
        kwargs['url'] = self.url_base + endpoint
        kwargs['headers'] = dict(kwargs.get('headers', {}), **self.auth_header)
        if 'json' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'

        if verbose:
            params_to_show = dict(**(path_variables or {}),
                                  **{k: v for k, v in kwargs.items() if k not in ['url', 'headers']})
            logging.info('Sending a request from %s with the following args: %s', type(self).__name__, params_to_show)

        if session:
            r = await session.request(method=method, **kwargs)
            data = (await r.json()) if (status := r.status) == 200 else None
        else:
            r = requests.request(method=method, **kwargs)
            data = r.json() if (status := r.status_code) == 200 else None

        if status == 200:
            if verbose:
                logging.info('Data received from %s', type(self).__name__)
            return data
        else:  # unlike the AI search API, do NOT raise on bad statuses (e.g. 500s are returned for no data)
            if verbose:
                logging.info(f'No data received from %s; (request response status: %s)', type(self).__name__, status)
            return None


class AISearchBaseClass(AuthenticatedEndpoint):
    """A base class for AI Search API endpoints."""

    def __init__(self, c: ConfigSchema, supported_orgs):
        self.set_config_and_orgs(c, supported_orgs)
        self.url_base = config.ai_search.url.base
        self.url_endpoint = '/'
        self.bearer_token = ''
        self._generate_new_bearer_token()
        self.auth_header = dict(Authorization=f'Bearer {self.bearer_token}')

    def _generate_new_bearer_token(self):
        r = requests.post(
            config.ai_search.url.base + config.ai_search.url.auth,
            data=dict(grant_type='client_credentials'),
            auth=HTTPBasicAuth(config.ai_search.client_id, config.ai_search.client_secret)
            # Note: passing client credentials through HTTP Basic auth is OAuth2's recommendation.
            #   Alternatively, the /token endpoint also accepts them as fields, i.e. removing auth and adding to data:
            #   client_id=config.ai_search.client_id, client_secret=config.ai_search.client_secret
        )

        if r.status_code == 200:
            self.bearer_token = r.json()['access_token']
            logging.info('Created a new AI search API bearer token')
        else:
            raise ValueError(f'Failed to generate access token. Status code {r.status_code}')

    def _send_request(self, method: str = None, verbose: bool = True, path_variables: dict[str, str] = None, **kwargs):
        """Send an authenticated request; keyword arguments are passed directly to the get.
        The path_variables argument is for converting ':'-tagged variables in self.url_base to their values,
        e.g. if path_variables == dict(id='ME'), '/something/:id' will be converted to '/something/ME'.
        """
        if 'params' in kwargs:
            kwargs['params'] = {k: v for k, v in kwargs['params'].items() if v is not None}

        method = method or 'GET'
        assert method in ['GET', 'POST']

        endpoint = self.url_endpoint
        if path_variables:
            for var, val in path_variables.items():
                endpoint = re.sub(f':{var}', val, endpoint)
        kwargs['url'] = self.url_base + endpoint
        kwargs['headers'] = dict(kwargs.get('headers', {}), **self.auth_header)

        if verbose:
            params_to_show = dict(**(path_variables or {}),
                                  **{k: v for k, v in kwargs.items() if k not in ['url', 'headers']})
            logging.info('Sending a request from %s with the following args: %s', type(self).__name__, params_to_show)

        r = requests.request(method=method, **kwargs)

        is_a_by_id_request = 'params' in kwargs and set(kwargs['params'].keys()) == {'organisation', 'key'}
        if r.status_code == 200:
            content = r.json()
            out_key = ('result' + ('' if is_a_by_id_request else 's')) if method == 'GET' else 'content'
            out = content.get(out_key)
            if out_key in content:
                if verbose:
                    out_len = len(out) if isinstance(out, list) else 1 if out else 0
                    logging.info('%s entries retrieved from %s', out_len, type(self).__name__)
            else:
                if verbose:
                    logging.info('Output of successful response of %s: %s', type(self).__name__, content)
            return out  # happy to return None if the expected out_key is not in content
        elif r.status_code == 404:
            return None
        else:  # unlike the customer API (which throws 500s for no data), do raise for bad statuses
            raise Exception(f'Non-200 status from AI search {type(self).__name__} API: {r.status_code}')


class DataEnhancerAPIBaseClass(AuthenticatedEndpoint):
    """A base class for customer API endpoints."""

    def __init__(self, c: ConfigSchema, supported_orgs):
        self.set_config_and_orgs(c, supported_orgs)
        self.url_base = config.data_enhancer.url.base
        self.url_endpoint = '/'
        self.bearer_token = ''
        self._generate_new_bearer_token()
        self.auth_header = dict(Authorization=f'Bearer {self.bearer_token}')

    def _generate_new_bearer_token(self):
        r = requests.post(
            url=config.data_enhancer.url.base + config.data_enhancer.url.token,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            data=json.dumps(dict(
                username=config.data_enhancer.username,
                password=config.data_enhancer.password,
            ))
        )

        if r.status_code == 200:
            self.bearer_token = r.json()['token']
            logging.info('Created a new Data Enhancer API bearer token')
        else:
            raise ValueError(f'Failed to generate access token. Status code {r.status_code}')

    async def _send_request(self, method: str = None, session: ClientSession = None, verbose: bool = True,
                            path_variables: dict[str, str] = None, **kwargs):
        """Send an authenticated request ('GET' by default);
        keyword arguments besides session are passed directly into the request.
        The session argument is meant for the by-ID endpoints which get called repeatedly by by-description ones.
        The path_variables argument is for converting ':'-tagged variables in self.url_base to their values,
        e.g. if path_variables == dict(id='ME'), '/something/:id' will be converted to '/something/ME'.
        """
        if 'params' in kwargs:
            kwargs['params'] = {k: v for k, v in kwargs['params'].items() if v is not None}

        method = method or 'GET'
        assert method in ['GET', 'POST']

        endpoint = self.url_endpoint
        if path_variables:
            for var, val in path_variables.items():
                endpoint = re.sub(f':{var}', val, endpoint)
        kwargs['url'] = self.url_base + endpoint
        kwargs['headers'] = dict(kwargs.get('headers', {}), **self.auth_header)

        if verbose:
            params_to_show = dict(**(path_variables or {}),
                                  **{k: v for k, v in kwargs.items() if k not in ['url', 'headers']})
            logging.info('Sending a request from %s with the following args: %s', type(self).__name__, params_to_show)

        if session:
            r = await session.request(method=method, **kwargs)
            data = (await r.json()) if (status := r.status) == 200 else None
        else:
            r = requests.request(method=method, **kwargs)
            data = r.json() if (status := r.status_code) == 200 else None

        if status == 200:
            if verbose:
                logging.info('Data received from %s', type(self).__name__)
            return data
        else:  # unlike the AI search API, do NOT raise on bad statuses (e.g. 500s are returned for no data)
            if verbose:
                logging.info(f'No data received from %s; (request response status: %s)', type(self).__name__, status)
            return None


class VorSearchBaseClass(AuthenticatedEndpoint):
    """A base class for VOR Search API endpoints."""

    def __init__(self, c: ConfigSchema, supported_orgs):
        self.set_config_and_orgs(c, supported_orgs)
        self.url_base = config.vor_search.url.base
        self.url_endpoint = '/'
        self.bearer_token = ''
        self._generate_new_bearer_token()
        self.auth_header = dict(Authorization=f'Bearer {self.bearer_token}')

    def _generate_new_bearer_token(self):
        token_url = config.vor_search.url.base + config.vor_search.url.auth
        r = requests.post(
            url=token_url,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            data=json.dumps(dict(
                userName=config.vor_search.client_id,
                password=config.vor_search.client_secret,
            ))
        )

        if r.status_code == 200:
            self.bearer_token = r.json()['token']
            logging.info('Created a new VOR search API bearer token')
        else:
            raise ValueError(f'Failed to generate access token. Status code {r.status_code}')

    def _send_request(
        self,
        path_variables: dict[str, str] = None,
        verbose: bool = True,
        **kwargs
    ):
        """Send an authenticated request; keyword arguments are passed directly to the get.
        The path_variables argument is for converting ':'-tagged variables in self.url_base to their values,
        e.g. if path_variables == dict(id='ME'), '/something/:id' will be converted to '/something/ME'.
        """
        if 'params' in kwargs:
            kwargs['params'] = {k: v for k, v in kwargs['params'].items() if v is not None}

        method = 'POST'

        endpoint = self.url_endpoint
        if path_variables:
            for var, val in path_variables.items():
                endpoint = re.sub(f':{var}', val, endpoint)
        kwargs['url'] = self.url_base + endpoint
        kwargs['headers'] = dict(kwargs.get('headers', {}), **self.auth_header)

        if verbose:
            params_to_show = dict(**(path_variables or {}),
                                  **{k: v for k, v in kwargs.items() if k not in ['url', 'headers']})
            logging.info('Sending a request from %s with the following args: %s', type(self).__name__, params_to_show)

        r = requests.request(method=method, **kwargs)
        data = r.json() if (status := r.status_code) == 200 else None

        if status == 200:
            if verbose:
                logging.info('Data received from %s', type(self).__name__)
            return data
        else:  # unlike the AI search API, do NOT raise on bad statuses (e.g. 500s are returned for no data)
            if verbose:
                logging.info(f'No data received from %s; (request response status: %s)', type(self).__name__, status)
            return None

    def _get_search_body(self, search_term: str = None, date_ranges: str = None, sort: str = None, other_filters: dict = None) -> dict:
        """Generate the request body as Python object (which will be converted to JSON in the request) with appropriate precautions,
        including not returning anything if no filters are given.
        Note that already-JSON arguments need to be de-JSON-ed in this process (and will be re-JSON-ed in the request).
        """
        try:
            parsed_date_ranges = json.loads(date_ranges) if date_ranges else None
        except json.JSONDecodeError:
            return dict(system_message=f'Argument `date_ranges` received bad JSON; try again. Bad value: {date_ranges}')

        try:
            parsed_sort = json.loads(sort) if sort else None
        except json.JSONDecodeError:
            return dict(system_message=f'Argument `sort` received bad JSON; try again. Bad value: {sort}')

        body = dict(
            searchTerm=search_term,
            dateRanges=parsed_date_ranges,
            sort=parsed_sort,
            **(other_filters if other_filters else {})
        )
        body = {k: v for k, v in body.items() if v is not None}

        if not body:  # trigger the no-response shortcut if no filters were given
            return dict(system_message='This tool has to be called with at least one argument (further_processing does not count, as it is ancillary).')

        if not body.get('searchTerm'):  # the API requires it
            body['searchTerm'] = ''
        body['size'] = config.ai_behaviour.source_results_limit  # the default cap is 100 and the max accepted is 1000
        return body

    def non_index_data_pipeline(self, search_results: list, params: dict,
        by_id_endpoint_class: type, index_id_field: str, limit: int = config.ai_behaviour.default_limit) -> list:
        """Map index hit ids for get_data enrichment from the configured by-ID endpoint."""
        for row in search_results:
            if index_id_field in row:
                row['id'] = row.pop(index_id_field)
        return asyncio.run(self.get_data(search_results, by_id_endpoint_class, limit=limit))

    def _query_pipeline(self, search_term: str, date_ranges: str | None, sort: str | None, other_filters: dict,
                        date_fields: list[str], by_id_fallback_patterns: list[str], by_id_endpoint_class: type,
                        further_processing: str | None) -> dict:
        """Shared flow for VOR description search: localise index datetimes, optional by-id fallback, Data Enhancer merge, package."""
        body = self._get_search_body(search_term, date_ranges, sort, other_filters)
        if 'system_message' in body:
            return body

        search_results = self._send_request(params=dict(organization=self.c['org']), json=body)
        search_results = [self.localise_dates(dict(r), date_fields) for r in search_results]

        # Return single result if looked for something which matches an appropriate ID pattern
        fallback = None
        for regex_name in by_id_fallback_patterns:
            fallback = fallback or self.by_id_fallback(regex_name, by_id_endpoint_class, search_results, body)
        if fallback:
            return fallback

        # Get better data from the appropriate non-index source
        non_index_data = [] if further_processing else self.non_index_data_pipeline(search_results, body)
        
        # Remove empty results from both sets (for old ones in the index which are NOT in the better source anymore)
        empty_results  = [i for i, v in enumerate(non_index_data) if v.get('status') == 'no data available']
        search_results = [r for i, r in enumerate(search_results) if i not in empty_results]
        non_index_data = [v for i, v in enumerate(non_index_data) if i not in empty_results]

        return self._package_data(non_index_data, limit=len(non_index_data), all_results=search_results,
                                  applied_filters=body, further_processing=further_processing)


class UserActionsBaseClass(AuthenticatedEndpoint):
    """A base class for the User Actions API endpoints."""

    def __init__(self, c: ConfigSchema, supported_orgs):
        self.set_config_and_orgs(c, supported_orgs)
        self.url_base = config.user_actions.url.base
        self.url_endpoint = '/'
        self.bearer_token = ''
        self._generate_new_bearer_token()
        self.auth_header = {
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'Authorization': f'Bearer {self.bearer_token}'
        }

    def _generate_new_bearer_token(self):
        r = requests.post(
            url=f'https://login.microsoftonline.com/{config.user_actions.tenant_id}/oauth2/v2.0/token',
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            data=dict(
                grant_type='client_credentials',
                client_id=config.user_actions.client_id,
                client_secret=config.user_actions.client_secret,
                scope='https://graph.microsoft.com/.default'
            )
        )

        if r.status_code == 200:
            self.bearer_token = r.json()['access_token']
            logging.info('Created a new VOR search API bearer token')
        else:
            raise ValueError(f'Failed to generate access token. Status code {r.status_code}')

    def _send_request(self, method: str = None, path_variables: dict[str, str] = None, verbose: bool = True, **kwargs):
        """Send an authenticated request; keyword arguments are passed directly to the get.
        The path_variables argument is for converting ':'-tagged variables in self.url_base to their values,
        e.g. if path_variables == dict(id='ME'), '/something/:id' will be converted to '/something/ME'.

        NOTE: this API expects application/json, so pass the payload AS A PYTHON OBJECT in an argument called json.
        """
        if 'params' in kwargs:
            kwargs['params'] = {k: v for k, v in kwargs['params'].items() if v is not None}

        method = method or 'POST'
        assert method in ['GET', 'POST']

        endpoint = self.url_endpoint
        if path_variables:
            for var, val in path_variables.items():
                endpoint = re.sub(f':{var}', val, endpoint)
        kwargs['url'] = self.url_base + endpoint
        kwargs['headers'] = dict(kwargs.get('headers', {}), **self.auth_header)

        if verbose:
            params_to_show = dict(**(path_variables or {}),
                                  **{k: v for k, v in kwargs.items() if k not in ['url', 'headers']})
            logging.info('Sending a request from %s with the following args: %s', type(self).__name__, params_to_show)

        r = requests.request(method=method, **kwargs)
        data = r.json() if (status := r.status_code) == 200 else None

        if status == 200:
            if verbose:
                logging.info('Data received from %s', type(self).__name__)
            return data
        else:  # do NOT raise on bad statuses (e.g. 500s are returned for no data)
            if verbose:
                logging.info(f'No data received from %s; (request response status: %s)', type(self).__name__, status)
            return None


class LangFlowBaseClass:  # note that it does instantiate the AuthenticatedEndpoint abstract class (no bearer token auth)
    """A base class for LangFlow flows."""

    def __init__(self, c: ConfigSchema, supported_orgs):
        # Verify that the org in the config is among those in supported_orgs, then set the homonymous fields.
        #   I.e. the set_config_and_orgs method from the AuthenticatedEndpoint class verbatim
        if c['org'] in supported_orgs:
            self.c, self.supported_orgs = c, supported_orgs
        else:  # vv no need for logging; this will propagate up the chain to a log (and DO want to fail for this)
            raise ValueError(f"{type(self).__name__} does not support organisation '{c['org']}'. Supported orgs: {supported_orgs}.")

        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": config.langflow.api_key
        }
        self.url_base = config.langflow.base_url
        self.flow_id = None

    def _send_request(self, method: str = None, verbose: bool = True, payload: dict = None, **kwargs):
        """Send an authenticated request; keyword arguments are passed directly to the get.
        The path_variables argument is for converting ':'-tagged variables in self.url_base to their values,
        e.g. if path_variables == dict(id='ME'), '/something/:id' will be converted to '/something/ME'.
        """
        if 'params' in kwargs:
            kwargs['params'] = {k: v for k, v in kwargs['params'].items() if v is not None}

        method = method or 'POST'
        assert method in ['GET', 'POST']

        kwargs['url'] = f'{self.url_base}api/v1/run/{self.flow_id}'
        kwargs['headers'] = dict(kwargs.get('headers', {}), **self.headers)
        kwargs['json'] = payload

        if verbose:
            params_to_show = {k: v for k, v in kwargs.items() if k not in ['url', 'headers']}
            logging.info('Sending a request from %s with the following args: %s', type(self).__name__, params_to_show)

        r = requests.request(method=method, **kwargs)

        if r.status_code == 200:
            content = r.json()
            try:  # vv yes, this is the shortest path to it (and the value is repeated in multiple other deeper spots)
                out = content['outputs'][0]['outputs'][0]['outputs']['message']['message']
                logging.info('Response received from %s: %s', type(self).__name__, out)
                return out
            except KeyError:
                logging.warning('The response received from %s did not conform to the expected format '
                                '(looking for outputs>0>outputs>0>outputs>message>message): %s',
                                type(self).__name__, content)
                return None
        else:  # raise for bad statuses
            raise Exception(f'Non-200 status from LangFlow {type(self).__name__}: {r.status_code}')


class RedisBaseClass(DataSource):
    """Base for Redis-backed data sources."""

    def __init__(self, c: ConfigSchema, supported_orgs: list[str], cache_path: str):
        self.set_config_and_orgs(c, supported_orgs)
        self._cache = SpecificRedisCache(org=c['org'], cache_path=cache_path)


