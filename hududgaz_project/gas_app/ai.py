"""AI yordamchi: OPENAI_API_KEY bo'lsa GPT, bo'lmasa oddiy FAQ (kalit so'zlar bo'yicha)."""
import json
import logging
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

EMERGENCY = (
    "🚨 Gaz hidi sezsangiz: olov yoqmang, elektr tugmalarini bosmang, derazalarni oching, "
    "gaz kranini yoping, binodan chiqing va darhol gaz favqulodda xizmatiga (104) qo'ng'iroq qiling."
)

SYSTEM_PROMPT = """Sen "Hududgaz" xizmatining Telegram yordamchisisan.
Qoidalar:
- Foydalanuvchi qaysi tilda yozsa (o'zbek lotin/kirill, rus), o'sha tilda qisqa va aniq javob ber.
- Faqat gaz ta'minoti, hisob, ko'rsatkich, to'lov, hisoblagich, murojaat mavzularida yordam ber.
- Tarif, qonun yoki raqamlarni o'ylab topma. Bilmasang, operatorga murojaat qilishni tavsiya qil.
- Gaz hidi/sizish haqida bo'lsa, birinchi navbatda xavfsizlik choralarini ayt va 104 raqamini ko'rsat.
- Quyidagi foydalanuvchi ma'lumotlaridan faqat savolga tegishli bo'lsa foydalan.
- Operator kerak bo'lsa, javob oxirida aynan shu belgini qo'y: [OPERATOR]
"""

FAQ = [
    (("gaz hid", "hidi", "sizib", "sizayap", "утечк", "запах", "пахнет", "portlash"), EMERGENCY, False),
    (("ko'rsatkich", "korsatkich", "ko‘rsatkich", "hisoblagich", "schetchik", "счетчик", "счётчик", "показани"),
     "Ko'rsatkich kiritish: ilovada «Hisoblagich» bo'limiga o'ting, hisoblagichdagi joriy raqamni yozing "
     "(xohlasangiz rasmini ham yuklang) va «Jo'natish» ni bosing.", False),
    (("qiyoslash", "poverka", "поверка", "plomba", "ta'mir", "almashtir"),
     "Hisoblagichni qiyoslash yoki plomba bilan bog'liq masalalar operator orqali hal qilinadi. "
     "«Arizalar» bo'limida ariza yuboring.", True),
    (("to'lov", "tolov", "payme", "click", "оплат", "платеж", "toldir", "to'ldir"),
     "To'lovni «Asosiy» bo'limidagi «Hisobni to'ldirish» tugmasi orqali qilishingiz mumkin.", False),
    (("e'tiroz", "etiroz", "xato", "noto'g'ri", "ошибк", "жалоб", "shikoyat"),
     "Bu masalani operator ko'rib chiqishi kerak. Iltimos, ariza yuboring.", True),
]


def _faq(message: str, context_account, balance_text: str):
    low = message.lower()
    if any(w in low for w in ("balans", "qarz", "qancha", "баланс", "долг")):
        return balance_text, False
    for keys, text, op in FAQ:
        if any(k in low for k in keys):
            return text, op
    return (
        "Savolingizni to'liq tushuna olmadim. Operatorga ariza yuborishni tavsiya qilaman.",
        True,
    )


def answer(message: str, account=None, history=None):
    """-> (matn, operator_taklifi: bool)"""
    from .services import account_context

    message = (message or "").strip()[:2000]
    if account:
        balance_text = f"Balansingiz: {account.balance:,.0f} so'm (hisob {account.number})."
    else:
        balance_text = "Avval hisob raqamingizni qo'shing."

    low = message.lower()
    if any(k in low for k in FAQ[0][0]):  # xavfsizlik har doim birinchi
        return EMERGENCY, True

    if not settings.OPENAI_API_KEY:
        return _faq(message, account, balance_text)

    msgs = [{"role": "system", "content": SYSTEM_PROMPT + "\nFoydalanuvchi ma'lumoti: " + account_context(account)}]
    for m in (history or [])[-8:]:
        msgs.append({"role": m["role"], "content": m["content"][:1500]})
    msgs.append({"role": "user", "content": message})
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps({"model": settings.OPENAI_MODEL, "messages": msgs, "temperature": 0.3, "max_tokens": 400}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        text = data["choices"][0]["message"]["content"].strip()
        suggest = "[OPERATOR]" in text
        return text.replace("[OPERATOR]", "").strip(), suggest
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAI xatosi, FAQ ishlatilmoqda: %s", exc)
        return _faq(message, account, balance_text)
