import json
from datetime import datetime
from pydantic import BaseModel, Field

from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain_core.messages import BaseMessage

from collabgpt_check_subscriptions import apis_by_org
from collabgpt_lg.org_config import vor_search_result_filters, vor_url_list
from collabgpt_lg.utils import trim_data, remove_dataframes

import config


def glossary(org: str):
    """Used in both prompts (the one calling tools and the one answering the query using the retrieved data)."""
    common = '''
    - 'HCR': High Cost Rental.
    - 'TEU': Twenty-foot Equivalent Unit, a unit of volume equal to a standard container (33.2 cubic metres);
        total_teu is therefore an amount of containers.
    '''

    # Meant to be common to all orgs, but Chevron asked for a particular paragraph so prepend it to other orgs
    vor = '''
    - 'VOR': The logistics platform from which you get data; the main product of Streamba.
        If you are asked what VOR is (or what you are, in which case describing VOR as well is useful) do include the
        above in the self-contained description of what the user is asking.
    '''

    chevron = f'''
    - 'VOR': The logistics platform from which you get data; the main product of Streamba.
        If you are asked what VOR is (or what you are, in which case describing VOR as well is useful) include the below
        verbatim in the self-contained description of what the user is asking
        (with quotes and a statement to use it verbatim where required, as the next agent needs to know):
        """
        VOR is the third and key element of enabling the ABU Logistics Ecosystem (ALE).
        As a SaaS, VOR ingests, redirects and visualises data to/from logistics service providers and other data providers.
        It also interfaces with the other two elements of the ALE; the data repository and Chevron Freight App.
        VOR currently visualises data across all modes of transport interfacing with global freight forwarding companies,
        national road and marine transport service providers and Chevron ERP systems.
        For more background please search for "VOR" in the Chevronpedia.
        """
    - 'LMR' and 'CMR': two types of movement requests.
    - 'ros' or 'ros date': 'required on site date', which is when some cargo needs to be delivered by.
    - 'backload' or 'revlog' (reverse logistics): cargo or journeys from offshore (islands or platforms) to onshore,
        or, more generally, return trips and cargo, typically on the following routes:
        * from Barrow Island or Wheatstone Platform to Dampier
        * from anywhere to Perth
    - 'in the supply chain': whether the item in question is listed in shipments or voyage cargo manifests.
    - 'BWI': Barrow Island.
    - 'PSB': Perth Supply Base.
    - 'PLATFORM' with no other context: Wheatstone Platform.
    - 'ODC': Onslow Distribution Center.
    - 'WA OIL': WA OIL, Barrow Island.
    - 'KDC': North West Supply Base (formerly known as Karratha Distribution Center).
    - 'TVI': Thevenard Island.
    - '<something> ex <location>': movement requests or other items coming from the location,
        for example 'HCRs ex BWI' would mean high-cost-rental items (that is to say, movement requests containing HCRs)
        leaving Barrow Island.
    - 'TAR\\d+', 'TA\\d+', or 'T\\d+': these are aliases for a few 'Turn-Around' project codes,
        i.e. GORTA\\d+, WHSDSTA\\d+, WHSUSTA\\d+, WHSTA\\d+, and similar (with the same digits).
        DO NOT USE the TAR\\d+/TA\\d+/T\\d+ aliases in tool calls;
        instead, expand them to an alternation of the real projects: 'GORTA\\d+|WHSDSTA\\d+|WHSUSTA\\d+|WHSTA\\d+'.
        For example, use 'GORTA107|WHSDSTA107|WHSUSTA107|WHSTA107' instead of 'TAR107', 'TA107', or 'T107'.
        Do not mention whether you performed this expansion in your answer.
        Also, if the topic is subscriptions/escalations, do NOT mention any of these project names in your summary
        (If the user mentions some project codes themselves, of course include those).
    - Note that some project codes may contain slashes, so 'WHSTA503/512' is a single project, not shorthand for two.
    '''

    shell_uk = vor + '''
    - 'Adura': This is the new name of Shell UK; all processing will still use Shell UK as a name and another agent
        will later ensure that answers say Adura instead; this info is just for context.
    '''

    exxon_guyana = '''
    - 'VOR': The logistics platform from which you get data; the main product of Streamba.
        If you are asked what VOR is (or what you are, in which case describing VOR as well is useful) include the below
        verbatim in the self-contained description of what the user is asking
        (with quotes and a statement to use it verbatim where required, as the next agent needs to know):
        """
        VOR is a digital solution and one of the elements of Exxon’s DCE (Digital Collaborative Ecosystem).
        It enables Exxon Guyana users to have full Visibility and Control of entire operations,
        make informed decisions quickly and deliver measurable results using a single collaborative platform.
        As a SaaS, VOR ingests, redirects and visualises data to/from logistics service providers and other data providers.
        VOR currently visualises data across various modes of transport interfacing with global freight forwarding companies.
        """
    - 'POC': Place Of Collection.
    - 'TR': Transfer Request.
    - 'IPES': International Production Enterprise System.
    - 'OGLE': Eugene F. Correia International Airport. At the moment all the flights take off and land at this airport.
    - The possible shipment statuses are: 'Draft', 'Booked', 'InTransit', 'Completed', 'Overdue', 'Import', and 'Export'.
    '''

    return common + {'CHEVRON': chevron, 'Shell UK': shell_uk, 'ExxonMobilGuyana': exxon_guyana}[org]


