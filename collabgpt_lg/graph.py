import logging
import re
import asyncio
from math import isnan
from more_itertools import unique_justseen

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph
from langgraph.types import Command, Send

from typing_extensions import Literal

from collabgpt_lg.graph_types import ConfigSchema, GraphState
from collabgpt_lg.prompts import (get_parser_prompt, get_router_prompt, Route,
                                  get_retrieval_tool_picker_prompt, get_action_tool_picker_prompt,
                                  get_sql_writer_prompt, get_sql_retry_prompt,
                                  get_notification_topic_router_prompt, NotificationTopic,
                                  get_teams_email_check_prompt, ConversationEmailCheck,
                                  get_answer_writer_prompt)
from collabgpt_lg.endpoints import VorGlobalSearch, VoyageCargoManifestsByID, NotificationAgent, MovementRequestByID
from collabgpt_lg.tools import tools_by_org, tool_maps_by_org, process_dataset_with_sql, sql_tool_map, non_index_data_retriever
from collabgpt_lg.tool_utils import extract_tool_calls
from collabgpt_lg.utils import LlmCallContext, get_categorical_columns

from shared.user_actions import ActiveSubscriptions
from shared.user_management import UserManagement
from shared.mixpanel import track_event
from shared.slack import log_on_slack
from shared.ids.all_regexes import REGEX_MAPPING

import config as conf  # because it clashes with the in-built config node argument


def _actions_allowed_for_org(org: str) -> bool:
    """Whether the system is allowed to us action-taking tools for the given org (whether they exist and permission is granted)."""
    return org in conf.ai_behaviour.actions_allowed_orgs and bool(tools_by_org[org]['action'])


# Nodes
#   Notes:
#   - 1st arg is state, 2nd arg is optional and can be a RunnableConfig for node-specific state-like things
#       https://langchain-ai.github.io/langgraph/concepts/low_level/?h=configuration#nodes
#   - Can either keep processing and path-choosing separate (respectively, in nodes and plain/conditional edges),
#       or can combine them in nodes by returning Command objects, which specify where to go
#       https://langchain-ai.github.io/langgraph/concepts/low_level/?h=configuration#command


def parser(state: GraphState, config: RunnableConfig):
    """Parse the query and message history with awareness of glossary etc."""
    model = 'normal'
    c = config['configurable']
    prompt = get_parser_prompt(
        org=c['org'],
        user_message=state['user_message'],
        message_history=state['message_history'].messages,
        reference_numbers=state['reference_numbers'],
        notification_agent_is_allowed=conf.langflow.notification_agent and c['notification_agent_is_allowed'],
        actions_are_allowed=_actions_allowed_for_org(c['org']),
    )
    with LlmCallContext(model, 'parser') as ctx:
        out = c['llms'][model].invoke(prompt.format_messages())
    return dict(processed_query=out.content, llm_calls=[ctx.llm_call])


def router(state: GraphState, config: RunnableConfig) -> Command[Literal['retrieval_tool_picker', 'action_tool_picker', 'answer_writer', 'notification_topic_router', 'router']]:
    """Determine whether enough has been done and perhaps write a private note to self about what to do."""
    model = 'low'
    c = config['configurable']
    visits = state['router_visits_counter'] + 1

    notification_agent_is_allowed = conf.langflow.notification_agent and c['notification_agent_is_allowed']
    if notification_agent_is_allowed and re.search('NOTIFICATION AGENT', state['processed_query']) and c['source'] != 'Collab':
        return Command(update=dict(router_visits_counter=visits, private_note='Passing the query to the Notification Agent'),
                       goto='notification_topic_router')

    actions_are_allowed = _actions_allowed_for_org(c['org'])
    prompt = get_router_prompt(
        processed_query=state['processed_query'],
        data=state['data'],
        action_are_allowed=actions_are_allowed,
    )  # vv telling the AI in the main prompt may be slightly more efficient than making it format the output, but close
    with LlmCallContext(model, 'router') as ctx:
        out: Route = c['llms'][model].with_structured_output(Route).invoke(prompt.format_messages())
                            # vv clear this in case another tool calling loop starts
    state_update = dict(current_tool_calls=['CLEAR'], router_visits_counter=visits, private_note=out.comment, llm_calls=[ctx.llm_call])

    if out.done_enough or visits > 2:  # this value may seem low, but many tools are tried in a single loop
        return Command(update=state_update, goto='answer_writer')
    elif out.use_action_tools:
        if actions_are_allowed:
            return Command(update=state_update, goto='action_tool_picker')
        else:
            logging.warning('Action-taking tool use requested but this is not allowed for %s', c['org'])
            state_update['private_note'] = f'{out.comment}\nAction-taking tool use requested but this is not allowed for {c['org']}; use_action_tools should be false; try something else.'
            return Command(update=state_update, goto='router')
    else:
        return Command(update=state_update, goto='retrieval_tool_picker')


