from django.conf import settings
from django.core.signing import BadSignature, TimestampSigner
from django.http import Http404
from django.views.static import serve as static_serve
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import ai, services
from .models import Account, Appeal, ChatMessage
from .serializers import (AccountSerializer, AppealSerializer, ReadingSerializer,
                          TransactionSerializer)
from .services import ServiceError


def fail(msg, code=400):
    return Response({"detail": str(msg)}, status=code)


def _account_of(user, pk):
    try:
        acc = Account.objects.filter(pk=int(pk), user=user).first()
    except (TypeError, ValueError):
        acc = None
    if acc is None:
        raise NotFound("Hisob topilmadi")
    return acc


def _float_or_none(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def media_view(request, path):
    """Rasmlar: faqat admin (staff) yoki imzolangan havola orqali."""
    ok = request.user.is_authenticated and request.user.is_staff
    if not ok:
        try:
            ok = TimestampSigner(salt="media").unsign(request.GET.get("t", ""), max_age=6 * 3600) == path
        except BadSignature:
            ok = False
    if not ok:
        raise Http404
    resp = static_serve(request, path, document_root=settings.MEDIA_ROOT)
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


@method_decorator(xframe_options_exempt, name="dispatch")  # Telegram Web iframe uchun
class IndexView(TemplateView):
    template_name = "index.html"


class MeView(APIView):
    parser_classes = [JSONParser]

    def get(self, request):
        p = request.user.profile
        return Response({
            "first_name": request.user.first_name,
            "username": p.username,
            "phone": p.phone,
            "language": p.language,
            "demo_payments": settings.DEMO_PAYMENTS,
            "payme_enabled": services.payme_enabled(),
            "accounts": AccountSerializer(request.user.accounts.all(), many=True).data,
        })

    def patch(self, request):
        try:
            if "phone" in request.data:
                services.save_phone(request.user, str(request.data["phone"]))
        except ServiceError as e:
            return fail(e)
        return self.get(request)


class AccountListCreate(APIView):
    parser_classes = [JSONParser]

    def get(self, request):
        return Response(AccountSerializer(request.user.accounts.all(), many=True).data)

    def post(self, request):
        d = request.data
        try:
            acc = services.create_account(
                request.user, d.get("number", ""), d.get("label", "Uy"), d.get("network", "natural"),
                d.get("address", ""), _float_or_none(d.get("lat")), _float_or_none(d.get("lng")),
            )
        except ServiceError as e:
            return fail(e)
        return Response(AccountSerializer(acc).data, status=status.HTTP_201_CREATED)


class AccountDetail(APIView):
    parser_classes = [JSONParser]

    def patch(self, request, pk):
        acc = _account_of(request.user, pk)
        d = request.data
        if "label" in d:
            acc.label = str(d["label"]).strip()[:50] or acc.label
        if "address" in d:
            acc.address = str(d["address"]).strip()[:255]
        if "lat" in d:
            acc.lat = _float_or_none(d.get("lat"))
        if "lng" in d:
            acc.lng = _float_or_none(d.get("lng"))
        acc.save()
        return Response(AccountSerializer(acc).data)

    def delete(self, request, pk):
        _account_of(request.user, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DashboardView(APIView):
    def get(self, request, pk):
        acc = _account_of(request.user, pk)
        last = acc.readings.first()
        return Response({
            "account": AccountSerializer(acc).data,
            "last_reading": ReadingSerializer(last).data if last else None,
            "monthly": services.monthly_consumption(acc),
            "readings": ReadingSerializer(acc.readings.all()[:5], many=True).data,
            "transactions": TransactionSerializer(acc.transactions.all()[:8], many=True).data,
            "tariff": float(settings.GAS_TARIFF),
        })


class ReadingCreate(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        acc = _account_of(request.user, request.data.get("account"))
        if acc is None:
            return fail("Hisob tanlanmagan")
        photo = request.FILES.get("photo")
        if photo and photo.size > 8 * 1024 * 1024:
            return fail("Rasm 8 MB dan oshmasligi kerak")
        try:
            r = services.add_reading(acc, request.data.get("value"), photo)
        except ServiceError as e:
            return fail(e)
        return Response(ReadingSerializer(r).data, status=status.HTTP_201_CREATED)


class TopupView(APIView):
    parser_classes = [JSONParser]

    def post(self, request):
        acc = _account_of(request.user, request.data.get("account"))
        if acc is None:
            return fail("Hisob tanlanmagan")
        provider = str(request.data.get("provider", "demo"))[:20]
        if provider == "payme" and services.payme_enabled():
            try:
                amount = int(float(request.data.get("amount")))
            except (TypeError, ValueError):
                return fail("Summa noto'g'ri")
            if not 1000 <= amount <= 50_000_000:
                return fail("Summa 1 000 dan 50 000 000 so'mgacha bo'lishi kerak")
            return Response({"checkout_url": services.payme_checkout_url(acc, amount)})
        try:
            t = services.demo_topup(acc, request.data.get("amount"), str(request.data.get("provider", "demo"))[:20])
        except ServiceError as e:
            return fail(e, 403 if not settings.DEMO_PAYMENTS else 400)
        return Response(TransactionSerializer(t).data, status=status.HTTP_201_CREATED)


class AppealListCreate(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        qs = Appeal.objects.filter(user=request.user).select_related("account")[:50]
        return Response(AppealSerializer(qs, many=True).data)

    def post(self, request):
        acc = _account_of(request.user, request.data.get("account")) if request.data.get("account") else None
        photo = request.FILES.get("photo")
        if photo and photo.size > 8 * 1024 * 1024:
            return fail("Rasm 8 MB dan oshmasligi kerak")
        kind = "ai" if request.data.get("kind") == "ai" else "operator"
        try:
            a = services.create_appeal(request.user, request.data.get("category"),
                                       request.data.get("text"), acc, photo, kind)
        except ServiceError as e:
            return fail(e)
        return Response(AppealSerializer(a).data, status=status.HTTP_201_CREATED)


class ChatView(APIView):
    parser_classes = [JSONParser]

    def get(self, request):
        msgs = list(ChatMessage.objects.filter(user=request.user).order_by("-id")[:30])[::-1]
        return Response([{"role": m.role, "content": m.content} for m in msgs])

    def post(self, request):
        text = str(request.data.get("message", "")).strip()
        if not text:
            return fail("Xabar bo'sh")
        acc = _account_of(request.user, request.data.get("account")) if request.data.get("account") else None
        history = [{"role": m.role, "content": m.content}
                   for m in ChatMessage.objects.filter(user=request.user).order_by("-id")[:8][::-1]]
        if not services.chat_rate_ok(request.user):
            return fail("Juda tez yozyapsiz, bir daqiqa kuting", 429)
        ChatMessage.objects.create(user=request.user, role="user", content=text[:2000])
        reply, suggest = ai.answer(text, acc, history)
        ChatMessage.objects.create(user=request.user, role="assistant", content=reply)
        return Response({"reply": reply, "suggest_operator": suggest})

    def delete(self, request):
        ChatMessage.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