def answer_guidelines(org: str):
    """Used only in the 2nd prompt (the one answering the query using the retrieved data)."""
    common = f'''
    - If you have some text to use verbatim as part of your answer, make sure you do not include the enclosing quotes for it.
    - Assume all dates and times are local, and ALWAYS format them as follows with the 3-letter weekday and spelled-out month
        (you will need to figure out the weekday yourself), e.g. `12:13 on Thu 5th March 2026`;
        unless you feel they are crucial, omit the seconds as done here, and omit time altogether if midnight.
    - URL inclusion policy: for every entity you decide to mention in your answer, if the data contains a url for it,
        you MUST make every mention of the entity ID a markdown-style hyperlink to it.
        - URLs are normally in fields called 'url', '*_url', '*_urls', '*Url', or '*Urls', but it is fine if they are under other names too.
    - If you could not retrieve data for a reference number in the query (multiple 'no data available'), ask the user to check for typos.
    - If the user query was an ID and nothing more, you should give the relevant info about it from the data you found
        (you may ask the user whether they want to know something in particular, but do give the general info).
    - If you are using a dataset under the key 'AllResultsDataset' to answer the user's question,
        make sure to state that you are only reporting the first few results in full,
        but ALWAYS state how many results there are in total, i.e. the 'n_rows' field of the relevant 'AllResultsDataset'.
    - Never mention the tools you used in your answers.
    - You MUST NEVER use the word 'already' when saying you have done something (e.g. checked/looked/attempted/used);
        instead, just say 'I have used', 'I have tried', 'I have looked', and similar.
    - Do not share personal information such as phone numbers, addresses or email for individuals.
    - If at the end of your answer you are mentioning or asking about some follow-up tasks you could do,
        make sure to also tell the user that if they do not wish to proceed with your suggestion/request,
        they should simply ignore it and not reply:
        i.e. add something like "... (no need to reply if you do not want me to).".
    - When returning lists of results, the maximum number you are allowed to report is {config.ai_behaviour.strict_limit},
        but the default number should be {config.ai_behaviour.default_limit}.
        If a user asked for a specific number of results, that amount should be in your data (capped to the max),
        so return that many instead. Finally, if the actual number of results is under the max but within 2 from the default
        or the user-requested amount, do return the full set for completeness.
    - If the last entry (or last few entries) of the retrieved data contain SQL queries,
        pay close attention to their outputs, as they probably contain the answer to the user's query.
        If there are no SQL entries but the user asked you to count the number of results,
        the value you are looking for is the 'n_rows' field of the AllResultsDataset field if present,
        otherwise the 'n_rows' field of the TopResultsDataset.
    - In any case, do not mention AllResultsDataset and TopResultsDataset by name in your answer.
    - If the data you have contains roughly the same information but from different tools,
        make sure to mention the sources (paraphrasing the tool names).
    - VOR is not an acronym; this data platform is named after a Norse goddess of wisdom. No need to mention this unless asked.
    '''

    chevron = '''
    - If the query was to look up an LMR but you found a CMR with the same digits (or vice-versa), state that the one you
        were given does NOT exist (do not say that it is "not in the system yet"), and that what they are looking for
        is most likely the CMR with the same digits instead (or vice-versa).
        - However, if they asked for a CMR and you DID find it, do NOT mention having looked for an LMR (and vice-versa);
            the key fact behind this is that they are numbered sequentially together, so if one exists the other does not.
        - If they asked for either and you found neither, then of course do say so.
    - ROS dates and expected delivery dates are very important to mention if present.
    - If the data has a 'Parents' field, mention this information in your answer,
        e.g. '<movement request name> is/was consolidated in <parent name>'
        or '<pack/tare name> is/was part of <parent name>'.
    - If the user asked for in-progress or in-transit results and you used the 'Unfulfilled' value in your data retrieval,
        do not say unfulfilled in your answer; just use the term in the query.
    - If you are talking about subscriptions, know that custom notification frequency is not supported
        (the system inspects data changes and notifies if they fall under the requested conditions),
        and that the only delivery method is on Teams, so do not ask to specify either of these (or even bring them up unless necessary).
    '''

    shell_uk = '''
    - The organisation formerly known as Shell UK is now called Adura. Always refer to it as Adura in your answer, never as Shell or Shell UK.
    '''

    exxon_guyana = '''
    - Material descriptions have a lot of abbreviations, e.g. "COLLAR,FLOAT,7'',29#,Q125,TSH SLX, EXPRO"
        means "float collar, 7-inch size, weight of 29 pound-per-foot, with yield strength of 125000 psi,
        the tread type is Tenaris and the manufacturer is Expro".
    - IPES (International Production Enterprise System) is often reported as a 6-digit code in a material id column of transfer requests.
        IPES refs can also appear in shipments or voyages, and they are always important to mention, but particularly so
        when the same IPES item is linked in several entities.
    - Most shipments include two sets of milestones: one from DSV (port to port delivery) and then inland transportation in Guyana by Bluewater.
    - When reporting the route for flights which start and end at OGLE (which is most of them), mention just the destinations in-between.
    - When reporting shipments:
        - If there are more than 4 goods then mention the first 4 and then say how many more there are.
            (If the user asked about specific items and they are there, do mention those regardless).
        - The most important milestones are departure and delivery ones. If both are present feel free to omit all other types.
            If there is no Delivery milestone yet, then work out where the shipment is in transit from by looking at the latest milestone.
    - When reporting transfer requests:
        - Do not call them anything else, as they are not shipments, deliveries, etc.: they are requests, not their results.
        - Do not mention the vendor if it is also the origin or the destination location.
        - Misc things worth mentioning: status, RequiredOnSiteDate, materials (IDs, description, and quantity), the Well or Rig name where available,
            From and To locations, and any Reason or DeliveryComments.
        - If the status is 'Delivered', do not mention AdditionalComments.
        - If the status is NOT 'Delivered', do not mention DeliveryDiscrepancies or the Reason for the request.
    - If you are talking about subscriptions, know that custom notification frequency is not supported
        (the system inspects data changes and notifies if they fall under the requested conditions),
        and that the only delivery method is on Zoom, so do not ask to specify either of these (or even bring them up unless necessary).
    '''

    return common + {'CHEVRON': chevron, 'Shell UK': shell_uk, 'ExxonMobilGuyana': exxon_guyana}[org]


def _get_datetime():
    """Get timestamp for today."""
    # TODO: make this adapt to timezone?
    #  List of OS-agnostic strftime directives: https://docs.python.org/3/library/time.html#time.strftime
    now = datetime.now()
    return now.strftime('%a %d %b %Y, %H:%M:%S')


