"""Single location to import (and possibly repackage) environment variables. Used to fail fast when due to env vars.
"""
from os import getenv
from zoneinfo import ZoneInfo


# Hardcoded configs

org_time_zones = {
    'CHEVRON': ZoneInfo('Australia/Perth'),
    'Shell UK': ZoneInfo('Europe/London'),
    'Shell TT': ZoneInfo('America/Port_of_Spain'),
    'ExxonMobilGuyana': ZoneInfo('America/Guyana')
}



# Config from environment variables

class _AIBehaviour:
    environment = getenv('AZURE_ENVIRONMENT')
    default_limit = int(getenv('DEFAULT_RESULTS_LIMIT'))
    history_length = int(getenv('HISTORY_LENGTH'))
    strict_limit = int(getenv('STRICT_RESULTS_LIMIT'))
    source_results_limit = int(getenv('RESULTS_LIMIT_FROM_SOURCE'))
    supported_orgs = getenv('SUPPORTED_ORGS').split('|')
    actions_allowed_orgs = getenv('ACTION_ALLOWED_ORGS', '').split('|')
ai_behaviour = _AIBehaviour()


class _AISearch:
    client_id = getenv('VOR_AISEARCH_CLIENT_ID')
    client_secret = getenv('VOR_AISEARCH_CLIENT_SECRET')
    class _URL:
        base = getenv('VOR_AISEARCH_BASE_URL')
        auth = getenv('VOR_AISEARCH_AUTH_URL')
        flights = getenv('VOR_AISEARCH_FLIGHT_URL')
        flight_indexing = getenv('VOR_AISEARCH_FLIGHT_INDEXING_URL')
        global_search = getenv('VOR_AISEARCH_GLOBAL_URL')
        mrs = getenv('VOR_AISEARCH_MRS_URL')
        priorities = getenv('VOR_AISEARCH_PRIORITIES_URL')
        priority_indexing = getenv('VOR_AISEARCH_PRIORITY_INDEXING_URL')
        road_transport = getenv('VOR_AISEARCH_ROAD_TRANSPORT_URL')
        road_transport_indexing = getenv('VOR_AISEARCH_ROAD_TRANSPORT_INDEXING_URL')
        shipments = getenv('VOR_AISEARCH_SHIPMENTS_URL')
        voyage_cargo_manifests = getenv('VOR_AISEARCH_VOYAGE_CARGO_MANIFESTS_URL')
        voyage_cargo_manifests_by_id = getenv('VOR_AISEARCH_VOYAGE_CARGO_MANIFESTS_BY_ID_URL')
    url = _URL()
ai_search = _AISearch()


class _Cosmos:
    db_prefix = dict(live='vorlive', dev='vordev')[getenv('AZURE_ENVIRONMENT')]
    main_db = getenv('VOR_COSMOSDB')
    cvx_abu_db = getenv('VOR_CVX_ABU_COSMOSDB')
cosmos = _Cosmos()


class _CustomerAPI:
    subscription_keys = {
        'CHEVRON': getenv('VOR_API_DEV_PORTAL_KEY_CHEVRON'),
        'Shell UK': getenv('VOR_API_DEV_PORTAL_KEY_SHELL_UK'),
        'ExxonMobilGuyana': getenv('VOR_API_DEV_PORTAL_KEY_EXXON_MOBIL_GUYANA')
    }
    client_id = getenv('VOR_ENDPOINT_BEARER_TOKEN_CLIENT_ID')
    client_secret = getenv('VOR_ENDPOINT_BEARER_TOKEN_CLIENT_SECRET')
    tenant_id = getenv('VOR_ENDPOINT_TENANT_ID')
    api_resource_id = getenv('VOR_ENDPOINT_API_RESOURCE_ID')
    class _URL:
        base = getenv('VOR_BASE_URL')
        container_events = getenv('VOR_ENDPOINT_CONTAINER_EVENTS_URL')
        flight_request = getenv('VOR_ENDPOINT_FLIGHT_REQUESTS_URL')
        movement_request = getenv('VOR_ENDPOINT_MOVEMENT_REQUEST_URL')
        services = getenv('VOR_ENDPOINT_SERVICES_URL')
        shipment = getenv('VOR_ENDPOINT_SHIPMENT_BY_NUMBER_URL')
        transfer_request = getenv('VOR_ENDPOINT_TRANSFER_REQUEST_URL')
        voyage_cargo_manifests = getenv('VOR_ENDPOINT_VOYAGE_CARGO_MANIFESTS_URL')
        work_orders = getenv('VOR_ENDPOINT_WORK_ORDERS_URL')
    url = _URL()
