<!-- docs_as_of: 2026-05-14T15:00:00 -->

# Environment variables

All production variables below are read via `getenv` in `config.py` unless noted. **Optional** means the code may accept empty/missing values in some paths but runtime failures are likely when that code path executes.

## AI behaviour and org policy

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `AZURE_ENVIRONMENT` | Selects Cosmos DB prefix key (`live` → `vorlive`, else `vordev`) | Yes |
| `DEFAULT_RESULTS_LIMIT` | Default cap on list sizes in mappings | Yes |
| `HISTORY_LENGTH` | Max prior chat messages parsed in `GraphLogisticsBot.parse_message_history` | Yes |
| `STRICT_RESULTS_LIMIT` | Stricter cap used in some tool/endpoint paths | Yes |
| `RESULTS_LIMIT_FROM_SOURCE` | Page size (`size`) for Vor Search index requests; read as `config.ai_behaviour.source_results_limit` | Yes |
| `SUPPORTED_ORGS` | Pipe-separated org keys allowed for VOR AI | Yes |
| `ACTION_ALLOWED_ORGS` | Pipe-separated org keys that may use action tools (default empty) | No |

## Azure OpenAI

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `AZURE_OPENAI_ENDPOINT` | Base URL for ChatOpenAI client | Yes |
| `AZURE_OPENAI_API_KEY` | API key | Yes |
| `AZURE_OPENAI_LOW_DEPLOYMENT_NAME` | Deployment name for “low” cost/speed tier | Yes |
| `AZURE_OPENAI_NORMAL_DEPLOYMENT_NAME` | “normal” tier | Yes |
| `AZURE_OPENAI_HIGH_DEPLOYMENT_NAME` | “high” tier | Yes |
| `AZURE_OPENAI_TEMPERATURE` | Passed where models still accept temperature | Yes |

## VOR AI Search (index + query)

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `VOR_AISEARCH_CLIENT_ID` / `VOR_AISEARCH_CLIENT_SECRET` | OAuth client for AI Search | Yes |
| `VOR_AISEARCH_BASE_URL` | API root | Yes |
| `VOR_AISEARCH_AUTH_URL` | Token endpoint | Yes |
| `VOR_AISEARCH_FLIGHT_URL` | Flight search | Yes |
| `VOR_AISEARCH_FLIGHT_INDEXING_URL` | Flight index ingestion | Yes |
| `VOR_AISEARCH_GLOBAL_URL` | Global search | Yes |
| `VOR_AISEARCH_MRS_URL` | Movement requests search | Yes |
| `VOR_AISEARCH_PRIORITIES_URL` | Priorities search | Yes |
| `VOR_AISEARCH_PRIORITY_INDEXING_URL` | Priority index ingestion | Yes |
| `VOR_AISEARCH_ROAD_TRANSPORT_URL` | Road transport search | Yes |
| `VOR_AISEARCH_ROAD_TRANSPORT_INDEXING_URL` | Road transport index ingestion | Yes |
| `VOR_AISEARCH_SHIPMENTS_URL` | Shipments search | Yes |
| `VOR_AISEARCH_VOYAGE_CARGO_MANIFESTS_URL` | Manifest search | Yes |
| `VOR_AISEARCH_VOYAGE_CARGO_MANIFESTS_BY_ID_URL` | Manifest by id | Yes |

## VOR Search (secondary search product)

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `VOR_SEARCH_CLIENT_ID` / `VOR_SEARCH_CLIENT_SECRET` | OAuth client | Yes when Vor Search tools used |
| `VOR_SEARCH_BASE_URL` | API root | Yes |

Auth and search paths (`/getToken`, `/global-search/search`, `/flights/search`, `/roadTransportJobs/search`, `/shipments/search`, `/voyages/search`) are **fixed in code** in `config.vor_search.url` (no per-path env vars).

## Cosmos DB

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `VOR_COSMOSDB` | Main Cosmos connection string or identifier consumed by `shared/cosmos.py` | Yes for AIS/voyage paths |
| `VOR_CVX_ABU_COSMOSDB` | Additional DB identifier for Chevron ABU data paths | Yes when those code paths run |

## VOR Customer API (developer portal keys + OAuth)

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `VOR_API_DEV_PORTAL_KEY_CHEVRON` | Subscription key header value for Chevron | Yes for Chevron API calls |
| `VOR_API_DEV_PORTAL_KEY_SHELL_UK` | Shell UK key | Yes for Shell UK |
| `VOR_API_DEV_PORTAL_KEY_EXXON_MOBIL_GUYANA` | ExxonMobil Guyana key | Yes for Guyana |
| `VOR_ENDPOINT_BEARER_TOKEN_CLIENT_ID` / `CLIENT_SECRET` / `TENANT_ID` | AAD app for bearer token | Yes |
| `VOR_ENDPOINT_API_RESOURCE_ID` | Resource URI for token audience | Yes |
| `VOR_BASE_URL` | Customer API host | Yes |
| `VOR_ENDPOINT_CONTAINER_EVENTS_URL` | … and other `VOR_ENDPOINT_*_URL` entries in `config.customer_api.url` | Yes per used endpoints |