def retrieval_tool_picker(state: GraphState, config: RunnableConfig) -> Command[Literal['tool_executor', 'answer_writer']]:
    """Pick retrieval/search tools to use (or return useful urls)."""
    model = 'normal'
    c = config['configurable']

    prompt = get_retrieval_tool_picker_prompt(
        org=c['org'],
        processed_query=state['processed_query'],
        private_note=state['private_note'],
        used_tools=state['used_tools']
    )
    with LlmCallContext(model, 'retrieval_tool_picker') as ctx:
        out = c['llms'][model].bind_tools(tools_by_org[c['org']]['retrieval']).invoke(prompt.format_messages())
    if good_calls := extract_tool_calls(out, tool_maps_by_org[c['org']]['retrieval']):
        logging.info('Decided to call the following tools: \n\t\t%s', '\n\t\t'.join(str(tc) for tc in good_calls))
                                    # vv clear private_note in case of multiple tool calling rounds
        return Command(update=dict(private_note='', llm_calls=[ctx.llm_call]),
                       goto=[Send('tool_executor', dict(current_tool_call=tc, tool_bucket='retrieval')) for tc in good_calls])
    else:                                       # note that ^^ is SINGULAR; it will not stick around after aggregation
        return Command(update=dict(private_note=out.content, llm_calls=[ctx.llm_call]), goto='answer_writer')


def action_tool_picker(state: GraphState, config: RunnableConfig) -> Command[Literal['tool_executor', 'answer_writer']]:
    """Pick mutating/action tools to use."""
    model = 'normal'
    c = config['configurable']

    prompt = get_action_tool_picker_prompt(
        org=c['org'],
        processed_query=state['processed_query'],
        private_note=state['private_note'],
        used_tools=state['used_tools']
    )
    with LlmCallContext(model, 'action_tool_picker') as ctx:
        out = c['llms'][model].bind_tools(tools_by_org[c['org']]['action']).invoke(prompt.format_messages())
    if good_calls := extract_tool_calls(out, tool_maps_by_org[c['org']]['action']):
        logging.info('Decided to call the following tools: \n\t\t%s', '\n\t\t'.join(str(tc) for tc in good_calls))
        return Command(update=dict(private_note='', llm_calls=[ctx.llm_call]),
                       goto=[Send('tool_executor', dict(current_tool_call=tc, tool_bucket='action')) for tc in good_calls])
    else:
        return Command(update=dict(private_note=out.content, llm_calls=[ctx.llm_call]), goto='answer_writer')


# Note on fanning out into parallel processing paths and aggregating them later
#   - If only splitting for one node (A -> many Bs -> single C) then there are no issues.
#   - If need every B node to then call their own C node (and then aggregating in a final D node) then there is an issue
#       due to not being able to assign multiple values to a state field in one parallel step unless they are all accumulated.
#       (Accumulating them defeats the point because then every C node will be given ALL the outputs of every B node).
#   There are 3 approaches to solve this:
#       - Do accumulate every B result but tag each with a key and have every C only use the value at that key.
#           - Probably need to strictly use Send objects to go from one individual-branch node to the next (to use their separate state).
#           - Then need a flexible reducer function which allows clearing the field (for further tool-calling loops).
#       - Aggregate into a single C and then re-spread over multiple Ds.
#           - THIS IS THE APPROACH USED HERE
#       - Create a separate subgraph containing only B->C and call that from A.

# Other note on fanning out into parallel processing paths with the Send object
#   - The state dict passed as the second argument in Send objects REPLACES the normal state for each of the parallel nodes.
#   - Therefore its fields need not match those of the standard state (not that they ever technically have to).
#   - Unless saved into the normal state from inside the parallel nodes, those custom state values disappear after them.
#   - Relevant case here: passing a (singular) 'current_tool_call' and 'tool_bucket' ('retrieval'|'action') to each
#       fanned-out node so tool_executor only dispatches within that bucket's tool map, then accumulate outputs into
#       the standard state (plural) 'current_tool_calls' field.


