"""Biznes mantiq: view'lar ham, Telegram bot ham shu funksiyalardan foydalanadi."""
import base64
import json
import logging
import threading
import urllib.request
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.functions import TruncMonth
from django.db.models import Sum
from django.utils import timezone

log = logging.getLogger(__name__)


class ServiceError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato."""


# ---------- foydalanuvchi ----------
def get_or_create_tg_user(tg_id: int, first_name: str = "", username: str = "") -> User:
    from .models import Profile

    with transaction.atomic():
        profile = Profile.objects.select_related("user").filter(tg_id=tg_id).first()
        if profile:
            user = profile.user
            if first_name and user.first_name != first_name:
                user.first_name = first_name[:150]
                user.save(update_fields=["first_name"])
            if username != profile.username:
                profile.username = username or ""
                profile.save(update_fields=["username"])
            return user
        user = User.objects.create(username=f"tg_{tg_id}", first_name=(first_name or "")[:150])
        user.set_unusable_password()
        user.save()
        Profile.objects.create(user=user, tg_id=tg_id, username=username or "")
        return user


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 9:  # 901234567
        digits = "998" + digits
    if len(digits) != 12 or not digits.startswith("998"):
        raise ServiceError("Telefon raqami noto'g'ri. Misol: +998 90 123 45 67")
    return "+" + digits


def save_phone(user: User, raw: str) -> str:
    phone = normalize_phone(raw)
    user.profile.phone = phone
    user.profile.save(update_fields=["phone"])
    return phone


# ---------- hisoblar ----------
def clean_account_number(raw: str) -> str:
    number = "".join(ch for ch in (raw or "") if ch.isalnum())
    if not (5 <= len(number) <= 20):
        raise ServiceError("Hisob raqami 5-20 ta belgidan iborat bo'lishi kerak")
    return number


def create_account(user, number, label="Uy", network="natural", address="", lat=None, lng=None):
    from .models import Account

    number = clean_account_number(number)
    if Account.objects.filter(user=user, number=number).exists():
        raise ServiceError("Bu hisob raqami allaqachon qo'shilgan")
    if network not in dict(Account.Network.choices):
        network = Account.Network.NATURAL
    return Account.objects.create(
        user=user, number=number, label=(label or "Uy").strip()[:50] or "Uy",
        network=network, address=(address or "").strip()[:255], lat=lat, lng=lng,
    )


# ---------- rasm tekshiruvi ----------
def clean_photo(f):
    """Fayl haqiqatan rasm ekanini Pillow bilan tekshiradi, nomini xavfsiz qilib o'zgartiradi."""
    if f is None:
        return None
    from PIL import Image

    if getattr(f, "size", 0) > 8 * 1024 * 1024:
        raise ServiceError("Rasm 8 MB dan oshmasligi kerak")
    try:
        f.seek(0)
        img = Image.open(f)
        fmt = img.format
        img.verify()
    except Exception:  # noqa: BLE001
        raise ServiceError("Rasm fayli yaroqsiz")
    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt)
    if not ext:
        raise ServiceError("Faqat JPG, PNG yoki WEBP rasm yuklang")
    f.seek(0)
    return ContentFile(f.read(), name=f"{uuid.uuid4().hex}.{ext}")


def chat_rate_ok(user) -> bool:
    from .models import ChatMessage

    since = timezone.now() - timedelta(minutes=1)
    return ChatMessage.objects.filter(user=user, role="user", created_at__gte=since).count() < settings.CHAT_PER_MINUTE


# ---------- Payme ----------
def payme_checkout_url(account, amount_som) -> str:
    tiyin = int(Decimal(str(amount_som)) * 100)
    raw = f"m={settings.PAYME_MERCHANT_ID};ac.{settings.PAYME_ACCOUNT_FIELD}={account.pk};a={tiyin};l=uz"
    host = "https://test.paycom.uz" if settings.PAYME_TEST else "https://checkout.paycom.uz"
    return f"{host}/{base64.b64encode(raw.encode()).decode()}"


