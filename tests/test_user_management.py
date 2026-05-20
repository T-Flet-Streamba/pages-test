"""
Tests for the user management shared module
"""
import pytest
from shared.user_management import UserManagement


def test_get_by_id():
    """Testing user management tool, get by id
    """
    api = UserManagement()
    with pytest.raises(KeyError):
        api.get_teams_email_by_id("abd")


def test_get_by_email():
    """Testing user management tool, get by email
    """
    api = UserManagement()
    with pytest.raises(KeyError):
        api.get_teams_id_by_email("abc")
