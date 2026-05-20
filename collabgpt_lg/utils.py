import logging
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from itertools import groupby
from collections import defaultdict, Counter

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_community.callbacks import get_openai_callback
from langchain_community.callbacks.openai_info import OpenAICallbackHandler
from typing import Union

from collabgpt_lg.graph_types import ConfigSchema

import config


# Iterable-related functions

def sort_dicts(dicts: list[dict], by: list[tuple[str, bool]], defaults: dict = None) -> list[dict]:
    """Sort the dicts (e.g. index search results) by the given fields and individual directions
    (tuples of field name and bool for the `reverse` argument of the sorted function).
    If a field is not present or None, then its default value will be '' unless specified in defaults.
    Note when used for index search results:
        might not want to include '@search.score' as a field to search by, with particular care if
        used as the first field; this is because using the 'query' argument when searching will likely return a
        different '@search.score' for each result, meaning that it will be a very strong order determinant
        (almost the sole one if placed as the first field).
    """
    for field, reverse in reversed(by):
        dicts.sort(key=lambda x: x.get(field) or (defaults or {}).get(field, ''), reverse=reverse)
    return dicts


def common_dict_entries(dicts: list[dict]) -> dict:
    """Returns a dictionary of the key-value pairs which are identical across all input dictionaries."""
    if not dicts:
        return {}

    # Start with the 1st dict and remove any key-value pair which is absent or different in the other ones
    common = dicts[0].copy()
    for d in dicts[1:]:  # not just a .get below because it would keep k if v were actually None while k is not in d
        keys_to_remove = [k for k, v in common.items() if k not in d or d[k] != v]
        for key in keys_to_remove:
            del common[key]

    return common


def sort_test_responses(response_cache: list[dict]) -> list[dict]:
    """Reorders and gives ids to responses from test batches.
    The output is grouped by the query field in the location of first occurrence, and replicates get +=100 for multiple
    iterations (e.g. if the batch was run twice with 2 replicates each, the values will go from 1,2,1,2 to 1,2,101,102).
    """
    query_positions = {}
    grouped_items = defaultdict(list)

    for r in response_cache:
        query = r['query']
        if query not in query_positions:
            query_positions[query] = len(query_positions)
        grouped_items[query].append(r)

    ordered_responses = sorted(response_cache, key=lambda x: query_positions[x['query']])

    seen_replicates = defaultdict(Counter)
    for r in ordered_responses:
        r['replicate'] += 100 * seen_replicates[r['query']][r['replicate']]
        seen_replicates[r['query']][r['replicate']] += 1

    return ordered_responses


def batch_test_responses(response_cache: list[dict], n: int) -> list[list[dict]]:
    """Batch responses (already ordered/grouped by unique query) in batches of n BUT allow deviating from n
    in order to not split replicates of the same query over batches.
    """
    batches = []
    current_batch = []

    for _, group in groupby(response_cache, key=lambda d: d['unique_query']):
        grouped_list = list(group)

        if len(grouped_list) > n:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append(grouped_list)
        elif len(current_batch) + len(grouped_list) > n:
            batches.append(current_batch)
            current_batch = grouped_list
        else:
            current_batch.extend(grouped_list)

    if current_batch:
        batches.append(current_batch)

    return batches


def remove_dataframes(data: list[dict]):
    """Remove DataFrames and their info from the state's data field so that it can be converted to JSON for to use in prompts."""
    # Structure of data:
    #   - each entry is a dict with keys 'source', 'output', and possibly 'original_data' and 'performed_sql'.
    #   - 'output' may be a dict, and it may contain 'TopResultsDataset' or 'AllResultsDataset', which are DataFrames + info.
    #   - 'original_data' should be removed regardless since it does not belong in prompts (and also contains dataframes).
    return [{dk: {k: v for k, v in dv.items() if not k.endswith('Dataset')}
                    if dk == 'output' and isinstance(dv, dict) else dv
                for dk, dv in data.items() if dk != 'original_data'}
              for data in data]


