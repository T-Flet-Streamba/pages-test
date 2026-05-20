import logging
import traceback
import asyncio
import json

# Set up the logger before importing anything else from this package
logging.getLogger().setLevel(logging.INFO)
if not logging.getLogger().hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

from azure.functions import TimerRequest
from azure.storage.queue import QueueClient, QueueMessage
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from deepdiff import DeepDiff

from collabgpt_check_subscriptions.classes import SubscriptionCache
from collabgpt_check_subscriptions.functions import get_new_entities, state_is_terminal, track_subscription_events
from collabgpt_lg.endpoints import (
    ContainerEventsByID,
    FlightRequests,
    FlightsByID,
    LogisticsSummaryReports,
    MovementRequestByID,
    RoadTransportJobsByID,
    ShipmentsByID,
    TransferRequestsByID,
    VoyagesByID,
    VoyageCargoManifestsByID,
    WorkOrderByID,
    WorkOrderByIDDancer
)

from shared.user_actions import ActiveSubscriptions
from shared.slack import slack_logging

import config


apis_by_org = {
    'CHEVRON': {
        'container': ContainerEventsByID,
        'flight': FlightsByID,
        'logistics summary report': LogisticsSummaryReports,
        'movement request': MovementRequestByID,
        'road transport job': RoadTransportJobsByID,
        'shipment': ShipmentsByID,
        'voyage': VoyageCargoManifestsByID,
        'work order': WorkOrderByID
    },
    'ExxonMobilGuyana': {
        'flight': FlightsByID,
        'shipment': ShipmentsByID,
        'transfer request': TransferRequestsByID,
        'voyage': VoyagesByID,
        'work order': WorkOrderByIDDancer
    },
    'Shell UK': {
        'flight requests': FlightRequests,
    }
}


@slack_logging
def main(subscriptionTimer: TimerRequest) -> None:
    """Run the subscription pipeline for all available orgs and report any of their data retrieval errors together after everything has run."""
    now = datetime.now(tz=timezone.utc)
    logging.info('Subscription checker function triggered at %s', now.isoformat())

    errors = {}
    for org in (enabled_orgs := config.user_actions.notification_agent_allow_list):
        try:
            if org not in apis_by_org:
                raise ValueError(f'{org} is enabled by env variable but not actually supported in infrastructure. '
                                 f'Enabled orgs: {enabled_orgs}. '
                                 f'Supported orgs: {list(apis_by_org.keys())}')
            process_subscriptions(org, now)
        except Exception as e:  # store errors for a collective raise after all orgs are done
            errors[org] = e

    # Raise (a summary of) retrieval errors only after everything else has run
    if errors:
        details = [f'{type(e).__name__} for {org}: {e}' for org, e in errors.items()]
        raise type(list(errors.values())[0])(f'{len(errors)} orgs had data retrieval errors for at least one entity:\n\t{'\n\t'.join(details)}')


