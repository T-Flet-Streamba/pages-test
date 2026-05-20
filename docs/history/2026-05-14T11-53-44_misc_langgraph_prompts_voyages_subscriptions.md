# Misc LangGraph prompts, voyages, subscriptions (#369)

This record follows merged work after [PR #367](https://github.com/streamba/vor-collabgpt-functions/pull/367); the merge commit covered here is [PR #369](https://github.com/streamba/vor-collabgpt-functions/pull/369).

**Timestamp in filename:** merge time of PR #369 on GitHub (`mergedAt`).

## Summary

- **Org config split:** `vor_search_result_filters` and `vor_url_list` moved from `collabgpt_lg/prompts.py` to new `collabgpt_lg/org_config.py` (imported by `prompts.py` and `endpoints.py`) to avoid a circular import when subscription entity types are referenced from prompts.
- **Shell UK / Adura:** glossary and answer guidelines tell the model the org is now called **Adura** in user-facing text while processing still uses the `Shell UK` org key.
- **Voyages:** `VoyagesByDescriptionVorSearch.query` short-circuits all-digit `search_term` through `VoyagesByID` before the index pipeline (restores voyage-number lookup).
- **Tool output trimming:** `trim_data` in `collabgpt_lg/utils.py` keeps `system_message` (and `status`) on dict outputs for the router node.
- **Subscriptions:** `get_notification_topic_router_prompt` lists supported subscribeable entity types from `apis_by_org` and clarifies unsupported cases (wrong entity type, subscribing others, etc.).
- **Retrieval guidance:** `vor_global_search` docstring warns against using global search when a typed tool supports time filtering.
- **Flight URLs:** `FlightsByID._data_mapping` uses `vor_url.helicopter` for Shell UK (`flightManifestId`); other orgs with `entityId` get `vor_url.flight` (including **ExxonMobilGuyana**).
- **Tests:** removed `Shell TT` “org not allowed” cases from `test_endpoints.py`; expected tools in `test_vorai.py` comments updated for voyage/shipment lookups.

## User stories

- [AB#12588](https://dev.azure.com/streambadev/f4c58d4f-554e-4af2-b9d7-2442543c3572/_workitems/edit/12588) — Adura naming context in prompts
- [AB#12579](https://dev.azure.com/streambadev/f4c58d4f-554e-4af2-b9d7-2442543c3572/_workitems/edit/12579) — voyage number shortcut search
- [AB#12618](https://dev.azure.com/streambadev/f4c58d4f-554e-4af2-b9d7-2442543c3572/_workitems/edit/12618) — `system_message` retained in trimmed tool outputs
- [AB#12614](https://dev.azure.com/streambadev/f4c58d4f-554e-4af2-b9d7-2442543c3572/_workitems/edit/12614) — subscription capability wording
- [AB#12626](https://dev.azure.com/streambadev/f4c58d4f-554e-4af2-b9d7-2442543c3572/_workitems/edit/12626) — ExxonMobilGuyana flight URLs

## Paths and symbols (primary)

| Area | Paths / symbols |
| ---- | ---------------- |
| Org-specific prompt URLs / search filters | `collabgpt_lg/org_config.py` — `vor_search_result_filters`, `vor_url_list` |
| Prompts & subscription router | `collabgpt_lg/prompts.py` — `glossary`, `answer_guidelines`, `get_notification_topic_router_prompt` |
| Voyage shortcut | `VoyagesByDescriptionVorSearch.query` in `collabgpt_lg/endpoints.py` |
| Tool output trim | `trim_data` in `collabgpt_lg/utils.py` |
| Global search tool | `vor_global_search_wrapper` in `collabgpt_lg/tools.py` |
| Subscribeable types source | `apis_by_org` in `collabgpt_check_subscriptions/__init__.py` |

## Feature IDs

- **01** — VOR AI (LangGraph): retrieval, prompts, tool-output shaping
- **02** — Entity subscriptions: notification-topic router capabilities text

## Documentation updates

- `product/feature_01_vor_ai_langgraph_http.md` — Adura naming, voyage-number shortcut, `org_config.py`, `vor_global_search` vs typed tools
- `product/feature_02_entity_subscription_notifications.md` — subscribeable entity types table from `apis_by_org`
- `technical/architecture.md` — org_config split, `trim_data`, flight URL mapping, voyage shortcut, notification router prompt
- `technical/project_layout.md` — `org_config.py` / symbol index; `docs_as_of` set to PR #369 merge time
