import hashlib
import hmac
import time

from app.config import settings


def create_ws_token(caller: str) -> str:
    if not settings.ws_auth_secret:
        return ""
    expires = int(time.time()) + 120
    msg = f"{caller}:{expires}"
    sig = hmac.new(settings.ws_auth_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{sig}:{expires}"


def verify_ws_token(token: str, caller: str) -> bool:
    if not settings.ws_auth_secret:
        return True
    try:
        sig, expires_str = token.rsplit(":", 1)
        expires = int(expires_str)
        if time.time() > expires:
            return False
        msg = f"{caller}:{expires}"
        expected = hmac.new(
            settings.ws_auth_secret.encode(), msg.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, sig)
    except (ValueError, Exception):
        return False