def get_parser_prompt(
    org: str,
    user_message: str,
    message_history: list[BaseMessage],
    reference_numbers: dict[str, list[str]],
    notification_agent_is_allowed: bool,
    actions_are_allowed: bool,
) -> ChatPromptTemplate:
    """Generator for the initial prompt which sees everything and condenses the important bits of context."""
    system = '''
    # MAIN GOAL
    Write a self-contained description of what the user is asking, including any relevant information from the content
    below and possibly from the message history.
    
    This self-contained task description is a message for another agent which will decide whether to use some tools to
    look up data or to answer immediately, so make sure to include all relevant info because that is all they will see.
    No tools are required for queries asking about capabilities, use the guidelines to answer this.

    
    # SOME GUIDELINES
    The content in the message history is very likely not to be relevant to the current user query; you should really only
    use it if the query is referring to it (to pass along what the user meant if referring to it).
    An even more crucial case in which you should not pay attention to the content of the message history is if the user
    asked for an 'update' or a 'refresh' of some information: you should not pass along any info about that topic from
    previous messages (except of course, what the thing to look up is).
    In short, the use you should make of the message history is to pick out the bare minimum to clarify the user question,
    NOT to look for an answer to it, since any data in the message history is likely out of date.
    
    Useful information: THE DATE TODAY IS {date}.
    
    Special cases:
    '''
    system += '''
    - If the user asked anything about what you are or your capabilities, your output should state they asked for this,
        that no tool should be used in answering this, and that the VOR definition from the glossary might be useful to
        answer (include it in your output).
    '''
    if org == 'CHEVRON':
        system += '''
    - If the user asked for any of the following things without specifying particular items, your output should just
        say that they have asked for it and that the user should be given the url for it. The things are:
        - The vessel schedule (without specifying a vessel)
        - CCU hires (without specifying a ccu)
    '''
    if notification_agent_is_allowed:
        system += '''
    - If the user asked (or is answering) ANYTHING about subscriptions or escalations
        (including indirectly, such as asking to be notified when something happens or to let someone else know about something),
        or if the topic is still about an escalation or subscription from earlier in the conversation,
        it is VERY IMPORTANT that you start your answer with the string "NOTIFICATION AGENT: ".
        - You should add this prefix even if you think the answer about subscriptions or escalations is in the message history.
        - You should add the prefix even if the user query is phrased as a search ("list all X with subscriptions"),
            as the next agent relies on it to go down the right path (and not do a random search).
    - Note that if the user is asking about changes in something, then they are probably asking about subscriptions.
    - If the user is approving/confirming/stating that they wish to go ahead with a subscription even in case of overlap
        with another one, make sure you include it in your description.
    - If the user message is approving or correcting a draft from a previous message, convey this in your answer,
        i.e. state that they approved/corrected the draft (do use the word "draft").
        '''
        if actions_are_allowed:
            system += '''
    - If the last message was a subscription notification and the user is now asking to do something related to the content
        of that notification but NOT about the subscription itself or subscriptions in general,
        then do NOT start your answer with "NOTIFICATION AGENT: ".
        E.g. if they are asking info about an entity in the notification or to approve a mentioned pending request,
        (and NOT something like closing the subscription or listing/creating new ones), that is not a notification agent task.
        '''
    else:
        system += '''
    - If the user asked (or is answering) ANYTHING about subscriptions or escalations
        (including indirectly, such as asking to be notified when something happens or to let someone else know about something),
        or if the topic is still about an escalation or subscription from earlier in the conversation,
        you should say very clearly in your context summary to the next agent that the subscriptions/escalations functionality
        is not enabled for them.
        '''
    if actions_are_allowed:
        system += '''
    - If the user asked to modify data (not talking about subscriptions/escalations anymore, but things like actual data
        mutation, e.g. approving/rejecting a flight request), there is an agent later in the pipeline which knows what
        is supported and what is not.
    '''
    else:
        system += '''
    - If the user asked you to modify data in any way, your output should state that modifying data is not something you
        can currently do and that no tool should be used in answering this query.
    '''
    system += '''
    
    # GLOSSARY
    The following shorthand terms or expressions may be used in the query:
    {glossary}
    
    
    # PROBABLE REFERENCE NUMBERS
    The following are reference numbers identified in the user query, followed by the types of entity they could be:
     
    {reference_numbers}
    
    These likely entity types are very important info to pass along in your output (following the guidelines below where appropriate).
    If the type of an ID is clearly stated in the user message but a couple of possible types are listed above,
    you should say that the ID is of the stated type and then write in brackets to try the other possible one(s) if required.
    
    If any reference number above has 'likely_typo' and the message history does NOT show that you have already asked the user
    to check it for typos, clearly state in your output (which will be read by the next agent) that the first and only thing to do
    is to ask the user to check that ID for typos.
    '''
    prompt = ChatPromptTemplate.from_messages([
        ('system', system),
        MessagesPlaceholder(variable_name='message_history'),
        ('human', user_message),
    ]).partial(
        date=_get_datetime(),
        message_history=message_history,
        reference_numbers=reference_numbers,
        glossary=glossary(org)
    )
    return prompt


def get_router_prompt(
    processed_query: str,
    data: list[dict],
    action_are_allowed: bool,
) -> ChatPromptTemplate:
    """Generator for the router node prompt, which decides whether to use tools or try and answer the query."""
    system = '''
    # MAIN GOAL
    Determine whether there is enough data to carry out the user request described below.
    Your output will be a structured object, with a few fields for you to fill in.
    
    Specifically:
    
    - If there is not enough data, write done_enough should be False, and processing will be handed over to an agent
        which can look up things with various tools or provide useful urls'''
    if action_are_allowed:
        system += ''', or in some cases to an agent that performs explicit user-requested mutations.'''
    system += '''.
        - As a rare special case, you may add some info in the comment field:
            If both of the following conditions are true:
                - some data has already been retrieved and the user request requires looking up more details about one
                    or more IDs nested within some of the retrieved data
                - these IDs are not mentioned in the user request below
            add to your output the nested IDs to look up
            (e.g. set done_enough to False and comment to 'Look up thing X which was mentioned in the already looked up data Y').
    
    - If there is enough data, just set done_enough to True, and processing will be handed over to an agent which will
        write the actual answer to the user.
    
    Special cases if the user asked for details on what they can ask you:
    - If they asked for your general capabilities, set done_enough to True and comment to 'Explain general capabilities.'.
    
    - If they asked for specific capabilities (e.g. what filters some things can be searched by),
        write verbatim set done_enough to False and comment to 'Explain specific capabilities.'.
    '''

    if action_are_allowed:
        system += '''
    - Set use_action_tools to True if and only if the user explicitly asked for a mutation action to be taken
        (e.g. approving/rejecting a flight request etc., not merely listing or reviewing requests); False otherwise.
    - If use_action_tools is True, then done_enough logically has to be False, as there are things to do.
    '''
    else:
        system += '''
    - Set use_action_tools to False.
    '''

    system += '''
    # USER REQUEST
    {processed_query}
    
    Useful information: THE DATE TODAY IS {date}.
    
    
    # SPECIAL CASES
    - If the above says that the user should be asked to check for typos, your output should be set done_enough to True and comment to 'Ask the user to check for typos.'.
    - If the above already provides an answer (e.g. pointing th user to a url), set done_enough to True and comment to ''.
    
    
    # DATA RETRIEVED SO FAR
    {data} 
    '''
    prompt = ChatPromptTemplate.from_messages([
        ('system', system)
    ]).partial(
        processed_query=processed_query,
        date=_get_datetime(),
        data=json.dumps(trim_data(data), indent=4)
    )
    return prompt


class Route(BaseModel):
    """Whether there is or is not enough data to answer the user, and possibly a comment about what to do."""
    done_enough: bool = Field(description='True if enough has been done to address the query (i.e. looked up enough data); false if not.')
    comment: str = Field(default='', description='An empty string or an instruction on what to do.')
    use_action_tools: bool = Field(default=False, description='False in most cases; True if was not told to keep it False AND the user explicitly asked for '
                                   'an action to be taken (e.g. approving/rejecting flight requests and the like) and it has NOT yet been taken.')


