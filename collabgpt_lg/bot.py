import logging
import json
import time
import re
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_openai import ChatOpenAI
from langchain_community.chat_message_histories import ChatMessageHistory
from langgraph.graph.state import CompiledStateGraph

from collabgpt_lg.graph_types import GraphState, ConfigSchema, apply_reducers
from collabgpt_lg.graph import graph_builder

from shared.ids.all_regexes import id_filter, REGEX_MAPPING, REGEX_ANTIMAPPING
import config


class GraphLogisticsBot:
    def __init__(self, org: str = None):
        if org and org not in config.ai_behaviour.supported_orgs:  # fine to raise because org is passed here only in testing
            raise ValueError(f'VOR AI was invoked by an unsupported organisation: {org}')

        # Infrastructure info
        self.org: str = org  # convenient for testing to allow passing org in at init; it is normally set in .full_call
        self.tz: ZoneInfo = config.org_time_zones[self.org] if org else None  # want to fail for bad org, so no .get
        self.source: str = None
        self.thread_id: str = None
        self.request_datetime: datetime = None

        # User info
        self.user_id: str = None
        self.user_display_name: str = None
        self.user_teams_id: str = None

        # Invocation content info
        self.message_history: ChatMessageHistory = None
        self.user_message: str = None
        self.reference_numbers: dict[str, list[str]] = None

        # Graph fields
        self.graph: CompiledStateGraph = None

        self.llms = {
            label: ChatOpenAI(
                api_key=config.llm.api_key,
                base_url=config.llm.endpoint,
                model=deployment,  # vv few models support temperature anymore
                temperature=config.llm.temperature if '4.' in deployment or '5-chat' in deployment else 1,
            ) for label, deployment in config.llm.deployment.items()
        }

    @staticmethod
    def _remove_ai_tag(msg: str) -> str:
        """Remove tags of the form @[voraiXXX?@XXX(.com|.cloud)] where the XXX must contain neither @ nor ]."""
        msg_stripped = re.sub(r'@\[vorai[^]@]*@[^]@]+\.(?:com|cloud)]', '', msg)  # regex inlined for syntax highlighting
        return msg_stripped.strip()

    @staticmethod
    def _parse_historic_message(msg: str) -> [bool, str]:
        """Return if AI message, returns cleaned message."""
        username = msg.split(':')[0].strip()
        msg = ''.join(msg.split(':')[1:])  # remove first part with username
        return 'VOR AI' in username, msg

    def parse_message_history(self, chat_history_raw) -> ChatMessageHistory:
        """Process the message history."""
        out = ChatMessageHistory()
        if chat_history_raw is not None:
            # limit to last n messages, assuming anything older is no longer relevant
            messages = list(reversed(chat_history_raw))[-config.ai_behaviour.history_length:]
            for msg in messages:
                msg_stripped = self._remove_ai_tag(msg)
                ai_user, msg_clean = self._parse_historic_message(msg_stripped)
                if ai_user:
                    out.add_ai_message(msg_clean)
                else:
                    out.add_user_message(msg_clean)
        return out

    def extract_reference_numbers(self, query):
        """Function to extract VOR reference numbers from a query."""
        # Dictionary of reference numbers to their possible entity types
        matches = defaultdict(list)
        for candidate in id_filter(query):
            for entity, pattern in REGEX_MAPPING[self.org].items():
                if match := re.fullmatch(pattern, candidate):
                    # If there is a captured group, store that instead of the full candidate
                    matches[match.group(1) if match.groups() else candidate].append(entity)

        # If matches are clearly of one type, remove other types
        for filter_entity, antipattern in REGEX_ANTIMAPPING[self.org].items():
            for match in matches:  # not .items() because modifying values
                if re.fullmatch(antipattern, match):  # vv also remove non-refs (e.g. dates, times, 'LMR', ...)
                    matches[match] = [filter_entity] if filter_entity in matches[match] else []

        # Keep only non-empty entries and convert from defaultdict[list] to dict for tidiness of string representation
        out = {k: v for k, v in matches.items() if v}

        logging.info('Extracted the following reference numbers: %s', out)
        return out

    def _run_graph(self):
        """Construct graph inputs, run the graph, and return the final state and the runtime."""
        state = GraphState(  # IDE hyperlinking gets confused here; the definition is in graph_types.py
            user_teams_email='',
            user_message=self.user_message,
            message_history=self.message_history,
            reference_numbers=self.reference_numbers,
            confirmed_types={},
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
            org=self.org,
            source=self.source,
            timezone=self.tz,
            llms=self.llms,
            notification_agent_is_allowed=self.org in config.user_actions.notification_agent_allow_list,
            user_id=self.user_id,
            user_teams_id=self.user_teams_id,
            user_display_name=self.user_display_name
        )

        timestamp_start = time.time()

        # Can either .invoke and get the final state directly
        # state = self.graph.invoke(state, dict(configurable=configurable))

        # Or can .stream and carefully keep track of the state manually
        for event in self.graph.stream(state, dict(configurable=configurable)):
            for node_name, state_updates in event.items():
                if state_updates:
                    state = apply_reducers(state, state_updates)

                # Trim selected fields for logging
                #   NOTE: any field possibly containing dataframes should be cast to str here because non-JSON-serialisable
                to_trim = ['current_tool_calls', 'data', 'response']
                for_log = {k: (str(v)[:200] + '...' if len(str(v)) > 200 else str(v)) if k in to_trim else v for k, v in state_updates.items()}
                json_str = json.dumps(for_log, indent=4)  # << this is indentation within the JSON
                indented_str = '\n\t'.join(json_str.splitlines())  # << this is the base indentation for the whole JSON
                logging.info(f'Graph stream event:\n\tNode: %s\n\tState update: %s', node_name, indented_str)

        response_time = round(time.time() - timestamp_start, 2)
        return state, response_time

    def run(self, query: dict):
        """Extract the various fields from the query object, use them to run the graph, and package the results
        into the expected response object.
        """
        # Infrastructure info
        self.source = query.get('source')  # 'Teams', 'Collab', ...
        self.thread_id = query.get('threadId')
        self.request_datetime = datetime.now()

        # User info
        self.org = query.get('organization')
        self.user_id = query.get('userId')  # there is one more user id param, but only for Teams: userAADId
        self.user_teams_id = query.get('teamsId')
        self.user_display_name = query.get('userDisplayName')

        logging.info('Organisation: %s - User: %s (id: %s)', self.org, self.user_display_name, self.user_id)

        # Invocation content info
        self.message_history = self.parse_message_history(raw_history := query.get('existingMessages'))
        self.user_message = self._remove_ai_tag(query.get('message'))

        logging.info('User query: %s', self.user_message)
        logging.info('Existing messages: %s', self.message_history)

        if self.org in config.ai_behaviour.supported_orgs:
            self.tz = config.org_time_zones[self.org]  # want to fail for bad org, so no .get
            self.reference_numbers = self.extract_reference_numbers(self.user_message)
            self.graph = graph_builder().compile()
            final_state, response_time = self._run_graph()
        else:
            logging.warning(f'VOR AI was invoked by an unsupported organisation: %s', self.org)
            final_state = dict(
                response = f'VOR AI is not enabled for your organisation ({self.org})',
                tokens_count=0,
                tokens_cost=0,
                tools_used={},
            )
            response_time = 0

        sql_tool_calls = [dict(tool='process_dataset_with_sql', args=dict(sql_query=d['performed_sql'], source=d['source']))
                          for d in final_state['data'] if 'performed_sql' in d]

        # Aggregate calls by model
        llm_calls = {llm.model: [] for llm in self.llms.values()}
        for call in final_state['llm_calls']:  # ^^ not defaultdict(list) so that llms with no calls are also present
            llm_calls[self.llms[call['name']].model].append({k: v for k, v in call.items() if k != 'name'})

        response = dict(
            source=self.source,
            organisation=self.org,
            user_id=self.user_id,
            user_display_name=self.user_display_name,
            user_teams_id=self.user_teams_id,
            request_datetime=self.request_datetime.isoformat(),
            existing_messages=list(reversed(raw_history)),
            query=self.user_message,
            likely_reference_numbers=self.reference_numbers,
            message=final_state['response'],
            response_time=response_time,
            llm_calls=llm_calls,
            tokens_count=sum(call['tokens_count'] for call in final_state['llm_calls']),
            tokens_cost=sum(call['tokens_cost'] for call in final_state['llm_calls']),
            used_tools=final_state['used_tools'] + sql_tool_calls,
            comments=final_state['comments'],  # not filled at any point so far, but the field is there

            ######################################################################
            #### To be removed after the AI Insights "topics" code is updated ####
            tools_used=[call['tool'] for call in final_state['used_tools']],
            tools_params=[call['args'] for call in final_state['used_tools']],
            ######################################################################
        )

        logging.info('Response time: %ss', response['response_time'])
        logging.info('Tokens used across all deployments: %s, costing $%s', response['tokens_count'], round(response['tokens_cost'], 6))
        logging.info('Response: %s', response['message'])
        logging.info(json.dumps(dict(azure_monitoring_payload=response), indent=4))

        return response
