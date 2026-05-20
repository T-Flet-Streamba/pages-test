import logging
from difflib import SequenceMatcher

from langchain_core.output_parsers.json import JsonOutputParser
from langchain_core.output_parsers.openai_tools import JsonOutputToolsParser


def _normalize_tool_call(tc: dict) -> dict:
    """Convert recipient_name/parameters format to type/args for downstream use."""
    if 'recipient_name' in tc and 'parameters' in tc:
        name = tc['recipient_name']
        if name.startswith('functions.'):
            name = name[10:]
        return dict(type=name, args=tc['parameters'])
    return tc


def extract_tool_calls(out, tool_map: dict) -> list[dict]:
    """Extract tool calls from an LLM output, trying both parser styles (in generic content blocks or explicit tools protocol field).
    Tool name hallucinations are corrected, and output call fields are standardised to type/args, not recipient_name/parameters.
    """
    raw_calls = None
    try:
        parsed = JsonOutputToolsParser().invoke(out)
        if parsed and len(parsed) > 0:
            raw_calls = parsed
    except Exception:
        pass
    if raw_calls is None:
        try:
            parsed = JsonOutputParser().invoke(out)
            raw_calls = parsed.get('tool_uses') if parsed else None
        except Exception:
            pass
    if not raw_calls:
        return []
    normalized = [_normalize_tool_call(tc) for tc in raw_calls]
    return correct_tool_hallucinations(normalized, tool_map)


def get_real_tool_name(wanted: str, tool_map: dict, log=True) -> str:
    """Return the wanted tool if it exists, and the one with the closest matching name if it does not."""
    if wanted in (tool_names := list(tool_map.keys()) + ['process_dataset_with_sql']):
        return wanted
    else:
        existing = max(tool_names, key=lambda available: SequenceMatcher(None, wanted, available).ratio())
        if log:
            logging.info("The LLM asked for the non-existing tool '%s'; using the most similar one instead: '%s'",
                        wanted, existing)
        return existing


def correct_tool_hallucinations(tool_calls: list[dict], tool_map: dict) -> list[dict]:
    """Corrects the following tool hallucinations if present:
        - Unnests calls to the hallucinated multi_tool_use tools (.parallel or not).
        - Replaces calls to unknown tools with the most similar known ones.
    tool_calls and the output are lists of dictionaries as produced by JsonOutputToolsParser.
    """
    out = []
    for tc in tool_calls:
        if tc['type'].startswith('multi_tool_use'):  # could be '.parallel' or not
            # See test_tool_correction test cases to see what a multi_tool_use invocation looks like
            logging.info("The LLM erroneously asked for a '%s' execution of the following tools: %s",
                        tc['type'], [tool['recipient_name'] for tool in tc['args']['tool_uses']])
            for nested in tc['args']['tool_uses']:
                de_prefixed = wanted[10:] if (wanted := nested['recipient_name']).startswith('functions.') else wanted
                out.append(dict(type=get_real_tool_name(de_prefixed, tool_map), args=nested['parameters']))
        else:
            tc['type'] = get_real_tool_name(tc['type'], tool_map)
            out.append(tc)
    return out


