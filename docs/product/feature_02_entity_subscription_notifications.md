# Feature 02 — Entity subscriptions (timer + queue)

## Summary

Two functions cooperate: a **timer** polls active subscriptions and enqueues work; a **queue-triggered** function runs the **subscription agent** (Langflow) to decide whether to notify users and whether a subscription should be closed after a final notification.

## Components


| Piece                   | Trigger             | Entry module                                     | Schedule / binding                                                       |
| ----------------------- | ------------------- | ------------------------------------------------ | ------------------------------------------------------------------------ |
| Subscription checker    | Timer               | `collabgpt_check_subscriptions/__init__.py`      | `*/15 * * * `* (every 15 minutes) per `function.json`                    |
| Subscription assessment | Azure Storage Queue | `collabgpt_check_subscription_queue/__init__.py` | Queue name from `%SUBSCRIPTION_QUEUE%`, connection `AzureWebJobsStorage` |


## Subscribeable entity types

The timer and the LangGraph **notification topic router** both use `apis_by_org` in `collabgpt_check_subscriptions/__init__.py` (entity-type label → endpoint class in `collabgpt_lg/endpoints.py`). The router prompt lists these keys so the model can refuse clearly unsupported subscription requests.


| Org key            | Entity types |
| ------------------ | ------------ |
| `CHEVRON`          | container, flight, logistics summary report, movement request, road transport job, shipment, voyage, work order |
| `ExxonMobilGuyana` | flight, shipment, transfer request, voyage, work order |
| `Shell UK`         | flight requests |

Unsupported cases called out in prompts include subscribing on behalf of another user, conditions on notification timing, and entity types outside this list (when the type is known upfront).

## Behaviour (code-derived)

- **Enabled orgs** for the timer loop are `config.user_actions.notification_agent_allow_list` (`UA_NOTIFICATION_AGENT_ALLOW_LIST`). Each org must exist in `apis_by_org` in `collabgpt_check_subscriptions/__init__.py` (maps entity types to `collabgpt_lg/endpoints.py` API classes).
- The timer compares cached entity snapshots to fresh API data (`DeepDiff`), enqueues messages per changed subscription, and uses `SubscriptionCache` for Redis-backed state (`collabgpt_check_subscriptions/classes.py`, `functions.py`).
- The queue worker calls `assess_diff` (`collabgpt_check_subscriptions/functions.py`) with a documented RPM limit comment (21700, which is 70% of current model RPM, vorai-gpt-5-nano-live). On success it may append to past-notifications cache, track Mixpanel (`subscription_notification_sent`, `subscription_scheduled_for_closure`), and schedule closure entries in Redis.
- Subscriptions to entities deemed to be in a terminal state (see `state_is_terminal` function) are automatically scheduled for closure.

## Technical pointers

- [Architecture](../technical/architecture.md) — high-level data flow
- [Environment variables](../technical/environment_variables.md) — Redis, queue, Langflow, user actions

