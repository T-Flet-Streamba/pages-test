from collections import Counter

# Context:
#   All regexes in this file share these first passes:
#       reduction of digit sequences to \d, of letter sequences to [a-z],
#       escaping of all regex-reserved characters, and removal of (all varieties of) spaces.
#   Then different final passes are performed w.r.t. the length of consecutive digits or letters; see sections below.


# #### Regexes to choose among for exporting ####

# Generated from the keys of minimal_length_aware_patterns (or, equivalently, minimal_length_ranges_patterns)
unified_length_aware_pattern = '(?:\\#[a-z]{11}|[a-z](?:\\#\\d{1,2}|\\-[a-z](?:\\-\\d{2}\\-\\d{4}|[a-z]\\-\\d{2}\\-\\d{4}|\\d{2}\\-\\d{4})|[a-z](?:\\#\\d{1,2}|\\-(?:[a-z](?:\\-\\d{4}|[a-z]\\-\\d{4})|\\d{3,4})|[a-z](?:\\#\\d(?:\\d{1,2})?|\\-(?:[a-z]\\d{4}\\-\\d{2,3}|\\d{3,4})|[a-z](?:\\#\\d(?:\\d{1,2})?|[a-z](?:[a-z](?:\\#\\d(?:\\d{1,2})?|[a-z](?:\\#\\d{1,2}|[a-z]))|\\d{3}(?:\\d(?:\\d{2}[a-z\\d]?)?)?)|\\d{3}(?:\\d(?:(?:\\-\\d{3}|\\d(?:\\d(?:(?:\\-\\d|\\.\\d|\\d(?:(?:\\-[a-z]{7}|[a-z]{2}\\d{2}|\\d(?:\\d{3})?))?))?)?))?)?)|\\d{3}(?:\\d(?:(?:[a-z]{2}|\\d{2,3}))?)?)|\\d(?:[a-z]\\d{7}|\\d(?:(?:\\-(?:[a-z]\\d{4}|\\d{4})|[a-z](?:\\-\\d{4}|[a-z]\\d{4}|\\d{4})|\\d(?:(?:[a-z]\\-\\d{3}|\\d(?:\\d{1,2})?))?))?))|\\d(?:[a-z]{2}\\d{7}|\\d{3}(?:\\-[a-z]\\d{3}|[a-z]\\d{3})))|\\d{4}(?:\\d(?:(?:\\-\\d(?:\\d{1,2})?|\\d(?:(?:[a-z]|\\d(?:\\d(?:\\d{2})?)?))?))?)?)'

# Generated from the keys of minimal_length_unaware_patterns
unified_length_unaware_pattern = '(?:[a-z]+(?:\\#\\d+|\\-(?:[a-z]+(?:\\-\\d+(?:\\-\\d+)?|\\d+\\-\\d+)|\\d+)|\\d+(?:(?:\\-(?:[a-z]+\\d+|\\d+)|\\.\\d+|[a-z]+(?:(?:\\-\\d+|\\d+))?))?)|\\d+(?:(?:\\-\\d+|[a-z]+))?)'


# #### EXPORTED VARIABLE ####
chevron_ccu_regex = unified_length_aware_pattern
# #### EXPORTED VARIABLE ####


# #### Counts of minimal patterns for different criteria ####
#   They are generated from VOR_CcuHires_20240604-153615.csv and VOR_OwnedAssets_20240604-153634.csv.
#   These are just for inspection, they are not used in the codebase.
#   The unified_* patterns above are generated from these keyes (excluding the commented-out lines ones).


# Consecutive digits and letters with precise lengths or ranges
minimal_length_ranges_patterns = Counter({
    '[a-z]{2,5}\\d{2,11}': 9318,
    '[a-z]{1,7}\\#\\d{1,3}': 1070,
    '\\d{4,10}': 272,
    '[a-z]{2,4}\\d{2,6}\\-\\d{1,4}': 117,
    '[a-z]{2,3}\\-\\d{3,4}': 80,
    '[a-z]{3,5}\\d{4,6}[a-z]{1,2}': 68,
    '[a-z]{2}\\d{2,3}[a-z]\\-\\d{3,4}': 27,
    '[a-z]{1,3}\\-[a-z]\\d{2,4}\\-\\d{2,4}': 11,
    '[a-z]{1,4}\\d{1,7}[a-z]{1,2}\\d{2,7}': 7,
    '[a-z]\\-[a-z]{1,2}\\-\\d{2}\\-\\d{4}': 5,
    '\\d{5}\\-\\d{1,3}': 4,
    '[a-z]{2}\\-[a-z]{1,2}\\-\\d{4}': 3,
    '[a-z]{4}\\d{6}\\.\\d': 3,
    '[a-z]{1,2}\\d{2,4}\\-[a-z]\\d{3,4}': 2,
    '\\d{6}[a-z]': 2,
    '\\#[a-z]{11}': 1,
    '[a-z]{4}\\d{7}\\-[a-z]{7}': 1,
    '[a-z]{8}': 1
})


