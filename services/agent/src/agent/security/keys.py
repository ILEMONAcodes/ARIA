"""Database keys stay in a native credential vault, never in configuration files."""

from __future__ import annotations

import base64
import binascii
import secrets
from typing import Protocol, cast

import keyring


class KeyUnavailableError(RuntimeError):
    """The encryption key could not be retrieved safely."""


class DatabaseKeyProvider(Protocol):
    def get_key(self, database_id: str, *, create: bool) -> bytes: ...


class VaultBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...


def _native_backend() -> VaultBackend:
    backend = keyring.get_keyring()
    native = {
        ("keyring.backends.Windows", "WinVaultKeyring"),
        ("keyring.backends.macOS", "Keyring"),
    }
    if (type(backend).__module__, type(backend).__name__) not in native:
        raise KeyUnavailableError("A native Windows or macOS credential vault is required")
    return cast(VaultBackend, backend)


class OSVaultKeyProvider:
    def get_key(self, database_id: str, *, create: bool) -> bytes:
        try:
            backend = _native_backend()
            encoded = backend.get_password("ARIA.Database", database_id)
            if encoded is None:
                if not create:
                    raise KeyUnavailableError("The existing database key is unavailable")
                encoded = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
                backend.set_password("ARIA.Database", database_id, encoded)
                # Confirm persistence before creating a database dependent on this key.
                if backend.get_password("ARIA.Database", database_id) != encoded:
                    raise KeyUnavailableError("Could not verify the saved database key")
            key = base64.b64decode(encoded, validate=True)
            if len(key) != 32:
                raise KeyUnavailableError("The stored database key is invalid")
            return key
        except (binascii.Error, ValueError):
            raise KeyUnavailableError("The stored database key is invalid") from None
        except KeyUnavailableError:
            raise
        except Exception:  # noqa: BLE001 - scrub errors from native credential backends
            raise KeyUnavailableError("The credential vault is unavailable") from None