def process_subscriptions(org: str, now: datetime) -> None:
    """Full pipeline for subscription checking for a single org. Data retrieval errors are accumulated and raised together at the end."""
    # Data sources
    sub_api = ActiveSubscriptions(org)
    snapshot_cache = SubscriptionCache('SNAPSHOTS', org)
    sub_closure_cache = SubscriptionCache('TO_CLOSE', org)
    past_notifications_cache = SubscriptionCache('PAST_NOTIFICATIONS', org)
    queue_client = QueueClient.from_connection_string(config.azure_storage.connection_string, config.azure_storage.subscription_queue)

    # Retrieve active subscriptions from the User Actions API
    active_subscriptions = sub_api.retrieve(org=org)
    logging.info('Retrieved %s active subscriptions', len(active_subscriptions))

    # Close any subscription scheduled for closure and past the grace period (and remove manually closed ones)
    subs_to_close = sub_closure_cache.get_entries()
    if subs_to_close:
        closed_manually = [sub_id for sub_id in subs_to_close if sub_id not in active_subscriptions]
        to_close_now = [sub_id for sub_id, scheduled_at in subs_to_close.items()
                        if datetime.fromisoformat(scheduled_at) + timedelta(days=1) < now]
        logging.info('Retrieved %s subscriptions scheduled for closure, of which %s are past their grace period and %s were already closed manually.',
                     len(subs_to_close), len(to_close_now), len(closed_manually))
        if closed_manually:
            sub_closure_cache.del_entries(closed_manually)
        if to_close_now:
            sub_api.close(to_close_now)
            sub_closure_cache.del_entries(to_close_now)
            track_subscription_events('subscription_closed', to_close_now, active_subscriptions)
            # vv needs to happen after its use in track_subscription_event_batch ^^
            active_subscriptions = {sub_id: sub for sub_id, sub in active_subscriptions.items() if sub_id not in to_close_now}
            logging.info('Closed %s subscriptions; %s active subscriptions remain.', len(to_close_now), len(active_subscriptions))

    # Remove snapshots of entities not in active subscriptions
    active_entities = set(sub['entityId'] for sub_id, sub in active_subscriptions.items())
    snapshot_cache_entities = set(snapshot_cache.get_keys())
    if snapshots_to_remove := snapshot_cache_entities.difference(active_entities):
        snapshot_cache.del_entries(snapshots_to_remove)
        logging.info('Removed %s entity snapshots (those not present in active subscriptions): %s.', len(snapshots_to_remove), list(snapshots_to_remove))

    # Remove past notifications of closed subscriptions
    past_notification_subs = set(parts[0] for k in past_notifications_cache.get_keys() if len(parts := k.split('::')) > 1)
    if past_notifications_to_remove := past_notification_subs.difference(active_subscriptions):
        past_notifications_cache.del_entries(past_notifications_to_remove, del_sub_keys=True)
        logging.info('Removed past notifications for %s subscriptions (closed just now or manually earlier).', len(past_notifications_to_remove))

    # Terminate execution if there are no active subscriptions (checking only now, after all the cleanups)
    if not active_subscriptions:
        return

    # Retrieve the data snapshots for each involved entity from the Redis cache
    snapshots = snapshot_cache.get_entries(active_entities)
    logging.info('Retrieved %s previous data snapshots for the %s entities in the %s active subscriptions (%s entities missing)',
                 len(exist := [s for _, s in snapshots.items() if s]), len(active_entities),
                 len(active_subscriptions), len(active_entities) - len(exist))

    # Fetch current data for the entities in active subscriptions
    new_entity_data, errors = asyncio.run(get_new_entities(sub_api.c, active_subscriptions, apis_by_org[org]))

    # Schedule for closure any subscription to entities in terminal states
    entity_to_type_and_subs = defaultdict(lambda: ['', []])
    for sub_id, sub in active_subscriptions.items():
        entity_to_type_and_subs[sub['entityId']][0] = sub['entityType']
        entity_to_type_and_subs[sub['entityId']][1].append(sub_id)
    terminal_entities = [e_id for e_id, (e_type, _) in entity_to_type_and_subs.items() if state_is_terminal(e_type, new_entity_data.get(e_id))]
    terminal_subs = [sub for e_id in terminal_entities for sub in entity_to_type_and_subs[e_id][1]]
    if subs_to_schedule := set(terminal_subs).difference(subs_to_close):  # otherwise schedule date is reset
        sub_closure_cache.set_entries({sub_id: now.isoformat() for sub_id in subs_to_schedule})
        logging.info('Scheduled %s subscriptions for closure since their entities (%s) have reached a terminal state.',
                     len(subs_to_schedule),
                     [e_id for e_id in terminal_entities if subs_to_schedule.intersection(entity_to_type_and_subs[e_id][1])])
        track_subscription_events('subscription_scheduled_for_closure_due_to_terminal_entity_state', subs_to_schedule, active_subscriptions)

    # Check whether data has changed and select snapshots to update and subscriptions to examine
    snapshot_updates, subs_to_check = {}, {}
    for sub_id, sub in active_subscriptions.items():
        if not (new_data := new_entity_data.get(sub['entityId'])):
            continue
        diff = {}  # Generate a diff if a previous snapshot is in the cache
        if old_data := snapshots.get(sub['entityId']):              # vv mention the new values for the changed fields
            diff = DeepDiff(old_data, new_data, ignore_order=True, verbose_level=2)
            if 'type_changes' in diff:
                for fields in diff['type_changes'].values():
                    fields['old_type'] = str(fields['old_type'])
                    fields['new_type'] = str(fields['new_type'])
        if not old_data or diff:  # i.e. in the first run of the subscription or if there is new data
            snapshot_updates[sub['entityId']] = new_data
            subs_to_check[sub_id] = dict(sub_id=sub_id, sub=sub, new_data=new_data, diff=diff)
        # else:
        #     logging.info('No data changes for subscription %s', sub_id)
    logging.info('%s subscriptions have data changes to be assessed.', len(subs_to_check))

    if subs_to_check:
        # Get the past notifications of the subscriptions to check, and limit both cached ones and to send ones
        cached_pns_to_remove = []
        past_notifications = past_notifications_cache.get_entries(subs_to_check.keys(), get_sub_keys=True)
        logging.info('%s of the %s subscriptions with data changes had past notifications to retrieve.',
                     sum(bool(x) for x in past_notifications), len(subs_to_check))
        for sub_id, details in subs_to_check.items():
            pn_keys = sorted(pns := past_notifications.get(sub_id))  # chronological order since ~ISO dates
            details['past_notifications'] = {k: pns[k] for k in pn_keys[-config.subscriptions.max_pns_to_send:]}
            cached_pns_to_remove.extend([f'{sub_id}::{k}' for k in pn_keys[:-config.subscriptions.max_pns_to_cache]])
        if cached_pns_to_remove:
            past_notifications_cache.del_entries(cached_pns_to_remove)

        # Dequeue not-yet-processed assessment requests for subscriptions whose data has already changed again
        already_queued: list[QueueMessage] = list(queue_client.receive_messages(messages_per_page=10))
        to_dequeue = [req for req in already_queued if json.loads(req.content).get('sub_id') in subs_to_check]
        if to_dequeue:
            for req in to_dequeue:
                queue_client.delete_message(req.id, req.pop_receipt)
            logging.info('Dequeued %s subscription assessment requests since data has changed again since enqueuing.', len(to_dequeue))

        # Enqueue the subscriptions assessment requests
        for i, params in enumerate(subs_to_check.values()):
            queue_client.send_message(json.dumps(dict(i=i+1, of=len(subs_to_check), at=now.isoformat(), **params)))
        logging.info('Enqueued %s subscriptions assessment requests.', len(subs_to_check))
        track_subscription_events('subscription_assessment_enqueued', subs_to_check, active_subscriptions)

        # Update the cached snapshot for every entity which changed
        if snapshot_updates:
            snapshot_cache.set_entries(snapshot_updates)
            logging.info('Updated %s snapshots in the %s Redis cache.', len(snapshot_updates), snapshot_cache.cache_path)
        else:
            logging.info('No data changes for any of the %s active subscriptions.', len(active_subscriptions))

    # Raise (a summary of) retrieval errors only after everything else has run
    if errors:
        details = [f'{type(e).__name__} for {_type} {_id}: {e} at {last_frame.filename}:{last_frame.lineno} in {last_frame.name}'
                   for _id, (_type, e) in errors.items() if (last_frame := traceback.extract_tb(e.__traceback__)[-1])]
        raise type(list(errors.values())[0][1])(f'\n\t{len(errors)} of the {len(active_subscriptions)} active subscriptions '
                                                f'failed the data retrieval:\n\t\t{'\n\t\t'.join(details)}')
        # Example:
        # ZeroDivisionError: 9 of the 9 active subscription data retrievals failed:
        #   ZeroDivisionError for voyage aurigaastrolabedsbbwi0618: division by zero at ...\vor-collabgpt-functions\collabgpt_check_subscriptions\__init__.py:87 in main
        # 	LookupError for shipment 42: the lookup ran fine but found no data at ...\vor-collabgpt-functions\collabgpt_check_subscriptions\__init__.py:97 in main
        #   ...


# if __name__ == '__main__':
#     # vv removes the harmless but annoying "RuntimeError: Event loop is closed" errors
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     main(TimerRequest)