def get_categorical_columns(df, max_unique=10, max_length=30, max_na_ratio=0.2) -> dict[str, list[str]]:
    '''Return the unique values of the columns whose values are strings, mostly present, short, and few, i.e. likely categorical columns.'''
    result = {}
    for col in df.select_dtypes(include='object').columns:
        absence_ratio = df[col].isna().mean()
        if absence_ratio > max_na_ratio:
            continue
        values = df[col].dropna().unique()
        if len(values) <= max_unique and all(isinstance(v, str) and len(v) <= max_length for v in values):
            result[col] = values.tolist()
    return result


def trim_data(tool_calls: list[dict]):
    """Removes the actual data from the input for when knowing its fields is enough (i.e. the router node, which needs
    to decide whether there is enough data to answer but does not actually write the answer).
    """
    explanation = 'You do not need to see the full data now; use the known column names to determine whether there is enough data.'
    out = []
    for tc in tool_calls:
        trimmed = {k: v for k, v in tc.items() if k not in ['output', 'original_data']}
        if data := tc.get('output'):  # it should always be there, just being careful
            # If already a nicely packaged data dict, no need to compress again, just remove TopResults and dataframes
            if isinstance(data, dict):
                trimmed['output'] = {k: v for k, v in data.items() if k in ['status', 'system_message']}
                if 'MetaData' in data:
                    trimmed['output'].update({k: {kk: vv for kk, vv in v.items() if kk != 'dataframe'}
                                               for k, v in data.items() if k.endswith('Dataset')})
                    trimmed['output']['MetaData'] = {k: v for k, v in tc['output']['MetaData'].items() if k != 'data_is_reduced'}
                    if not set(trimmed['output'].keys()).intersection({'status', 'system_message'}):
                        trimmed['output']['MetaData']['explanation'] = explanation
            else:  # otherwise keep only the field names at their nested level
                trimmed['output'] = dict(explanation=explanation, structure=compress_nested_dict(data))
        out.append(trimmed)
    return out


def compress_nested_dict(data: Union[dict, list]):
    """Convert a nested data structure to just its skeleton, i.e. only mentioning the keys at the appropriate nested level."""
    if isinstance(data, dict):
        return {k: v for k, v in [(kk, compress_nested_dict(vv)) for kk, vv in data.items()]}
    elif isinstance(data, list):
        entries = [compress_nested_dict(v) for v in data]
        entries = [e for e in entries if e]
        return [entries[0]] if entries else []  # only give the structure of the first entry
    else:
        return {}


def format_message_history(history: ChatMessageHistory) -> list[str]:
    """Convert a ChatMessageHistory into a simple list of strings, each starting with '<SPEAKER>: '."""
    return [f'{msg.type.upper()}: {msg.content}' for msg in history.messages]



# Datetime-related functions

def localise_dt(dt_str: str, tz: ZoneInfo, assume_local_if_no_tz=False, print_tz=False, treat_midnight_as_date=True) -> str:
    """Returns an ISO datetime string in the form someone in the given tz would expect it (localised, and by default with no tz info).
    If dt_str has tz info, the output will be converted to the local timezone.
    If dt_str does NOT have tz info, UTC is assumed unless assume_local_if_no_tz.
    If treat_midnight_as_date is True, then tz info (present or absent) will be ignored if inputs are midnight.
    Note that yyyy-mm-dd dates are also valid inputs (the output WILL include the time).

    Examples for a +08:00 time zone:
        # Explicit timezone given
        '2024-12-30T13:52:00+08:00' -> '2024-12-30T13:52:00'        # "just dropped the offset"
        '2024-11-04T11:56:02.88+11:00' -> '2024-11-04T08:56:02'     # ignored seconds and localised
        # No timezone given and assume_local_if_no_tz=False
        '2024-11-04T01:00:00' -> '2024-11-04T09:00:00'              # no tz given => output is localised
        # No timezone given and assume_local_if_no_tz=True
        '2024-11-04T01:00:00' -> '2024-11-04T01:00:00'              # no tz given => output is untouched
        # Date special case
        '2024-11-04' -> '2024-11-04T00:00:00'                       # dates get automatically set to the localised midnight
        # If treat_midnight_as_date=True then midnight datetimes are treated as dates
        '2024-11-04T00:00:00' -> '2024-11-04T00:00:00'               # no tz given => time is unchanged
        '2024-11-04T00:00:00+11:00' -> '2024-11-04T00:00:00'         # tz given => time is still unchanged
    """
    if not isinstance(dt_str, str) or not dt_str:
        return dt_str  # ^^ in case being applied to a df column (Pandas passes missing cells as float NaN)

    if treat_midnight_as_date and 'T00:00:00' in dt_str:
        dt_str = dt_str[:10]  # i.e. keep only the date; ignore time AND timezone

    try:
        dt = datetime.fromisoformat(dt_str)  # vv either set or convert the tz
        dt = dt.replace(tzinfo=tz) if not dt.tzinfo and (assume_local_if_no_tz or len(dt_str) == 10) else dt.astimezone(tz)
        return dt.isoformat() if print_tz else dt.strftime('%Y-%m-%dT%H:%M:%S')
    except Exception as e:  # no need to be more specific
        return dt_str

