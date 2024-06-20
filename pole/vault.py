from typing import AsyncIterator

import asyncio

from hvac import Client
from hvac.api.secrets_engines.kv_v1 import KvV1
from hvac.api.secrets_engines.kv_v2 import KvV2
from hvac.exceptions import InvalidPath

from pole.async_utils import eager_async_iter


async def detect_kv_version(client: Client, mount_point: str = "secret") -> KvV1 | KvV2:
    """
    Detect the kv store version mounted at the provided mount_point and return
    the relevant API class.
    """
    loop = asyncio.get_running_loop()
    kv1_list = loop.run_in_executor(
        None, client.secrets.kv.v1.list_secrets, "", mount_point
    )
    kv2_list = loop.run_in_executor(
        None, client.secrets.kv.v2.list_secrets, "", mount_point
    )

    try:
        await kv2_list
        return client.secrets.kv.v2
    except InvalidPath:
        await kv1_list
        return client.secrets.kv.v1
    except:
        # kv2_list failed for some other reason (e.g. access denied), cleanup
        kv1_list.cancel()
        raise


async def read_secret(kv: KvV1 | KvV2, path: str, mount_point: str = "secret"):
    """
    Read (the latest version of) a KV value from vault. Returns only the
    key/value pairs stored: any metadata is excluded.
    """
    if isinstance(kv, KvV1):
        return kv.read_secret(path, mount_point=mount_point)["data"]
    elif isinstance(kv, KvV2):
        return kv.read_secret_version(
            path,
            mount_point=mount_point,
            raise_on_deleted_version=True,
        )["data"]["data"]


async def list_secrets(
    kv: KvV1 | KvV2, path: str, mount_point: str = "secret"
) -> list[str]:
    """
    List the secrets at a given path.

    The returned list is sorted lexicographically.
    """
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, kv.list_secrets, path, mount_point)
    return sorted(response["data"]["keys"])


async def list_secrets_recursive(
    kv: KvV1 | KvV2,
    path: str = "",
    mount_point: str = "secret",
) -> AsyncIterator[str]:
    """
    List the secrets recursively at a given path.

    Generates a series of path names for all secrets recursively starting at
    the given path..

    Lists only secret paths (directory paths are omitted).

    Iteration is depth-first in hierarchical lexicographical order.
    """
    if not path.endswith("/"):
        path += "/"

    # Recurse into all child directories simultaneously
    child_iterators = {
        key: (
            eager_async_iter(list_secrets_recursive(kv, path + key, mount_point))
            if key.endswith("/")
            else None
        )
        for key in await list_secrets(kv, path, mount_point)
    }

    # Serialise the iteration
    for key, children in child_iterators.items():
        if children is None:
            yield key
        else:
            async for subkey in children:
                yield key + subkey