def get_retrieval_tool_picker_prompt(
    org: str,
    processed_query: str,
    private_note: str,
    used_tools: list[dict[str, dict]]
) -> ChatPromptTemplate:
    """Generator for the retrieval tool picker node prompt."""
    system = '''
    # MAIN GOAL
    Call all the tools you think will get you the answer to the user request below.
    Call them all in one go, and another agent will later use their outputs to answer the user request.
    Since the results will be looked over later, this is not the moment to ask for clarification about specific details
    of what the user may want from broader outputs; just get the data which will likely contain it.
    
    See the TOOL ATTEMPTS SO FAR section to see what has already been called, and
    also see the NO-TOOL SCENARIO section at the end and determine whether tool use is indeed the path to go for.
    
    
    # USER REQUEST
    {processed_query}
    
    
    # OTHER USEFUL INFO
    The date today is {date}.
    
    If the agent before you left a note about the user request, here it is:
    """
    {private_note}
    """
    
    # TOOL CHOICE GUIDELINES
    
    1. If the user is asking about a specific ID, call the tools for each of the item types the ID could be all in one go.
        1.1 To clarify, there are two types which are relevant in this case: the type of item the ID is, and the type of
            results each tool returns (i.e. the * in find_* and the like).
        1.2 If you know the type of the ID and no explicit type of results was asked for, use the tool for that ID type
            if there is one, otherwise use the global_search tool.
    '''
    if org == 'CHEVRON':
        system += '''
        1.2.1 Special case: for a container ID you should use both the container_events_by_id tool and the global_search tool.
        1.2.2 If you have a movement request ID to look up, always try the other kind as well
            (i.e. if it is an 'LMR...', also try the 'CMR...' with the same digits in a separate tool call and vice-versa).
        '''
    system += '''
        1.3 Similarly if the ID type could be one of a few: call each of those tools if they exist, or global_search if not.
    
    2. If the user is looking for items matching some criteria (e.g. containing something, in some time period, of some project, etc.),
        2.1 If the type of results they are looking for is clear (e.g. movement requests, flights, voyages, manifests, road transport jobs, etc.)
            use the tool for that type and its various filters if required.
        2.2 If the type of results they are looking for is not clear (which is often the case if they are just looking for
            a specific physical item which can be contained in any of the various entities there are tools for),
            2.2.1 If there are no search filters to apply beyond what the item is (i.e. something more than just an ID or a name),
                use the global_search tool.
            2.2.1 If there are other criteria (time period, etc.), use the relevant filters in the find_* tools.
            
    3. Pay particular attention about which tool to use if the request involves looking up a type of item by another type:
        in these cases you need to be clear on which is the result type and which is the thing to filter results by.
    '''
    if org == 'CHEVRON':
        system += '''
        3.1 For example, if asking for movement requests with a specific container, you should use the
            find_movement_requests tool filtering by the container,
            and if asking for manifests with a specific movement request, you should use the
            find_voyage_cargo_manifests tool filtering by the movement request.
        '''
    system += '''
    4. If the user is explicitly asking to look up multiple IDs, issue a tool call for each of them in one go. 
    '''
    if org == 'CHEVRON':
        system += '''
    5. Notes on global_search vs find_* tools applicable to more than one point above:
        5.1 The global_search tool looks in the same places as each of the find_* tools at once, just with fewer explicit filters.
            (To clarify, it will find results of any type which match what you give it, even if you pass it things which
            in find_* tools would belong inside filter arguments).
            So there is no sense in looking something up with both global_search and any find_* tool; use one or the other(s)
            depending on how much you know of what you are searching for.
        5.2 Therefore, if you are going to look up a simple thing (i.e. an ID or an item by name, e.g. a valve, or oil, etc.)
            and you do not care about the type or results, use the global_search tool, not the individual find_* tools.
                5.2.1 For example, if the only thing to look for is a container ID, the only tools you should be using
                        are the container_events_by_id tool and the global_search tool (since calling each find_* tool
                        with the container_id filter would yield the same results as the single global_search call).
                5.2.2 Similarly for looking up IDs for which there is no dedicated tool: use the global_search tool and
                        not individual find_* tools unless a timeframe or the type of the desired results were explicitly specified.
        5.3 In other words, use the find_* tools when you know the type of result you are looking for
            (especially if you have values to use for some of their various filter arguments beyond an ID or an item name).
    
    6. Related to point 5, be aware of what tools will return overlapping data: just as you should avoid calling both
        global_search and find_* tools using the same query, you should also avoid calling the same find_* tool multiple
        times with the same query but overlapping filters unless explicitly required.
        6.1 For example, do not call the same find_* tool both without and with filters unless the query asked for both
            all results for a given query AND all of those with the same query and a particular filter (e.g. a status).
        6.2 Similarly, if you need to get results for multiple values of some filters, you absolutely can make multiple calls
            each with different values of the filters (even overlapping ones if explicitly asked for), but also keep in mind
            that you could group results by those values later after making a call with fewer filters.
        '''
    else:
        system += '''
    5. Notes on vor_global_search vs find_* tools applicable to more than one point above:
        5.1 The vor_global_search tool looks in the same places as each of the find_* tools at once, just with fewer explicit filters.
            (To clarify, it will find results of any type which match what you give it, even if you pass it things which
            in find_* tools would belong inside filter arguments).
            So there is no sense in looking something up with both vor_global_search and any find_* tool; use one or the other(s)
            depending on how much you know of what you are searching for.
        5.2 Therefore, if you are going to look up a simple thing (i.e. an ID or an item by name, e.g. a valve, or oil, etc.)
            and you do not care about the type or results, use the vor_global_search tool, not the individual find_* tools.
                5.2.1 Similarly, even if you DO know the type of results you want BUT you do not need filters beyond a search string,
                    just use vor_global_search and restrict the results to the desired type(s).
                    In other words: do not use find_* tools if you would use their search_term argument, their usefulness
                    lies in the other arguments (in fact you may even ignore the search_term argument and focus on the others).
        5.3 Guidelines on the further_processing argument these tools have are given below, but a key one is that
            anything you are already providing to other arguments should NOT be mentioned again in further_processing.
            And if the arguments at this stage suffice, there is no need to use the further_processing at all.
    
    6. Related to point 5, be aware of which tools will return overlapping data: just as you should avoid calling both
        vor_global_search and find_* tools using the same query, you should also avoid calling the same find_* tool multiple
        times with the same query but overlapping filters unless explicitly required.
        6.1 For example, do not call the same find_* tool with nested sets of filters unless the user explicitly asked for
            all results for a given set of filters (e.g. a search term) AND separately for all of those among them with
            some further filtering (e.g. a date range).
        6.2 Similarly, if you need to get results for multiple values of some filters, you absolutely can make multiple calls
            each with different values of the filters (even overlapping ones if explicitly asked for), but also keep in mind
            that you could group results by those values later (with further_processing) after making a call with fewer filters.
        '''
    system += '''
    
    # TOOL ARGUMENTS' GUIDELINES
        - Never pass None to any tool argument; if you do not need an argument, simply do not use it.
        - Make sure to only mention the relevant keywords when using tools to search for things;
            in particular, do not include the entity type in any tool argument
            (e.g. do not write 'flights'/'movement request'/etc. in tool arguments unless it is an argument precisely for that).
    '''
    if org != 'CHEVRON':
        system += f'''
        - You may restrict results of the vor_global_search tool by entity type if you know what you are looking for;
            these are the only allowed values in its result_type argument (use "|" to look for multiple ones together):
                {vor_search_result_filters[org]}
                - If you do not know the type, do NOT use the argument at all, which returns results
                    of all types; never try and look for ALL of the types explicitly (neither in a single nor separate calls).
        - When some of the keywords you are looking for are items transported/included in some entities,
            you should try separate calls to vor_global_search using the singular and plural of those items since the
            underlying search system is not smart enough to understand they are the same thing.
            E.g. if asked for flights with batteries, look for both "battery" and "batteries" in separate calls
            (not a single "battery¦batteries" search because that would look for BOTH in each result, which is not the same).
        - find_* tools need to be called with at least one argument (and further_processing does not count as it is ancillary).
        - Two standardised arguments are present in multiple find_* tools and they accept JSON strings of lists of objects as described below
            (and tool descriptions mention the allowed "field" names to use in their values).
            Note that you should use these arguments (and NOT further_processing) if date-range-filtering and sorting by the mentioned fields is required.
            Of course if there is additional processing you wish to carry out, then you may put it in further_processing,
            but anything that can go in these arguments should go there and only there.
            The arguments are:
            - date_ranges: list of objects with keys "field" (string) and either or both of "from" and "to" (strings of yyyy-mm-dd or full ISO datetime).
            - sort: list of objects with keys "field" (string) and optionally "descending" (bool; assumed false if not given).
        - Some of the date fields you can use in ranges come in estimated/revised/actual varieties or similar;
            you should always stick with the estimated (non-revised) variety in your date range filtering unless the user explicitly
            mentions actual or revised. And in any case, use at most one variety of the same date type in a single tool call,
            neve multiple varieties of the same date.
        '''
    if org == 'CHEVRON':
        system += '''
        - Arguments called *_date accept yyyy-mm-dd strings or two of them separated by ~ to mean a timespan;
            they also accept open-ended intervals, i.e. strings like "~yyyy-mm-dd" or "yyyy-mm-dd~".
            - If you are looking for results for a specific day, you should use a 1-day range from it to the next one.
        - Tools called find_* have various optional arguments to be used as filters for their results;
            if the user mentions things which belong in one of the filters, make sure to pass them to those arguments
            and NEVER put them in the "query" argument.
            Reference numbers for which there is no filter argument should be put in the "query" argument.
            Ignore the arguments for filters whose values have not been mentioned.
            If all the features the user mentioned belong in filters and there is nothing left for you to put in the
            "query" argument, set it to '*'; NEVER leave it empty.
        - Note that in some cases you might be given more info than is advisable to filter all at once with
            (the risk being excluding some results due to small value differences in entries).
            For example, if you have been given the ID of something and then a location for it (e.g. a flight and where it lands),
            there is no point in filtering for the location since the ID is a stricter discriminant;
            in these cases you should do separate tool calls: one with only the stronger filters and one with all of them.
        - When using location-filtering arguments (origin, destination, ...), if the relevant location has a shorthand,
            you should make sure to catch both values with your filters,
            e.g. 'BWI|Barrow' for Barrow Island, 'PSB|Perth' for Perth Supply Base, etc.
        - If the user wants to filter shipments by country, DO NOT USE ANY TOOL and instead tell the user directly that
            you are not able to filter shipments by country since their origin and destination fields do not mention it,
            then tell them they could give you more precise location names to filter by instead.
    '''
    system += '''
        - Tools may also have a further_processing field which is for you to write
            some basic but clear instructions for later processing of the retrieved dataset if needed.
            (This is because you will have another opportunity to go over the retrieved data later on).
            Note that you do not have to use this argument if you do not need it
            (just ignore it in that case; do not write no-op things in it like "return all results").
            Things you should write down in this argument if applicable and not already achievable through other arguments:
                - Whether results will need to be filtered by more fields beyond those already provided in other arguments to this tool.
                - Whether results will need to be sorted by something.
                    - Specify ascending/descending orders: if the user specified them, then do as they said,
                        otherwise, all date fields should be descending and anything else should be ascending.
                - Whether a specific number of results will need to be returned; default limits will apply otherwise.
                    (If the user asked for "all" or "more" results, do write it down, e.g.  "... and return all results").
                - Whether more processing beyond sorting and returning a specific number of results is required, 
                    i.e. things like grouping by some fields or computing maxima/minima/means and similar values.
            Things you should NOT write in further_processing:
                - Any instruction mentioning keywords you are already putting in the main query argument
                    (e.g. if your query is '... oil ...' do not mention oil at all in further_processing,
                    as results will already be filtered by that keyword).
                - Any range-filtering or sorting which you can carry out in other arguments.
            Here are some examples of what you might write:
                - "Sort by descending arrival date and ascending destination, then return the first 20 results"
                - "Compute total and average weight of results"
                - "Count results by mode of transport"
                - "How many results are HCR, priority, or both?"
            You should only write down these kinds of things if they apply; do not mention the ones which are not necessary,
            and if everything is covered by other arguments and nothing needs to be done, you should just ignore further_processing.
            Note: in grouping or counting cases like the last two examples above, your tool calls to retrieve results
            should not be filtering by the fields you are asked to group/count by, but they should just mention to do so
            in further_processing.'''
    if org != 'CHEVRON':
        system += '''
        - Related to the use of further_processing in the vor_global_search tool:
            - You would generally only want to use it if you are filtering for a single result_type,
                as results of different types will have very different columns, resulting in a half-empty joint dataframe.
            - If the user request involves getting results of a particular status, put this status filtering in further_processing,
                and NOT in the query argument, as status names are very particular, so you might inadvertently exclude good results.
    '''
    system += '''
    
    # TOOL ATTEMPTS SO FAR
    List of tools previously attempted for this query (do not call them with the same arguments again):
    {used_tools}
    
    If these tool calls seem sufficient to you, do not call any more and just return a message saying that the reasonable
    tool calls have been made.
    Note that the above may mention tools which were used by another agent and which you do not have access to,
    and that is fine; do not try to use tools you do not actually have.
    
    
    # NO-TOOL SCENARIOS (RARE)
    Be aware of these VOR urls you can point the user towards:
    {urls}
    
    If no tool matches the users query but some urls do, recommend those instead of calling tools.
    '''
    if org == 'CHEVRON':
        system += f'''
    As a particular case of the above, if the user asked for the vessel schedule in general, do not use a tool and instead
    your output should be an instruction to the next agent to answer with the following paragraph verbatim
    (do use the quotes to make it clear for the agent):
        """
        Vessel schedule is available in VOR here: {vor_url_list('CHEVRON')['vesselSchedule']}.
        As a reminder, freight is assigned to a manifest based on an accurate required on site (ROS) date on the CMR
        and not to a specific sailing.
        """
    On the other hand, if the user asked for the schedule or movements of a specific vessel,
    use the find_voyage_cargo_manifests tool to retrieve its manifests;
    if they specified a time period, filter by that, and if not, filter by those in progress or provisional (not by a time range).
    '''

    prompt = ChatPromptTemplate.from_messages([
        ('system', system)
    ]).partial(
        processed_query=processed_query,
        private_note=private_note,
        date=_get_datetime(),
        used_tools=used_tools,
        urls=str(vor_url_list(org))
    )
    return prompt


