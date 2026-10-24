from django.contrib import admin
from django.utils.html import format_html

from .models import Account, Appeal, ChatMessage, MeterReading, Profile, Transaction


class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    fields = ("kind", "amount", "provider", "note", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "tg_id", "username", "phone", "language", "created_at")
    search_fields = ("tg_id", "username", "phone", "user__first_name")


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("number", "label", "user", "network", "address", "balance_display", "map")
    search_fields = ("number", "address", "user__first_name", "user__profile__phone")
    list_filter = ("network",)
    inlines = [TransactionInline]

    @admin.display(description="Balans")
    def balance_display(self, obj):
        return f"{obj.balance:,.0f}"

    @admin.display(description="Xarita")
    def map(self, obj):
        if obj.lat and obj.lng:
            return format_html('<a target="_blank" href="https://www.openstreetmap.org/?mlat={0}&mlon={1}#map=18/{0}/{1}">Ochish</a>', obj.lat, obj.lng)
        return "-"


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("account", "value", "consumption", "created_at", "photo")
    search_fields = ("account__number",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("account", "kind", "amount", "provider", "created_at")
    list_filter = ("kind", "provider")
    search_fields = ("account__number",)


@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "user", "account", "kind", "status", "created_at")
    list_filter = ("status", "kind")
    list_editable = ("status",)
    search_fields = ("text", "account__number", "user__first_name")
    readonly_fields = ("user", "account", "kind", "category", "text", "photo", "created_at")
    fields = ("user", "account", "kind", "category", "text", "photo", "status", "reply", "created_at")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at")


from .models import PaymeTransaction  # noqa: E402


@admin.register(PaymeTransaction)
class PaymeTransactionAdmin(admin.ModelAdmin):
    list_display = ("paycom_id", "account", "amount", "state", "reason")
    list_filter = ("state",)
    readonly_fields = [f.name for f in PaymeTransaction._meta.fields]