def iso_dt_range(dt_or_range: str, tz: ZoneInfo) -> str:
    """Expands a datetime string or a ~ range of them to full ISO format with explicit timezone
    (using tz if the timezone was not already explicit in the datetime(s)).
    Open intervals are fine, e.g. for a +08:00 tz '2025-05-03~' -> '2025-05-03T00:00:00+08:00~'.
    """
    if not dt_or_range:  # could inline this below, but splitting it for clarity and symmetry with .localised
        return dt_or_range

    return '~'.join([localise_dt(date, tz, True, True) for date in dt_or_range.split('~')])



# Misc functions

def words_from_misc_case(text: str) -> list[str]:
    """Extract (lowercase) words from camelCase, PascalCase, snake_case, or kebab-case strings."""
    text = re.sub(r'[_\-]+', ' ', text)  # _ and - to spaces
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)  # space at lower-to-Upper transitions
    text = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', text)  # space before last-of-multiple-Uppers-to-lower transition (acronyms)
    return [word.lower() for word in text.split()]


def org_state(org: str) -> ConfigSchema:
    """Return a basic GraphState."""
    user_ids = {
        'CHEVRON': 'chevrontest@vor.cloud',
        'Shell UK': 'shelluk-airmarinetest@vor.cloud',
        'ExxonMobilGuyana': 'exxonmobil-guyana-ai-test@vor.cloud'
    }
    return ConfigSchema(org=org, timezone=config.org_time_zones[org], llms={}, user_id=user_ids[org])


class LlmCallContext:
    """Context manager wrapping get_openai_callback with model/node args, timing, and an output llm_call dict.

    Usage:
        with llm_call_context(model, node_name) as ctx:
            out = c['llms'][model]....invoke(...)
        llm_call = ctx.llm_call  # dict with name, node, token_info, response_time
    """
    def __init__(self, model: str, node: str):
        self.model = model
        self.node = node
        self._callback = None  # context manager from get_openai_callback()
        self.callback: OpenAICallbackHandler = None  # OpenAICallbackHandler
        self.llm_call: dict = None  # dict with name, node, token_info, and response_time (set in __exit__)
        self._start_time = None

    def _get_cost(self) -> float:
        """Compute total token cost since LangChain's method for it lacks some models.
        Model identification relies on the deployment name containing the model name
        (our naming standard has always been even stricter: starting with vorai- and ending with either -dev or -live).
        """
        cb = self.callback
        deployment = config.llm.deployment[self.model]
        if matches := [m for m in config.llm.costs_per_million if m in deployment]:
            costs = config.llm.costs_per_million[max(matches, key=len)]  # longest is correct, e.g. gpt-4.1-mini over gpt-4.1 if found both
            return ((cb.prompt_tokens - cb.prompt_tokens_cached) * costs['in'] +
                    cb.prompt_tokens_cached * costs['cached'] +
                    # vv apparently reasoning tokens are not priced separately
                    # cb.reasoning_tokens * reasoning cost +
                    cb.completion_tokens * costs['out']) / 1e6
        else:
            logging.warning('Could not compute token cost for unrecognised underlying model of deployment %s', deployment)
            return .0

    def __enter__(self):
        self._callback = get_openai_callback()
        self._start_time = time.perf_counter()
        self.callback = self._callback.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self._start_time
        self._callback.__exit__(exc_type, exc_val, exc_tb)
        self.llm_call = dict(
            name=self.model,
            node=self.node,
            tokens_count=self.callback.total_tokens,
            tokens_cost=self._get_cost(),
            response_time=elapsed,
        )
        return False


