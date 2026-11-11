"""Who is calling the mini app: validation of the ``initData`` string Bale hands to the page.

The page sends ``Bale.WebApp.initData`` untouched with every request; nothing in it is trusted before the signature
has been checked with the bot's token (https://docs.bale.ai/miniapp).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl

#: an ``initData`` older than this is refused (the page gets a fresh one every time it is opened)
MAX_AGE_SECONDS = 24 * 3600


@dataclass(frozen=True)
class WebUser:
    id: int
    username: str | None = None
    first_name: str = ""


class AuthError(Exception):
    """The request carries no valid proof of who is asking."""


def _signatures(token: str, check_string: str) -> tuple[str, str]:
    """Both readings of the documented key derivation (key and message of the first HMAC swapped)."""
    out = []
    for key, message in ((b"WebAppData", token.encode()), (token.encode(), b"WebAppData")):
        secret = hmac.new(key, message, hashlib.sha256).digest()
        out.append(hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest())
    return out[0], out[1]


def validate(init_data: str, token: str, now: int, max_age: int = MAX_AGE_SECONDS) -> WebUser:
    """Check the signature and the age of ``initData`` and return the user it names."""
    if not init_data or len(init_data) > 8192:
        raise AuthError("no init data")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    given = pairs.pop("hash", "")
    if not given:
        raise AuthError("no hash")
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    if not any(hmac.compare_digest(given, good) for good in _signatures(token, check_string)):
        raise AuthError("bad signature")
    try:
        age = now - int(pairs.get("auth_date", "0"))
        user = json.loads(pairs.get("user", ""))
        user_id = int(user["id"])
    except (ValueError, KeyError, TypeError) as error:
        raise AuthError("bad payload") from error
    if age > max_age or age < -300:
        raise AuthError("expired")
    return WebUser(user_id, user.get("username") or None, str(user.get("first_name") or ""))


def sign(fields: dict[str, str], token: str) -> str:
    """Build a valid ``initData`` string (for tests and local tools)."""
    from urllib.parse import urlencode

    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    return urlencode({**fields, "hash": _signatures(token, check_string)[0]})
