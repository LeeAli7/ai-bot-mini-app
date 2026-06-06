import hashlib
import hmac
import time
from urllib.parse import parse_qs, unquote

from config import BOT_TOKEN


def validate_init_data(init_data: str, max_age: int = 86400) -> dict | None:
    """
    Validates Telegram WebApp initData string.
    Returns parsed user data dict if valid, None if invalid.
    """
    if not init_data:
        return None

    # Parse query string
    parsed = {}
    for pair in init_data.split("&"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        parsed[key] = unquote(value)

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    # Build data-check-string (sorted keys joined by \n)
    data_check_string = "\n".join(
        f"{k}={parsed[k]}" for k in sorted(parsed.keys())
    )

    # Compute secret key: HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()

    # Compute hash: HMAC-SHA256(secret_key, data_check_string)
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_hash, computed_hash):
        return None

    # Check auth_date freshness
    auth_date = int(parsed.get("auth_date", 0))
    if time.time() - auth_date > max_age:
        return None

    # Parse user from initData
    user_raw = parsed.get("user", "{}")
    import json
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None

    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
    }
