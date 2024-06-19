__version__ = "0.0.1"

from typing import AsyncIterator

import asyncio

from hvac import Client

from pole.vault import (
    detect_kv_version,
    list_secrets_recursive,
)


async def async_main() -> None:
    # XXX
    import urllib3

    urllib3.disable_warnings()

    # XXX
    client = Client(verify=False)
    mountpoint = "secret"
    kv = await detect_kv_version(client, mountpoint)
    from pprint import pprint

    async for key in list_secrets_recursive(kv, ""):
        print(key)


def main() -> None:
    asyncio.run(async_main())