def tool_executor(state: GraphState, config: RunnableConfig):
    """Execute a tool call."""
    c = config['configurable']

    # Note that 'current_tool_call' is singular (hence not a standard state field) and will not stick around after this graph splitting
    tool, args = state['current_tool_call']['type'], state['current_tool_call']['args']
    bucket = state['tool_bucket']
    logging.info('Called the %s tool with the following args: %s', tool, args)
    if bucket == 'action' and c['org'] not in conf.ai_behaviour.actions_allowed_orgs:
        logging.warning('Refusing action tool %s for org %s (not in ACTIONS_ALLOWED_ORGS)', tool, c['org'])
        tool_output = dict(error='Action tools are not enabled for this organisation.')
    else:
        tool_output = tool_maps_by_org[c['org']][bucket][tool].invoke(dict(c=c, **args))  # note the injection of the config
    pretty_call = dict(tool=tool, args=args)

    return dict(used_tools=[pretty_call], current_tool_calls=[dict(source=pretty_call, output=tool_output)])


# Adding this as a node instead of a conditional edge to highlight the parallel branching in one of the two cases
def sql_chooser(state: GraphState, config: RunnableConfig) -> Command[Literal['sql_writer', 'router']]:
    """Route datasets requiring further processing to the sql_writer node."""
    tool_calls = state['current_tool_calls']
    process_further = [tc for tc in tool_calls if tc['output'].get('MetaData', {}).get('further_processing_is_required')]

    if process_further:             # vv clear current_tool_calls because used for sql tool calls as well
        return Command(update=dict(current_tool_calls=['CLEAR'], data=[tc for tc in tool_calls if tc not in process_further]),
                       goto=[Send('sql_writer', dict(current_tool_call=tc)) for tc in process_further])
    else:                                   # once again ^^ is singular, visible only in the split branches
        return Command(update=dict(data=tool_calls), goto='router')


def sql_writer(state: GraphState, config: RunnableConfig) -> Command[Literal['sql_executor', 'router']]:
    """Create SQL tool calls (not running them here because concurrent ones can stall, so aggregating and running sequentially elsewhere)."""
    model = 'low'
    c = config['configurable']
    source, data = state['current_tool_call']['source'], state['current_tool_call']['output']
    datasets_info = {}
    for name in ['TopResultsDataset', 'AllResultsDataset']:
        if dataset := data.get(name):
            datasets_info[name] = dict({k: v for k, v in dataset.items() if k != 'dataframe'},
                                       categorical_values=get_categorical_columns(dataset['dataframe']))

    prompt = get_sql_writer_prompt(
        further_processing=data['MetaData']['further_processing_is_required'],
        applied_filters=data['MetaData']['applied_filters'],
        datasets_info=datasets_info
    )
    with LlmCallContext(model, 'sql_writer') as ctx:
        out = c['llms'][model].bind_tools([process_dataset_with_sql]).invoke(prompt.format_messages())
    if sql_calls := extract_tool_calls(out, sql_tool_map):
        sql_calls_with_context = [dict(original_source=source, original_output=data, **tc) for tc in sql_calls]
        return Command(update=dict(current_tool_calls=sql_calls_with_context, llm_calls=[ctx.llm_call]), goto='sql_executor')
    else:  # ^^ vv not updating used_tools with the sql tool as already mentioned in the data and confusing for the LLM
        return Command(
            update=dict(
                data=[handle_post_sql_data(c, original_source=source, original_data=data, sql_args={}, tool_output=out.content)],
                llm_calls=[ctx.llm_call]
            ),
            goto='router'
        )


