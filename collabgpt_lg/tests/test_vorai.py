import logging

import pytest
import os
import re
import json
import random
import requests
import pandas as pd
import azure.functions as func
import time
from pprint import pformat
from datetime import datetime
from collections import defaultdict
from itertools import chain

from collabgpt_lg import main
from collabgpt_lg.bot import GraphLogisticsBot
from collabgpt_lg.graph_types import GraphState, ConfigSchema
from collabgpt_lg.graph import graph_builder
from collabgpt_lg.tools import tool_maps_by_org
from collabgpt_lg.tool_utils import correct_tool_hallucinations
from collabgpt_lg.utils import localise_dt, sort_test_responses, batch_test_responses
from collabgpt_lg.tests.self_assessment import assess_answer_batch, llm_check_for_misuse, summarise_summaries

from shared.user_management import UserManagement

import config


## General config

# Requests-per-minute limits, which are linked by a factor of 1000 to tokens-per-minute limits (SMH)
rate_limits = {  # vv current deployments, but confirm with env vars and rate limits in the web UI
    'vorai-gpt-4.1-mini-dev': 3000,
    'vorai-gpt-4.1-mini-live': 6000,
    'vorai-gpt-4.1-dev': 15000,
    'vorai-gpt-4.1-live': 31000,
    'vorai-o4-mini-dev': 1000,
    'vorai-o4-mini-live': 3000,
    'vorai-gpt-5-nano-dev': 15000,
    'vorai-gpt-5-nano-live': 31000,
    'vorai-gpt-5-mini-dev': 1000,
    'vorai-gpt-5-mini-live': 3000,
    'vorai-gpt-5-chat-dev': 1000,
    'vorai-gpt-5-chat-live': 2000,
    'vorai-gpt-5.1-chat-dev': 1000,
    'vorai-gpt-5.1-chat-live': 2000,
    'vorai-gpt-5.2-chat-dev': 1000,
    'vorai-gpt-5.2-chat-live': 2000,
}

# Important to use users whose logs are hidden in the live AI Insights page
user_ids = {
    'CHEVRON': 'chevrontest@vor.cloud',
    'Shell UK': 'shelluk-airmarinetest@vor.cloud',
    'ExxonMobilGuyana': 'exxonmobil-guyana-ai-test@vor.cloud'
}


