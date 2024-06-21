Pole: A high-level vault tool
=============================

Pole is a human-oriented interface to [Hashicorp
Vault](https://www.vaultproject.io/)/[OpenBao](https://openbao.org/) which
provides a convenient way to find and read secrets within a `kv` secrets
engine.

Pole provides the following useful functionality:

* Recursively enumerate secrets
* Fuzzy-search of all secrets (powered by [fzf](https://github.com/junegunn/fzf))
* Load secrets directly into the clipboard
* Match URLs and `ssh` commands to secret names automatically using
  user-defined rules for password-manager like usage.

Pole *is not*:

* A substitute for the `vault` command
* Suitable for use in scripts/playbooks
* Able to read non-`kv` values
* Able to modify or delete secrets
* Able to access kv V2 metadata or historical secret versions


Usage examples
--------------

Reading values:

    $ pole get passwords/example
    Key       Value
    ========  =======
    username  AzureDiamond
    password  hunter2
    
    $ pole get passwords/example password
    hunter2
    
    $ pole get passwords/example password --copy
    Selected passwords/example
    Copied password value to clipboard!
    Clipboard will be cleared in 30 seconds.
    
    $ pole get passwords/example --json
    {
      "username": "AzureDiamond",
      "password": "hunter2"
    }

> *Note:* Pole will auto-detect the version of the `kv` secrets engine in use
> and will, by default, assume it is mounted at `secret/`. By contrast with the
> `vault` tool, you don't need to use different commands per `kv` version nor
> prefix paths with `secret/` (or provide this explicitly in an argument). (See
> `--kv-version` and `--mount` arguments to override).

Searching for secrets using [fzf fuzzy
search](https://github.com/junegunn/fzf):

    $ pole ls find
    > passwords/example
    1/4
    > examp

More boringly listing secrets:

    $ pole ls
    passwords/
    certificates/
    et-cetera
    
    $ pole tree
    /
    ├── passwords/
    │   ├── example
    │   └── foobar
    ├── certificates/
    │   └── swimming-100-meters
    └── et-cetera

Using [user-defined rules](#secret-guessing) to lookup relevant secrets, e.g.
based on URLs or SSH invocations:

    $ pole --no-verify guess "https://compute116-ipmi.example.com/#/login"
    Guessed passwords/ipmi/compute116
    Key       Value
    ========  =====
    password  1234


Installation
------------

Install using `pip` into your chosen Python environment:

    $ pip install "git+ssh://git@github.com/bbc/pole.git@main"

For fuzzy-search functionality, [fzf](https://github.com/junegunn/fzf) must be
installed.

For clipboard support under Linux you'll need to install `xclip` (if you use an
X11 based desktop) or `wl-clipboard` (if you use a Wayland based desktop).

For example, on Debian/Ubuntu, use:

    $ sudo apt install fzf xclip wl-clipboard


Configuration
-------------

Like the `vault` command, pole will look for the Vault/OpenBao server address
in `VAULT_ADDR` environment variable. It can also be specified using the
`--address` argument.

Pole will also use the token in the `VAULT_TOKEN` environment variable (or
`~/.vault-token`, or [token
helper](https://developer.hashicorp.com/vault/docs/commands/token-helper)).
Alternatively, it can be supplied via the `--token` argument.

By default pole assumes your `kv` store is mounted at `secret/`. If needed, you
can specify an alternative mountpoint using `--mount` or the
`POLE_VAULT_KV_MOUNT` environment variable.

If your Vault instance is using a non-public HTTPS certificate you'll
(regrettably) need to configure pole using one of the following (in descending
order of precedence):

* Set the `--certificate-authority` argument
* Set the `POLE_VAULT_CA` environment variable
* Place the certificate in `default_ca.pem` in the pole config directory (on
  Linux this is `~/.config/pole/`, see `pole --help` for your local platform's
  location).


Secret guessing
---------------

Pole's secret guessing feature makes it possible to define mappings between,
for example, URLs or SSH commands, and secrets (e.g. passwords) stored in
Vault. This can make it easier to find the secrets you need, especially in a
somewhat 'organically' grown Vault. Combined with pole's clipboard integration,
its makes it possible to use pole like a password manager.

For example, a rule might be defined to map IPMI web interface URLs to secrets
like:

    $ pole guess "http://compute103-ipmi.hosts.example.com/login"
    Guessed passwords/ipmi/compute103
    Key       Value
    =====     =============
    password  verysecure123

As with the `get` command, the `--copy` argument can be used to place the
matched secret in the clipboard. Further, if no argument is given to `pole
guess`, the value to search with is taken from the clipboard. For example, you
could select and copy the URL from your browser then run the following to put
the password in your clipboard:

    $ pole guess --copy
    Guessed passwords/ipmi/compute103
    Copied ADMIN value to clipboard!
    Clipboard will be cleared in 30 seconds.

> *Tip:* Try assigning the above to a keyboard shortcut in your desktop
> environment!


### Defining guessing rules

Guessing rules are defined in [`*.toml`](https://toml.io/en/) files in the
`guess` subdirectory of pole's configuration directory. On Linux this will be
`~/.config/pole/guess`, on other platforms see `--rules` in `pole guess
--help`. Alternatively you can specify an alternative directory using the
`--rules` argument.

A guessing rule file is a simple [TOML](https://toml.io/en/) which contains one
or many rules. An example rules file looks might look like this:

    [[rule]]
    name = "IPMI URL to password"
    match = 'http://(.*)-ipmi\.hosts\.example\.com/.*'
    path = "passwords/ipmi/{1}"
    
    [[rule]]
    name = "Switch to password"
    match = 'ssh (switch[0-9]+)( .*)?'
    path = "passwords/switches/{1}"

These rules would then allow you to do things like:

    $ pole guess "http://compute103-ipmi.hosts.example.com/login"
    Guessed passwords/ipmi/compute103
    Key       Value
    =====     =============
    password  verysecure123

The `rule` tables may have the following keys:

#### `name`

**Required.**

A short human-readable description of what the matching rule
does. Used in error messages to identify the rule.

#### `match`

**Required.**

A [Python-style regular expression](https://docs.python.org/3/library/re.html)
which matches the complete string to be matched.

#### `path`

**Required.**

A [Python `.format()`
style](https://docs.python.org/3/library/string.html#custom-string-formatting)
string template defining the path to the vault secret to fetch.

Within a template `{n}` is substituted for capture group 'n' in the `match`
regular expression. For example `{1}` is replaced with the value of the first
capture group. You can also reference named capture groups, e.g. `{name}` --
see the [`(?P<name>...)` syntax in the Python `re`
docs](https://docs.python.org/3/library/re.html).

If your vault isn't perfectly consistently laid out, you can provide a list
instead of a single string value for `path`. Pole will try each suggestion in
turn until it finds one which exists. For example:

    [[rule]]
    name = "Switch to password"
    match = 'ssh (switch[0-9]+)( .*)?'
    
    # Ooops, some people used `switches` whilst others used `switch`!
    path = [
        "passwords/switches/{1}",  # Try this spelling first
        "passwords/switch/{1}",    # Then this one
    ]

Complex regular expressions may have some capture groups which don't always
match, `path` templates which reference capture groups which don't match are
skipped. For example:

    [[rule]]
    name = "Switch to password"
    match = 'ssh ([^@\s]+@)?(switch[0-9]+)( .*)?'
    
    path = [
        # This first path will only be returned if the regular expression
        # matched a user name (i.e. the 1st capture group exists)
        "passwords/switches/{2}/user-{1}",
        
        # This path will tried if no username was matched in the ssh command
        # (or the secret above does not exist).
        "passwords/switches/{2}",
    ]

#### `key`

**Optional.**

When pole's `--copy` option is used, pole needs some way to know *which* of a
secret's keys to copy into the clipboard. For secrets with just a single value
defined, pole will always pick that. For secrets with multiple values, the
`key` value can be used to tell pole which one to pick by default.

The `key` option may be either a single string or a list of strings. Pole will
try each key specified in turn until it finds one which exists for the matched
secret.

If a secret has multiple keys and none match `key`, pole will stop and produce
an error indicating that the user must pick one of the secrets. In particular,
pole will not continue trying other matching rules.

#### `priority`

**Optional.**

To make pole try a particular guessing rule before (or after) others, the
`priority` option can be given. Guessing rules with higher numerical `priority`
values will be chosen first. If not specified, rules have a priority of 0.



### Guessing rule priority

Pole's `guess` command will test the provided input against every rule defined
until a `match` is found which yields a `path` which exists in Vault. The order
of rule evaluation is (in decreasing order of precedence):

* Highest `priority` value first, then...
* Lexicographically highest filename first (e.g. `50-rules.toml` before
  `20-rules.toml`), then...
* First-most definition within a file.


### Unix/Linux Clipboard precedence

On Unix/Linux desktops, pole will first test all guessing rules against the
value in the primary clipboard before falling back on testing against the value
in the system clipboard. That is, the primary clipboard has a higher
precedence.

> *Note:* Most Unix/Linux desktop environments have *two* separate clipboards
> referred to as the 'primary' and 'system' clipboards. The primary clipboard
> is the one which is automatically populated when selecting text and pasted
> using middle-click. The system clipboard is the one usually populated and
> pasted from using shortcuts like Ctrl+C and Ctrl+V.