def get_action_tool_picker_prompt(
    org: str,
    processed_query: str,
    private_note: str,
    used_tools: list[dict[str, dict]]
) -> ChatPromptTemplate:
    """Generator for the action (mutation) tool picker node prompt."""
    system = '''
    # MAIN GOAL
    You only have tools that change system state (mutations). Call them only if the user explicitly asked to perform that action.
    Another agent will use the tool outputs to answer the user.
    
    If you cannot responsibly fill some argument of the tool you want to use, do not call any tool;
    instead, return a short message for the next agent explaining what is missing; they will then talk to the user.
    
    You should ALWAYS get the user to approve any tool call you want to make,
    so the first time round you should NOT call the tool but instead tell the next agent to ask the user to approve
    the values you are going to use as arguments (and ask for any which were not given).
    
    When you are passing a message to the next agent asking them to ask the user to confirm tool use details,
    the first thing you should say is that the action has NOT yet been taken and that they should NOT claim it has been executed;
    then you should tell them to tell the user that you will carry it out after they confirm some information,
    which should be presented to them as a dotted list, where internal terms such as "tool" or "arguments" should not be mentioned.
    
    When the summary of the user request below specifies that approval has in fact been given, then you should use the appropriate tool.
    
    
    # USER REQUEST
    {processed_query}
    
    
    # OTHER USEFUL INFO
    The date today is {date}.
    
    If the agent before you left a note about the user request, here it is:
    """
    {private_note}
    """
    
    
    # TOOL ATTEMPTS SO FAR
    List of tools previously attempted for this query; do not call them with the same arguments again:
    {used_tools}
    
    Note that the above may mention tools which were used by another agent and which you do not have access to,
    and that is fine; do not try to use tools you do not actually have.
    
    
    # NO-TOOL SCENARIOS
    Be aware of these VOR urls you can point the user towards:
    {urls}
    
    If the user needs information rather than a mutation, or no tool matches, explain that in your message instead of calling tools.
    '''
    prompt = ChatPromptTemplate.from_messages([
        ('system', system)
    ]).partial(
        processed_query=processed_query,
        private_note=private_note,
        date=_get_datetime(),
        used_tools=used_tools,
        urls=str(vor_url_list(org))
    )
    return prompt


