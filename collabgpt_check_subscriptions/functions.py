import random
import logging
import time
import asyncio

import config


# Set up the logger before importing anything else from this package
logging.getLogger().setLevel(logging.INFO)
if not logging.getLogger().hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

from aiohttp import ClientSession, TCPConnector
from collections import defaultdict

from collabgpt_check_subscriptions.classes import SubscriptiontionAgent
from collabgpt_lg.graph_types import ConfigSchema

from shared.mixpanel import track_events


async def get_new_entities(c: ConfigSchema, active_subscriptions: dict, apis: dict,
                           concurrent_requests_limit=20, verbose=True,
                           kwargs_by_e_type: dict[str, dict] | None = None):
    """Same parallelism as in collabgpt_lg.endpoints.VorGlobalSearch.get_data but with the added error preservation.
    kwargs_by_e_type is for always injecting the same kwargs for all subscriptions of specific entity types.
    """
    kwargs_by_e_type = kwargs_by_e_type if kwargs_by_e_type else {}

    # Group active subscriptions by the involved entity's type and ID (and get the set of those IDs)
    by_entity_type_and_id, entities = defaultdict(lambda: defaultdict(str)), set()
    for sub_id, sub in active_subscriptions.items():
        by_entity_type_and_id[sub['entityType']][sub['entityId']] = sub_id
        entities.add(sub['entityId'])  # could have passed in the active_entities variable, but easy to recover here

    # Schedule and async-run the api requests (provided the entity type is known; log errors otherwise)
    tasks, errors = [], {}
    async with ClientSession(connector=TCPConnector(limit=concurrent_requests_limit)) as session:
        sessioned_apis = {e_type: api(c, session) for e_type, api in apis.items()}
        for e_type, e_ids in by_entity_type_and_id.items():
            if api := sessioned_apis.get(e_type):
                tasks.extend([get_entity(e_id, e_type, api, verbose, **kwargs_by_e_type.get(e_type, {})) for e_id in e_ids])
            else:
                try:  # would have just warned here, but need actual raising for Slack logging
                    raise LookupError(f'no API available for entities of type {e_type}; subscriptions to it: {list(by_entity_type_and_id[e_type])}')
                except Exception as e:  # store errors for a collective raise after working cases have run
                    for e_id in by_entity_type_and_id[e_type].keys():
                        errors[e_id] = e_type, e
        random.shuffle(tasks)  # so that requests jump around between different entity-endpoints instead of all in a row
        results = await asyncio.gather(*tasks)

    # Unpack and return results
    values = {}
    for e_id, value, error in results:
        if error:
            errors[e_id] = error
        else:
            values[e_id] = value
    return values, errors


async def get_entity(e_id: str, e_type: str, api, verbose=True, **kwargs):
    """Make the api call to retrieve a single entity's info and safely store any error."""
    out, error = None, None
    try:
        out = await api.query(_id=e_id, verbose=verbose, **kwargs)
        if out.get('status', '').startswith('no data available'):
            raise LookupError('the lookup ran fine but found no data')
    except Exception as e:  # store errors for a collective raise after working cases have run
        error = e_type, e  # would have just warned here, but need actual raising for Slack logging
    return e_id, out, error


async def assess_diffs(c: ConfigSchema, subs_to_check: dict[str, dict], concurrent_requests_limit = 3, requests_per_minute_limit = 100):
    """Send async requests to the subscription agent ensuring that those for the same user DO NOT run in parallel
    (this is to avoid complications in the session logging on LangFlow) and that the given rate limit is not exceeded.
    The rate throttling is VERY conservative so that no issues happen at any later stage:
        it ALWAYS sleeps after a given number of requests have run (a fraction of the limit),
        even in the (likely) scenario that they took more than a minute.
    """
    # Group subscriptions by user
    by_user = defaultdict(list)
    for sub_id, info in subs_to_check.items():
        by_user[info['sub']['createdByUserId']].append(info)

    # Create batches of size <= concurrent_requests_limit in which all subscriptions are from different users
    batches = []
    while any(by_user.values()):
        batch = []
        for user in list(by_user.keys()):  # casting to list makes it a copy, so not affected by del
            if len(batch) >= concurrent_requests_limit:
                break
            if by_user[user]:
                batch.append(by_user[user].pop())
            else:
                del by_user[user]
        batches.append(batch)

    # Super-batch the batches so that each super-batch does not exceed a given fraction of the requests_per_minute_limit
    super_batches, super_batch, count, fraction = [], [], 0, .7
    for batch in batches:                                           # vv prevents passing an empty super_batch if
        if count + len(batch) > requests_per_minute_limit * fraction and super_batch:
            super_batches.append(super_batch)                       # ^^ len(batch) is over the limit by itself
            super_batch, count = [], 0
        super_batch.append(batch)
        count += len(batch)
    if super_batch:
        super_batches.append(super_batch)

    # Run batches sequentially (async requests inside each batch), sleeping between super-batches
    logging.info('Beginning execution of %s requests to the Subscription Agent, '
                 'in sequential batches of at most %s asynchronous requests (lower if not enough distinct users to fill the batch), '
                 'all in %s super-batches determined by the model RPM rate (waiting 30s between super-batches).',
                 len(subs_to_check), concurrent_requests_limit, len(super_batches))
    sub_agent = SubscriptiontionAgent(c)
    results = []
    for i, super_batch in enumerate(super_batches):
        if results:  # i.e. not the first super_batch
            logging.info('Sleeping for 30 seconds between batches of batches of requests to the subscription agent '
                         'to stay below %s of the %s-requests-per-minute limit.', fraction, requests_per_minute_limit)
            time.sleep(30)
        for j, batch in enumerate(super_batch):
            tasks = [sub_agent.query(**sub_info) for sub_info in batch]
            start = time.perf_counter()
            #### vv TEMPORARY NON-CONCURRENT REQUESTS vv ####
            batch_results = []
            for sub_info in batch:
                batch_results.append(await sub_agent.query(**sub_info))
            #### ^^ TEMPORARY NON-CONCURRENT REQUESTS ^^ ####
            # batch_results = await asyncio.gather(*tasks)
            logging.info('Ran batch %s/%s of super-batch %s/%s: %s requests in %.3f seconds.',
                         j+1, len(super_batch), i+1, len(super_batches), len(tasks), time.perf_counter()-start)
            results.extend(batch_results)

    return results


