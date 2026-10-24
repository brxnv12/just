from urllib.parse import quote

from django.conf import settings
from django.core.signing import TimestampSigner
from rest_framework import serializers

from .models import Account, Appeal, MeterReading, Transaction


class SignedImageField(serializers.ImageField):
    """Rasmga vaqtinchalik imzolangan havola beradi (ochiq /media/ emas)."""

    def to_representation(self, value):
        if not value:
            return None
        token = TimestampSigner(salt="media").sign(value.name)
        return f"{settings.MEDIA_URL}{value.name}?t={quote(token, safe='')}"


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    unit = serializers.CharField(read_only=True)

    class Meta:
        model = Account
        fields = ["id", "number", "label", "network", "address", "lat", "lng", "balance", "unit"]


class ReadingSerializer(serializers.ModelSerializer):
    photo = SignedImageField(read_only=True)

    class Meta:
        model = MeterReading
        fields = ["id", "value", "consumption", "photo", "created_at"]


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ["id", "amount", "kind", "provider", "note", "created_at"]


class AppealSerializer(serializers.ModelSerializer):
    photo = SignedImageField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    account_number = serializers.CharField(source="account.number", read_only=True, default=None)

    class Meta:
        model = Appeal
        fields = ["id", "kind", "category", "text", "photo", "status", "status_label",
                  "reply", "account_number", "created_at"]
