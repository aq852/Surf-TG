"""Security primitives used by the web application.

The module deliberately has no Telegram or database dependencies so its
behaviour can be covered by fast unit tests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass


PBKDF2_ITERATIONS = 310_000


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return a portable PBKDF2-SHA256 password hash."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(digest).decode().rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _decode_b64(salt_text)
        expected = _decode_b64(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(rounds)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class StreamClaim:
    chat_id: int
    message_id: int
    expires_at: int
    scope: str = "stream"


class StreamTokenError(ValueError):
    pass


def create_stream_token(
    secret: str, chat_id: int, message_id: int, *, ttl: int = 6 * 60 * 60,
    now: int | None = None, scope: str = "stream"
) -> str:
    payload = {
        "c": int(chat_id),
        "m": int(message_id),
        "e": int(now if now is not None else time.time()) + ttl,
        "s": scope,
        "v": 2,
    }
    body = _encode_b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _encode_b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_stream_token(secret: str, token: str, *, now: int | None = None) -> StreamClaim:
    try:
        body, supplied_signature = token.split(".", 1)
        expected = _encode_b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected):
            raise StreamTokenError("invalid signature")
        payload = json.loads(_decode_b64(body))
        if payload.get("v") not in {1, 2}:
            raise StreamTokenError("unsupported token")
        claim = StreamClaim(
            int(payload["c"]), int(payload["m"]), int(payload["e"]),
            str(payload.get("s", "stream")),
        )
    except StreamTokenError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StreamTokenError("malformed token") from exc
    if claim.expires_at < int(now if now is not None else time.time()):
        raise StreamTokenError("expired token")
    return claim


def _encode_b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_b64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


if __name__ == "__main__":
    import getpass
    print(hash_password(getpass.getpass("Password: ")))
