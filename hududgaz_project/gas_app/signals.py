from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Appeal
from .services import notify_user


@receiver(pre_save, sender=Appeal)
def remember_old_state(sender, instance, **kwargs):
    if instance.pk:
        old = Appeal.objects.filter(pk=instance.pk).values("status", "reply").first()
        instance._old = old
    else:
        instance._old = None


@receiver(post_save, sender=Appeal)
def notify_on_change(sender, instance, created, **kwargs):
    old = getattr(instance, "_old", None)
    if created or not old:
        return
    changed_status = old["status"] != instance.status
    changed_reply = old["reply"] != instance.reply and instance.reply
    if not (changed_status or changed_reply):
        return
    text = f"📝 Murojaatingiz #{instance.pk}: {instance.get_status_display()}"
    if instance.reply:
        text += f"\n\n💬 Operator javobi:\n{instance.reply}"
    notify_user(instance.user.profile.tg_id, text)
