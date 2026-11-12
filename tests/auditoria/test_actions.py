"""Pruebas del catálogo de acciones (SPEC 05, §3.1)."""

import pytest

from apps.auditoria.actions import ACTION_CATEGORIES, AuditAction, AuditCategory


def test_every_action_has_a_category():
    assert set(ACTION_CATEGORIES) == set(AuditAction)


def test_categories_are_valid():
    assert set(ACTION_CATEGORIES.values()) <= set(AuditCategory)


def test_the_four_categories_exist():
    assert set(AuditCategory.values) == {
        "access",
        "security",
        "personal_data",
        "financial",
    }


@pytest.mark.parametrize("action", [a for a in AuditAction if a.startswith("auth.")])
def test_access_actions_are_in_access_category(action):
    assert ACTION_CATEGORIES[action] is AuditCategory.ACCESS


@pytest.mark.parametrize("action", [a for a in AuditAction if a.startswith("users.")])
def test_user_actions_are_in_security_category(action):
    assert ACTION_CATEGORIES[action] is AuditCategory.SECURITY


def test_catalog_has_eight_access_and_seven_user_actions():
    categories = list(ACTION_CATEGORIES.values())
    user_actions = [a for a in AuditAction if a.startswith("users.")]

    assert categories.count(AuditCategory.ACCESS) == 8
    assert len(user_actions) == 7


def test_settings_actions_have_their_group_category():
    # SPEC 06, §3.7.
    assert ACTION_CATEGORIES == ACTION_CATEGORIES | {
        AuditAction.SETTINGS_BUSINESS_UPDATED: AuditCategory.SECURITY,
        AuditAction.SETTINGS_COLLECTION_UPDATED: AuditCategory.FINANCIAL,
        AuditAction.SETTINGS_ROUNDING_UPDATED: AuditCategory.FINANCIAL,
        AuditAction.SETTINGS_SECURITY_UPDATED: AuditCategory.SECURITY,
    }
    assert {a for a in AuditAction if a.startswith("parametros.")} == {
        AuditAction.SETTINGS_BUSINESS_UPDATED,
        AuditAction.SETTINGS_COLLECTION_UPDATED,
        AuditAction.SETTINGS_ROUNDING_UPDATED,
        AuditAction.SETTINGS_SECURITY_UPDATED,
    }


def test_action_values_fit_the_column():
    assert max(len(value) for value in AuditAction.values) <= 64
