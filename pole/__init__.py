__version__ = "0.0.1"

import os
import sys
import asyncio
import re
import string
from argparse import ArgumentParser, Namespace
import urllib3
import json
from pathlib import Path

import platformdirs

from hvac import Client
from hvac.api.secrets_engines.kv_v1 import KvV1
from hvac.api.secrets_engines.kv_v2 import KvV2
from hvac.exceptions import InvalidPath, Forbidden

from pole.text_art import dict_to_table, PathsToTrees
from pole.async_utils import countdown
from pole.clipboard import copy, paste, temporarily_copy
from pole.guess import guess, GuessError
from pole.vault import (
    detect_kv_version,
    read_secret,
    list_secrets,
    list_secrets_recursive,
)


async def ls_command(parser: ArgumentParser, args: Namespace, kv: KvV1 | KvV2) -> None:
    """Implements the 'ls' command."""
    if args.recursive:
        async for key in list_secrets_recursive(kv, args.path, mount_point=args.mount):
            print(key)
    else:
        for key in await list_secrets(kv, args.path, mount_point=args.mount):
            print(key)


async def tree_command(
    parser: ArgumentParser, args: Namespace, kv: KvV1 | KvV2
) -> None:
    """Implements the 'tree' command."""
    ptt = PathsToTrees()
    print(args.path.rstrip("/") + "/")
    async for path in list_secrets_recursive(kv, args.path, mount_point=args.mount):
        print(ptt.push(path), end="")
    print(ptt.close())


def print_secret(secrets: dict[str, str], key: str | None, use_json: bool) -> None:
    """Print a secret to stdout."""
    # Print secrets to the terminal
    if use_json:
        if key is not None:
            print(json.dumps(secrets[key]))
        else:
            print(json.dumps(secrets, indent=2))
    else:
        if key is not None:
            print(secrets[key])
        else:
            print(dict_to_table(secrets))


async def copy_secret(key: str, value: str, delay: float) -> None:
    """Place a secret in the clipboard."""
    if delay != 0:
        async with temporarily_copy(value):
            print(f"Copied {key} value to clipboard!")
            await countdown(
                "Clipboard will be cleared in {} second{s}.",
                delay,
            )
            print(f"Clipboard cleared.")
    else:
        await copy(value)
        print(f"Copied {key} value to clipboard!")


