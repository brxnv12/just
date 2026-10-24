"""Payme Merchant API (JSON-RPC). Kabinetda Endpoint URL: https://DOMEN/api/payme/
Hujjat: https://developer.help.paycom.uz  (Payme test sandbox bilan tekshirib chiqing)
"""
import base64
import hmac
import json
import time
from decimal import Decimal

from django.conf import settings
from django.db import transaction as dbtx
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Account, PaymeTransaction, Transaction

TIMEOUT_MS = 12 * 3600 * 1000
MIN_TIYIN, MAX_TIYIN = 1000 * 100, 50_000_000 * 100


class PaymeError(Exception):
    def __init__(self, code, uz, ru="", en="", data=None):
        self.code, self.data = code, data
        self.message = {"uz": uz, "ru": ru or uz, "en": en or uz}


E_AUTH = lambda: PaymeError(-32504, "Ruxsat yo'q", "Недостаточно привилегий", "Insufficient privileges")
E_ACCOUNT = lambda: PaymeError(-31050, "Hisob topilmadi", "Счёт не найден", "Account not found", "account")
E_AMOUNT = lambda: PaymeError(-31001, "Summa noto'g'ri", "Неверная сумма", "Wrong amount")
E_NOT_FOUND = lambda: PaymeError(-31003, "Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found")
E_STATE = lambda: PaymeError(-31008, "Amalni bajarib bo'lmaydi", "Невозможно выполнить операцию", "Unable to perform operation")


def now_ms():
    return int(time.time() * 1000)


def authorized(request) -> bool:
    key = settings.PAYME_KEY
    header = request.headers.get("Authorization", "")
    if not key or not header.startswith("Basic "):
        return False
    try:
        login, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:  # noqa: BLE001
        return False
    return login == "Paycom" and hmac.compare_digest(pwd, key)


def _account(params):
    try:
        return Account.objects.filter(pk=int((params.get("account") or {}).get(settings.PAYME_ACCOUNT_FIELD))).first()
    except (TypeError, ValueError):
        return None


def _check(params):
    amount = params.get("amount")
    if not isinstance(amount, int) or not MIN_TIYIN <= amount <= MAX_TIYIN:
        raise E_AMOUNT()
    acc = _account(params)
    if not acc:
        raise E_ACCOUNT()
    return acc, amount


def _get(params):
    t = PaymeTransaction.objects.select_for_update().filter(paycom_id=str(params.get("id", ""))).first()
    if not t:
        raise E_NOT_FOUND()
    return t


def _expire(t):
    t.state, t.reason, t.cancel_time = -1, 4, now_ms()
    t.save()


def check_perform(params):
    _check(params)
    return {"allow": True}


def create_tx(params):
    t = PaymeTransaction.objects.select_for_update().filter(paycom_id=str(params.get("id", ""))).first()
    if t:
        if t.state != 1:
            return E_STATE()
        if now_ms() - t.create_time > TIMEOUT_MS:
            _expire(t)
            return E_STATE()
        return {"create_time": t.create_time, "transaction": str(t.pk), "state": t.state}
    acc, amount = _check(params)
    t = PaymeTransaction.objects.create(
        paycom_id=str(params["id"]), account=acc, amount=amount, state=1,
        payme_time=int(params.get("time") or 0), create_time=now_ms())
    return {"create_time": t.create_time, "transaction": str(t.pk), "state": t.state}


def perform_tx(params):
    t = _get(params)
    if t.state == 2:
        return {"transaction": str(t.pk), "perform_time": t.perform_time, "state": 2}
    if t.state != 1:
        return E_STATE()
    if now_ms() - t.create_time > TIMEOUT_MS:
        _expire(t)
        return E_STATE()
    t.state, t.perform_time = 2, now_ms()
    t.save()
    Transaction.objects.create(
        account=t.account, amount=Decimal(t.amount) / 100, kind=Transaction.Kind.TOPUP,
        provider="payme", note=f"Payme {t.paycom_id}")
    return {"transaction": str(t.pk), "perform_time": t.perform_time, "state": 2}


def cancel_tx(params):
    t = _get(params)
    if t.state in (-1, -2):
        return {"transaction": str(t.pk), "cancel_time": t.cancel_time, "state": t.state}
    if t.state == 2:
        Transaction.objects.create(
            account=t.account, amount=-(Decimal(t.amount) / 100), kind=Transaction.Kind.ADJUST,
            provider="payme", note=f"Payme qaytarish {t.paycom_id}")
        t.state = -2
    else:
        t.state = -1
    t.reason, t.cancel_time = params.get("reason"), now_ms()
    t.save()
    return {"transaction": str(t.pk), "cancel_time": t.cancel_time, "state": t.state}


def _view(t):
    return {"create_time": t.create_time, "perform_time": t.perform_time, "cancel_time": t.cancel_time,
            "transaction": str(t.pk), "state": t.state, "reason": t.reason}


def check_tx(params):
    return _view(_get(params))


def statement(params):
    qs = PaymeTransaction.objects.filter(payme_time__gte=int(params.get("from", 0)), payme_time__lte=int(params.get("to", 0))).order_by("payme_time")
    return {"transactions": [
        {"id": t.paycom_id, "time": t.payme_time, "amount": t.amount, "account": {settings.PAYME_ACCOUNT_FIELD: str(t.account_id)},
         **_view(t)} for t in qs]}


METHODS = {
    "CheckPerformTransaction": check_perform, "CreateTransaction": create_tx, "PerformTransaction": perform_tx,
    "CancelTransaction": cancel_tx, "CheckTransaction": check_tx, "GetStatement": statement,
}


def _err(rid, e: PaymeError):
    body = {"code": e.code, "message": e.message}
    if e.data:
        body["data"] = e.data
    return JsonResponse({"error": body, "id": rid})


@csrf_exempt
@require_POST
def payme_endpoint(request):
    try:
        body = json.loads(request.body)
        rid, method, params = body.get("id"), body.get("method"), body.get("params") or {}
    except (ValueError, AttributeError):
        return JsonResponse({"error": {"code": -32700, "message": "Parse error"}, "id": None})
    if not authorized(request):
        return _err(rid, E_AUTH())
    handler = METHODS.get(method)
    if not handler:
        return JsonResponse({"error": {"code": -32601, "message": "Method not found"}, "id": rid})
    try:
        with dbtx.atomic():
            result = handler(params)
    except PaymeError as e:
        return _err(rid, e)
    if isinstance(result, PaymeError):
        return _err(rid, result)
    return JsonResponse({"result": result, "id": rid})