def sql_executor(state: GraphState, config: RunnableConfig):
    """Execute (and troubleshoot) all SQL tool calls sequentially (because concurrent ones can stall)."""
    model = 'normal'  # 'low' for the first SQL attempt, 'normal' to fix any issue
    c = config['configurable']

    sqlled_outputs = []
    llm_calls = []
    for tc in state['current_tool_calls']:
        source, data = tc['original_source'], tc['original_output']
        datasets = {k: v['dataframe'] for k, v in data.items() if k in ['TopResultsDataset', 'AllResultsDataset']}
        datasets_info = {}
        for name in ['TopResultsDataset', 'AllResultsDataset']:
            if dataset := data.get(name):
                datasets_info[name] = dict({k: v for k, v in dataset.items() if k != 'dataframe'},
                                           categorical_values=get_categorical_columns(dataset['dataframe']))

        tool, args = tc['type'], tc['args']  # tool can only be the sql one, but being consistent
        logging.info('Called the %s tool with the following args: %s', tool, args)

        notes = []
        if args['full_data_key'] not in datasets:
            notes.append(f'The process_dataset_with_sql was asked to work on a non-existing dataset ({args['full_data_key']}); '
                         f'replaced it with {list(datasets.keys())[0]}')
            args['full_data_key'] = list(datasets.keys())[0]

        tool_output = process_dataset_with_sql.invoke(dict(c=c, datasets=datasets, **args))  # note the injection of config and datasets

        # Rewrite the SQL if failed on the 1st attempt
        attempt, max_attempts = 1, 2
        while attempt <= max_attempts and 'try again' in tool_output:
            logging.info('Retrying SQL query, attempt: %s', attempt)
            prompt = get_sql_retry_prompt(
                failed_sql_query=args['sql_query'],
                error=tool_output,
                applied_filters=data['MetaData']['applied_filters'],
                full_data_key=args['full_data_key'],
                dataset_info=datasets_info[args['full_data_key']]
            )
            with LlmCallContext(model, 'sql_executor') as ctx:
                out = c['llms'][model].bind_tools([process_dataset_with_sql]).invoke(prompt.format_messages())
            llm_calls.append(ctx.llm_call)

            retry_calls = extract_tool_calls(out, sql_tool_map)
            tc = retry_calls[0] if retry_calls else None
            if not tc:
                break
            tool, args = tc['type'], tc['args']
            logging.info('Called the %s tool with the following args: %s', tool, args)
            tool_output = process_dataset_with_sql.invoke(dict(c=c, datasets=datasets, **args))
            attempt += 1

        sqlled_outputs.append(handle_post_sql_data(
            c,
            original_source=source,
            original_data=data,
            sql_args=args,
            tool_output=tool_output,
            notes=notes
        ))

    # There could conceivably be duplicates if more than one SQL call was generated for the same dataset
    #   Checking at the end (and by output rather than sql) instead of the beginning because duplicates could be created by failures
    no_duplicates = list(unique_justseen(sqlled_outputs, key=lambda x: (x['source'], x['output'])))
    return dict(data=no_duplicates, llm_calls=llm_calls)


def handle_post_sql_data(c: ConfigSchema, original_source: dict, original_data: dict,
                         sql_args: dict, tool_output: list[dict] | dict, notes: list[str] = None) -> dict:
    """Post-sql cleanup operations and packaging of return dict to add to the data field of the state:
    - If SQL failed or was not performed, return the top few results and add the TopResults field
        (since it is not there for data with further_processing).
    - If the output is standard entries, try and look them up in the non-index source.
    - Appropriately update mentions of further processing in all places.
    """
    no_sql = isinstance(tool_output, str)
    out = tool_output
    notes = notes if notes else []

    if no_sql:
        cause = 'SQL processing failed after the allowed attempts' if 'try again' in tool_output else 'Decided not to run any SQL'
        logging.warning(f'%s for data from %s(%s). Returning the first %s entries instead. Explanation: %s',
                       cause, original_source['tool'], original_source['args'], conf.ai_behaviour.default_limit, tool_output)

        if (dataset := original_data.get('AllResultsDataset')) is None:  # not doing a simple "or" between the two because
            dataset = original_data.get('TopResultsDataset')             # checking the bool of a DataFrame is ambiguous
        out = dataset['dataframe'].head(conf.ai_behaviour.default_limit).to_dict('records')
    elif isinstance(tool_output, list) and len(tool_output) > conf.ai_behaviour.strict_limit:
        original_dataset = original_data[sql_args['full_data_key']]
        notes.append(f'The data processing by the SQL tool produced {len(tool_output)} results '
                     f'(from the {original_dataset["n_rows"]} entries of the {sql_args["full_data_key"]} dataset); '
                     f'only showing the first {conf.ai_behaviour.strict_limit} here.')
        logging.warning('The SQL tool returned too many results (%s); restricting them to %s.',
                        len(tool_output), conf.ai_behaviour.strict_limit)
        out = tool_output[:conf.ai_behaviour.strict_limit]

    # If the output is standard entries, try and look them up in the non-index source
    if all('id' in entry for entry in tool_output):
        non_index_out = non_index_data_retriever(c=c, original_tool=original_source['tool'],
                                                 index_results=out, params=original_source['args'])
        out = non_index_out  # splitting from the above to compare when debugging

    # Update mentions of further processing
    original_source['args']['further_processing'] = (('NOT PERFORMED; IGNORE: ' if no_sql else 'ALREADY PERFORMED: ')
                                                     + original_source['args']['further_processing'])
    original_data['MetaData'].pop('further_processing_is_required', None)

    # Remove all None and nan values (many can form for all lines due to the flattened nested fields of just a few of them)
    for i in range(len(out)):  # by index because modifying the values
        out[i] = {k: v for k, v in out[i].items() if v is not None and not (isinstance(v, float) and isnan(v))}

    # Package up the dict to append to the data field of the state
    out = dict(
        source=original_source,
        original_data=original_data,
        output=out
    )
    if notes:
        out['notes'] = notes
    return dict(**out, **({} if no_sql else dict(performed_sql=sql_args['sql_query'])))


