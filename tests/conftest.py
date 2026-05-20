"""
Test fixtures module
"""
import json
import pytest


@pytest.fixture
def logistics_summary_warnings():
    with open("data/logistics_summary_warnings.json") as f:
        data = json.load(f)
    return data


@pytest.fixture
def logistics_summary_warnings_cvx():
    with open("data/logistics_summary_warnings_cvx.json") as f:
        data = json.load(f)
    return data
