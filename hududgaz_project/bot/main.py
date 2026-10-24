"""Telegram bot (aiogram 3): ro'yxatdan o'tish, balans, murojaat, AI yordamchi.
Ishga tushirish:  python manage.py runbot
"""
import asyncio
import io
import logging
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from aiogram import Bot, Dispatcher, F, Router  # noqa: E402
from aiogram.filters import Command, CommandStart  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.state import State, StatesGroup  # noqa: E402
from aiogram.types import (KeyboardButton, MenuButtonWebApp, Message,  # noqa: E402
                           ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo)
from django.conf import settings  # noqa: E402

from gas_app import ai, services  # noqa: E402
from gas_app.models import Account, Appeal, ChatMessage  # noqa: E402
from gas_app.services import ServiceError  # noqa: E402

log = logging.getLogger("bot")
router = Router()

BTN_APP = "📱 Ilovani ochish"
BTN_BAL = "💰 Balans"
BTN_APPEAL = "📝 Murojaat yuborish"
BTN_AI = "🤖 AI yordamchi"
BTN_MY = "📋 Murojaatlarim"
BTN_CANCEL = "❌ Bekor qilish"
BTN_SKIP = "⏭ O'tkazib yuborish"
BTN_TEXT_ADDR = "✍️ Manzilni yozaman"


class Reg(StatesGroup):
    phone = State()
    number = State()
    label = State()
    address = State()


class AppealFlow(StatesGroup):
    category = State()
    text = State()
    photo = State()


class Chat(StatesGroup):
    active = State()


# ---------- yordamchi (sinxron ORM -> thread) ----------
def run(fn, *a, **kw):
    return asyncio.to_thread(fn, *a, **kw)


def webapp_ok() -> bool:
    return settings.WEBAPP_URL.startswith("https://")


def main_kb() -> ReplyKeyboardMarkup:
    rows = []
    if webapp_ok():
        rows.append([KeyboardButton(text=BTN_APP, web_app=WebAppInfo(url=settings.WEBAPP_URL))])
    rows += [[KeyboardButton(text=BTN_BAL), KeyboardButton(text=BTN_APPEAL)],
             [KeyboardButton(text=BTN_AI), KeyboardButton(text=BTN_MY)]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb(*extra_rows):
    rows = [list(r) for r in extra_rows] + [[KeyboardButton(text=BTN_CANCEL)]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_user(m: Message):
    return services.get_or_create_tg_user(m.from_user.id, m.from_user.first_name or "", m.from_user.username or "")


def user_state(m: Message):
    user = get_user(m)
    return user, user.profile.phone, list(user.accounts.all())


# ---------- /start va ro'yxatdan o'tish ----------
@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    user, phone, accounts = await run(user_state, m)
    if phone and accounts:
        await m.answer(f"Assalomu alaykum, {m.from_user.first_name}! Menyudan tanlang 👇", reply_markup=main_kb())
        return
    await m.answer("Assalomu alaykum! Hududgaz botiga xush kelibsiz.\nAvval qisqa ro'yxatdan o'tamiz (3 qadam).")
    await ask_phone(m, state)


async def ask_phone(m: Message, state: FSMContext):
    await state.set_state(Reg.phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Raqamimni yuborish", request_contact=True)]], resize_keyboard=True)
    await m.answer("1/3 Telefon raqamingizni yuboring (tugmani bosing yoki +998901234567 ko'rinishida yozing):", reply_markup=kb)


@router.message(Reg.phone, F.contact)
async def reg_phone_contact(m: Message, state: FSMContext):
    if m.contact.user_id and m.contact.user_id != m.from_user.id:
        await m.answer("Iltimos, o'zingizning raqamingizni yuboring.")
        return
    await save_phone_and_next(m, state, m.contact.phone_number)


@router.message(Reg.phone, F.text)
async def reg_phone_text(m: Message, state: FSMContext):
    await save_phone_and_next(m, state, m.text)


async def save_phone_and_next(m: Message, state: FSMContext, raw: str):
    try:
        await run(lambda: services.save_phone(get_user(m), raw))
    except ServiceError as e:
        await m.answer(str(e))
        return
    user, _, accounts = await run(user_state, m)
    if accounts:
        await state.clear()
        await m.answer("Raqamingiz saqlandi ✅", reply_markup=main_kb())
        return
    await state.set_state(Reg.number)
    await m.answer("2/3 Shaxsiy hisob raqamingizni yozing (gaz to'lov kvitansiyasida bor):", reply_markup=ReplyKeyboardRemove())


@router.message(Reg.number, F.text)
async def reg_number(m: Message, state: FSMContext):
    try:
        number = services.clean_account_number(m.text)
    except ServiceError as e:
        await m.answer(str(e))
        return
    await state.update_data(number=number)
    await state.set_state(Reg.label)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Uy"), KeyboardButton(text="Ofis"), KeyboardButton(text="Boshqa")]],
                             resize_keyboard=True)
    await m.answer("Bu hisobni qanday nomlaymiz? (tugmani bosing yoki o'zingiz yozing)", reply_markup=kb)


@router.message(Reg.label, F.text)
async def reg_label(m: Message, state: FSMContext):
    await state.update_data(label=m.text.strip()[:50])
    await state.set_state(Reg.address)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
        [KeyboardButton(text=BTN_TEXT_ADDR)]], resize_keyboard=True)
    await m.answer("3/3 Manzilingizni yuboring: joylashuv tugmasi yoki matn bilan "
                   "(haydovchi aniq topishi uchun joylashuv yaxshiroq).", reply_markup=kb)


