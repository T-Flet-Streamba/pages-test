import threading
import requests
import base64
import time
from uuid import uuid4
from itertools import batched

import config


HEADERS = {
    'Authorization': 'Basic ' + base64.b64encode(f'{config.mixpanel.project_token}:'.encode()).decode()
}

def _send_to_mixpanel(events: list[dict]):
    """1s-timeout Mixpanel tracking request to put in a new thread.
    events has to contain dicts with keys 'event' (str) and 'properties' (dict).
    """
    try:
        requests.post('https://api.mixpanel.com/import', json=events, headers=HEADERS, timeout=1)
    except Exception:
        pass  # ignore all failures for fire-and-forget purposes

def _send_batched(events: list[dict], batch_size=50):
    """Sequential 1s-timeout Mixpanel tracking requests to put in a new thread.
    events has to contain dicts with keys 'event' (str) and 'properties' (dict),
    and properties should ideally contain a 'distinct_id' field so that Mixpanel has a user to attribute the event to.
    Events are batched into batches of 50 by default (the recommended amount for a batched Mixpanel request).
    """
    now = int(time.time())
    for e in events:  # fine without, but docs say required: https://developer.mixpanel.com/reference/import-events
        e['properties']['time'] = now
        e['properties']['$insert_id'] = uuid4().hex
        # if 'distinct_id' not in e['properties']:
        #     e['properties']['distinct_id'] = 'test@user.com'
    for batch in batched(events, batch_size):
        _send_to_mixpanel(list(batch))

def track_event(event_name, properties):
    """Fire-and-forget single-event Mixpanel tracking."""
    thread = threading.Thread(
        target=_send_batched,  # not using _send_to_mixpanel in order to not duplicate the extra field insertion
        args=[[dict(event=event_name, properties=properties)], 1],
        daemon=True
    )
    thread.start()

def track_events(events: list[dict], batch_size=50):
    """Fire-and-forget multi-event Mixpanel tracking.
    events has to contain dicts with keys 'event' (str) and 'properties' (dict),
    and properties should ideally contain a 'distinct_id' field so that Mixpanel has a user to attribute the event to.
    Events are batched into batches of 50 (the recommended amount for a batched Mixpanel request).
    """
    if not events: return
    assert all(set(x.keys()) == {'event', 'properties'} for x in events)

    thread = threading.Thread(
        target=_send_batched,
        args=[events, batch_size],
        daemon=True
    )
    thread.start()


# if __name__ == '__main__':
#     from datetime import datetime
#
#     def log(msg):
#         print(f'{datetime.now().isoformat(timespec='milliseconds')}  {msg}')
#
#     # Multiple single-events test
#     for i in range(5):
#         loop_start = time.perf_counter()
#         track_event('CollabGPT_test', dict(counter=i))#, distinct_id='test@user.com'))
#         log(f'Spawned background task {i}')
#         time.sleep(1)
#         loop_end = time.perf_counter()
#         log(f'Loop {i} duration: {loop_end - loop_start:.3f}s')
#     log('Multiple single-events test complete')
#
#     # Single multi-event test (multiple batches)
#     loop_start = time.perf_counter()
#     track_events([dict(event='CollabGPT_test_batched', properties=dict(counter=i, distinct_id='test@user.com')) for i in range(5)], batch_size=3)
#     time.sleep(1)
#     loop_end = time.perf_counter()
#     log(f'Loop duration: {loop_end - loop_start:.3f}s')
#     log('Single multi-event test complete')