def answer_writer(state: GraphState, config: RunnableConfig):
    """Use the guidelines to write the final answer to the user request."""
    model = 'high'
    c = config['configurable']
    prompt = get_answer_writer_prompt(
        org=c['org'],
        user_display_name=c['user_display_name'],
        processed_query=state['processed_query'],
        private_note=state['private_note'],
        data=state['data']
    )
    with LlmCallContext(model, 'answer_writer') as ctx:
        out = c['llms'][model].invoke(prompt.format_messages())
    return dict(response=out.content, llm_calls=[ctx.llm_call])


def notification_topic_router(state: GraphState, config: RunnableConfig) -> Command[Literal['ids_for_subscriptions_getter', 'notification_agent_caller', 'answer_writer']]:
    """
    Extract IDs, and if the request is about setting up a subscription, check whether it overlaps with any of the
    existing ones.
    """
    state_output = {}
    model = 'normal'
    c = config['configurable']
    teams_id = c['user_teams_id']
    llm_calls = []

    if c['source'] == 'Teams':  # Check the Teams email is mapped and map it if not
        um = UserManagement()
        email = um.get_teams_email_by_id(teams_id)
        if email and '@' in email:
            state_output['user_teams_email'] = email
        else:  # check if the email is in the message or conversation history
            prompt = get_teams_email_check_prompt(
                user_message=state['user_message'],
                message_history=state['message_history'].messages,
            )
            with LlmCallContext('low', 'notification_topic_router') as ctx:
                out = c['llms']['low'].with_structured_output(ConversationEmailCheck).invoke(prompt.format_messages())
            llm_calls.append(ctx.llm_call)

            if out.contains_email:
                um.update_user_account(teams_id=teams_id, email=out.email)
                state_output['user_teams_email'] = out.email
                logging.info('Updated user account: %s', out.email)
                log_on_slack(
                    'VOR AI - email address linked to Teams account:\n'
                    f'\tEmail: {out.email}\n\tDisplay name: {c["user_display_name"]}\n\tOrg: {c["org"]}\n\tTeams ID: {teams_id}'
                )
                track_event('user_account_updated', dict(
                    distinct_id=out.email,
                    user_teams_id=teams_id,
                    user_display_name=c['user_display_name'],
                    organisation=c['org']
                ))
            else:
                note = ('CANNOT PROCEED: anything to do with subscriptions requires knowing the user\'s Teams email. '
                        'Tell them so and ask for it, mentioning that you cannot read it directly from their account '
                        'for security reasons and that they only need to tell you once and you will remember it.')
                return Command(update=dict(private_note=note, llm_calls=llm_calls), goto='answer_writer')

    active_subscriptions = ActiveSubscriptions(c['org']).retrieve(user=c['user_id'])
    logging.info('Retrieved %s active subscriptions', len(active_subscriptions))
    nice_subscriptions = [f'{sub['entityId']} ({sub['entityType']}): "{sub['description']}"' for sub in active_subscriptions.values()]

    prompt = get_notification_topic_router_prompt(
        org=c['org'],
        processed_query=state['processed_query'],
        existing_subscriptions='- ' + '\n\t\t- '.join(nice_subscriptions)
    )
    with LlmCallContext(model, 'notification_topic_router') as ctx:
        out: NotificationTopic = c['llms'][model].with_structured_output(NotificationTopic).invoke(prompt.format_messages())
    llm_calls.append(ctx.llm_call)
    state_output['llm_calls'] = llm_calls
    state_output['notification_topic'] = dict(out)

    if out.unsupported_feature or (out.topic_is_subscription_set_up and not out.ids):
        state_output['private_note'] = out.unsupported_feature
        return Command(update=state_output, goto='answer_writer')
    elif out.topic_is_subscription_listing:
        state_output['private_note'] = 'Current user subscriptions:\n\t- ' + '\n\t- '.join(nice_subscriptions) if nice_subscriptions else 'There are no active user subscriptions.'
        return Command(update=state_output, goto='answer_writer')
    elif out.topic_is_subscription_set_up:
        return Command(update=state_output, goto='ids_for_subscriptions_getter')
    else:
        return Command(update=state_output, goto='notification_agent_caller')