customer_api = _CustomerAPI()


class _DataEnhancer:
    username = getenv('VOR_DATA_ENHANCER_USERNAME')
    password = getenv('VOR_DATA_ENHANCER_PASSWORD')
    class _URL:
        base = getenv('VOR_DATA_ENHANCER_URL')
        token = getenv('VOR_DATA_ENHANCER_TOKEN_URL')
        active_ccu_hires = getenv('VOR_DATA_ENHANCER_ACTIVE_CCU_HIRES_URL')
        cargo_events_by_id = getenv('VOR_DATA_ENHANCER_CARGO_EVENTS_BY_ID_URL')
        flights_by_id = getenv('VOR_DATA_ENHANCER_FLIGHTS_BY_ID_URL')
        flights_by_date = getenv('VOR_DATA_ENHANCER_FLIGHTS_BY_DATE_URL')
        road_transports_by_id = getenv('VOR_DATA_ENHANCER_ROAD_TRANSPORTS_BY_ID_URL')
        road_transports_events = getenv('VOR_DATA_ENHANCER_ROAD_TRANSPORTS_EVENTS_URL')
        road_transports_by_date = getenv('VOR_DATA_ENHANCER_ROAD_TRANSPORTS_SUMMARY_BY_DATE_URL')
        voyages_by_id = getenv('VOR_DATA_ENHANCER_VOYAGES_BY_ID_URL')
        work_orders_by_id = getenv('VOR_DATA_ENHANCER_WORK_ORDERS_BY_ID_URL')
    url = _URL()
data_enhancer = _DataEnhancer()


class _Flowise:
    root_url = getenv('FLOWISE_ROOT_URL')
    bearer_token = getenv('FLOWISE_BEARER_TOKEN')
    po_warnings_chatflow_id = getenv('FLOWISE_PO_WARNINGS_CHATFLOW_ID')
flowise = _Flowise()


class _LangFlow:
    api_key = getenv('LANGFLOW_API_KEY')
    base_url = getenv('LANGFLOW_URL')
    notification_agent = getenv('LANGFLOW_NOTIFICATION_AGENT')
    subscription_agent = getenv('LANGFLOW_SUBSCRIPTION_AGENT')
langflow = _LangFlow()


