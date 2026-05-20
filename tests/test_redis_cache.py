"""
Tests for the redis cache data shared module
"""
from collabgpt_get_ls_warnings import SummaryWarningsCache


def test_get_summary_warnings(mocker, logistics_summary_warnings):
    """Simple test to ensure the redis summary warnings function works as expected
    """
    # mock the response of the redis _get_data function with a fixture
    r = SummaryWarningsCache(org="Test")
    mocker.patch.object(r, "_get_data", lambda x: logistics_summary_warnings)
    data = r.get_summary_warnings(filter_type="InboundHighCostRentalsForVoyageSummary")
    assert data is not None
    assert len(data) > 0


