"""
Utils file with various handy functions
"""


def truncate_json(obj, max_list_length=5, max_depth=2, _depth=0):
    """
    Truncate a JSON-like structure to a max depth and list/dict size.

    Parameters:
        obj (Any): The object to truncate.
        max_list_length (int): Max number of items per list or dict.
        max_depth (int): Max depth to recurse into nested structures.
        _depth (int): Internal parameter to track recursion depth.

    Returns:
        Any: A truncated version of the input object.
    """
    if isinstance(obj, dict):
        if _depth >= max_depth:
            return {k: '...' for k in list(obj.keys())[:max_list_length]}
        truncated = {}
        for i, (k, v) in enumerate(obj.items()):
            if i >= max_list_length:
                break
            truncated[k] = truncate_json(v, max_list_length, max_depth, _depth + 1)
        return truncated

    elif isinstance(obj, list):
        if _depth >= max_depth:
            return ['...'] * min(len(obj), max_list_length)
        truncated = [
            truncate_json(item, max_list_length, max_depth, _depth + 1)
            for item in obj[:max_list_length]
        ]
        if len(obj) > max_list_length:
            truncated.append('...')
        return truncated

    return obj


def filter_dataframe(df, filters=None):
    """
    Filters a pandas DataFrame based on optional filters.

    Parameters:
    - df (pd.DataFrame): The input DataFrame to filter.
    - filters (dict): Optional filters in the form of {column_name: filter_value}.
                      filter_value can be:
                          - A scalar (e.g., 5, 'A')
                          - A list/tuple/set of values (e.g., [1, 2, 3])
                          - A callable function (e.g., lambda x: x > 5)
                          - A tuple with (operator, value), e.g. ('>', 5)
                          - None (ignored)

    Returns:
    - pd.DataFrame: Filtered DataFrame.
    """
    if filters is None:
        return df.copy()

    ops = {
        "==": lambda x, y: x == y,
        "!=": lambda x, y: x != y,
        ">": lambda x, y: x > y,
        "<": lambda x, y: x < y,
        ">=": lambda x, y: x >= y,
        "<=": lambda x, y: x <= y,
    }

    filtered_df = df.copy()
    for column, condition in filters.items():
        if column not in filtered_df.columns:
            # case where filter column not in dataset, ignore it
            continue
        if condition is None or condition == "":
            continue
        if len(condition) == 2 and condition[1] is None:
            # where the filter condition is empty, skip
            continue
        if callable(condition):
            filtered_df = filtered_df[filtered_df[column].apply(condition)]
        elif isinstance(condition, (list, tuple, set)) and not isinstance(condition, tuple):
            filtered_df = filtered_df[filtered_df[column].isin(condition)]
        elif isinstance(condition, tuple) and len(condition) == 2 and condition[0] in ops:
            op_func = ops[condition[0]]
            filtered_df = filtered_df[op_func(filtered_df[column], condition[1])]
        else:
            filtered_df = filtered_df[filtered_df[column] == condition]

    return filtered_df
