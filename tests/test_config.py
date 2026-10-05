"""Settings tests run in a temp dir with their own config.yaml, never the repo's."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from handbook_rag.config import Settings, load_settings


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for var in ("LOGGING__LEVEL", "LOGGING__FORMAT", "LOGGING__LOG_PAYLOADS"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_defaults_without_config_file() -> None:
    settings = load_settings()

    assert settings.logging.level == "INFO"
    assert settings.logging.format == "json"
    assert settings.logging.log_payloads is False


def test_yaml_is_read_and_untyped_sections_ignored(isolated: Path) -> None:
    (isolated / "config.yaml").write_text(
        "logging:\n  level: DEBUG\n  format: console\nmodels:\n  judge: x\n"
    )

    settings = load_settings()

    assert settings.logging.level == "DEBUG"
    assert settings.logging.format == "console"


def test_env_overrides_yaml(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (isolated / "config.yaml").write_text("logging:\n  level: DEBUG\n  log_payloads: false\n")
    monkeypatch.setenv("LOGGING__LEVEL", "ERROR")
    monkeypatch.setenv("LOGGING__LOG_PAYLOADS", "true")

    settings = load_settings()

    assert settings.logging.level == "ERROR"
    assert settings.logging.log_payloads is True


def test_secret_in_yaml_is_rejected(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class WithSecret(Settings):
        api_key: SecretStr | None = None

    (isolated / "config.yaml").write_text("api_key: sk-from-yaml\n")
    with pytest.raises(ValueError, match="api_key"):
        WithSecret()

    (isolated / "config.yaml").write_text("")
    monkeypatch.setenv("API_KEY", "sk-from-env")
    secret = WithSecret().api_key
    assert secret is not None
    assert secret.get_secret_value() == "sk-from-env"
