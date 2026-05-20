import re
from string import punctuation
from itertools import pairwise

from shared.ids.flight_numbers import flight_number_regex
from shared.ids.ccus_chevron import chevron_ccu_regex
from shared.ids.ccus_shell_uk import shell_uk_ccu_regex
from shared.ids.shipments import shipment_regex
from shared.ids.projects import project_regex


# Regex defining candidates:
#   [length >= 3] AND [[at least one digit] OR [more than 2 capital letters in a row]] AND [no @]
#   (later matches are case-insensitive, but this initial upper-case filter is reasonable)
candidate_regex = re.compile('(?=.*(?:[0-9]|[A-Z]{2,}))(?!@).{3,}')

# Regex to remove prefix and suffix punctuation from candidate query words
bad_punctuation = re.escape(punctuation)
bad_punctuation_regex = re.compile(f'[{bad_punctuation}]*(.+[^{bad_punctuation}])[{bad_punctuation}]*')

# Prefixes which can collapse possibilities if being the word before a reference number candidate
prefixes_regex = re.compile('[CL]MR|[WPS]O|[OS]T', flags=re.IGNORECASE)


def id_filter(query: str) -> set[str]:
    """Remove prefix and suffix punctuation and return the strings which might be IDs:
    [length >= 3] AND [[containing at least one digit] OR [containing more than 2 capital letters in a row]].
    If the word preceding a candidate is a known type prefix, the two are joined.
    """
    return set((pre + clean) if re.fullmatch(prefixes_regex, pre) else clean
               for pre, word in pairwise([''] + re.split(r'\s+', query))
               if re.fullmatch(candidate_regex, word)
               if (cleanable := re.fullmatch(bad_punctuation_regex, word))
               if (clean := cleanable.group(1)))


# Known reference number regexes
# NOTES:
#   - No \b in the patterns since some IDs may contain dashes or similar bounding symbols
#     (and punctuation is handled by id_filter).
#   - If there is a captured group (brackets without leading "?:"), that will be stored instead of the full match.
#   - The order of these keys will be reflected in matches if multiple apply, therefore it is best to place them
#     in the order in which the LLM should consider them (not guaranteed, of course)
#   - Some patterns (work_order and purchase_order at the time of writing) make use of a capture group to extract
#     only portions of the capture (e.g. only digits after a known letter prefix)
REGEX_MAPPING = {
    'CHEVRON': dict(
        container=chevron_ccu_regex,
        flight_id='[a-z]{4,8}(?:-\\d{1,5}){5}',
        flight_number=flight_number_regex,
        kabal_id='CHEVRONAU\\d{5}',
        movement_request='[CL]MR#?[0-9]{6}',
        pack='0\\d{17}',
        tare='1\\d{17}',
        project=project_regex,  # Almost-direct pattern for projects (digits can vary); reused as a negative filter
        purchase_order='(?:PO)?[#:]?(\\d{1,10}(?:\\-\\d{1,3})?)',  # Not enough patterns for its own file
        road_transport_job='SR\\d{5,6}',
        shipment=shipment_regex,
        st_number='ST\\d{2,6}',
        voyage_cargo_manifest='[a-z]{6,}\\d{4}[a-z]*|\\d{4}',  # No need to be more precise than this
        work_order='(?:WO)?#?([0-9]{6})',

        # Clearly mistyped reference numbers
        #   - Too few or too many digits in the patterns which are strict about it, i.e. WOs, POs, MRs, packs, and tares
        #   - The pack/tare portion quantifiers are due to the existence of '\\d{4,10}' containers and '\\d{14}' shipments
        likely_typo='(?:[CL]MR|WO)#?(?:\\d{1,5}|\\d{7,})|PO[#:]?\\d{11,}|ST\\d{7,}|[01](?:\\d{10,12}|\\d{14,16}|\\d{18,})|SR#?(?:\\d{1,4}|\\d{6,})'
    ),
    'Shell UK': dict(
        container=shell_uk_ccu_regex,
        flight_number='LM\\d{3}(?:-[a-z]{2,3})?|SH[a-z]\\d-(?:[a-z](?:[a-z]{2}[a-z\\d]?|\\d{3})|\\d{2}[a-z]?)',
        voyage='(?:ABZ|LWK)?/?\\d{3,4}(?:/?\\d{2})?'
    ),
    'ExxonMobilGuyana': dict(
        container='\\d{5,6}',
        flight_id='[a-z]{4,8}-\\d{5}-\\d{4}-\\d{2}-\\d{2}',
        flight_number='RW\\d_[a-z]\\w{1,2}',
        shipment='(?:[a-z]{3}(?:[a-z]\\d{7}|\\d{8})|\\d{8})',
        transfer_request='TR\\d{10}',
        voyage='\\d{5}',
        voyage_id='[a-z]{20,30}-\\d{5}',
        work_order='(?:WO)?#?[0-9]{7,9}'
    )
}
REGEX_MAPPING = {org: {entity: re.compile(pattern, flags=re.IGNORECASE) for entity, pattern in regexes.items()}
                 for org, regexes in REGEX_MAPPING.items()}