The `VOR_API_DEV_PORTAL_KEY_*` naming is slightly misleading in that these variables apply to both Dev and Live environments.

## Data Enhancer

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `VOR_DATA_ENHANCER_USERNAME` / `PASSWORD` | Resource owner style credentials | Yes for Data Enhancer ingestion |
| `VOR_DATA_ENHANCER_URL` | Base URL | Yes |
| `VOR_DATA_ENHANCER_TOKEN_URL` | Token | Yes |
| `VOR_DATA_ENHANCER_ACTIVE_CCU_HIRES_URL` | CCU hires | Yes when used |
| `VOR_DATA_ENHANCER_CARGO_EVENTS_BY_ID_URL` | Guyana cargo events | Yes when used |
| `VOR_DATA_ENHANCER_FLIGHTS_BY_ID_URL` / `BY_DATE_URL` | Flight detail / date range | Yes for flight jobs |
| `VOR_DATA_ENHANCER_ROAD_TRANSPORTS_BY_ID_URL` / `EVENTS_URL` / `SUMMARY_BY_DATE_URL` | RTJ detail / events / summary | Yes for RTJ jobs |
| `VOR_DATA_ENHANCER_VOYAGES_BY_ID_URL` | Voyages | Yes when used |
| `VOR_DATA_ENHANCER_WORK_ORDERS_BY_ID_URL` | Work orders | Yes when used |

## LangFlow (active external agents)

Orchestration for notification and subscription agents **lives on LangFlow** today (replacing the old Flowise deployment).

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `LANGFLOW_API_KEY` / `LANGFLOW_URL` | LangFlow host | Yes when notification/subscription agents enabled |
| `LANGFLOW_NOTIFICATION_AGENT` / `LANGFLOW_SUBSCRIPTION_AGENT` | Agent identifiers/paths | Yes when those features enabled |

## Flowise env vars (historical / dormant)

The **`FLOWISE_*`** settings are still read in `config.py` for `collabgpt_po_shipments_trigger`, which called a Flowise PO warnings chatflow. **The Flowise backend no longer exists**; the team uses **LangFlow** for new/revived flows, and **this PO flow was not ported** until it is needed again. Treat these variables as **optional / legacy** unless you are reviving or deleting that code path.

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `FLOWISE_ROOT_URL` / `FLOWISE_BEARER_TOKEN` / `FLOWISE_PO_WARNINGS_CHATFLOW_ID` | Former Flowise PO workflow (feature 006) | No for normal operation; only if dormant function is reconnected to a host |

## Redis

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `VOR_REDIS_CONNECTION_STR` | Redis URL | Yes for Redis-backed features |
| `VOR_REDIS_SUBSCRIPTIONS` | Base path/key segment for subscription caches | Yes for feature 002 |
| `VOR_REDIS_LOGISTICS_SUMMARY` | Documented in code comments; used with org-specific cache paths | Context-dependent |
| `VOR_REDIS_PRIORITYFREIGHT_CVX` | Key for priority freight JSON blob | Yes for `collabgpt_get_priority_items` |
| `VOR_REDIS_INTFREIGHTFORWARDING_ENDORSEDFORCOLLECTION_CVX` | Chevron Redis path | Yes when referenced |
| `VOR_REDIS_VOYAGESUMMARY_CVX` | Voyage summary cache | Yes for vessel/voyage features |

## Subscriptions and storage queue

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `SUBSCRIPTIONS_MAX_PAST_NOTIFICATIONS_TO_CACHE` | Int cap | Yes |
| `SUBSCRIPTIONS_MAX_PAST_NOTIFICATIONS_TO_SEND` | Int cap | Yes |
| `AzureWebJobsStorage` | Azure Functions storage account (queues, hosts) | Yes |
| `SUBSCRIPTION_QUEUE` | Queue name for subscription assessment messages | Yes for feature 002 |

## User Actions API

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `UA_TENANT_ID` / `UA_CLIENT_ID` / `UA_CLIENT_SECRET` | Service principal for User Actions | Yes |
| `UA_NOTIFICATION_AGENT_ALLOW_LIST` | Pipe-separated orgs enabled for notification/subscription sweep | Yes for timer |
| `UA_BASE_URL` | Host | Yes |
| `UA_GET_USER_ACTIONS_URL` / `UA_CLOSE_SUBSCRIPTION_URL` | REST paths | Yes |

## Analytics and logging

| Variable | Meaning | Required |
| -------- | ------- | -------- |
| `MIXPANEL_PROJECT_TOKEN` | Server-side Mixpanel token | Optional (skips if absent in helper) |
| `SLACK_LOGGING_WEBHOOK_URL` | Incoming webhook for `@slack_logging` | Optional but expected in deployed envs |

## Test-only (not in `config.py`)

| Variable | Meaning |
| -------- | ------- |
| `COLLAB_GPT_LG_DEV` / `COLLAB_GPT_LG_DEV_KEY` | Used in `collabgpt_lg/tests/test_vorai.py` for live HTTP tests against dev |
| `COLLAB_GPT_LG_LIVE` / `COLLAB_GPT_LG_LIVE_KEY` | Same for live environment |

These are **human-only / CI-secret** style variables; see [Testing](testing.md).
