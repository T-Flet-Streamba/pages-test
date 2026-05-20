from collabgpt_get_ls_warnings import filter_items


def test_filtering_events(logistics_summary_warnings_cvx):
    """Testing the dataframe filtering util
    """
    filters = {
        "location": "barrowislandrevlog",
        "projectCode": "JIC"
    }
    assert len(logistics_summary_warnings_cvx) == 13
    data_filtered = filter_items(logistics_summary_warnings_cvx, filters=filters)

    assert data_filtered is not None
    assert len(data_filtered) == 2


def test_filtering_events_empty(logistics_summary_warnings_cvx):
    """Testing the dataframe filtering util
    """
    filters = {
        "location": "barrowislandrevlog",
        "projectCode": "TEST"
    }
    assert len(logistics_summary_warnings_cvx) == 13
    data_filtered = filter_items(logistics_summary_warnings_cvx, filters=filters)

    assert len(data_filtered) == 0


def test_filtering_transit_time(logistics_summary_warnings_cvx):
    """Testing the dataframe filtering util
    """
    filters = {
        "type": "RoadTransportJobHCRTransitTimeExceededWarning",
    }
    assert len(logistics_summary_warnings_cvx) == 13
    data_filtered = filter_items(logistics_summary_warnings_cvx, filters=filters)

    assert len(data_filtered) == 2


def test_filtering_threshold(logistics_summary_warnings_cvx):
    """Testing the dataframe filtering util
    """
    filters = {
        "type": "HcrDwellTimeExceededAtLocation",
        "location": "barrowislandrevlog",
        "threshold": (">=", 9)
    }
    assert len(logistics_summary_warnings_cvx) == 13
    data_filtered = filter_items(logistics_summary_warnings_cvx, filters=filters)

    assert len(data_filtered) == 4
