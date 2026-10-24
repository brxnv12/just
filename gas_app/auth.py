"""Telegram Mini App initData tekshiruvi (HMAC-SHA256)."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .services import get_or_create_tg_user


def validate_init_data(init_data: str) -> dict:
    if not settings.BOT_TOKEN:
        raise AuthenticationFailed("Serverda BOT_TOKEN sozlanmagan")
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise AuthenticationFailed("initData noto'g'ri")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise AuthenticationFailed("initData imzosi noto'g'ri")
    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if time.time() - auth_date > settings.INIT_DATA_MAX_AGE:
        raise AuthenticationFailed("Sessiya eskirgan, ilovani qayta oching")
    try:
        return json.loads(data["user"])
    except (KeyError, ValueError):
        raise AuthenticationFailed("Foydalanuvchi ma'lumoti yo'q")


class TelegramAuthentication(BaseAuthentication):
    def authenticate(self, request):
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        if init_data:
            tg_user = validate_init_data(init_data)
        elif settings.DEV_AUTH:
            # Faqat lokal sinov uchun (.env: DEV_AUTH=1)
            tg_user = {"id": 1, "first_name": "Dev Foydalanuvchi", "username": "dev"}
        else:
            return None
        user = get_or_create_tg_user(
            tg_user["id"], tg_user.get("first_name", ""), tg_user.get("username", "")
        )
        return (user, None)

    def authenticate_header(self, request):
        return "TelegramInitData"
