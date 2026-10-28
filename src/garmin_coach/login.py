"""One-time interactive Garmin Connect login.

Handles MFA and persists tokens (~1 year, self-refreshing) to
~/.garminconnect with 0700/0600 permissions. Run in a real terminal:

    uv run garmin-login
"""

import os
import stat
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin

from .client import TOKENSTORE


def main() -> None:
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin Connect email: ")
    password = os.environ.get("GARMIN_PASSWORD") or getpass("Garmin Connect password: ")

    garmin = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA code: "),
    )
    garmin.login()
    garmin.client.dump(TOKENSTORE)

    # dump() doesn't set permissions itself — lock the token dir/file down
    # (it always writes exactly one file: <TOKENSTORE>/garmin_tokens.json).
    token_dir = Path(TOKENSTORE).expanduser()
    token_dir.chmod(stat.S_IRWXU)  # 0700
    token_file = token_dir / "garmin_tokens.json"
    if token_file.exists():
        token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600

    print(f"Logged in as {garmin.get_full_name()}. Tokens saved to {TOKENSTORE}.")


if __name__ == "__main__":
    main()
