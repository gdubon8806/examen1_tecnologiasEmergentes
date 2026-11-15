"""Tokens firmados (HMAC) para el login del dashboard. Solo libreria estandar."""
import base64
import hashlib
import hmac
import time


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user: str, secret: str, ttl: int = 8 * 3600, now: float | None = None) -> str:
    exp = int((now if now is not None else time.time()) + ttl)
    payload = _b64(f"{user}|{exp}".encode())
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token: str, secret: str, now: float | None = None) -> str | None:
    """Devuelve el usuario si el token es valido y no ha expirado; si no, None."""
    try:
        payload, sig = token.split(".", 1)
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        user, exp = _unb64(payload).decode().rsplit("|", 1)
        if (now if now is not None else time.time()) > int(exp):
            return None
        return user
    except Exception:  # noqa: BLE001  (token mal formado)
        return None


def same_text(a: str, b: str) -> bool:
    """Comparacion en tiempo constante (soporta acentos)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
