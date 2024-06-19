Pole: A high-level vaulting tool
================================

Pole is a simple wrapper around [Hashicorp
Vault](https://www.vaultproject.io/)/[OpenBao](https://openbao.org/) designed
to provide more convenient interactive access to secrets within a `kv` secrets
engine.

Pole provides the following useful functionality:

* Tab-completion
* Easy enumeration of all secrets
* Fuzzy-search of all secrets
* Load secrets directly into the clipboard
* Match URLs and `ssh` commands to secret names automatically using
  user-defined rules for password-manager like usage.

Example usage:

    $ pole ls secret/
    foo/
    bar/
    baz/
    qux
    quo
    
    $ pole tree secret/foo
    foo/
      subdir/
        secret_a
        secret_b
      secret_c
    
    $ pole find needle
    bar/hidden_needle_secret
    baz/iNeedLessSecrecy
    
    $ pole get secret/foo/secret_c
    Key      Value
    ======== ============
    user     AzureDiamond
    password hunter2
    
    $ pole get secret/foo/secret_c password
    hunter2
    
    $ pole copy secret/foo/secret_c password
    Copied password to clipboard.
    Will clear clipboard in 30 seconds or on exit.
    
    $ pole auto "https://ampere3-ipmi.os.mcr1.rd.bbc.co.uk/#/login"
    Copied password for secret/baz/ipmi/mcr1/ampere3.mcr1.
    Will clear clipboard in 30 seconds or on exit.
