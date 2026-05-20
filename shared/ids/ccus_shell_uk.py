from collections import Counter

# Context:
#   All regexes in this file share these first passes:
#       reduction of digit sequences to \d, of letter sequences to [a-z],
#       escaping of all regex-reserved characters, and removal of (all varieties of) spaces.
#   Then different final passes are performed w.r.t. the length of consecutive digits or letters; see sections below.


# #### Regexes to choose among for exporting ####

# Generated from the keys of minimal_length_aware_patterns (or, equivalently, minimal_length_ranges_patterns)
unified_length_aware_pattern = '(?:[a-z](?:[a-z](?:[a-z](?:\\-[a-z]{2}\\d{3}|\\d(?:\\-\\d{2}|\\d{2,3}))|\\d{2}(?:\\-\\d{3}|\\d(?:(?:\\-[a-z]|\\d))?))|\\d{3})|\\d(?:[a-z]{3}\\d{3}|\\d{2}(?:[a-z]\\d{4}[a-z]{2}\\d{2}|\\d(?:(?:/[a-z]|\\d{1,2}))?)))'

# Generated from the keys of minimal_length_unaware_patterns
unified_length_unaware_pattern = '(?:[a-z]+\\d+(?:\\-\\d+)?|\\d+(?:(?:/[a-z]+|[a-z]+\\d+))?)'


# #### EXPORTED VARIABLE ####
shell_uk_ccu_regex = unified_length_aware_pattern
# #### EXPORTED VARIABLE ####


# #### Counts of minimal patterns for different criteria ####
#   They are generated from VOR_CcuHires_20240604-153615.csv and VOR_OwnedAssets_20240604-153634.csv.
#   These are just for inspection, they are not used in the codebase.
#   The unified_* patterns above are generated from these keyes (excluding the commented-out lines ones).


# Consecutive digits and letters with precise lengths or ranges
minimal_length_ranges_patterns = Counter({
    '[a-z]{1,3}\\d{3,4}': 608,
    '\\d{4,6}': 44,
    '[a-z]{2,3}\\d{1,2}\\-\\d{2,3}': 30,
    '\\d[a-z]{3}\\d{3}': 22,
    '\\d{4}/[a-z]': 11,
    '\\d{3}[a-z]\\d{4}[a-z]{2}\\d{2}': 1,
    '[a-z]{3}\\-[a-z]{2}\\d{3}': 1,
    '[a-z]{2}\\d{3}\\-[a-z]': 1
})


# Consecutive digits and letters with precise lengths but no ranges
#   I.e. a less refined version of minimal_length_ranges_patterns
minimal_length_aware_patterns = Counter({
    '[a-z]{3}\\d{3}': 205,
    '[a-z]{2}\\d{3}': 185,
    '[a-z]{3}\\d{4}': 103,
    '[a-z]{2}\\d{4}': 85,
    '\\d{4}': 40,
    '[a-z]\\d{3}': 30,
    '[a-z]{2}\\d{2}\\-\\d{3}': 27,
    '\\d[a-z]{3}\\d{3}': 22,
    '\\d{4}/[a-z]': 11,
    '[a-z]{3}\\d\\-\\d{2}': 3,
    '\\d{6}': 2,
    '\\d{5}': 2,
    '\\d{3}[a-z]\\d{4}[a-z]{2}\\d{2}': 1,
    '[a-z]{3}\\-[a-z]{2}\\d{3}': 1,
    '[a-z]{2}\\d{3}\\-[a-z]': 1
})


# Consecutive digits and letters with unknown lengths
minimal_length_unaware_patterns = Counter({
    '[a-z]+\\d+': 608,
    '\\d+': 44,
    '[a-z]+\\d+\\-\\d+': 30,
    '\\d+[a-z]+\\d+': 22,
    '\\d+/[a-z]+': 11,
    '\\d+[a-z]+\\d+[a-z]+\\d+': 1,  # ['271N1063MS06']
    '[a-z]+\\-[a-z]+\\d+': 1,  # ['AMC-OT559']
    '[a-z]+\\d+\\-[a-z]+': 1  # ['KA047-S']
})


