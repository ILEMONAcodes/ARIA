import pytest

from agent.config import ENV_FIELDS, SettingsError, load_settings


def test_defaults_can_load_offline_without_creating_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = load_settings(environ={})
    assert settings.profile == "hosted"
    assert settings.gateway_url is None
    assert settings.install_token is None
    assert settings.vad_silence_ms == 700
    assert settings.cloud_timeout_s == 8
    assert settings.confidence_threshold == 0.6
    assert settings.db_key_source == "os_vault"
    assert list(tmp_path.iterdir()) == []


def test_environment_overrides_file_then_defaults(tmp_path):
    path = tmp_path / "agent.toml"
    path.write_text('[agent]\nprofile = "local"\ncloud_enabled = true\nvad_silence_ms = 600\n')
    settings = load_settings(path, environ={"ARIA_CLOUD_ENABLED": "false"})
    assert settings.profile == "local"
    assert settings.cloud_enabled is False
    assert settings.vad_silence_ms == 600
    assert settings.log_level == "INFO"


def test_file_paths_are_relative_to_settings_file_and_env_paths_to_cwd(tmp_path, monkeypatch):
    directory = tmp_path / "config"
    directory.mkdir()
    path = directory / "agent.toml"
    path.write_text('[agent]\nlibrary_path = "policies"\ndb_path = "private.db"\n')
    monkeypatch.chdir(tmp_path)
    settings = load_settings(path, environ={"ARIA_DB_PATH": "override.db"})
    assert settings.library_path == directory / "policies"
    assert settings.db_path == tmp_path / "override.db"


def test_install_token_is_environment_only_and_not_serialized(tmp_path):
    settings = load_settings(environ={"ARIA_INSTALL_TOKEN": "fictional-install-token"})
    assert settings.install_token.get_secret_value() == "fictional-install-token"
    assert "fictional-install-token" not in repr(settings)
    assert "install_token" not in settings.model_dump()
    assert "fictional-install-token" not in settings.model_dump_json()
    path = tmp_path / "agent.toml"
    path.write_text('[agent]\ninstall_token = "fictional-install-token"\n')
    with pytest.raises(SettingsError, match="environment"):
        load_settings(path, environ={})


def test_environment_reads_only_agent_variables_and_accepts_https_gateway():
    settings = load_settings(
        environ={
            "ARIA_GATEWAY_URL": "https://gateway.example.com",
            "GATEWAY_PROVIDER_API_KEY": "fictional-provider-key",
            "ARIA_INSTALL_TOKEN": "",
        }
    )
    assert str(settings.gateway_url) == "https://gateway.example.com/"
    assert settings.install_token is None
    assert "fictional-provider-key" not in settings.model_dump_json()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ARIA_PROFILE", "unknown"),
        ("ARIA_CLOUD_ENABLED", "perhaps"),
        ("ARIA_VAD_SILENCE_MS", "499"),
        ("ARIA_VAD_SILENCE_MS", "801"),
        ("ARIA_CLOUD_TIMEOUT_S", "0"),
        ("ARIA_CLOUD_TIMEOUT_S", "9"),
        ("ARIA_CONFIDENCE_THRESHOLD", "1.1"),
        ("ARIA_CONFIDENCE_THRESHOLD", "nan"),
        ("ARIA_DB_KEY_SOURCE", "plaintext"),
        ("ARIA_LOG_LEVEL", "LOUD"),
        ("ARIA_GATEWAY_URL", "http://gateway.example.com"),
        ("ARIA_GATEWAY_URL", "https://user:fictional-password@gateway.example.com"),
        ("ARIA_GATEWAY_URL", "https://gateway.example.com?token=fictional-token"),
        ("ARIA_GATEWAY_URL", "https://gateway.example.com/#fictional-token"),
    ],
)
def test_invalid_settings_fail_without_exposing_values(key, value):
    with pytest.raises(SettingsError) as error:
        load_settings(environ={key: value})
    assert key in str(error.value)
    assert value not in str(error.value)


@pytest.mark.parametrize("text", ["[agent", '[agent]\nunknown_setting = "fictional-value"', ""])
def test_malformed_or_unknown_file_settings_are_rejected(tmp_path, text):
    path = tmp_path / "agent.toml"
    path.write_text(text)
    with pytest.raises(SettingsError):
        load_settings(path, environ={})


def test_missing_explicit_settings_file_is_an_error(tmp_path):
    with pytest.raises(SettingsError):
        load_settings(tmp_path / "missing.toml", environ={})


def test_real_environment_is_used_when_no_mapping_is_supplied(monkeypatch):
    for variable in ENV_FIELDS:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("ARIA_PROFILE", "local")
    assert load_settings().profile == "local"
