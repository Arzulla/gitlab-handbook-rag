"""Access model: handbook section -> access_group, role -> visible access_groups.

Loaded from `config/access.yaml`. Everything fails closed: an unknown section or role
raises; nothing ever defaults to `public`. The retrieval-time filter that uses these
groups lives in `retrieval/access.py`.
"""

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from handbook_rag.errors import AccessDeniedError

ACCESS_CONFIG_FILE = Path("config/access.yaml")

NonEmptyStr = Annotated[str, Field(min_length=1)]


class AccessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sections: dict[NonEmptyStr, NonEmptyStr]
    roles: dict[NonEmptyStr, list[NonEmptyStr]]

    @model_validator(mode="after")
    def _roles_use_known_groups(self) -> "AccessConfig":
        known = set(self.sections.values())
        for role, groups in self.roles.items():
            unknown = set(groups) - known
            if unknown:
                raise ValueError(f"Role {role!r} references unknown groups: {sorted(unknown)}")
        return self


def load_access_config(path: Path = ACCESS_CONFIG_FILE) -> AccessConfig:
    return AccessConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def access_group_for_section(section: str, config: AccessConfig) -> str:
    """Map a handbook section to its access group. Unknown section -> ValueError."""
    try:
        return config.sections[section]
    except KeyError:
        raise ValueError(f"Handbook section {section!r} is not in the access config") from None


def groups_for_role(role: str, config: AccessConfig) -> list[str]:
    """Access groups a role may see. Unknown or empty role -> AccessDeniedError."""
    try:
        return list(config.roles[role])
    except KeyError:
        raise AccessDeniedError(f"Unknown role: {role!r}") from None
