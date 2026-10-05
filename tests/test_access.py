from pathlib import Path

import pytest
from pydantic import ValidationError

from handbook_rag.access import (
    AccessConfig,
    access_group_for_section,
    groups_for_role,
    load_access_config,
)
from handbook_rag.errors import AccessDeniedError

REPO_ACCESS_CONFIG = Path(__file__).parents[1] / "config" / "access.yaml"


@pytest.fixture
def access() -> AccessConfig:
    return load_access_config(REPO_ACCESS_CONFIG)


@pytest.mark.parametrize(
    ("role", "groups"),
    [
        ("employee", ["public"]),
        ("people_ops", ["public", "people"]),
        ("finance", ["public", "finance"]),
        ("legal", ["public", "legal"]),
    ],
)
def test_groups_for_known_roles(access: AccessConfig, role: str, groups: list[str]) -> None:
    assert groups_for_role(role, access) == groups


@pytest.mark.parametrize("role", ["admin", "", "Employee", "employee "])
def test_unknown_or_empty_role_is_denied(access: AccessConfig, role: str) -> None:
    with pytest.raises(AccessDeniedError):
        groups_for_role(role, access)


def test_unknown_section_raises_instead_of_defaulting_to_public(access: AccessConfig) -> None:
    assert access_group_for_section("legal", access) == "legal"
    with pytest.raises(ValueError, match="marketing"):
        access_group_for_section("marketing", access)


def test_role_referencing_unknown_group_is_rejected() -> None:
    with pytest.raises(ValidationError, match="secret"):
        AccessConfig(sections={"company": "public"}, roles={"employee": ["public", "secret"]})


def test_empty_access_group_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AccessConfig(sections={"company": ""}, roles={})