def ids_for_subscriptions_getter(state: GraphState, config: RunnableConfig) -> Command[Literal['notification_agent_caller', 'answer_writer']]:
    """Look up IDs and determine whether can subscription is possible with current data."""
    c = config['configurable']
    notification_topic = NotificationTopic(**state['notification_topic'])
    state_output = dict(used_tools=[])

    # Write down whether the requested entities are subscribeable or what related subscribeable ones were found in their stead
    ls_report_ids_by_org = {
        'CHEVRON': ['hcr transit time', 'hcr dwell time', 'new cmrs', 'dangerous goods'],
        'ExxonMobilGuyana': [],
        'Shell UK': []
    }
    result_notes, confirmed_types = {}, {}
    for _id in notification_topic.ids:
        if _id.upper().startswith(('GORTA', 'WHSDSTA', 'WHSUSTA', 'WHSTA')):
            continue  # projects are not subscribeable entities, so save unnecessary steps

        if _id.lower() in ls_report_ids_by_org[c['org']]:  # vv the positive case has to start with _id
            result_notes[_id] = (f'{_id} is a logistics summary report and can be subscribed to for the condition of new reports/warnings appearing '
                                 f'("{_id}" is the subscription entity, so do not repeat it in the condition itself; '
                                 f'also, it is fine if lookups of other IDs you wish to include in a {_id} condition had no results, they can still be mentioned).')
            confirmed_types[_id] = 'logistics summary report'
            continue

        if _id in ['PENDING', 'APPROVED', 'REJECTED'] and c['org'] == 'Shell UK':
            result_notes[_id] = (f'{_id} is a flight request status and can be subscribed to as entity type "flight requests" '
                                 f'("{_id}" is the subscription entity, so do not repeat it in the condition itself).')
            confirmed_types[_id] = 'flight requests'
            continue

        # VOR Search does not find voyages by voyage number; they get their own (faster) lookup
        if c['org'] == 'CHEVRON' and len(_id) <= 4 and _id.isnumeric():
            results = asyncio.run(VoyageCargoManifestsByID(c).query(_id))
            if multiple := results.get('multiple_matches'):
                result_notes[_id] = f'There are multiple voyages with number {_id}; ask the user which one they mean among {[v['id'] for v in multiple]}.'
            elif full_id := results.get('id'):
                result_notes[_id] = f'{_id} is a voyage, with full ID {full_id}.'  # the positive case has to start with _id
            else:
                result_notes[_id] = f'No results were found for {_id}, so nothing can be subscribed to.'
            state_output['used_tools'].append(dict(tool='indirect_voyage_by_number', args=dict(query=_id)))
            continue

        # Standard VOR Search for anything but voyage numbers
        _id = m.group(1) if (m := re.fullmatch(r'[WP]O ?(\d+)', _id, flags=re.IGNORECASE)) else _id  # remove leading PO/WO
        results = VorGlobalSearch(c).simple_query(_id)
        state_output['used_tools'].append(dict(tool='indirect_vor_search', args=dict(query=_id)))

        # Check whether a full match was found (without problematic prefixes)
        prefixes = ['ignition-', 'chevronvoyagemanifest-', 'wels-', 'ifs-', 'exxonmobilsupplychaindatahub-']
        found_type = [e_type for e_type, rs in results.items() for r in rs
                      if next((r[len(p):] for p in prefixes if r.lower().startswith(p.lower())), r).lower() == _id.lower()]

        # Subscriptions to not-yet-indexed MRs should be allowed if found with the Customer API
        if c['org'] == 'CHEVRON' and _id.upper().startswith(('CMR', 'LMR')) and 'movement request' not in found_type:
            mr_result = asyncio.run(MovementRequestByID(c).query(_id))
            state_output['used_tools'].append(dict(tool='indirect_movement_request_by_id', args=dict(_id=_id)))
            if not (mr_result.get('status') or '').startswith('no data available'):
                found_type.append('movement request')

        # Transfer Requests should be recognised by their friendly ID
        if (c['org'] == 'ExxonMobilGuyana' and re.fullmatch(REGEX_MAPPING[c['org']]['transfer_request'], _id)
                and (trs := results.get('transfer request')) and 'transfer request' not in found_type):
            if next((tr for tr in trs.values() if re.match(REGEX_MAPPING[c['org']]['transfer_request'], tr)), ''):
                found_type.append('transfer request')  # ^^ if the description starts with TR/d{10} (i.e. its title field)

        if found_type:
            result_notes[_id] = f'{_id} is a {found_type} and can be subscribed to.'  # the positive case has to start with _id
            confirmed_types[_id] = found_type
        elif results:
            # Keep only the first few results of each type
            suffix, cut_off = '', 5
            if extra := [e_type for e_type, rs in results.items() if len(rs) > cut_off]:
                suffix = f'\n(There were more entities mentioning {_id} (of types {extra}), but the above are the most relevant ones).'
                for e_type in results:
                    results[e_type] = dict(list(results[e_type].items())[:cut_off])

            if 'flight_number' in state['reference_numbers'].get(_id, []) and (flights := results.get('flight', [])):
                result_notes[_id] = (f'Subscriptions cannot be created for flight number {_id} directly, '
                                     f'but the most recent flight instances for it can be subscribed to: {dict(list(flights.items())[:3])}')
                # Not sure whether the below ever occurs, but being safe (an _id which looks like a flight number being mentioned in non-flights)
                if non_flight_mentions := {k: v for k, v in results.items() if k != 'flight'}:
                    result_notes[_id] += f'\n{_id} is also mentioned in these other subscribeable entities: {non_flight_mentions}'
            else:
                result_notes[_id] = f'Subscriptions cannot be created for {_id} directly, but the following entities mention it and can be subscribed to with a focus on {_id}: {dict(results)}'

            result_notes[_id] += suffix
        else:
            result_notes[_id] = f'No results were found for {_id}, so nothing can be subscribed to.'

    # Pass the request to the subscription agent if have clear subscribeable entities, or go to answer_writer if not
    goto = 'answer_writer'  # the "bad" case; toggling away from it for the "good" case below
    if result_notes:
        state_output['confirmed_types'] = confirmed_types
        nice_notes = '\n\t- ' + '\n\t- '.join(result_notes.values())
        directly_subscribeable = [_id for _id, note in result_notes.items() if note.startswith(_id)]
        if all(note.startswith(_id) or any(dir_sub in note for dir_sub in directly_subscribeable) for _id, note in result_notes.items()):
            # ^^ i.e. every _id has to be either directly subscribeable or has to mention a directly subscribeable one
            state_output['processed_query'] = f'{state['processed_query']}\nID lookup results:{nice_notes}'
            goto = 'notification_agent_caller'  # the only "good" case
        else:
            state_output['private_note'] = f'The entities have been looked up, so now ASK THE USER what they would like to do based on these results:{nice_notes}'
    else:  # i.e. if no IDs were passed in; should be impossible since the previous node would not route here in that case; just being safe
        state_output['private_note'] = f'Tell the user that in order to create a subscription you need the ID of the entity they wish to subscribe to and what they would like to be notified about.'

    # Reroute to asking the user for clarification if related subscriptions exist (or add context if already asking them)
    ask_about_existing_subs = notification_topic.related_subscriptions and not notification_topic.user_override
    if goto == 'answer_writer' or ask_about_existing_subs:
        if ask_about_existing_subs:
            existing_subs_request = (f'There are existing subscriptions related to the current request, '
                                     f'so ASK THE USER whether they would like to proceed anyway considering these exist:'
                                     f'\n\t- {'\n\t- '.join(notification_topic.related_subscriptions)}')
            if goto == 'answer_writer':
                state_output['private_note'] = f'UPDATED MAIN GOAL(S):\n- {existing_subs_request}\n- {state_output['private_note']}'
            else:
                state_output['private_note'] = f'UPDATED MAIN GOAL: {existing_subs_request}'
        else:
            state_output['private_note'] = f'UPDATED MAIN GOAL: {state_output['private_note']}'
        goto = 'answer_writer'

    return Command(update=state_output, goto=goto)


