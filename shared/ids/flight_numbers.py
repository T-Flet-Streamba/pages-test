from collections import Counter

# Context:
#   All regexes in this file share these first passes:
#       reduction of digit sequences to \d, of letter sequences to [a-z],
#       escaping of all regex-reserved characters, and removal of (all varieties of) spaces.
#   Then different final passes are performed w.r.t. the length of consecutive digits or letters; see sections below.


# #### Regexes to choose among for exporting ####

# Generated from the keys of minimal_length_aware_patterns (or, equivalently, minimal_length_ranges_patterns)
unified_length_aware_pattern = '[a-z]{2}(?:[a-z](?:[a-z](?:(?:[a-z](?:[a-z](?:[a-z]{2}(?:[a-z](?:(?:[a-z](?:\\d{2})?|\\d{2}))?)?|\\d{1,2})|\\d{1,2})|\\d{1,2}))?|\\d)|\\d{2}(?:\\d(?:\\d[a-z]?)?)?)'

# Generated from the keys of minimal_length_unaware_patterns
unified_length_unaware_pattern = '[a-z]+(?:\\d+[a-z]+?)?'


# #### EXPORTED VARIABLE ####
flight_number_regex = unified_length_aware_pattern
# #### EXPORTED VARIABLE ####


# #### Counts of minimal patterns for different criteria ####
#   They are generated from VOR_CcuHires_20240604-153615.csv and VOR_OwnedAssets_20240604-153634.csv.
#   These are just for inspection, they are not used in the codebase.
#   The unified_* patterns above are generated from these keyes (excluding the commented-out lines ones).


# Consecutive digits and letters with precise lengths or ranges
minimal_length_ranges_patterns = Counter({
    '[a-z]{2,10}\\d{1,4}': 70,
    '[a-z]{4,10}': 5,
    '[a-z]{2}\\d{4}[a-z]': 4
})


# Consecutive digits and letters with precise lengths but no ranges
#   I.e. a less refined version of minimal_length_ranges_patterns
minimal_length_aware_patterns = Counter({'[a-z]{2}\\d{4}': 19,
    '[a-z]{6}\\d{2}': 14,
    '[a-z]{5}\\d{2}': 11,
    '[a-z]{2}\\d{3}': 8,
    '[a-z]{4}\\d{2}': 4,
    '[a-z]{2}\\d{4}[a-z]': 4,
    '[a-z]{2}\\d{2}': 3,
    '[a-z]{4}\\d': 3,
    '[a-z]{6}\\d': 3,
    '[a-z]{9}': 2,
    '[a-z]{5}\\d': 2,
    '[a-z]{10}\\d{2}': 1,
    '[a-z]{3}\\d': 1,
    '[a-z]{8}': 1,
    '[a-z]{9}\\d{2}': 1,
    '[a-z]{10}': 1,
    '[a-z]{4}': 1
})


# Consecutive digits and letters with unknown lengths
minimal_length_unaware_patterns = Counter({
    '[a-z]+\\d+': 70,
    '[a-z]+': 5,
    '[a-z]+\\d+[a-z]+': 4
})