def assess_diff(sub_info: dict, requests_per_minute_limit = 20000):
    """Send a single request to the subscription agent ensuring that the given rate limit is not exceeded
    by sleeping proportionally to the request index.
    """
    # Sleep proportionally to the request index
    sleep_per_request = 60 / requests_per_minute_limit
    logging.info('Sleeping for %.2f seconds for request %s (of %s) to the Subscription Agent to stay below %s requests per minute '
                 '(this limit should be lower than true model RPM one, say 70%% of it).',
                 sub_info['i'] * sleep_per_request, sub_info['i'], sub_info['of'], requests_per_minute_limit)
    time.sleep(sub_info['i'] * sleep_per_request)

    # Make (and time) the request
    sub_agent = SubscriptiontionAgent(ConfigSchema(
        org=sub_info['sub']['organisation'],
        timezone=config.org_time_zones[sub_info['sub']['organisation']],
        llms={}
    ))
    start = time.perf_counter()
    sub_id, response = asyncio.run(sub_agent.query(**sub_info))
    logging.info('The request to the Subscription Agent ran in %.3f seconds.', time.perf_counter()-start)
    return response


def state_is_terminal(e_type: str, e_data: dict) -> bool:
    """Determine whether the entity has reached the terminal state after which subscription closure should be scheduled in every case."""
    if not e_data:
        return False
    match e_type:
        case 'container':
            return False  # there is no real terminal state for containers, as TakenOffHire is typically followed by PutOnHire
            # return e_data.get('Events', [{}])[-1].get('EventDescription') == 'TakenOffHire'
        case 'flight':
            return e_data.get('statusCodeType') in ['Completed', 'Cancelled']
        case 'flight requests':
            return False
        case 'logistics summary report':
            return False
        case 'movement request':
            return all(mr.get('Stage') == 'Delivered' for mr in e_data.values())  # it will be a singleton dict of MRs, but a  dict nonetheless
        case 'road transport job':
            return e_data.get('jobStatus') in ['Delivered', 'Cancelled']
        case 'shipment':
            return e_data.get('ShipmentStatus') == 'Completed'
        case 'transfer request':
            return e_data.get('Status') in ['Delivered', 'Rejected', 'Rescinded']
        case 'voyage':
            return e_data.get('status') == 'Complete'
        case 'work order':
            return set(e_data.get('total_status_counts', {}).keys()).issubset({'Delivered', 'Closed', 'Cancelled'})
        case _:
            logging.warning('A non-recognised entity type (%s) made its way down to the terminal state check.', e_type)
            return True  # i.e. DO close any subscriptions to bad entities


def track_subscription_events(event: str, sub_ids: list[str], subs_info: dict):
    """Shorthand for tracking a batch of subscription events of the same type, filling in fields from the given subs_info (e.g. active_subscriptions)."""
    track_events([dict(
                    event=event,
                    properties=dict(
                        organisation=subs_info[sub_id]['organisation'],
                        distinct_id=subs_info[sub_id]['createdByUserId'],
                        sub_id=sub_id,
                        entity_id=subs_info[sub_id]['entityId'],
                        entity_type=subs_info[sub_id]['entityType'],
                        created_time=subs_info[sub_id]['createdAtTimestamp']
                    )
                  ) for sub_id in sub_ids])