# Consecutive digits and letters with precise lengths but no ranges
#   I.e. a less refined version of minimal_length_ranges_patterns
minimal_length_aware_patterns = Counter({
    '[a-z]{4}\\d{7}': 8122,
    '[a-z]{2}\\d{4}': 614,
    '[a-z]{3}\\d{4}': 359,
    '[a-z]{3}\\#\\d{3}': 351,
    '[a-z]{6}\\#\\d{3}': 301,
    '\\d{7}': 129,
    '\\d{6}': 119,
    '[a-z]{4}\\#\\d{2}': 100,
    '[a-z]{6}\\#\\d{2}': 90,
    '[a-z]{3}\\#\\d{2}': 90,
    '[a-z]{3}\\-\\d{4}': 76,
    '[a-z]{4}\\d{6}\\-\\d': 69,
    '[a-z]{3}\\d{4}[a-z]{2}': 65,
    '[a-z]{4}\\d{3}': 58,
    '[a-z]{4}\\d{4}': 52,
    '[a-z]{4}\\d{6}': 47,
    '[a-z]{2}\\d{2}\\-\\d{4}': 47,
    '[a-z]{7}\\#\\d{2}': 41,
    '[a-z]{2}\\#\\d{2}': 31,
    '[a-z]{3}\\d{3}': 28,
    '\\d{10}': 17,
    '[a-z]{2}\\d{3}[a-z]\\-\\d{3}': 16,
    '[a-z]{2}\\d{3}': 12,
    '[a-z]\\#\\d{2}': 11,
    '[a-z]{2}\\d{2}[a-z]\\-\\d{4}': 11,
    '[a-z]{7}\\#\\d': 9,
    '[a-z]{2}\\#\\d': 9,
    '[a-z]{3}\\#\\d': 9,
    '[a-z]\\#\\d': 9,
    '[a-z]{4}\\#\\d': 9,
    '[a-z]{6}\\#\\d': 9,
    '[a-z]{3}\\-[a-z]\\d{4}\\-\\d{3}': 8,
    '[a-z]{4}\\d{8}': 7,
    '\\d{5}': 5,
    '[a-z]\\-[a-z]{2}\\-\\d{2}\\-\\d{4}': 4,
    '[a-z]{3}\\d{7}': 4,
    '[a-z]{3}\\d{6}': 4,
    '[a-z]{2}\\d{6}': 3,
    '[a-z]{4}\\d{6}\\.\\d': 3,
    '[a-z]{5}\\d{6}[a-z]': 3,
    '[a-z]{3}\\-[a-z]\\d{4}\\-\\d{2}': 2,
    '\\d{6}[a-z]': 2,
    '[a-z]{2}\\d[a-z]\\d{7}': 2,
    '[a-z]{2}\\-[a-z]\\-\\d{4}': 2,
    '[a-z]{3}\\-\\d{3}': 2,
    '\\d{5}\\-\\d{2}': 2,
    '[a-z]{8}': 1,
    '[a-z]{2}\\d{2}[a-z]{2}\\d{4}': 1,
    '\\d{5}\\-\\d{3}': 1,
    '[a-z]{2}\\d{2}': 1,
    '[a-z]{5}\\d{6}': 1,
    '[a-z]\\d{4}[a-z]\\d{3}': 1,
    '[a-z]\\d{4}\\-[a-z]\\d{3}': 1,
    '[a-z]{2}\\d{2}[a-z]\\d{4}': 1,
    '[a-z]{4}\\d{4}\\-\\d{3}': 1,
    '[a-z]{2}\\-\\d{4}': 1,
    '[a-z]{5}\\d{3}': 1,
    '[a-z]\\d[a-z]{2}\\d{7}': 1,
    '[a-z]{4}\\d{7}[a-z]{2}\\d{2}': 1,
    '[a-z]\\-[a-z]\\-\\d{2}\\-\\d{4}': 1,
    '[a-z]{5}\\d{4}': 1,
    '\\d{5}\\-\\d': 1,
    '[a-z]{4}\\d{11}': 1,
    '[a-z]{2}\\-[a-z]{2}\\-\\d{4}': 1,
    '[a-z]\\-[a-z]\\d{2}\\-\\d{4}': 1,
    '[a-z]{2}\\d{2}\\-[a-z]\\d{4}': 1,
    '[a-z]{2}\\-\\d{3}': 1,
    '[a-z]{4}\\d{5}': 1,
    '\\d{8}': 1,
    '[a-z]{4}\\#\\d{3}': 1,
    '[a-z]{4}\\d{7}\\-[a-z]{7}': 1,
    '[a-z]{2}\\d{5}': 1,
    '\\d{4}': 1,
    '\\#[a-z]{11}': 1,
    '[a-z]{5}\\d{7}': 1
})


# Consecutive digits and letters with unknown lengths
minimal_length_unaware_patterns = Counter({
    '[a-z]+\\d+': 9318,
    '[a-z]+\\#\\d+': 1070,
    '\\d+': 272,
    '[a-z]+\\d+\\-\\d+': 117,
    '[a-z]+\\-\\d+': 80,
    '[a-z]+\\d+[a-z]+': 68,
    '[a-z]+\\d+[a-z]+\\-\\d+': 27,
    '[a-z]+\\-[a-z]+\\d+\\-\\d+': 11,
    '[a-z]+\\d+[a-z]+\\d+': 7,
    '[a-z]+\\-[a-z]+\\-\\d+\\-\\d+': 5,
    '\\d+\\-\\d+': 4,
    '[a-z]+\\d+\\.\\d+': 3,
    '[a-z]+\\-[a-z]+\\-\\d+': 3,
    '\\d+[a-z]+': 2,
    '[a-z]+\\d+\\-[a-z]+\\d+': 2,
    '[a-z]+': 1,  # ['FLARETIP']
    '[a-z]+\\d+\\-[a-z]+': 1,  # ['SBIU2608834-LIDONLY']
    '\\#[a-z]+': 1  # ['#NOT RECORDED']
})


