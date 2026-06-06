import datetime
import time

import jwt as pyjwt

from config import JWT_ALGORITHM, JWT_EXPIRE_DAYS, JWT_SECRET


def create_jwt(user_id: int, telegram_id: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "iat": now,
        "exp": now + datetime.timedelta(days=JWT_EXPIRE_DAYS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict | None:
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None