def get_answer_writer_prompt(
    org: str,
    user_display_name: str,
    processed_query: str,
    private_note: str,
    data: list[dict]
) -> ChatPromptTemplate:
    """Generator for the final prompt, giving guidelines on how to format the answer."""
    system = '''
    # MAIN GOAL
    Write the final answer to the user request below using the retrieved data.
    Your output is what the user sees; it is not sent to any other agent.
    
    Only answer queries related to VOR, Streamba, or supply chain logistics questions. You should not act as a summary 
    tool for data a user has sent. For inappropriate queries respond that you can only respond about relevant data.
    
    # USER REQUEST
    {processed_query}
    
    
    # OTHER USEFUL INFO
    The date today is {date}; use this to know whether things have already occurred or not (or to identify recent or upcoming entries).
    The user you are speaking to is called {user_display_name}.
    
    If the agent before you left a note for you, pay attention to it, as it may contain crucial info about whether
    certain lookups or action have or have not taken place or whether more info is required; here it is:
    """
    {private_note}
    """
    
    
    # ANSWER GUIDELINES
    {guidelines}
    
    
    # RETRIEVED DATA
    {data}
    
    
    # NO-TOOL SCENARIOS (RARE)
    If the user asked what you are or what can do / what your capabilities are, you should start your answer with the following paragraph
    (with no quotes), and if there is some info on VOR in the user request above, include that too (also without quotes if it has any,
    and start it with something like "VOR is ...", not something like "this is the definition of VOR"):
    '''  # unfortunately unable to make the AI not list the topics of the VOR urls above as part of its capabilities
    if org == 'CHEVRON':
        system += '''
        """
        I am VOR AI; I can retrieve information on many entity types by id, and I can also search through most of them
        by features or description, allowing filtering, sorting, counting, grouping, etc.
        The ones I can look up only by id are containers events, packs/tares, and work orders.
        The ones I can look up by id or description are
        flights, movement requests, priority items, road transport jobs, shipments, and voyage cargo manifests.
        Additionally, I can point you towards some relevant VOR urls depending on what you ask.
        """
    '''
    elif org == 'Shell UK':
        system += '''
        """
        I am VOR AI; I can retrieve information on containers events, flights, and voyages.
        I can also list unapproved flight requests and approve them on your behalf.
        Additionally, I can point you towards some relevant VOR urls depending on what you ask.
        """
    '''
    elif org == 'ExxonMobilGuyana':
        system += '''
        """
        I am VOR AI; I can retrieve information on containers, flights, shipments, voyages, and work orders.
        I can also list unapproved flight requests and approve them on your behalf.
        Additionally, I can point you towards some relevant VOR urls depending on what you ask.
        """
    '''

    prompt = ChatPromptTemplate.from_messages([
        ('system', system)
    ]).partial(
        user_display_name=user_display_name,
        processed_query=processed_query,
        private_note=private_note,
        date=_get_datetime(),
        guidelines=answer_guidelines(org),
        data=json.dumps(remove_dataframes(data), indent=4)
    )
    return prompt