async def get_command(parser: ArgumentParser, args: Namespace, kv: KvV1 | KvV2) -> None:
    """Implements the 'get' command."""
    secrets = await read_secret(kv, args.path, mount_point=args.mount)

    # Verify key is valid if given
    if args.key is not None:
        if args.key not in secrets:
            print(
                f"Error: Unknown key {args.key}, expected one of {', '.join(secrets)}",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.copy:
        # Place secrets into clipboard
        if args.key is not None:
            key = args.key
            value = secrets[args.key]
        else:
            if len(secrets) != 1:
                print(
                    f"Error: Secret has multiple keys ({', '.join(secrets)}). Pick one."
                )
                sys.exit(1)
            key, value = secrets.copy().popitem()

        # Place in the clipboard
        await copy_secret(key, value, args.clear_clipboard_delay)
    else:
        print_secret(secrets, args.key, args.json)


async def fzf_command(parser: ArgumentParser, args: Namespace, kv: KvV1 | KvV2) -> None:
    """Implements the 'fzf' command."""
    # Start fzf
    try:
        fzf = await asyncio.create_subprocess_exec(
            "fzf",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        print(
            "Error: The 'fzf' command must be installed to use this feature.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Enumerate all secrets
        assert fzf.stdin is not None
        async for path in list_secrets_recursive(kv, "", mount_point=args.mount):
            if fzf.returncode is not None:  # FZF already quit!
                break

            fzf.stdin.write(f"{path}\n".encode("utf-8"))
        fzf.stdin.close()

        # Wait for the user to make their choic
        stdout, _stderr = await fzf.communicate()
    except BaseException:
        # Kill fzf before throwing the exception to avoid corrupting terminal
        fzf.terminate()
        await fzf.wait()
        raise

    if stdout.strip() != "":
        # Get the value
        args.path = stdout.decode("utf-8").splitlines()[0]
        await get_command(parser, args, kv)
    else:
        # Nothing selected!
        print("Error: No secret selected.", file=sys.stderr)
        sys.exit(1)


async def guess_command(
    parser: ArgumentParser, args: Namespace, kv: KvV1 | KvV2
) -> None:
    """Implements the 'guess' command."""

    # Use hints from clipboard if none given
    hints: tuple[str, ...]
    if args.hint:
        hints = (args.hint,)
    else:
        hints = await paste()

    # Find the first guessed secret which actually exists
    for path, keys in guess(args.rules, hints):
        try:
            secrets = await read_secret(kv, path, mount_point=args.mount)
            break
        except InvalidPath:
            continue
    else:
        print(f"Error: No matching rules.", file=sys.stderr)
        sys.exit(1)

    print(f"Guessed {path}")

    # Verify key is valid if given
    if args.key is not None:
        if args.key not in secrets:
            print(
                f"Error: Unknown key {args.key}, expected one of {', '.join(secrets)}",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.copy:
        # Work out which key to pick
        if args.key is not None:
            # Key specified, use that one
            key = args.key
            value = secrets[args.key]
        elif len(secrets) == 1:
            # Only one secret, use that one
            key, value = secrets.copy().popitem()
        else:
            # Multiple secrets. See if any are mentioned by the matched rule.
            for key in keys:
                if key in secrets:
                    value = secrets[key]
                    break
            else:
                print(
                    f"Error: Secret has multiple keys ({', '.join(secrets)}). Pick one."
                )
                sys.exit(1)

        # Place in the clipboard
        await copy_secret(key, value, args.clear_clipboard_delay)
    else:
        print_secret(secrets, args.key, args.json)


async def async_main() -> None:
    parser = ArgumentParser(
        description="""
            A high-level `vault` wrapper for simplified day-to-day reading of
            secrets in a kv store.
        """
    )

    parser.add_argument(
        "--address",
        default=None,
        help="""
            The vault server URL. If not given, uses the value in the
            VAULT_ADDRESS environment variable.
        """,
    )
    parser.add_argument(
        "--token",
        default=None,
        help="""
            The vault token to use. If not given, uses the value in the
            VAULT_ADDRESS environment variable or the configured Vault token
            agent.
        """,
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        default=False,
        help="""
            If given, do not verify HTTPS TLS certificates.
        """,
    )
    parser.add_argument(
        "--kv-version",
        type=int,
        default=None,
        help="""
            The version of the kv secrets engine to target. If not given, auto
            detection will be attempted (which requires list priviledges for
            the root).
        """,
    )
    parser.add_argument(
        "--mount",
        default=os.environ.get("POLE_VAULT_KV_MOUNT", "secret"),
        help="""
            The mount point of the kv store to access. Defaults to the value in
            the POLE_VAULT_KV_MOUNT environment variable or, if that is not
            defined, 'secret'.
        """,
    )

    subparsers = parser.add_subparsers(title="command", required=True)

    ls_parser = subparsers.add_parser(
        "ls",
        aliases=["list"],
        help="""
            List the secrets at a given path.
        """,
    )
    ls_parser.set_defaults(command=ls_command)
    ls_parser.add_argument(
        "path",
        nargs="?",
        default="",
        help="""
            The path to list. Defaults to the root of the kv store.
        """,
    )
    ls_parser.add_argument(
        "--recursive",
        "-R",
        "-r",
        action="store_true",
        default=False,
        help="""
            List the contents of the provided directory recursively.
        """,
    )

    tree_parser = subparsers.add_parser(
        "tree",
        help="""
            Recursively visualise the tree of secrets at a given path.
        """,
    )
    tree_parser.set_defaults(command=tree_command)
    tree_parser.add_argument(
        "path",
        nargs="?",
        default="",
        help="""
            The path to list. Defaults to the root of the kv store.
        """,
    )

    get_parser = subparsers.add_parser(
        "get",
        aliases=["read"],
        help="""
            Get a secret from a given path.
        """,
    )
    get_parser.set_defaults(command=get_command)
    get_parser.add_argument(
        "path",
        default="",
        help="""
            The secret to read.
        """,
    )

    def add_get_non_path_arguments(get_parser: ArgumentParser) -> None:
        get_parser.add_argument(
            "key",
            nargs="?",
            default=None,
            help="""
                The specific key to be read. If not given, all secrets will be
                printed.
            """,
        )
        get_parser.add_argument(
            "--json",
            "-j",
            action="store_true",
            default=False,
            help="""
                Print the secret as a JSON object (if no specific key specified) or
                as a JSON string (if a specific key is given). Ignored when --copy
                is used.
            """,
        )
        get_parser.add_argument(
            "--copy",
            "-c",
            action="store_true",
            default=False,
            help="""
                Do not display the secret, instead place it in the clipboard. For
                values with multiple keys, each key is placed into the clipboard in
                sequence.
            """,
        )
        get_parser.add_argument(
            "--clear-clipboard-delay",
            "-C",
            metavar="SECONDS",
            type=float,
            default=30,
            help="""
                When --copy is used, the clipboard will be automatically cleared
                again after this many seconds. Set to 0 to disable. Default:
                %(default)s.
            """,
        )

    add_get_non_path_arguments(get_parser)

    fzf_parser = subparsers.add_parser(
        "fzf",
        aliases=["find", "search"],
        help="""
            Search for and then print a secret using fzf (fuzzy find).
        """,
    )
    fzf_parser.set_defaults(command=fzf_command)
    add_get_non_path_arguments(fzf_parser)

    guess_parser = subparsers.add_parser(
        "guess",
        aliases=["auto"],
        help="""
            Use a user-defined set of rules to guess the appropriate secret to
            fetch.
        """,
    )
    guess_parser.set_defaults(command=guess_command)
    guess_parser.add_argument(
        "hint",
        nargs="?",
        default="",
        help="""
            The 'hint' to provide to the user-defined matching rules. If
            omitted (or an empty string), uses the value in the clipboard.
        """,
    )
    guess_parser.add_argument(
        "--rules",
        "-r",
        type=Path,
        default=Path(platformdirs.user_config_dir("pole", "BBC")) / "guess",
        help="""
            The directory from which to read *.toml files containing rules.
            Default %(default)s.
        """,
    )
    add_get_non_path_arguments(guess_parser)

    args = parser.parse_args()

    if args.no_verify:
        urllib3.disable_warnings()

    client = Client(
        url=args.address,
        token=args.token,
        verify=not args.no_verify,
    )

    try:
        # Select kv version
        if args.kv_version is None:
            kv = await detect_kv_version(client, args.mount)
        elif args.kv_version == 1:
            kv = client.secrets.kv.v1
        elif args.kv_version == 2:
            kv = client.secrets.kv.v2
        else:
            parser.error(f"unsupported kv version: {args.kv_version}")

        # Run the command
        await args.command(parser, args, kv)
    except InvalidPath as exc:
        print(f"Error: Invalid path: {exc}", file=sys.stderr)
        sys.exit(1)
    except Forbidden as exc:
        print(f"Error: Forbidden: {exc}", file=sys.stderr)
        sys.exit(1)
    except GuessError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    asyncio.run(async_main())
