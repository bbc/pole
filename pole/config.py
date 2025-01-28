"""
This module defines the set of configuration directories which pole will search
for its configuration. See notes in README about precedence.

When used as a script, prints the configuration directories in decending order
of precedence to stdout.
"""

from typing import Optional

import os
from pathlib import Path

import platformdirs

__all__ = ["config_dirs", "config_dir"]

_pd = platformdirs.PlatformDirs("pole", "bbc", multipath=True)

config_dirs = list(
    map(
        Path,
        os.pathsep.join([_pd.user_config_dir, _pd.site_config_dir]).split(os.pathsep),
    )
)
"""
The complete set of possible configuration directories, in reducing order of
precedence.
"""

config_dir: Optional[Path] = None
"""
The actual configuration directory in use.
"""

for p in config_dirs:
    if p.is_dir():
        config_dir = p


if __name__ == "__main__":
    for p in config_dirs:
        print(str(p))