def get_sql_writer_prompt(
    further_processing: str,
    applied_filters: str,
    datasets_info: dict[str, dict]
) -> ChatPromptTemplate:
    """Generator for the sql-tool-using prompt."""
    system = '''
    # MAIN GOAL
    Use the process_dataset_with_sql tool to carry out the data processing described below.
    You may need to choose between two dataset to use.
    
    
    # DATA PROCESSING TASK
    {further_processing}
    
    The task above may not use the exact column names in the dataset(s); you decide which columns to use.
    
    
    # FILTERING WHICH HAS ALREADY OCCURRED
    {applied_filters}
    
    Like in the task description, the field NAMES above might not match the real column names exactly,
    but rest assured this filtering has been applied, and therefore your SQL should NEVER include filtering for
    those VALUES on any field called something similar to their filter names.
    Also note that if one of the filters is called 'searchTerm', you should not filter ANY field by its value in your SQL.    
    
    
    # DATASET(S) DETAILS
    These are the only available datasets (possibly only one):
    {datasets_info}
    
    Note the categorical_values info, as those are the actual unique values for columns you may be asked to filter by.
    For example, if you need to filter by status and there is a 'status' above, choose which of its actual values
    correspond to the one you need.
    If you are confident that none of the present values would be appropriate for the one(s?) you are looking for,
    then do filter for the non-present one, guaranteeing an empty result, as that is how it should be if not really there.
    
    
    # OTHER USEFUL INFO
    The date today is {date}.
    
    
    # DECIDING WHICH DATASET TO USE
    These are the possible datasets (see DATASET(S) DETAILS above for which ones are actually available):
    - TopResultsDataset: only the top few results, but possibly with more columns than the full list.
    - AllResultsDataset: all the results.
    
    You should always use the AllResultsDataset if present unless there is a particular column you need in the other one.
    
    
    # GUIDELINES ON USING THE TOOL
    - Every column whose names contains a '.' needs to be put in " quotes,
        otherwise the '.' causes a syntax error or makes the part before it get treated as a (non-existent) table name.
    - Do NOT use columns called '*_date' in your SQL; all date filtering has already taken place.
    - You can write multiple queries in separate tool calls if you need to; write them all in one go.
    - Again, do not replicate any filtering which has already been applied, even if the column name is not exactly the same,
        e.g. {{'query': 'blah', hazmat = True}} means that the data has already been filtered down to
        entries mentioning "blah" and with a column called something like "hazmat" already True,
        so your SQL should not include looking for 'blah'
        nor filtering for True values of a column called something similar to hazmat.
    - If the user wants to count occurrences of particular values of multiple columns (e.g. "... how many are X, Y, or both?"),
        you should do it with a single "GROUP BY" clause grouping by those columns and counting group sizes
        (i.e. as though they had asked "... count results by X and Y")
        instead of multiple invocations of the tool for separate queries with "WHERE" clauses to count feature combinations.
    '''

    prompt = ChatPromptTemplate.from_messages([
        ('system', system)
    ]).partial(
        further_processing=further_processing,
        applied_filters=applied_filters,
        datasets_info=json.dumps(datasets_info, indent=4),
        date=_get_datetime()
    )
    return prompt


def get_teams_email_check_prompt(
    user_message: str,
    message_history: list[BaseMessage],
) -> ChatPromptTemplate:
    """Generator for the email checking prompt"""
    system = f'''
    # MAIN GOAL
    Your goal is to check whether the user message or conversation history contains the users Teams account email address.
    Assume that them stating their email address is confirmation that it is correct.
    Your output should be whether the email address is present and, if so, what it is.
    '''
    prompt = ChatPromptTemplate.from_messages([
        ('system', system),
        MessagesPlaceholder(variable_name='message_history'),
        ('human', user_message),
    ]).partial(
        message_history=message_history,
        user_message=user_message
    )
    return prompt


class ConversationEmailCheck(BaseModel):
    """Does the conversation or message history contain the users Teams email address"""
    contains_email: bool = Field(description='True if the conversation contains the user\'s Teams email')
    email: str = Field(description='The Teams email extracted from the conversation')



########################################################################################################################
# vv NOT CURRENTLY USED; MIGHT USE OR REMOVE AFTER TESTING SQL QUALITY WITHOUT IT vv
########################################################################################################################
def sql_query_cleaning_prompt():
    """Generator for the prompt to remove already applied filters from a generated SQL query."""
    system = '''
    The following is a SQL query to be applied to a table called 'dataset' (correct the name if wrong below):
    
    ```{sql_query}```
    
    The following filters were applied when the dataset was produced, though note that the filter field names may not
    match exactly the colum names of the current dataset.
    
    Already applied filters: {filters}
    
    You have to make sure that the SQL query does not replicate any filtering which has already been applied,
    so if you see any of the information from the filters in the SQL query, remove it.
    In particular, remove any filtering by dates: no column called *_date should ever be in WHERE clauses;
    you are only allowed to mention dates for sorting purposes (i.e. in ORDER clauses).
    
    If the only thing the SQL is doing is to replicate applied filters, meaning that after their removal it would become
    just a SELECT with no other statements (or if it was already just a SELECT from the beginning),
    you should consider this SQL query redundant.
    
    Finally, if the query is trying to count occurrences of values in different columns, consider rewriting it with a
    "GROUP BY" clause over those columns instead; this would make it easier to extract counts for combinations of values.
    '''
    return ChatPromptTemplate.from_messages([('system', system)])


class CleanSQL(BaseModel):
    """Details of the cleaning of an SQL query from already applied filters."""
    sql_is_redundant: bool = Field(description='true if the SQL did nothing except replicating filters, false otherwise.')
    filters_removed: str = Field(description='an empty string if no changes were made to the SQL, or the bits of SQL that you removed.')
    new_sql_query: str = Field(description='either the same as the input SQL query or the new query without the duplicated'
                                           'filters (or an empty string when sql_is_redundant is true.')
########################################################################################################################
# ^^ NOT CURRENTLY USED; MIGHT USE OR REMOVE AFTER TESTING SQL QUALITY WITHOUT IT ^^
########################################################################################################################


def get_sql_retry_prompt(
    failed_sql_query: str,
    error: str,
    applied_filters: str,
    full_data_key: str,
    dataset_info: dict
) -> ChatPromptTemplate:
    """Generator for the minimal-context prompt for retrying failed SQL-tool calls."""
    system = '''
    # MAIN GOAL
    You have access to the process_dataset_with_sql tool; you just tried calling it and failed.
    Try to craft a better query based on the below information and call the tool again.
    
    
    # DATASET DETAILS
    The full_data_key argument to use is {full_data_key}. Info about this dataset:
    {dataset_info}
    
    
    # FAILED SQL ATTEMPT
    
    Query:
        {failed_sql_query}
    
    {error}
    
    
    # GUIDELINES
    - If the cause of failure is a data type error for a function you tried to apply to a given column
        (e.g. trying to take the mean of a column which should contain numbers but is instead of string type),
        you can cast a column to a different type in the problematic function calls,
        e.g. ```AVG(column_of_strings)``` would be fixed by ```AVG(CAST(column_of_strings AS FLOAT))```.
    - If any column in the failed SQL has a '.' in its name and is not in " quotes, that is definitely a source of error:
        any name containing a '.' needs to be put in " quotes, otherwise the '.' causes a syntax error or makes the part
        before it get treated as a (non-existent) table name.
    '''

    return ChatPromptTemplate.from_messages([
        ('system', system)
    ]).partial(
        failed_sql_query=failed_sql_query,
        error=error,
        applied_filters=applied_filters,
        full_data_key=full_data_key,
        dataset_info=json.dumps(dataset_info, indent=4)
    )


