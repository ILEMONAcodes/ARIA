import base64

import pytest

from agent.security.keys import KeyUnavailableError, OSVaultKeyProvider, _native_backend


class FakeVault:
    def __init__(self):
        self.entries = {}

    def get_password(self, service, username):
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        self.entries[(service, username)] = password


@pytest.fixture
def vault(monkeypatch):
    vault = FakeVault()
    monkeypatch.setattr("agent.security.keys._native_backend", lambda: vault)
    return vault


def test_vault_generates_persists_and_reuses_a_256_bit_key(vault):
    provider = OSVaultKeyProvider()
    key = provider.get_key("fictional-database", create=True)
    assert len(key) == 32
    assert provider.get_key("fictional-database", create=False) == key
    assert provider.get_key("fictional-database", create=True) == key
    assert len(vault.entries) == 1
    assert base64.b64decode(next(iter(vault.entries.values()))) == key


def test_missing_existing_key_is_never_replaced(vault):
    with pytest.raises(KeyUnavailableError):
        OSVaultKeyProvider().get_key("fictional-database", create=False)
    assert vault.entries == {}


@pytest.mark.parametrize("encoded", ["not valid base64!", base64.b64encode(b"short").decode()])
def test_corrupt_stored_key_is_not_overwritten_or_exposed(vault, encoded):
    vault.entries[("ARIA.Database", "fictional-database")] = encoded
    with pytest.raises(KeyUnavailableError) as error:
        OSVaultKeyProvider().get_key("fictional-database", create=True)
    assert encoded not in str(error.value)
    assert vault.entries[("ARIA.Database", "fictional-database")] == encoded


def test_failed_vault_write_prevents_key_use(vault, monkeypatch):
    def fail(*args):
        raise RuntimeError("fictional-vault-secret")

    monkeypatch.setattr(vault, "set_password", fail)
    with pytest.raises(KeyUnavailableError) as error:
        OSVaultKeyProvider().get_key("fictional-database", create=True)
    assert "fictional-vault-secret" not in str(error.value)


def test_unpersisted_key_is_rejected(vault, monkeypatch):
    monkeypatch.setattr(vault, "set_password", lambda *args: None)
    with pytest.raises(KeyUnavailableError):
        OSVaultKeyProvider().get_key("fictional-database", create=True)


def test_untrusted_or_plaintext_vault_backend_is_rejected(monkeypatch):
    monkeypatch.setattr("keyring.get_keyring", FakeVault)
    with pytest.raises(KeyUnavailableError, match="native"):
        _native_backend()
