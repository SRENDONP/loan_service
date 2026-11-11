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


def test_catalog_has_eight_access_and_seven_security_actions():
    categories = list(ACTION_CATEGORIES.values())

    assert categories.count(AuditCategory.ACCESS) == 8
    assert categories.count(AuditCategory.SECURITY) == 7


def test_action_values_fit_the_column():
    assert max(len(value) for value in AuditAction.values) <= 64
