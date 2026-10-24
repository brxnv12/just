from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum


class Profile(models.Model):
    class Lang(models.TextChoices):
        UZ = "uz", "O'zbekcha"
        RU = "ru", "Ruscha"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    tg_id = models.BigIntegerField(unique=True)
    username = models.CharField("Telegram username", max_length=64, blank=True)
    phone = models.CharField("Telefon", max_length=20, blank=True)
    language = models.CharField(max_length=2, choices=Lang.choices, default=Lang.UZ)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Profil"
        verbose_name_plural = "Profillar"

    def __str__(self):
        return f"{self.user.first_name or self.tg_id} ({self.tg_id})"


class Account(models.Model):
    class Network(models.TextChoices):
        NATURAL = "natural", "Tabiiy gaz"
        LPG = "lpg", "Suyultirilgan gaz"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accounts")
    number = models.CharField("Shaxsiy hisob raqami", max_length=20)
    label = models.CharField("Nomi (uy/ofis...)", max_length=50, default="Uy")
    network = models.CharField(max_length=10, choices=Network.choices, default=Network.NATURAL)
    address = models.CharField("Manzil", max_length=255, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Hisob"
        verbose_name_plural = "Hisoblar"
        unique_together = [("user", "number")]
        ordering = ["id"]

    def __str__(self):
        return f"{self.label} · {self.number}"

    @property
    def balance(self) -> Decimal:
        total = self.transactions.aggregate(s=Sum("amount"))["s"]
        return total or Decimal("0")

    @property
    def unit(self):
        return "m³" if self.network == self.Network.NATURAL else "kg"


class Transaction(models.Model):
    """Balans = barcha tranzaksiyalar yig'indisi (to'lov +, hisob-kitob -)."""

    class Kind(models.TextChoices):
        TOPUP = "topup", "To'lov"
        CHARGE = "charge", "Hisoblandi"
        ADJUST = "adjust", "Tuzatish"

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="transactions")
    amount = models.DecimalField("Summa (+/-)", max_digits=14, decimal_places=2)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    provider = models.CharField(max_length=20, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tranzaksiya"
        verbose_name_plural = "Tranzaksiyalar"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount}"


class MeterReading(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="readings")
    value = models.DecimalField("Ko'rsatkich", max_digits=12, decimal_places=2)
    consumption = models.DecimalField("Sarf", max_digits=12, decimal_places=2, default=0)
    photo = models.ImageField(upload_to="meters/%Y/%m/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ko'rsatkich"
        verbose_name_plural = "Ko'rsatkichlar"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.account.number}: {self.value}"


class Appeal(models.Model):
    class Kind(models.TextChoices):
        OPERATOR = "operator", "Operatorga ariza"
        AI = "ai", "AI orqali yo'naltirilgan"

    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        REVIEW = "review", "Ko'rib chiqilmoqda"
        DONE = "done", "Bajarildi"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="appeals")
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="appeals")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OPERATOR)
    category = models.CharField("Mavzu", max_length=100)
    text = models.TextField("Matn")
    photo = models.ImageField(upload_to="appeals/%Y/%m/", null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    reply = models.TextField("Operator javobi", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Murojaat"
        verbose_name_plural = "Murojaatlar"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"#{self.pk} {self.category}"


class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=10)  # user / assistant
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chat xabari"
        verbose_name_plural = "Chat xabarlari"
        ordering = ["id"]


class PaymeTransaction(models.Model):
    """Payme Merchant API tranzaksiyasi (holatlar: 1 yaratildi, 2 to'landi, -1/-2 bekor)."""

    paycom_id = models.CharField(max_length=40, unique=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="payme_transactions")
    amount = models.BigIntegerField("Summa (tiyin)")
    state = models.IntegerField(default=1)
    reason = models.IntegerField(null=True, blank=True)
    payme_time = models.BigIntegerField(default=0)
    create_time = models.BigIntegerField(default=0)
    perform_time = models.BigIntegerField(default=0)
    cancel_time = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "Payme tranzaksiya"
        verbose_name_plural = "Payme tranzaksiyalar"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.paycom_id} ({self.state})"
