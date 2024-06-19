import pytest

from typing import Iterator

import os
from pathlib import Path
from subprocess import Popen, run, PIPE
import json
import time

from hvac import Client
from hvac.api.secrets_engines.kv_v1 import KvV1
from hvac.api.secrets_engines.kv_v2 import KvV2

from pole.vault import (
    detect_kv_version,
    list_secrets,
    list_secrets_recursive,
)


@pytest.fixture
def vault(tmp_path: Path) -> Iterator[Client]:
    """
    Test fixture which spins up an in-memory Vault intance and sets vault
    environment variables to point at it with a root token.

    Returns a connected Client but also temporarily sets the vault server and
    root token in environment variables.
    """
    server_config_file = tmp_path / "config.hcl"
    server_config_file.write_text(
        """
            storage "inmem" {}

            listener "tcp" {
              address     = "127.0.0.1:8200"
              tls_disable = "true"
            }

            api_addr = "http://127.0.0.1:8200"
        """
    )

    vault_process = Popen(
        [
            "vault",
            "server",
            "-config",
            str(server_config_file),
        ],
        cwd=server_config_file.parent,
    )
    environ_before = os.environ.copy()
    try:
        os.environ["VAULT_ADDR"] = "http://127.0.0.1:8200"

        # Wait for vault to start
        client = Client()
        for _attempt in range(10):
            try:
                client.sys.is_initialized()  # API endpoint always available
                break
            except:
                time.sleep(0.05)
                continue
        else:
            raise ConnectionError()

        # Initialise vault
        init_result = client.sys.initialize(secret_shares=1, secret_threshold=1)
        os.environ["VAULT_TOKEN"] = client.token = init_result["root_token"]

        # Unseal it
        client.sys.submit_unseal_keys(init_result["keys"])
        assert not client.sys.is_sealed()

        yield client
    finally:
        os.environ.clear()
        os.environ.update(environ_before)
        vault_process.kill()


class TestDetectKvVersion:
    async def test_v1(self, vault: Client) -> None:
        vault.sys.enable_secrets_engine(
            backend_type="kv",
            path="my-secrets/",
            options={"version": "1"},
        )
        vault.secrets.kv.v1.create_or_update_secret(
            "foo", {"bar": "baz"}, mount_point="my-secrets/"
        )

        assert isinstance(await detect_kv_version(vault, "my-secrets/"), KvV1)

    async def test_v2(self, vault: Client) -> None:
        vault.sys.enable_secrets_engine(
            backend_type="kv",
            path="my-secrets/",
            options={"version": "2"},
        )
        vault.secrets.kv.v2.create_or_update_secret(
            "foo", {"bar": "baz"}, mount_point="my-secrets/"
        )

        assert isinstance(await detect_kv_version(vault, "my-secrets/"), KvV2)


class TestListSecrets:
    async def test_v1(self, vault: Client) -> None:
        vault.sys.enable_secrets_engine(
            backend_type="kv",
            path="secret/",
            options={"version": "1"},
        )
        vault.secrets.kv.v1.create_or_update_secret("foo", {"a": "x"})
        vault.secrets.kv.v1.create_or_update_secret("bar/baz", {"a": "x"})

        assert await list_secrets(vault.secrets.kv.v1, "") == ["bar/", "foo"]
        assert await list_secrets(vault.secrets.kv.v1, "bar/") == ["baz"]

    async def test_v2(self, vault: Client) -> None:
        vault.sys.enable_secrets_engine(
            backend_type="kv",
            path="secret/",
            options={"version": "2"},
        )
        vault.secrets.kv.v2.create_or_update_secret("foo", {"a": "x"})
        vault.secrets.kv.v2.create_or_update_secret("bar/baz", {"a": "x"})

        assert await list_secrets(vault.secrets.kv.v2, "") == ["bar/", "foo"]
        assert await list_secrets(vault.secrets.kv.v2, "bar/") == ["baz"]


async def test_list_secrets_recursive(vault: Client) -> None:
    vault.sys.enable_secrets_engine(
        backend_type="kv",
        path="secret/",
        options={"version": "2"},
    )
    vault.secrets.kv.v2.create_or_update_secret("foo", {"a": "x"})
    vault.secrets.kv.v2.create_or_update_secret("bar/baz", {"a": "x"})
    vault.secrets.kv.v2.create_or_update_secret("bar/qux/quo", {"a": "x"})

    secrets = []
    async for secret in list_secrets_recursive(vault.secrets.kv.v2):
        secrets.append(secret)

    assert secrets == [
        "bar/baz",
        "bar/qux/quo",
        "foo",
    ]