# Regexes for a negative pass on the identified reference numbers
#   Used to remove the patterns which are definitely of one type but which may have also been flagged as others.
# NOTES:
#   - Can use any key here, but matching a key with REGEX_MAPPING protects that field from removal of the pattern.
#   - Patterns with keys also in REGEX_MAPPING *should* be stricter than (or at most equal to) their counterparts.
#   - This dictionary can also cover non-reference-number patterns to remove from captures, e.g. dates.
REGEX_ANTIMAPPING = {
    'CHEVRON': dict(
        flight_id='DaWinci(?:-\\d{1,5}){5}',
        kabal_id='CHEVRONAU\\d{5}',
        movement_request='[CL]MR(?:[0-9]{6}|s)?',
        project=project_regex,  # All project names are (assumed) known and can hence be filtered out
        purchase_order='PO[#:]?\\d+',
        road_transport_job='SR\\d{5,6}',
        st_number='ST\\d{2,6}',
        work_order='WO#?[0-9]{6}',

        # Non-reference-number patterns
        date='(?:0?|[1-3])\\d[/\\-](?:0?|1)\\d[/\\-](?:\\d{2}|\\d{4})|\\d{4}[/\\-](?:0?|1)\\d[/\\-](?:0?|[1-3])\\d',
        protected_terms='HCRs?|BWI|MOF|CCU(?:Id)?s?|VOR',
        time='(?:0?\\d|1\\d|2[0-4]):[0-5]\\d(?::[0-5]\\d(?:\\.\\d+)?)?',
        year='(?:19|20)\\d\\d',
    ),
    'Shell UK': dict(
        flight_number='LM\\d{3}(?:-[a-z]{2,3})?|SH[a-z]\\d-(?:[a-z](?:[a-z]{2}[a-z\\d]?|\\d{3})|\\d{2}[a-z]?)',  # identical since unambiguous enough
        voyage='(?:ABZ|LWK)/?\\d{3,4}(?:/?\\d{2})?'  # difference: the prefix is not optional
    ),
    'ExxonMobilGuyana': dict(
        flight_id='Helipass-\\d{5}-\\d{4}-\\d{2}-\\d{2}',
        flight_number='RW\\d_[a-z]\\w{1,2}',  # identical since unambiguous enough
        transfer_request='TR\\d{10}',
        voyage_id='exxonmobilsupplychaindatahub-\\d{5}',
        work_order='WO#?[0-9]{7,9}'  # difference: the prefix is not optional
    )
}
REGEX_ANTIMAPPING = {org: {entity: re.compile(pattern, flags=re.IGNORECASE) for entity, pattern in regexes.items()}
                     for org, regexes in REGEX_ANTIMAPPING.items()}