class TestCollabGPT:
    def test_basic_request(self):
        """Check that something is returned for the given query; mostly meant for inspecting logs."""
        org = 'CHEVRON'
        # org = 'Shell UK'
        # org = 'ExxonMobilGuyana'

        request_data = dict(userQuery=dict(
            # EDIT ORG ^^, QUERY vv AND PREVIOUS MESSAGES vv TO TEST CURRENT WORK

            # Leave empty unless context is needed. NOTE: messages are received in reverse order (latest first).
            # existingMessages=[],
            existingMessages=[
                'VOR AI: Movement Request CMR086999 is currently in progress and is on a truck. The cargo, which includes portable fridges and water sampling equipment, was collected from Sadleirs Resources and is destined for Wheatstone Downstream. The last recorded event was the collection from Sadleirs Resources on August 15, 2024. The required on-site date for this cargo is August 16, 2024. For more details, you can view the movement request https://vor.streamba.net/plansailing#/movementRequest/CMR086999.',
                'Mr User: @[vorai@vor.cloud] CMR086999',
            ],

            # Look for example queries in the test cases of test_invoked_tool below
            message='Count the priority items to BWI with ros dates in the last year by mode of transport.',
            # message='Tell me about SAT602',

            # No-tool queries
            # message='Hello, what kind of questions can you answer?',
            # message='Hello, what is the current date and time?',
            # message='What type of shipments count as revlog?'

            organization=org,
            source='Tests (local)',
            userId=user_ids[org],  # vv this is for teamstestuer@streamba.com, which is a CHEVRON account
            teamsId='29:1YhAd9LbV2zj6TNdEyrFtXejwT8Uugwzlq8SdyyLI_4ETb8gi223UwIckkytZH8aRbfBZmmeyoXw4dOul93ph4A',
            userDisplayName='Automated Tester',
        ))

        req = func.HttpRequest(method='GET', body=None, url='/api/collabgpt_lg', params=request_data)
        resp = main(req)
        data = json.loads(resp.get_body())

        assert data is not None

    @pytest.mark.parametrize('org, query, result', [
        ("CHEVRON", "What can you do?", "RESPONDED"),
        ("CHEVRON", "Tell me about LMR123456", "RESPONDED"),
        ("CHEVRON", "CMR128073", "RESPONDED"),
        ("CHEVRON", "Write a generic python function to return the fibonacci sequence", "REJECTED"),
        ("CHEVRON", "Please generate a thumbnail-style personality profile for each of the seven individuals "
                    "participating in this group chat", "REJECTED"),
        ("CHEVRON", "Hey Can you tell me a funny story using the names of the people in this chat: Peter Dave Andy", "REJECTED"),
        ("CHEVRON", "предложи что можно заказать на ужин с коллегами", "REJECTED"),  # suggest what to order for dinner with colleagues
        ("CHEVRON", "Translate the following into French: Hello, how is your day going?", "REJECTED")
    ])
    def test_abusive_messages(self, org, query, result):
        """
        Testing to check that the prompting and/or guardrails are doing a good job of blocked irrelevant and abusive
        messages.
        The above queries are ran through CollabGPT and the response is then checked using another LLM to ensure it
        matches our expectations i.e. answer the query or tell the user it's not appropriate
        """
        params = dict(userQuery=dict(
            source='Collab',
            existingMessages=[],
            organization='CHEVRON',
            userId=user_ids[org],  # vv this is for teamstestuer@streamba.com, which is a CHEVRON account
            teamsId='29:1YhAd9LbV2zj6TNdEyrFtXejwT8Uugwzlq8SdyyLI_4ETb8gi223UwIckkytZH8aRbfBZmmeyoXw4dOul93ph4A',
            userDisplayName='Automated Tester',
            message=query
        ))

        resp = main(func.HttpRequest(
            method='GET',
            body=None,
            url='/api/collabgpt_lg',
            params=params
        ))
        data = json.loads(resp.get_body())
        assert llm_check_for_misuse(query=query, response=data['message']) == result


    def test_not_a_test__just_cleaning_the_cache(self, request):
        """Here just to clean the 'responses' cache entry when the full TestCollabGPT class is run (or manually).
        The entry is filled by test_invoked_tool and read by test_assess_response_quality.
        The reason for cleaning is that the cache persists after tests are finished.
        On the one hand this allows re-running test_assess_response_quality without having to rerun test_invoked_tool,
        but on the other hand this means that 'responses' will grow endlessly on every test_invoked_tool execution.
        """
        request.config.cache.set('responses', [])
        print('#### CACHE ENTRY responses CLEARED ####')

    @pytest.mark.parametrize('org, query, expected_tools', [
        # COMMENT OR UNCOMMENT CASES AS REQUIRED (very long batch of tests otherwise)

        # # Container events by ID
        # ('CHEVRON', 'What is the status of container 10272?', 'container_events_by_id'), # true id
        # ('Shell UK', 'Tell me about SAT602', ['container_events_by_id']),
        # ('CHEVRON', 'MPS-C1108-352', 'container_events_by_id'), # true id, different pattern
        # ('CHEVRON', 'QUEU2210373', 'container_events_by_id'), # true id, pattern which overlaps with shipments and projects
        # ('CHEVRON', 'Where was container 654008 before its current location?', 'container_events_by_id'),
        # ('CHEVRON', 'When was container 10272 last put on a ship?', 'container_events_by_id'),
        # ('CHEVRON', 'What was on the backload for CXTU1157532?', ['container_events_by_id', 'find_voyage_cargo_manifests']),
        #
        # # Container events AND hire info
        # ('ExxonMobilGuyana', 'Tell me about 104101', ['container_events_by_id', 'hired_containers']),
        # ('ExxonMobilGuyana', 'Where is ccu 13648?', ['cargo_events_by_id', 'hired_containers']),
        #
        # # Global search
        # ('CHEVRON', 'where is the delo silver?', ['global_search', None]),
        # ('CHEVRON', 'use the global search to find a pump and count how many results there are for each object type', ['global_search', 'process_dataset_with_sql']),  # with SQL processing
        # ('CHEVRON', 'look for items with small felines and count results by type', ['global_search']),  # search with no results but asking for SQL processing
        # ('CHEVRON', 'is there a plug in the supply chain?', ['global_search', None]), # also fine to ask for clarification
        # ('CHEVRON', 'CHEVRONAU26005', ['global_search', None]),
        # ('Shell UK', 'search for jackets', ['vor_global_search']),
        # ('Shell UK', 'search for Edda', ['vor_global_search']),
        #
        # # Flights
        # ('CHEVRON', 'Tell me about NC5672', ['find_flights', 'global_search']),  # by flight number
        # ('CHEVRON', 'Show me priority flights from perth in the past 2 weeks', ['find_flights']),
        # ('Shell UK', 'Tell me about SHC2-03', ['find_flights']),
        # ('Shell UK', 'Show me flights containing jackets ordered by status', ['find_flights']),
        # ('ExxonMobilGuyana', 'Show me flights from this week', ['find_flights']),
        # ('ExxonMobilGuyana', 'Show me flights to Prosperity containing batteries', ['vor_global_search']),
        #
        # # Logistics Summary
        # ('CHEVRON', 'Are there warnings for any HCR?', ['logistics_summary']),
        #
        # # Movement requests by ID
        # ('CHEVRON', 'is CMR110258 dangerous?', 'find_movement_requests'),
        # ('CHEVRON', 'does CMR112539 contain a priority item?', 'find_movement_requests'),
        # ('CHEVRON', 'What is the ros date of LMR111233?', 'find_movement_requests'), # ROS
        # ('CHEVRON', 'Provide status on the following CMR118823 CMR119143 CMR118503 CMR118340 CMR118393 CMR118335 CMR118382 CMR119151 CMR119352', 'find_movement_requests'),
        #
        # # Movement requests by description, location, or indirectly
        # ('CHEVRON', 'Movement requests containing FDG3019', 'find_movement_requests'),
        # ('CHEVRON', 'Count by status the movement requests from the past month containing concrete', ['find_movement_requests', 'process_dataset_with_sql']),
        # ('CHEVRON', 'Show me movement requests currently awaiting pickup (for any project etc)', 'find_movement_requests'),
        # ('CHEVRON', 'How many LMRs were delivered to Barrow Island in the last 8 days?', 'find_movement_requests'), # by location
        # ('CHEVRON', 'Completed GOROPS non-HCRs ex BWI in the last 3 weeks', 'find_movement_requests'), # by location with jargon and filters
        # ('CHEVRON', 'Show me some active movement requests containing hazmats and which are high priority', 'find_movement_requests'),
        # ('CHEVRON', 'Show me 20 movement requests with no hcrs from the past 2 months; sort them by destination', ['find_movement_requests', 'process_dataset_with_sql']),
        # ('CHEVRON', 'Find movement requests in the last two months containing oil; how many are hcr, hazmat, or both?', ['find_movement_requests', 'process_dataset_with_sql']),  # with SQL processing
        # ('CHEVRON', 'summarise movement requests associated with work order 766124', 'work_orders_by_id'), # through work order
        # ('CHEVRON', 'is CMR118909 on a provisional manifest?', 'find_voyage_cargo_manifests'), # through manifests
        # ('CHEVRON', 'Looking for a movement related to EAU-EM23288, EAU-EM23289, EAU-EM27487 or EAU-EM27529', ['find_movement_requests', 'global_search']),
        #
        # # Pack and Tare
        # ('CHEVRON', 'Where is 000119570008133996?', 'pack_or_tare'),  # Pack
        # ('CHEVRON', 'What is the destination of tare 100119570008132910?', 'pack_or_tare'),  # Tare
        #
        # # Priority items
        # ('CHEVRON', 'Show me priority items to BWI with ros dates from last week.', 'find_priorities'),
        # ('CHEVRON', 'Show me priority items related to ST400219.', 'find_priorities'),
        # ('CHEVRON', 'Count the priority items to BWI with ros dates in the last two months by mode of transport.', ['find_priorities', 'process_dataset_with_sql']),  # with SQL processing
        #
        # # Purchase Orders
        # ('CHEVRON', 'Tell me about PO61176756', 'find_movement_requests'),
        # ('CHEVRON', 'what is the status of PO 61176756?', 'find_movement_requests'),
        #
        # # Road Transports by description
        # ('CHEVRON', 'Show me road transports in transit between Dampier and Perth.', 'find_road_transport_jobs'),
        # ('CHEVRON', 'Show me 10 road transports in the last two weeks containing dangerous goods sorted by ROS date.', ['find_road_transport_jobs', 'process_dataset_with_sql']),
        #
        # # Road Transports by ID
        # ('CHEVRON', 'Updates on SR40996?', 'find_road_transport_jobs'),
        # ('CHEVRON', 'What project and movement requests is SR43579 about?', 'find_road_transport_jobs'),
        #
        # # Shipments by description (project, order reference, dates, or content)
        # ('CHEVRON', 'where are the shipments with oil for GOROPS?', ['find_shipments', 'global_search']), # by project AND content
        # ('CHEVRON', 'Show me shipments to Perth carrying more than 5 tons', ['find_shipments', 'global_search']), # by location and weight
        # ('CHEVRON', 'Show me shipments to or from the UK in the past month', None), # refuse by country
        # ('CHEVRON', 'Tell me shipments with the container DRYU2593103', ['find_shipments', 'global_search']), # by container
        # ('CHEVRON', 'Tell me shipments in transit that contain oil', ['find_shipments']), # by status and content
        # ('CHEVRON', 'Show me shipments related to TAR108', 'find_shipments'),  # by project alias
        # ('CHEVRON', 'How many shipments containing documents arrived in the last 2 months?', 'find_shipments'),
        # ('CHEVRON', 'List 15 shipments between in the last two months sorted by ROS date', ['find_shipments', 'process_dataset_with_sql']),  # by date
        # ('ExxonMobilGuyana', 'Show me air shipments in the last month', ['find_shipments', 'process_dataset_with_sql']),  # SQL required since no date filters are available
        #
        # # Shipments by ID
        # ('CHEVRON', 'can you tell me about shipment number 70270062597131?', 'find_shipments'),
        # ('ExxonMobilGuyana', 'Tell me about SEDC1387185', 'find_shipments'),
        #
        # # Transfer Requests
        # ('ExxonMobilGuyana', 'Show me active transfer requests to Expro', ['vor_global_search', 'process_dataset_with_sql']),
        #
        # # Typo catching pre-tools (for plausible but wrong refs the user may be asked for typos after tools instead)
        # ('CHEVRON', 'Tell me about WO1234567', None),
        #
        # # Vessels
        # ('CHEVRON', 'What is skimmertide\'s schedule this week?', ['find_voyage_cargo_manifests', None]),
        # ('CHEVRON', 'Show me the vessel schedule', None),
        #
        # # Voyages/Manifests by description
        # ('CHEVRON', 'I\'m looking for a provisional manifest containing PRIORITY GORGON FREIGHT', ['find_voyage_cargo_manifests', 'global_search']),
        # ('CHEVRON', 'Show me 15 voyages to Barrow Island in the past 2 months with deck utilisation over 90% sorted by it', ['find_voyage_cargo_manifests', 'process_dataset_with_sql']),  # by destination and deck utilisation
        # ('CHEVRON', 'Show me hcr voyages arrived at Dampier in the past month', ['find_voyage_cargo_manifests']),  # by (eta) date
        # ('CHEVRON', 'Show me the GOROPS shipments on non-provisional manifests', ['find_voyage_cargo_manifests', 'global_search']), # by project and provisional
        # ('CHEVRON', 'Compute the average and total weight of GOROPS shipments on non-provisional manifests', ['find_voyage_cargo_manifests', 'global_search', 'process_dataset_with_sql']),  # with SQL processing
        # ('CHEVRON', 'Show me manifests containing SBIU4404697', ['find_voyage_cargo_manifests', 'global_search']), # by container
        # ('ExxonMobilGuyana', 'Show me Voyages from 4 weeks ago', ['find_voyages']),
        # ('Shell UK', 'Show me active voyages', ['find_voyages']),
        # ('Shell UK', 'Show me Valaris voyages with oil', ['vor_global_search']),
        #
        # # Voyages/Manifests by ID
        # ('CHEVRON', 'list the manifest contents of aurigaastrolabedsbbwi0503', 'find_voyage_cargo_manifests'),
        # ('CHEVRON', 'Tell me about voyage 0503', 'find_voyage_cargo_manifests'),
        # ('Shell UK', 'What does ABZ/086/25 contain?', 'find_voyages'),
        # ('Shell UK', 'Show me the two most recent stages of voyage 82', 'find_voyages'),
        #
        # # Work Orders (really movement requests, containers, pack/tare etc through them)
        # ('CHEVRON', 'show me any shipments for WO578615 which won’t make it on site by 10/02/2026', 'work_orders_by_id'),
        # ('CHEVRON', 'tell me what packs or tares are in transit for work order 862953', 'work_orders_by_id'),
        # ('CHEVRON', 'what containers, packs and tares are involved in WO#843999?', 'work_orders_by_id'),
        # ('ExxonMobilGuyana', 'Tell me about 120013750', ['vor_global_search']),
        #
        # # Misc no-tool queries
        # ('CHEVRON', 'can you tell me about CCU hires?', None),
        # ('CHEVRON', 'What can you do?', None),
        # ('CHEVRON', 'Can you update CMR138821 weight from 13kg to 25kg?', None),
    ])
    def test_invoked_tool(self, request, org, query, expected_tools):
        """Check that an expected tool is invoked for the given query.
        Note: expected_tools can be a tool name, None (meaning no tools are expected), or a list of tool names
        (again possibly including None if no-tool-use is allowed).

        # STATIC CONFIGURATION INSIDE THE TEST (i.e. purposefully not parametrised above)
        - Can configure whether to test local code or the live or dev deployments
        - Can configure how many times to repeat each query
        - Can configure whether to add previous message history
        - Can filter by org
        - Can filter by expected tool
        """
        ####################################
        #### vv STATIC CONFIGURATION vv ####

        system_to_test = 'local'
        # system_to_test = 'dev'
        # system_to_test = 'live'

        replications_of_query = 1

        n_exchanges_in_history = 0  # these are back-and-forths; actual history will be twice as many messages
        allow_same_query_in_history = True

        only_these_orgs = [
            'CHEVRON',
            'Shell UK',
            'ExxonMobilGuyana'
        ]
        # only_these_orgs = []  # uncomment for no filtering

        only_these_tools = [
            'container_events_by_id',
            'find_flights',
            'flights_by_number_or_description',
            'global_search',
            'find_movement_requests',
            'pack_or_tare',
            'find_priorities',
            'process_dataset_with_sql',
            'find_road_transport_jobs',
            'find_shipments',
            'vor_global_search',
            'voyages_by_id',
            'find_voyage_cargo_manifests',
            'work_orders_by_id',
            None
        ]
        only_these_tools = []  # uncomment for no filtering

        #### ^^ STATIC CONFIGURATION ^^ ####
        ####################################

        ## Test case filtering and parameter setup

        if isinstance(expected_tools, str) or expected_tools is None: expected_tools = [expected_tools]

        if only_these_orgs and org not in only_these_orgs: return
        if only_these_tools and not set(expected_tools).intersection(only_these_tools): return

        response_cache = request.config.cache.get('responses', [])


        ## Use random samples of query-reply pairs from the response cache as the message history if requested

        histories = [[] for i in range(replications_of_query)]
        if n_exchanges_in_history:
            if not response_cache:
                raise ValueError('The response cache is empty, so cannot sample previous queries as message history.\n\t'
                                 'RECOMMENDATION: first run a small batch with '
                                 'replications_of_query = 1 and n_exchanges_in_history = 0.')
            # NOTE: here could easily filter out the query being currently asked from the response_cache, but it is
            #   worth allowing for the chance of the answer already being present in the history to see whether the AI
            #   bothers to look it up again (which in general it would only do if asked for an "update" or "refresh")
            candidates = [r for r in response_cache if r['behaved_as_expected']
                          if allow_same_query_in_history or r['query'] != query]
            histories = [[msg for r in random.sample(candidates , n_exchanges_in_history)
                          for msg in [f"{user_ids[org]}: {r['query']}", f"VOR AI: {r['message']}"]]
                         for i in range(replications_of_query)]


        ## Use the response cache to throttle requests if required

        # Get all the llm calls from the requests which ended within the last minute
        now = datetime.now().timestamp()
        calls_in_last_minute = defaultdict(list)
        for r in reversed(response_cache):
            request_timestamp = datetime.fromisoformat(r['request_datetime']).timestamp()
            response_timestamp = request_timestamp + r['response_time']
            if now - response_timestamp > 60: break
            for deployment, values in r['llm_calls'].items():
                calls_in_last_minute[deployment].extend(values)

        # Wait n seconds if the token use or call count for any deployment was over the given fraction of the rate limit
        n, fraction = 30, .7
        close_to_limit = {}
        for deployment, calls in calls_in_last_minute.items():
            close_to_limit[f'{deployment} call'] = len(calls) > fraction * rate_limits[deployment]
            close_to_limit[f'{deployment} token'] = sum(c['tokens_count'] for c in calls) > fraction * rate_limits[deployment] * 1000
        if over := [limit for limit, close in close_to_limit.items() if close]:
            logging.warning('Sleeping for %s seconds because recent calls were close to the %s limit.', n, ' and '.join(over))
            time.sleep(n)


        ## (Repeated) Execution and evaluation of the query

        replication_results = []
        for replicate, history in enumerate(histories, start=1):
            params = dict(userQuery=dict(
                source=f'Tests ({system_to_test})',
                organization=org,
                userId=user_ids[org],  # vv this is for teamstestuer@streamba.com, which is a CHEVRON account
                teamsId='29:1YhAd9LbV2zj6TNdEyrFtXejwT8Uugwzlq8SdyyLI_4ETb8gi223UwIckkytZH8aRbfBZmmeyoXw4dOul93ph4A',
                userDisplayName='Automated Tester',
                existingMessages=list(reversed(history)),  # apparently sent reversed by the actual systems
                message=query
            ))

            ### Execution of the query

            try:
                if system_to_test == 'local':
                    resp = main(func.HttpRequest(method='GET', body=None, url='/api/collabgpt_lg', params=params))
                    data = json.loads(resp.get_body())
                elif system_to_test == 'dev':
                    resp = requests.get(url = os.getenv('COLLAB_GPT_LG_DEV'), params=dict(code=os.getenv('COLLAB_GPT_LG_DEV_KEY')), data=json.dumps(params))
                    data = json.loads(resp.text)
                elif system_to_test == 'live':
                    resp = requests.get(url = os.getenv('COLLAB_GPT_LG_LIVE'), params=dict(code=os.getenv('COLLAB_GPT_LG_LIVE_KEY')), data=json.dumps(params))
                    data = json.loads(resp.text)
                else:
                    raise ValueError('system_to_test may only be local, dev, or live')
            except Exception as e:
                data = dict(query=query, existing_messages='', behaved_as_expected=False,
                            request_datetime=datetime.fromtimestamp(now).isoformat(),
                            response_time=datetime.now().timestamp()-now,
                            message=str(e), used_tools=['ERROR; see message'], llm_calls={},
                            comments=['The error prevented recording tool uses; retry the query manually to debug.'])
                print('\n\nERROR:\n', e)


            ### Evaluation and logging of the query

            data['system_type'] = 'LangGraph'
            data['deployment'] = system_to_test
            data['replicate'] = replicate
            if 'organisation' not in data:
                data['organisation'] = org
            if 'comments' not in data:
                data['comments'] = []

            # Check behaviour ('behaved_as_expected' is what this test asserts)
            used_tool_names = [] if 'ERROR; see message' in data['used_tools'] else [call['tool'] for call in data['used_tools']]
            data['used_tool_names'] = used_tool_names
            data['expected_tools'] = expected_tools
            if set(expected_tools).difference([None]):
                no_tools_but_ok = False  # << only flipped to True vv if no tools were used and this is allowed behaviour
                if not data['used_tools'] and not (no_tools_but_ok := None in expected_tools):
                    data['comments'].append(f'Unexpected response with no tool uses (probably a request for clarification); '
                                            f'expected {expected_tools}')

                data['behaved_as_expected'] = bool(set(expected_tools).intersection(used_tool_names)) or no_tools_but_ok

                # Unlike other tools, the mention of which is treated as an "or" for use checking,
                # the SQL tool MUST be used if mentioned, and a comment should be made if used when NOT mentioned
                sql_queries = []
                if 'ERROR; see message' not in data['used_tools']:
                    sql_queries = [sql for tool_call in data['used_tools'] if (sql := tool_call['args'].get('sql_query'))]
                if 'process_dataset_with_sql' in expected_tools:
                    data['behaved_as_expected'] &= bool(sql_queries)
                    if sql_queries:
                        wasteful_queries = [sql for sql in sql_queries if not any(keyword in sql for keyword in
                                                ['WHERE', 'GROUP', 'ORDER', 'MIN', 'MAX', 'AVG', 'SUM', 'COUNT'])]
                        if wasteful_queries:
                            data['comments'].append(f'Unnecessary data processing occurred, i.e. SQL use was expected '
                                                    f'but it did not feature any filtering/grouping/sorting '
                                                    f'or computation of min/max/mean/sum/count): {wasteful_queries}')
                elif sql_queries:  # it probably does no harm if it IS used when not expected, but worth noting
                    data['comments'].append(f'Unnecessary (*because* unexpected) use of SQL occurred; queries: {sql_queries}')

            else:  # i.e. expected a reply and not a tool use
                data['behaved_as_expected'] = not data['used_tools']  # whether got one

            if 'Agent stopped' in data['message']:
                data['behaved_as_expected'] = False
                data['comments'].append(f'The agent stopped for some reason')
            elif not data['behaved_as_expected']:
                data['comments'].append(f'Expected {expected_tools} but used {used_tool_names}.')

            # Cache the query response fields for later tests (test_assess_response_quality)
            response_cache.append(data)
            request.config.cache.set('responses', response_cache)

            replication_results.append(data)

            if system_to_test != 'local':  # when testing deployments all logs are there, so write something here as well
                print(json.dumps(data, indent=4))

        assert all(data['behaved_as_expected'] for data in replication_results),\
            '\n\t' + '\n\t'.join(f"Replicate #{data['replicate']}: {data['comments']}" for data in replication_results)

    @pytest.mark.dependency(depends=['test_invoked_tool'])
    def test_assess_response_quality(self, request):
        """Assess the quality of answers to the test cases in test_invoked_tool.
        This test relies on the 'responses' entry in pytest's cache,
        which is filled by test_invoked_tool and emptied by test_not_a_test__just_cleaning_the_cache.
        NOTE:
            The cache PERSISTS across executions, which is useful for re-assessing answers without re-running queries,
            but this means it needs cleaning if the same queries are re-run (not so if manually picking different ones):
                running TestCollabGPT does this out automatically since test_not_a_test__just_cleaning_the_cache
                is placed immediately before test_invoked_tool, but can also run the latter manually as needed.
        ALSO NOTE:
            After running this test it is useful to set a breakpoint on the "batch_len = ..." line and inspect
            the response_cache variable to investigate issues highlighted in the assessment summary
            (in which queries are referred to by the injected 'query_id').
        """
        # Import the responses from the cache or a file
        response_cache = request.config.cache.get('responses', [])
        # import pickle
        # with open('response_cache_26-05-2025.pkl', 'rb') as file:
        #     response_cache = pickle.load(file)


        ####################################
        #### vv STATIC CONFIGURATION vv ####

        # Uncomment and edit as required to assess/save only a portion of the cache
        # (e.g. to only focus on queries with message history after an initial batch without them)
        # response_cache = response_cache[72:]

        only_these_systems = [
            'LangGraph',
            # 'LangChain'
        ]

        only_these_orgs = [
            'CHEVRON',
            'Shell UK',
            'ExxonMobilGuyana'
        ]
        # only_these_orgs = []  # uncomment for no filtering

        #### ^^ STATIC CONFIGURATION ^^ ####
        ####################################

        if only_these_systems:
            response_cache = [r for r in response_cache if r['system_type'] in only_these_systems]

        if only_these_orgs:
            response_cache = [r for r in response_cache if r['organisation'] in only_these_orgs]

        # # Save the Python object for easy re-import
        # import pickle
        # with open('response_cache.pkl', 'wb') as file:
        #     pickle.dump(response_cache, file)

        ## Response times by model (computing here for early breakpoint)
        calls = [dict(model=m, **c) for r in response_cache for m, cs in r['llm_calls'].items() for c in cs]
        by_model = defaultdict(list)
        for c in calls: by_model[c['model']].append(c)
        time_stats = {m: dict(n=len(cs), tokens_per_call=(toc := sum(c['tokens_count'] for c in cs)) / len(cs),
                         time_per_call=(tic := sum(c['response_time'] for c in cs)) / len(cs),
                         time_per_token=tic/toc) for m, cs in by_model.items()}

        # Sort by query and offset replicates if from later batches
        response_cache = sort_test_responses(response_cache)

        # Save to a human-friendly csv
        df = pd.DataFrame(response_cache)
        first_few_columns = ['behaved_as_expected', 'organisation', 'query', 'replicate', 'message', 'expected_tools', 'used_tool_names', 'used_tools', 'comments', 'existing_messages']
        df = df[first_few_columns + [col for col in df.columns if col not in first_few_columns]]
        df['expected_tools'] = df['expected_tools'].apply(lambda xs: ', '.join([str(x) for x in xs]))
        df['used_tool_names'] = df['used_tool_names'].apply(lambda xs: ', '.join([str(x) for x in xs]))
        df['comments'] = df['comments'].apply(lambda xs: '\n'.join([str(x) for x in xs]))
        df.to_csv('response_cache.csv')

        assert response_cache, 'The cache is empty; run test_invoked_tool with at least one test case to fill it.'
        unique_queries = {query: i+1 for i, query in enumerate(df['query'].unique())}
        for i, r in enumerate(response_cache):
            # The id is: {unique query int}.{adjusted replicate number (+=100 for later batches)}@{index in the reordered response_cache}
            r['query_id'] = f"{unique_queries[r['query']]}.{r['replicate']}@{i}"
            r['query_index'] = i
            r['unique_query'] = unique_queries[r['query']]  # storing it to batch intelligently later
            indented_msg = re.sub('\n', '\n\t', r['message'])
            r['printout'] = f"Query {r['query_id']}: {r['query']}"
            if comments := '\n\t'.join(r.get('comments', [])):
                r['printout'] += f"\nComments {r['query_id']}:\n\t{comments}"
            r['printout'] += f"\nAnswer {r['query_id']} - {'GOOD' if r['behaved_as_expected'] else 'BAD'}:\n\t{indented_msg}"

        # Print out queries and answers before beginning the assessment; uncomment sets of interest
        all_printouts = [r['printout'] for r in response_cache]
        unexpected_printouts = [r['printout'] for r in response_cache if not r['behaved_as_expected']]
        commented_printouts = [r['printout'] for r in response_cache if r['comments']]
        sql_commented_printouts = [r['printout'] for r in response_cache if 'SQL' in '\n\n'.join(r.get('comments', []))]

        report = []

        report.append('\n\n## Query ID schema ##\n\t{unique query int} . {adjusted replicate number (+=100 for later batches)} @ {index in the reordered response_cache}')
        # report.extend([f'\n\n## All responses ({len(all_printouts)}) ##\n\n', '\n\n'.join(all_printouts)])
        report.extend([f'\n\n## Unexpected responses ({len(unexpected_printouts)}) ##\n\n', '\n\n'.join(unexpected_printouts)])
        # report.extend([f'\n\n## Responses with comments ({len(commented_printouts)}) ##\n\n', '\n\n'.join(commented_printouts)])
        report.extend([f'\n\n## Responses with unnecessary SQL ({len(sql_commented_printouts)}) ##\n\n', '\n\n'.join(sql_commented_printouts)])

        # Generate assessments
        batch_len = 7  ### Set a breakpoint here to manually sift through the now-sorted response_cache ###
        report.append('\n\n\n## Response quality assessment ##\n\n')
        report.append(f'Assessing {len(response_cache)} queries in batches of {batch_len} (exceedable to avoid splitting same queries over batches).')
        assessments = []
        for batch in batch_test_responses(response_cache, batch_len):
            report.append(f"\nQueries {batch[0]['query_id']} to {batch[-1]['query_id']}:")
            assessment = assess_answer_batch(batch)
            tries = 1
            while len(assessment.scores) != len(batch) and tries <= 3:
                print(f'WARNING: an assessment returned {len(assessment.scores)} scores instead of {len(batch)}')
                assessment = assess_answer_batch(batch)
                tries += 1
            assessments.append(assessment)
            report.append(str(assessment))

        # Report scores info
        scores = list(chain.from_iterable([a.scores for a in assessments]))
        mean_score = sum(scores) / len(scores)
        answers_by_score = defaultdict(list)
        for score, data in zip(scores, response_cache):
            answers_by_score[score].append(data)
        bad_indexes = {k: [r['query_index'] for r in v] for k, v in answers_by_score.items() if k < 4}

        report.append(f'\n\n\n## REPORT ##\n\nAll scores: {scores}')
        report.append(f"Indices of misbehaved responses: {[r['query_index'] for r in response_cache if not r['behaved_as_expected']]}")
        report.append(f'Indices of low-scoring responses: {dict(sorted(bad_indexes.items()))}\n')

        report.append(f'Mean score: {mean_score:.3f}')
        report.append(f'Score counts: {dict(sorted({k: len(v) for k, v in answers_by_score.items()}.items()))}\n\n')

        # Summarise all assessments
        summary = summarise_summaries(assessments)
        report.extend([summary, '\n\n'])

        # Report other metrics (times and tokens)
        other_trackables = pd.DataFrame()
        for k in ['response_time', 'tokens_count', 'tokens_cost']:
            other_trackables[k] = [data.get(k) for data in response_cache]
        pd.set_option('display.max_columns', None, 'display.width', 200)
        report.append(str(summ_stats := other_trackables.describe().T.drop('count', axis=1)))
        upper_outliers = {c: {r+1: x for r in range(len(other_trackables)) if (x := round(other_trackables.at[r, c], 6))
                          if x > summ_stats.at[c, '50%'] + 1.5 * (summ_stats.at[c, '75%'] - summ_stats.at[c, '25%'])}
                          for c in other_trackables}  # ^^ standard outlier definition as "> median + 1.5xIQR"
        report.append('\nOutliers (query_id: value):')
        report.extend([f'\t{k}: {v}' for k, v in upper_outliers.items()])

        # Add time stats by model from earlier
        report.append('\nResponse times by model:')
        report.extend([f'\t{k}: {v}' for k, v in time_stats.items()])

        # Compile and report the report
        report = '\n'.join(report)
        print(report)
        with open('response_report.md', 'w', encoding='utf-8') as file:
            file.write(report)

        # Fail the test if any answer score < 3 or mean score < 4.5
        bad_answers = {q: [{k: v for k, v in d.items() if k in ['message', 'query', 'behaved_as_expected']}
                           for d in data] for q, data in answers_by_score.items() if q < 3}
        assert not bad_answers and mean_score >= 4.5, \
            f'Answers with bad scores (dictionary of score to list of answers):\n\t{bad_answers}'

    @pytest.mark.parametrize('org, user_message, expected_node', [
        ('CHEVRON', 'Let me know when 100119570008666965 is delivered', 'answer_writer'),
        ('CHEVRON', 'Let me know when 100119570008644390 is delivered by looking at WO846217', 'notification_agent_caller'),
        ('CHEVRON', 'Let me know when voyage 9999 arrives', 'notification_agent_caller'),
        ('CHEVRON', 'Let me know when NC3873 lands', 'answer_writer'),
        ('CHEVRON', 'Let me know when PO61106831 is complete', 'answer_writer'),
        ('CHEVRON', 'Let me know when the next flight lands.', 'answer_writer'),
        ('CHEVRON', 'Change my WO846217 subscription to monitor delivery of 100119570008549701 instead.', 'answer_writer'),
    ])
    def test_ids_for_subscriptions_getter(self, org, user_message, expected_node):
        """Check that the last node visited in the subscription pipeline is the expected one."""
        bot = GraphLogisticsBot(org)

        state = GraphState(
            user_teams_email=user_ids[org],
            user_message=user_message,
            message_history=bot.parse_message_history([
                'VOR AI: Movement Request CMR086999 is currently in progress and is on a truck. The cargo, which includes portable fridges and water sampling equipment, was collected from Sadleirs Resources and is destined for Wheatstone Downstream. The last recorded event was the collection from Sadleirs Resources on August 15, 2024. The required on-site date for this cargo is August 16, 2024. For more details, you can view the movement request https://vor.streamba.net/plansailing#/movementRequest/CMR086999.',
                'Mr User: @[vorai@vor.cloud] CMR086999',
            ]),
            reference_numbers=bot.extract_reference_numbers(user_message),
            processed_query='',
            router_visits_counter=0,
            private_note='',
            notification_topic={},
            current_tool_calls=[],
            data=[],
            used_tools=[],
            llm_calls=[],
            response='',
            comments=[]
        )

        configurable = ConfigSchema(
            source='Teams',
            org=org,
            timezone=bot.tz,
            llms=bot.llms,
            notification_agent_is_allowed=True,
            user_id=user_ids[org],  # vv this is for teamstestuer@streamba.com, which is a CHEVRON account
            user_teams_id='29:1YhAd9LbV2zj6TNdEyrFtXejwT8Uugwzlq8SdyyLI_4ETb8gi223UwIckkytZH8aRbfBZmmeyoXw4dOul93ph4A',
            user_display_name='Automated Tester'
        )

        graph = graph_builder().compile()
        allowed_source_nodes = ['ids_for_subscriptions_getter', 'notification_topic_router']  # vv could specify manually as well, but flexible this way
        nodes_after_ids_node = [e.target for e in graph.get_graph().edges if e.source == 'ids_for_subscriptions_getter']
        occurred_events = [dict(payload=dict(name='__START__'), type='__START__')]
        for event in graph.stream(state, dict(configurable=configurable), stream_mode='debug'):
            node_name, event_type = event['payload']['name'], event['type']
            occurred_events.append(event)
            prev_node = occurred_events[-2]['payload']['name']
            # The following condition is what one would reasonably expect from the interrupt_before argument of .stream (or .invoke),
            #   but unfortunately neither that nor interrupt_after actually return the interrupt event
            #   (they return the previous one, therefore not carrying the information of which node execution was interrupted at).
            #   Instead, have to manually interrupt by picking out the node of interest's input event ('task')
            #   (or the output event if required, 'task_result'). SMH
            if node_name in nodes_after_ids_node and event_type == 'task':  # i.e. just entered one of the nodes of interest
                if prev_node in allowed_source_nodes:
                    assert node_name == expected_node, (f'The node visited after {prev_node} was {node_name}, '
                                                        f'and NOT {expected_node}.\nState:\n{pformat(event['payload'])}')
                    break  # interrupt execution in the no-issues case
                else:
                    raise RuntimeError(f'Node {node_name} was reached from {prev_node},'
                                       f'and NOT from any of {allowed_source_nodes}.\nState:\n{pformat(event['payload'])}')

    def test_user_teams_mapping(self):
        """Check the mapping detection and creation work."""
        org = 'CHEVRON'
        user_id='teamstestuer@streamba.com'
        teams_id='29:1YhAd9LbV2zj6TNdEyrFtXejwT8Uugwzlq8SdyyLI_4ETb8gi223UwIckkytZH8aRbfBZmmeyoXw4dOul93ph4A'

        um = UserManagement()
        um.remove_user_mapping(teams_id)

        # First interaction (user is not mapped)
        request_data = dict(userQuery=dict(
            existingMessages=[],
            message='Let me know when CMR146067 is delivered',
            organization=org,
            source='Tests (local)',
            userId=user_id,
            teamsId=teams_id,
            userDisplayName='Automated Tester',
        ))
        req = func.HttpRequest(method='GET', body=None, url='/api/collabgpt_lg', params=request_data)
        resp = main(req)
        data = json.loads(resp.get_body())

        assert all(x in data['message'] for x in ['Teams', 'security', 'remember']), 'Did not mention one of the key points'


        # Follow-up interaction
        request_data = dict(userQuery=dict(
            existingMessages=[
                'VOR AI: To set up a notification for delivery status updates on movement request CMR146067, I need your Teams email address. For security reasons, I cannot read it directly from your account; please provide it here, and I will remember it for future notifications. Once I have your email, I will subscribe you to delivery notifications for CMR146067.',
                'Mr User: Let me know when CMR146067 is delivered'
            ],
            message=f'Sure: {user_id}',
            organization=org,
            source='Tests (local)',
            userId=user_id,
            teamsId=teams_id,
            userDisplayName='Automated Tester',
        ))
        req = func.HttpRequest(method='GET', body=None, url='/api/collabgpt_lg', params=request_data)
        resp = main(req)
        data = json.loads(resp.get_body())

        assert um.get_teams_id_by_email(user_id) == teams_id