async def finish_registration(m: Message, state: FSMContext, address: str, lat=None, lng=None):
    data = await state.get_data()
    try:
        await run(lambda: services.create_account(
            get_user(m), data["number"], data.get("label", "Uy"), "natural", address, lat, lng))
    except ServiceError as e:
        await state.clear()
        await m.answer(f"{e}\n/start ni bosib qayta urinib ko'ring.", reply_markup=ReplyKeyboardRemove())
        return
    await state.clear()
    await m.answer("✅ Ro'yxatdan o'tdingiz! Endi balans, ko'rsatkich va murojaatlardan foydalanishingiz mumkin.",
                   reply_markup=main_kb())


@router.message(Reg.address, F.location)
async def reg_address_loc(m: Message, state: FSMContext):
    await finish_registration(m, state, "GPS joylashuv", m.location.latitude, m.location.longitude)


@router.message(Reg.address, F.text == BTN_TEXT_ADDR)
async def reg_address_ask_text(m: Message):
    await m.answer("Manzilni yozing (tuman, ko'cha, uy):", reply_markup=ReplyKeyboardRemove())


@router.message(Reg.address, F.text)
async def reg_address_text(m: Message, state: FSMContext):
    await finish_registration(m, state, m.text.strip())


# ---------- menyu ----------
async def require_registered(m: Message, state: FSMContext):
    user, phone, accounts = await run(user_state, m)
    if not (phone and accounts):
        await m.answer("Avval ro'yxatdan o'ting: /start")
        return None
    return user, accounts


@router.message(F.text == BTN_CANCEL)
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Bekor qilindi.", reply_markup=main_kb())


@router.message(F.text == BTN_BAL)
async def balance(m: Message, state: FSMContext):
    await state.clear()
    r = await require_registered(m, state)
    if not r:
        return
    _, accounts = r

    def build():
        lines = []
        for a in accounts:
            last = a.readings.first()
            lines.append(f"🏠 {a.label} · {a.number}\n💰 Balans: {a.balance:,.0f} so'm\n"
                         f"🔢 Oxirgi ko'rsatkich: {last.value if last else '—'} {a.unit}")
        return "\n\n".join(lines)

    await m.answer(await run(build))


@router.message(F.text == BTN_MY)
async def my_appeals(m: Message, state: FSMContext):
    await state.clear()
    r = await require_registered(m, state)
    if not r:
        return
    user, _ = r
    items = await run(lambda: list(Appeal.objects.filter(user=user)[:5]))
    if not items:
        await m.answer("Hozircha murojaatlaringiz yo'q.")
        return
    await m.answer("\n\n".join(
        f"#{a.pk} · {a.category}\nHolati: {a.get_status_display()}" + (f"\n💬 {a.reply}" if a.reply else "")
        for a in items))


# ---------- murojaat ----------
CATEGORIES = ["Hisoblagichni qiyoslash", "Plomba / muammo", "Ma'lumotni o'zgartirish", "Qarzdorlikka e'tiroz", "Boshqa"]


@router.message(F.text == BTN_APPEAL)
async def appeal_start(m: Message, state: FSMContext):
    await state.clear()
    if not await require_registered(m, state):
        return
    await state.set_state(AppealFlow.category)
    kb = cancel_kb(*[[KeyboardButton(text=c)] for c in CATEGORIES])
    await m.answer("Murojaat mavzusini tanlang:", reply_markup=kb)