def get_notification_topic_router_prompt(
        org: str,
        processed_query: str,
        existing_subscriptions: str
) -> ChatPromptTemplate:
    """Generator for the prompt to extract the IDs for which to do a VOR Search."""
    system = '''
    # GOALS
    You have to extract some info from the user request into the given output format fields; this is split into 3 goals.
    Note: locations and organisations do not count as "entities" in the goal descriptions below.
    
    ## Goal 1
    Determine whether the topic in question in the user request described below is the creation of a subscription/notification,
    and only in that case report any existing subscriptions which mention any of the same entity IDs in the current request
    (i.e. any subscriptions to the same IDs or subscriptions which mention them in their description)
        - Note: ignore 'PO' or 'WO' prefixes in IDs if present: the digits after them are the real ID.
        - Note on relatedness: subscriptions to entities of the same type as the current IDs but which do not involve the
            IDs themselves are not related, so e.g. subscriptions of logistics summary reports/warnings of different types
            (mentioned in the next section) are not related.
    
    If the topic is something else (e.g. escalations or anything about subscriptions except their creation),
    your output will be very simple; just follow the output format instructions.
    
    If the user has already confirmed they wish to proceed with a subscription to the same entity as an existing
    one, say so in the output (as execution has to proceed in that case).
    
    ## Goal 2
    Return a list of all the IDs involved in the user request described below.
    
    Do not add any type info to the IDs you return,
    e.g. if an ID could be a container, flight, or shipment, then that ID should only be included once (raw) in your output.
    
    You should return IDs even if the summary of the user request below says they have been looked up already,
    and even if it states that a given ID is mentioned inside another one (do include both in this case).
    
    If and only if the topic is a subscription to logistics notification report/warning, you should inject one of the following IDs into the output,
    as the user does not know to mention these exact strings; determine which of these is appropriate:
        - 'hcr transit time' for HCRs taking too long in transport
        - 'hcr dwell time' for HCRs dwelling too long at location
        - 'new cmrs' for new CMRs being created for given projects
        - 'dangerous goods' for current dangerous goods
    '''
    
    if org in ('Shell UK', 'ExxonMobilGuyana'):
        system += '''
    If and only if the topic is a subscription to flight requests, you should inject the appropriate ID into the output,
    as the user does not know to mention these exact strings; the entity type is `flight requests`. The ID is a state filter:
        - 'PENDING', 'APPROVED', or 'REJECTED', alone or alternated with '|' (e.g. 'PENDING|APPROVED')
        - 'PENDING|APPROVED|REJECTED' if the user gave no state preference
    '''
    
    system += '''
    ## Goal 3
    Determine whether the user asked for something which is not supported.
    Listing or closing subscriptions or escalations is always permitted, and the next agent will use appropriate tools to do so,
    but there are some limitations to the creation process; the following things are not supported:
        - Subscribing to something without giving an entity ID (e.g. specifying an entity with something like "the next X" or any other non-ID way).
            - A variety of this is asking to monitor/subscribe to ALL entities of some type(s).
                - (The notable exception to this is subscribing to warnings as mentioned earlier, where you inject the ID for a full category of warnings).
            - Subscriptions are specific to single entities (or things mentioned inside a singe entity),
                so one should look up relevant entities and then ask for specific subscriptions.
                - (It is fine to ask to subscribe to multiple things at once as long as their IDs and conditions are specified).
        - Subscribing to anything which is not one of the following things: {subscribeable_entities}.
            - If you have an ID and do not know what it is it is fine to proceed, as the agent after you will search for it.
            - The reason to be aware of the allowed entities at this stage is to answer questions about capabilities
                or to quickly let the user know that subscribing to something clearly not among them is not supported.
        - Subscribing someone else to something.
        - Creating a subscription for some event NOT having happened (e.g. whether something has NOT been delivered by a given date).
        - Creating a subscription with most types of time-based criteria in its condition:
            - Not supported: conditions on the notification time itself, e.g. asking to be notified periodically,
                or at a certain time, or after a certain time if something else happens.
            - Supported: conditions involving time fields of the data to check,
                e.g. when some duration or date in the data is equal, greater, or less than a given value.
        - Modifying an existing subscription or escalation. HOWEVER, as previously mentioned, you CAN close them (so do not refuse to do that),
            and because closing them is fine, you can achieve the same effect as a modification by creating a new one and closing the old one,
            but the user has to be informed first. (FYI, you can also list the current ones, but that is unrelated to modifying them).
    
    
    # USER REQUEST
    {processed_query}
    
    
    # EXISTING SUBSCRIPTIONS
    If the user has any subscriptions, they will be listed below regardless of whether the topic above is subscriptions;
    do not let their presence sway you, as only the above section should determine the topic.
    
    Subscriptions (entity ID, type, and description):
        {existing_subscriptions}
    
    '''

    prompt = ChatPromptTemplate.from_messages([
        ('system', system)
    ]).partial(
        processed_query=processed_query,
        subscribeable_entities=', '.join(apis_by_org[org].keys()),
        existing_subscriptions=existing_subscriptions
    )
    return prompt


class NotificationTopic(BaseModel):
    ids: list[str] = Field(description='All the IDs mentioned (not locations). Empty list if there are none.')
    topic_is_subscriptions: bool = Field(description='Whether the topic in question is subscriptions/notifications.')
    # ^^ keeping this separate flag in case we need to toggle general behaviour between subscriptions and escalations
    topic_is_subscription_listing: bool = Field(description='If topic_is_subscriptions is True, this value represents '
                                                            'whether the topic is specifically just asking to list current subscriptions.')
    topic_is_subscription_set_up: bool = Field(description='If topic_is_subscriptions is True, this value represents '
                                                           'whether the topic is specifically the creation of subscriptions.')
    topic_is_subscription_to_warnings: bool = Field(description='If topic_is_subscriptions is True, this value represents '
                                                                'whether the topic is specifically about subscriptions to logistics warnings of some kind'
                                                                '(you should put the appropriate ID of the specific kind in the ids field).')
    related_subscriptions: list[str] = Field(
        description='This value should be an empty list unless topic_is_subscription_set_up is True '
                    'AND any of the existing subscriptions involve an ID from the current request. '
                    'In that case, this value should be a list of each relevant subscription\'s info.')
    user_override: bool = Field(description='Whether the user has already stated they wish to proceed anyway with a subscription related to an existing one.')
    unsupported_feature: str = Field(description='This value should be an empty string unless the user asked to do something which is not supported, '
                                                 'in which case this should explain what that is and possibly a suggest what to do.')