class _LLM:
    endpoint = getenv('AZURE_OPENAI_ENDPOINT')
    api_key = getenv('AZURE_OPENAI_API_KEY')
    deployment = dict(
        low=getenv('AZURE_OPENAI_LOW_DEPLOYMENT_NAME'),
        normal=getenv('AZURE_OPENAI_NORMAL_DEPLOYMENT_NAME'),
        high=getenv('AZURE_OPENAI_HIGH_DEPLOYMENT_NAME')
    )
    costs_per_million = {  # https://azure.microsoft.com/en-us/pricing/details/azure-openai/ ; benchmarked on 11/03/2026
        'gpt-4.1-mini': {'in': 0.40,    'cached': 0.1,  'out': 1.60},   # seconds per 1K tokens: 0.908, 130.0% of 4.1
        'gpt-4.1':      {'in': 2,       'cached': 0.5,  'out': 8},      # seconds per 1K tokens: 0.699, 100.0% (fastest)
        'o4-mini':      {'in': 1.21,    'cached': 0.31, 'out': 4.84},   # seconds per 1K tokens: 1.346, 192.6% of 4.1
        'gpt-5-nano':   {'in': 0.05,    'cached': 0.01, 'out': 0.40},   # seconds per 1K tokens: 4.073, 582.9% of 4.1
        'gpt-5-mini':   {'in': 0.25,    'cached': 0.03, 'out': 2},      # seconds per 1K tokens: 4.639, 663.9% of 4.1
        'gpt-5-chat':   {'in': 1.25,    'cached': 0.13, 'out': 10},     # seconds per 1K tokens: 0.747, 107.0% of 4.1
        'gpt-5.1-chat': {'in': 1.25,    'cached': 0.13, 'out': 10},     # seconds per 1K tokens: 0.832, 119.1% of 4.1
        'gpt-5.2-chat': {'in': 1.75,    'cached': 0.18, 'out': 14}      # seconds per 1K tokens: 1.285, 183.9% of 4.1
    }
    temperature = getenv('AZURE_OPENAI_TEMPERATURE')
llm = _LLM()


class _MixPanel:
    project_token = getenv('MIXPANEL_PROJECT_TOKEN')
mixpanel = _MixPanel()


class _Redis:
    connection_str = getenv('VOR_REDIS_CONNECTION_STR')
    subscriptions = getenv('VOR_REDIS_SUBSCRIPTIONS')
    logistics_summary = getenv('VOR_REDIS_LOGISTICS_SUMMARY')
    class _CVX:
        priorityfreight = getenv('VOR_REDIS_PRIORITYFREIGHT_CVX')
        endorsedforcollection = getenv('VOR_REDIS_INTFREIGHTFORWARDING_ENDORSEDFORCOLLECTION_CVX')
        voyagesummary = getenv('VOR_REDIS_VOYAGESUMMARY_CVX')
    cvx = _CVX()
redis = _Redis()


class _Slack:
    logging_webhook_url = getenv('SLACK_LOGGING_WEBHOOK_URL')
slack = _Slack()


class _Susbscriptions:
    max_pns_to_cache = int(getenv('SUBSCRIPTIONS_MAX_PAST_NOTIFICATIONS_TO_CACHE'))
    max_pns_to_send = int(getenv('SUBSCRIPTIONS_MAX_PAST_NOTIFICATIONS_TO_SEND'))
subscriptions = _Susbscriptions()


class _Azure_Storage:
    connection_string = getenv('AzureWebJobsStorage')
    subscription_queue = getenv('SUBSCRIPTION_QUEUE')
azure_storage = _Azure_Storage()


class _UserActions:
    tenant_id = getenv('UA_TENANT_ID')
    client_id = getenv('UA_CLIENT_ID')
    client_secret = getenv('UA_CLIENT_SECRET')
    notification_agent_allow_list = getenv('UA_NOTIFICATION_AGENT_ALLOW_LIST').split('|')
    class _URL:
        base = getenv('UA_BASE_URL')
        get_user_actions = getenv('UA_GET_USER_ACTIONS_URL')
        close_subscription = getenv('UA_CLOSE_SUBSCRIPTION_URL')
    url = _URL()
user_actions = _UserActions()


class _VorSearch:
    client_id = getenv('VOR_SEARCH_CLIENT_ID')
    client_secret = getenv('VOR_SEARCH_CLIENT_SECRET')
    class _URL:
        base = getenv('VOR_SEARCH_BASE_URL')
        auth = '/getToken'
        global_search = '/global-search/search'
        flights_search = '/flights/search'
        road_transport_jobs_search = '/roadTransportJobs/search'
        shipments_search = '/shipments/search'
        voyages_search = '/voyages/search'
    url = _URL()
vor_search = _VorSearch()


