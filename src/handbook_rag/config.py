"""Application settings: `config.yaml` + environment variables.

Precedence (highest first): env vars -> `.env` file -> `config.yaml` -> defaults.
Nested keys use `__` in env vars, e.g. `LOGGING__LEVEL=DEBUG`, `LOGGING__FORMAT=console`.

Secrets are `SecretStr` fields and may come only from the environment; putting one in
`config.yaml` is an error. Only the `logging` section is typed for now; other sections
are added when the code that uses them lands.
"""

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from handbook_rag.logging_setup import LogFormat

CONFIG_FILE = "config.yaml"


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: LogFormat = "json"
    log_payloads: bool = False


class _YamlWithoutSecrets(YamlConfigSettingsSource):
    """YAML source that refuses any top-level key typed as `SecretStr`."""

    def __init__(self, settings_cls: type[BaseSettings], **kwargs: Any) -> None:
        super().__init__(settings_cls, **kwargs)
        secret_fields = {
            name
            for name, field in settings_cls.model_fields.items()
            if SecretStr in (field.annotation, *get_args(field.annotation))
        }
        leaked = secret_fields.intersection(self.yaml_data)
        if leaked:
            raise ValueError(
                f"Secrets must come from environment variables, not {self.yaml_file_path}: "
                f"{sorted(leaked)}"
            )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=CONFIG_FILE,
        env_file=".env",
        env_nested_delimiter="__",
        # config.yaml has sections not typed yet; ignore them instead of failing.
        extra="ignore",
    )

    logging: LoggingSettings = LoggingSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, dotenv_settings, _YamlWithoutSecrets(settings_cls))


def load_settings() -> Settings:
    """Read `config.yaml` from the current directory and apply env overrides."""
    return Settings()