def notification_agent_caller(state: GraphState, config: RunnableConfig):
    """Pass the query to the notification agent."""
    c = config['configurable']
    notification_topic = NotificationTopic(**state['notification_topic'])

    api = NotificationAgent(c=c)
    user_account = state['user_teams_email'] if c['source'] == 'Teams' else c['user_id']
    response = api.query(
        org=c['org'],
        user_id=c['user_id'],
        messaging_account=user_account,
        user_display_name=c['user_display_name'],
        query=state['processed_query'],
        message_history=state['message_history']
    )
    
    # Track subscription creation or manual closure based on response content
    if response:
        response_lower = response.lower()
        # Do not get back details of the involved subscription, otherwise would log the entity (not certain from state)
        properties = dict(distinct_id=user_account, user_display_name=c['user_display_name'], organisation=c['org'])
        if notification_topic.topic_is_subscriptions:
            # Only track the ID and type of the entity the subscription is about if there is no ambiguity about it
            properties['entity_id'] = e_ids[0] if len(e_ids := notification_topic.ids) == 1 else ''
            properties['entity_type'] = e_types[0] if len(e_types := state['confirmed_types'].get(e_ids[0] if e_ids else '', [])) == 1 else ''
            if (notification_topic.topic_is_subscription_set_up and
                any(x in response_lower for x in ['is set up', 'is now set up', 'been set up', 'successfully set up', 'I created', 'been created', 'successfully created'])):
                track_event('subscription_created', properties)
            elif any(x in response_lower for x in ['is closed', 'is now closed', 'I closed', 'been closed', 'successfully closed']):
                track_event('subscription_manually_closed', properties)
    
    return dict(response=response)


