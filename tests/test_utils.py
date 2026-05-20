"""
Tests for the utils shared module
"""
from shared.utils import truncate_json


def test_truncate_json(logistics_summary_warnings):
    """Testing the json truncation util
    """
    data = truncate_json(logistics_summary_warnings, max_list_length=3, max_depth=4)
    assert data is not None
    assert len(data.get("items")) == 4  # list of 3 plus the "..."
    assert data.get("items")[1].get("flightUtilizations")[0].get("flightId") == '...'
    assert len(data) > 0
