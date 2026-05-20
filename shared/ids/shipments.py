from collections import Counter

# Context:
#   All regexes in this file share these first passes:
#       reduction of digit sequences to \d, of letter sequences to [a-z],
#       escaping of all regex-reserved characters, and removal of (all varieties of) spaces.
#   Then different final passes are performed w.r.t. the length of consecutive digits or letters; see sections below.


# #### Regexes to choose among for exporting ####

# Generated from the keys of minimal_length_aware_patterns (or, equivalently, minimal_length_ranges_patterns)
unified_length_aware_pattern = '(?:[a-z]{2}(?:[a-z](?:[a-z]\\d{7}|\\d{8})|\\d(?:[a-z](?:[a-z](?:\\-\\d(?:[a-z]{2}\\d{2}|\\d{4})|[a-z]\\d{5})|\\d{7})|\\d{2}\\-\\d{5}))|\\d{14})'

# Generated from the keys of minimal_length_unaware_patterns
unified_length_unaware_pattern = '(?:[a-z]+\\d+(?:[a-z]+(?:\\-\\d+|\\d+))?|\\d+)'


# #### EXPORTED VARIABLE ####
shipment_regex = unified_length_aware_pattern
# #### EXPORTED VARIABLE ####


# #### Counts of minimal patterns for different criteria ####
#   They are generated from the vordev-cvx-abu.shipments cosmos collection.
#   These are just for inspection, they are not used in the codebase.
#   The unified_* patterns above are generated from these keyes (excluding the commented-out lines ones).


# Consecutive digits and letters with precise lengths or ranges
minimal_length_ranges_patterns = Counter({
    '[a-z]{3,4}\\d{7,8}': 3961,
    '\\d{14}': 1435,
    '[a-z]{2}\\d[a-z]{1,3}\\d{5,7}': 73,
    '[a-z]{2}\\d[a-z]{2}\\-\\d{5}': 26,
    '[a-z]{2}\\d{3}\\-\\d{5}': 1,
    '[a-z]{2}\\d[a-z]{2}\\-\\d[a-z]{2}\\d{2}': 1
})


# Consecutive digits and letters with precise lengths but no ranges
#   I.e. a less refined version of minimal_length_ranges_patterns
minimal_length_aware_patterns = Counter({
    '[a-z]{4}\\d{7}': 3934,
    '\\d{14}': 1435,
    '[a-z]{2}\\d[a-z]\\d{7}': 71,
    '[a-z]{3}\\d{8}': 27,
    '[a-z]{2}\\d[a-z]{2}\\-\\d{5}': 26,
    '[a-z]{2}\\d[a-z]{3}\\d{5}': 2,
    '[a-z]{2}\\d{3}\\-\\d{5}': 1,
    '[a-z]{2}\\d[a-z]{2}\\-\\d[a-z]{2}\\d{2}': 1
})


# Consecutive digits and letters with unknown lengths
minimal_length_unaware_patterns = Counter({
    '[a-z]+\\d+': 3961,
    '\\d+': 1435,
    '[a-z]+\\d+[a-z]+\\d+': 73,
    '[a-z]+\\d+[a-z]+\\-\\d+': 26,
    '[a-z]+\\d+\\-\\d+': 1,
    '[a-z]+\\d+[a-z]+\\-\\d+[a-z]+\\d+': 1
})