# Graph builder
def graph_builder() -> StateGraph:
    """Assemble the nodes into a graph builder.
    To get the actual graph need to `.compile()` the output (and then `.invoke()` or `.stream()` to use it).
    """
    # Note on explicit/implicit edges and their visualisation:
    #   - Some nodes handle processing paths directly by Command (and Send) objects, hence no edges need declaring/
    #   - However, those implicit edges would not be visualised in mermaid, so there the 'destinations' argument
    #       is precisely to annotate this information for visualisation purposes.
    #   - The 'destinations' argument accepts either tuples of node names or dictionaries where keys are node names
    #       and values are their edge labels.
    #       - If the edge label is None then there is no discolouring at the middle of the edge (discolouring occurs even for '').

    builder = StateGraph(GraphState, config_schema=ConfigSchema)

    builder.set_entry_point('parser')

    builder.add_node(parser)
    builder.add_edge('parser', 'router')

    builder.add_node(router, destinations=('retrieval_tool_picker', 'action_tool_picker', 'answer_writer', 'notification_topic_router'))  # handles own conditional edges

    builder.add_node(retrieval_tool_picker, destinations=dict(tool_executor='fan out', answer_writer=None))  # handles own conditional edges
    builder.add_node(action_tool_picker, destinations=dict(tool_executor='fan out', answer_writer=None))  # handles own conditional edges

    builder.add_node(tool_executor)
    builder.add_edge('tool_executor', 'sql_chooser')

    builder.add_node(sql_chooser, destinations=dict(sql_writer='fan out', router=None))  # handles own conditional edges

    builder.add_node(sql_writer)
    builder.add_edge('sql_writer', 'sql_executor')

    builder.add_node(sql_executor)
    builder.add_edge('sql_executor', 'router')

    builder.add_node(answer_writer)

    builder.add_node(notification_topic_router, destinations=('ids_for_subscriptions_getter', 'notification_agent_caller', 'answer_writer'))  # handles own conditional edges
    builder.add_node(ids_for_subscriptions_getter, destinations=('notification_agent_caller', 'answer_writer'))  # handles own conditional edges
    builder.add_node(notification_agent_caller)

    return builder


# with open(r'.\tests\graph.png', 'wb') as f:
#     f.write(graph_builder().compile().get_graph().draw_mermaid_png())


