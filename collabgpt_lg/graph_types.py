from operator import add
from zoneinfo import ZoneInfo

from typing import Annotated
from typing_extensions import TypedDict, _AnnotatedAlias

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.language_models.chat_models import BaseChatModel


# Reducers with which to annotate state fields
#   https://langchain-ai.github.io/langgraph/concepts/low_level/?h=configuration#reducers

def dict_reducer(a: dict, b: dict) -> dict:
    return dict(**a, **b)


def add_or_clear_reducer(a: list, b: list) -> list:
    return [] if b == ['CLEAR'] else (a + b)


# Define the graph state (I/O of nodes) and config objects
#   Keep all fields generated during graph execution in the state object
#   Pass the bot itself as the config so that both its fields AND methods can be used

class GraphState(TypedDict):  # NOTE: new fields need to be given default values in bot.GraphLogisticsBot._run_graph
    # Note: fields not annotated with a reducer ("Annotated[type, reducer]") will be overwritten if node outputs
    #   https://langchain-ai.github.io/langgraph/concepts/low_level/?h=configuration#reducers

    # Graph input fields
    user_teams_email: str
    user_message: str
    message_history: ChatMessageHistory
    reference_numbers: dict[str, list[str]]
    confirmed_types: dict[str, str]

    # Produced fields
    processed_query: str
    router_visits_counter: int
    private_note: str
    notification_topic: dict  # not a collabgpt_lg.prompts.NotificationTopic to avoid complications
    current_tool_calls: Annotated[list[dict], add_or_clear_reducer]

    data: Annotated[list[dict], add]
    used_tools: Annotated[list[dict[str, dict]], add]

    llm_calls: Annotated[list[dict], add]

    response: str
    comments: Annotated[list[str], add]


class ConfigSchema(TypedDict):
    # https://langchain-ai.github.io/langgraph/how-tos/graph-api/#add-runtime-configuration
    org: str
    source: str
    timezone: ZoneInfo
    llms: dict[str, BaseChatModel]
    notification_agent_is_allowed: bool
    user_id: str
    user_teams_id: str | None
    user_display_name: str

    # No need for checkpointing, but if desired in the future need to add this AND to remove dataframes from data in state
    # thread_id: UUID  # https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/time-travel/#setup



# Utility functions

def apply_reducers(state: GraphState, state_updates: dict):
    """Update a GraphState objects using the reducers with which its fields are annotated (as LangGraph does internally).
    This function is needed to keep a copy of state up to date outside the graph if wish to use graph.stream to see
    the state updates by each node (instead of getting the final state directly with graph.invoke).
    """
    reducers = GraphState.__annotations__
    for k, v in state_updates.items():
        if k in reducers and isinstance(reducers[k], _AnnotatedAlias):
            state[k] = reducers[k].__metadata__[0](state.get(k), v)
        else:  # overwrite if no reducer is declared or even if the field itself is not a standard one
            state[k] = v
    return state