def payme_enabled() -> bool:
    return bool(settings.PAYME_MERCHANT_ID and settings.PAYME_KEY)


# ---------- ko'rsatkich ----------
def add_reading(account, value, photo=None):
    from .models import Account, MeterReading, Transaction

    photo = clean_photo(photo)
    try:
        value = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        raise ServiceError("Ko'rsatkich raqam bo'lishi kerak")
    if value < 0 or value > Decimal("99999999"):
        raise ServiceError("Ko'rsatkich noto'g'ri")

    with transaction.atomic():
        account = Account.objects.select_for_update().get(pk=account.pk)  # ketma-ket yuborishdan himoya
        prev = account.readings.order_by("-created_at", "-id").first()
        if prev and value < prev.value:
            raise ServiceError(f"Ko'rsatkich oldingisidan ({prev.value}) kam bo'lishi mumkin emas")
        consumption = (value - prev.value) if prev else Decimal("0")
        reading = MeterReading.objects.create(account=account, value=value, consumption=consumption, photo=photo)
        if consumption > 0:
            charge = (consumption * settings.GAS_TARIFF).quantize(Decimal("0.01"))
            Transaction.objects.create(
                account=account, amount=-charge, kind=Transaction.Kind.CHARGE,
                note=f"{consumption} {account.unit} × {settings.GAS_TARIFF}",
            )
    return reading


def monthly_consumption(account, months=6):
    from .models import MeterReading

    rows = (
        MeterReading.objects.filter(account=account)
        .annotate(m=TruncMonth("created_at"))
        .values("m").annotate(total=Sum("consumption")).order_by("-m")[:months]
    )
    return [{"month": r["m"].strftime("%Y-%m"), "volume": float(r["total"] or 0)} for r in reversed(list(rows))]


# ---------- to'lov (DEMO) ----------
def demo_topup(account, amount, provider="demo"):
    from .models import Transaction

    if not settings.DEMO_PAYMENTS:
        raise ServiceError("Onlayn to'lov hali ulanmagan. Payme/Click orqali to'lang.")
    try:
        amount = Decimal(str(amount))
    except InvalidOperation:
        raise ServiceError("Summa noto'g'ri")
    if amount < 1000 or amount > 50_000_000:
        raise ServiceError("Summa 1 000 dan 50 000 000 so'mgacha bo'lishi kerak")
    return Transaction.objects.create(
        account=account, amount=amount, kind=Transaction.Kind.TOPUP,
        provider=provider, note="DEMO to'lov",
    )


# ---------- murojaat ----------
def create_appeal(user, category, text, account=None, photo=None, kind="operator"):
    from .models import Appeal

    text = (text or "").strip()
    if len(text) < 5:
        raise ServiceError("Murojaat matni juda qisqa")
    photo = clean_photo(photo)
    return Appeal.objects.create(
        user=user, account=account, kind=kind, category=(category or "Boshqa")[:100],
        text=text[:4000], photo=photo,
    )


def photo_from_bytes(data: bytes, name="photo.jpg"):
    return ContentFile(data, name=name)


# ---------- Telegram xabar yuborish (admin javobi uchun) ----------
def _send_message(chat_id: int, text: str):
    if not settings.BOT_TOKEN:
        return
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
            data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegramga xabar yuborilmadi: %s", exc)


def notify_user(chat_id: int, text: str):
    threading.Thread(target=_send_message, args=(chat_id, text), daemon=True).start()


# ---------- AI uchun kontekst ----------
def account_context(account) -> str:
    if not account:
        return "Foydalanuvchida hisob qo'shilmagan."
    last = account.readings.order_by("-created_at", "-id").first()
    return (
        f"Hisob: {account.number} ({account.label}), tarmoq: {account.get_network_display()}, "
        f"manzil: {account.address or 'ko‘rsatilmagan'}, balans: {account.balance:,.0f} so'm, "
        f"oxirgi ko'rsatkich: {last.value if last else 'kiritilmagan'} {account.unit}, "
        f"1 {account.unit} narxi: {settings.GAS_TARIFF:,.0f} so'm."
    )