class TestLogisticsBot:
    """Tests for the logistics bot class."""

    @pytest.mark.parametrize('org, query, expected', [
        ('CHEVRON', 'Hello,  world! \n @#12/3 `|/`¦~, 21/03/2003, 1234-12-01, 15:30, 18:15:31.111',
         None),
        ('CHEVRON', '|GORTA107, GOROPS! DEPMP, WHSDSTA503 and even GORTA999, but not MADEUP!',
         dict(project={'GORTA107', 'GOROPS', 'WHSDSTA503', 'GORTA999', 'DEPMP'})),
        ('CHEVRON', 'A pack: 000119570007349114. A tare: 100119570007355006. A shipment: 57890000445981. Panama.',
         dict(pack_or_tare={'000119570007349114', '100119570007355006'})),
        ('CHEVRON', '{SBKK0333803, SEDC0728708?, 469657 ABQU2001629 QUEU2217064; 35086-19.  MPS-C1108-354: SLZU240951-2',
         dict(container={'SEDC0728708', 'ABQU2001629', '469657', 'QUEU2217064', 'SBKK0333803', '35086-19', 'MPS-C1108-354', 'SLZU240951-2'})),
        ('CHEVRON', ' (CMR057069, LMR050035], LMR #059035#',   # vv check that obvious movement requests are removed from other compatible types
         dict(movement_request={'CMR057069', 'LMR050035', 'LMR059035'}, project=set())),
        ('CHEVRON', '82690012858979!, SBKK0333803; SEDC0728708 and BM8T0003487',
         dict(shipment={'82690012858979', 'SBKK0333803', 'SEDC0728708', 'BM8T0003487'})),
        ('CHEVRON', 'aurigaastrolabe8656,  `aurigaastrolabedsbbwi0351", skimmertide8657, \'skimmertidewhspldsb0343r, ',
         dict(voyage_cargo_manifest={'skimmertide8657', 'aurigaastrolabedsbbwi0351', 'skimmertidewhspldsb0343r', 'aurigaastrolabe8656'})),
        ('CHEVRON', '751845, WO#123456 WO274580, work order 501895, WO 749432!',       # vv check that obvious WOs are removed from other types
         dict(work_order={'751845', '123456', '274580', '501895', '749432'}, container={'501895', '751845'})),
        ('CHEVRON', '207067, 60033733, PO#60034342 PO:60035191 PO274580, purchase order 60730961-1 PO60734029-5, 60890718-001, PO 60031144!',
         dict(purchase_order={'60034342', '60734029-5', '274580', '207067', '60035191', '60890718-001', '60730961-1', '60033733', '60031144'},
              container={'207067', '60033733'})),  # << check that obvious POs are removed from other types
        ('CHEVRON', 'A proper one ST123456 and a split one ST 54321',
         dict(st_number={'ST123456', 'ST54321'})),
        ('CHEVRON', 'A flight id DaWinci-5658-2024-12-30-1 and some flight numbers NC5672 BWJSKTBW HBWPFB01 VA2505',
         dict(flight_id={'DaWinci-5658-2024-12-30-1'}, flight_number={'NC5672', 'BWJSKTBW', 'HBWPFB01', 'VA2505'})),
        ('Shell UK', 'Blah ST11-077 blah SAT602, AMD1996  736003  1MCS172  WRC6-31',
         dict(container={'ST11-077', 'SAT602', 'AMD1996', '736003', '1MCS172', 'WRC6-31'})),
        ('Shell UK', 'ABZ/082/25, abz11226 86 087 08825 LWK117',
         dict(voyage={'ABZ/082/25', 'abz11226', '087', '08825', 'LWK117'})),
        ('Shell UK', 'SHC2-04, SHC1-04A and SHC3-WILE, SHC2-OHS1 SHN2-02A  SHC2-V121 LM903 LM905-TC',
         dict(flight_number={'SHC2-04', 'SHC1-04A', 'SHC3-WILE', 'SHC2-OHS1', 'SHN2-02A', 'SHC2-V121', 'LM903', 'LM905-TC'})),
        ('ExxonMobilGuyana', 'exxonmobilsupplychaindatahub-29763 12345',
         dict(voyage={'12345'}, voyage_id={'exxonmobilsupplychaindatahub-29763'})),
        ('ExxonMobilGuyana', 'RW1_VIP, RW8_C0 Helipass-54321-2025-03-05',
         dict(flight_number={'RW1_VIP', 'RW8_C0'}, flight_id={'Helipass-54321-2025-03-05'})),
        ('ExxonMobilGuyana', 'WO1234567 987654321 WO0123456789',
         dict(work_order={'WO1234567', '987654321'})),
    ])
    def test_reference_number_extraction(self, org, query, expected):
        """Test that known reference number types are extracted from queries as expected (and that noise is ignored).
        Identification as multiple entity types is ok, as some of them really do overlap;
        the system tries multiple tools in those cases.
        """
        bot = GraphLogisticsBot(org)

        # Invert the extracted data structure to match the parametrised test cases (from ref->types to type->refs)
        ref_to_types = bot.extract_reference_numbers(query)
        extracted = defaultdict(list)
        for ref, ref_types in ref_to_types.items():
            for ref_type in ref_types:
                extracted[ref_type].append(ref)

        if expected is None:
            assert not extracted
        else:
            for ref_type, refs in expected.items():
                if refs:
                    assert not (bad := refs.difference(extracted[ref_type])), \
                        f'The following {ref_type}s were NOT captured: {bad}.\nInput: {query}'
                    assert not (bad := set(extracted[ref_type]).difference(refs)), \
                        f'The following values were NOT MEANT to be captured as {ref_type}s: {bad}.\nInput: {query}'
                else:  # vv also check that if a type was expected empty it actually is
                    assert ref_type not in extracted
            if collateral_captures := {k: v for k, v in extracted.items() if k not in expected}:
                print(f'\nFYI, the following were collateral captures for input "{query}" '
                      f'(which is fine, as the important ones are not impacted):\n\t{collateral_captures}')

    @pytest.mark.parametrize('org, received, assume, expected', [
        # Assume no tz means UTC
        ('CHEVRON', '2024-11-04T12:00:00', False, '2024-11-04T20:00:00'),  # no tz given => output is localised
        ('CHEVRON', '2024-12-30T13:52:00+08:00', False, '2024-12-30T13:52:00'),  # i.e. "just dropped the offset"
        ('CHEVRON', '2024-11-04T11:56:02.88+11:00', False, '2024-11-04T08:56:02'),  # i.e. ignored seconds and localised
        ('Shell UK', '2024-11-04T11:56:02.88+00:00', False, '2024-11-04T11:56:02'),  # Shell UK is UTC already
        # Assume no tz means the local tz
        ('CHEVRON', '2024-11-04T12:00:00', True, '2024-11-04T12:00:00'),  # no tz given => output is unchanged
        ('CHEVRON', '2024-11-04T12:00:00+08:00', True, '2024-11-04T12:00:00'),  # tz given so no effect of assumption
        ('CHEVRON', '2024-11-04T12:00:00+09:00', True, '2024-11-04T11:00:00'),  # same but with the "wrong" tz so visible change
        # Dates and (by default) midnights regardless of tz are mapped to local midnight (the 'assume' bool is irrelevant in these cases)
        ('CHEVRON', '2024-11-04', True, '2024-11-04T00:00:00'),  # pure date
        ('CHEVRON', '2024-11-04T00:00:00', True, '2024-11-04T00:00:00'),  # same for no tz midnight
        ('CHEVRON', '2024-11-04T00:00:00+11:00', True, '2024-11-04T00:00:00'),  # same for midnight with tz
    ])
    def test_datetime_localisation(self, org, received, assume, expected):
        """Check that datetime string localisation works across orgs."""
        assert localise_dt(received, config.org_time_zones[org], assume_local_if_no_tz=assume) == expected

    @pytest.mark.parametrize('tool_invocation, real_name', [
        # COMMENT OR UNCOMMENT CASES AS REQUIRED
        [{'args': {'query': 'testing'}, 'type': 'shipments_by_descriptions'}, 'find_shipments'],
        [{'args': {'id': '123'}, 'type': 'movements_reqs_ids'}, 'find_movement_requests'],
        [{
            'args': {
                'tool_uses': [
                    {'recipient_name': 'functions.container_events_by_id', 'parameters': {'query': 'QUEU2216509'}},
                    {'recipient_name': 'functions.find_shipments', 'parameters': {'query': 'QUEU2216509'}},
                    {'recipient_name': 'functions.find_movement_requests', 'parameters': {'query': 'QUEU2216509'}}
                ]
            },
            'type': 'multi_tool_use.parallel'
        }, ['container_events_by_id', 'find_shipments', 'find_movement_requests']]
    ])
    def test_tool_correction(self, tool_invocation, real_name):
        real_name = [real_name] if isinstance(real_name, str) else real_name  # vv org is irrelevant for this test
        result = correct_tool_hallucinations([tool_invocation], tool_maps_by_org['CHEVRON']['retrieval'])
        assert all(out['type'] == real for out, real in zip(result, real_name))

    @pytest.mark.parametrize('tag, message', [
        # Live
        ('@[vorai@vor.cloud]', 'vorai@vor.cloud: @[vorai@vor.cloud] what\'s the status of CMR057069?'),
        ('@[vorai.suk@vor.cloud]', 'vorai.suk@vor.cloud: @[vorai.suk@vor.cloud] what\'s the status of CMR057069?'),
        # Dev
        ('@[vorai@vor2dev.onmicrosoft.com]', 'vorai@vor2dev.onmicrosoft.com: @[vorai@vor2dev.onmicrosoft.com] hello!'),
        ('@[vorai.suk@vor2dev.onmicrosoft.com]', 'vorai.suk@vor2dev.onmicrosoft.com: @[vorai.suk@vor2dev.onmicrosoft.com] hello!')
    ])
    def test_parsing_messages(self, tag, message):
        """Test the regex for removing the VORAI tags from queries/historic messages."""
        bot = GraphLogisticsBot()  # do not care about org here
        msg_tags_removed = bot._remove_ai_tag(message)
        assert tag not in msg_tags_removed