@router.message(AppealFlow.category, F.text)
async def appeal_category(m: Message, state: FSMContext):
    await state.update_data(category=m.text.strip()[:100])
    await state.set_state(AppealFlow.text)
    await m.answer("Muammoni batafsil yozing:", reply_markup=cancel_kb())


@router.message(AppealFlow.text, F.text)
async def appeal_text(m: Message, state: FSMContext):
    if len(m.text.strip()) < 5:
        await m.answer("Matn juda qisqa, batafsilroq yozing.")
        return
    await state.update_data(text=m.text.strip())
    await state.set_state(AppealFlow.photo)
    await m.answer("Rasm yoki fayl yuboring (ixtiyoriy) yoki o'tkazib yuboring:", reply_markup=cancel_kb([KeyboardButton(text=BTN_SKIP)]))


async def submit_appeal(m: Message, state: FSMContext, photo_bytes=None):
    data = await state.get_data()
    user, _, accounts = await run(user_state, m)

    def make():
        photo = services.photo_from_bytes(photo_bytes) if photo_bytes else None
        return services.create_appeal(user, data["category"], data["text"], accounts[0] if accounts else None, photo)

    try:
        appeal = await run(make)
    except ServiceError as e:
        await m.answer(str(e), reply_markup=main_kb())
        await state.clear()
        return
    await state.clear()
    await m.answer(f"✅ Murojaatingiz qabul qilindi (#{appeal.pk}). Javob kelganda shu yerda xabar beramiz.",
                   reply_markup=main_kb())


@router.message(AppealFlow.photo, F.text == BTN_SKIP)
async def appeal_skip(m: Message, state: FSMContext):
    await submit_appeal(m, state)


@router.message(AppealFlow.photo, F.photo)
async def appeal_photo(m: Message, state: FSMContext, bot: Bot):
    buf = io.BytesIO()
    await bot.download(m.photo[-1], destination=buf)
    await submit_appeal(m, state, buf.getvalue())


@router.message(AppealFlow.photo)
async def appeal_photo_other(m: Message):
    await m.answer("Iltimos, rasm yuboring yoki «O'tkazib yuborish» ni bosing.")


# ---------- AI yordamchi ----------
@router.message(F.text == BTN_AI)
async def ai_start(m: Message, state: FSMContext):
    await state.clear()
    if not await require_registered(m, state):
        return
    await state.set_state(Chat.active)
    await m.answer("🤖 Savolingizni yozing. Chiqish uchun «❌ Bekor qilish» ni bosing.", reply_markup=cancel_kb())


@router.message(Chat.active, F.text)
async def ai_chat(m: Message, state: FSMContext):
    user, _, accounts = await run(user_state, m)

    def work():
        if not services.chat_rate_ok(user):
            return "Juda tez yozyapsiz, bir daqiqa kuting.", False
        history = [{"role": x.role, "content": x.content}
                   for x in ChatMessage.objects.filter(user=user).order_by("-id")[:8][::-1]]
        ChatMessage.objects.create(user=user, role="user", content=m.text[:2000])
        reply, suggest = ai.answer(m.text, accounts[0] if accounts else None, history)
        ChatMessage.objects.create(user=user, role="assistant", content=reply)
        return reply, suggest

    await m.bot.send_chat_action(m.chat.id, "typing")
    reply, suggest = await run(work)
    if suggest:
        reply += f"\n\nOperatorga yozish uchun «{BTN_APPEAL}» tugmasini bosing."
    await m.answer(reply)


@router.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer("/start — ro'yxatdan o'tish / menyu\nTugmalar orqali balans, murojaat va AI yordamchidan foydalaning.")


@router.message(F.text)
async def fallback(m: Message):
    await m.answer("Menyudan tanlang yoki /start ni bosing.", reply_markup=main_kb())


async def main():
    logging.basicConfig(level=logging.INFO)
    if not settings.BOT_TOKEN:
        raise SystemExit(".env faylida BOT_TOKEN ko'rsatilmagan")
    bot = Bot(settings.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    if webapp_ok():
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Ilova", web_app=WebAppInfo(url=settings.WEBAPP_URL)))
        except Exception as exc:  # noqa: BLE001
            log.warning("Menu tugmasi o'rnatilmadi: %s", exc)
    else:
        log.warning("WEBAPP_URL https:// bilan boshlanmagan: Mini App tugmasi ko'rsatilmaydi")
    await bot.delete_webhook(drop_pending_updates=False)
    me = await bot.get_me()
    log.info("Bot ishga tushdi: @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
