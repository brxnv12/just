import asyncio

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Telegram botni ishga tushirish (polling)"

    def handle(self, *args, **options):
        from bot.main import main

        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            self.stdout.write("Bot to'xtatildi")
