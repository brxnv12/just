# Hududgaz: Telegram bot + Mini App (Django + DRF + aiogram)

Docker va PostgreSQL shart emas: standart baza SQLite (fayl). Windows (Git Bash yoki CMD) uchun moslangan.

## 1. O'rnatish (bir marta)
```bash
python -m venv .venv
source .venv/Scripts/activate        # Git Bash.  CMD: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # CMD: copy .env.example .env
```
`.env` ichida **BOT_TOKEN** ni @BotFather dan olib yozing.

## 2. HTTPS manzil (Mini App uchun shart)
Telegram Mini App faqat HTTPS ochadi. Eng oson yo'l (ro'yxatdan o'tish shart emas):
```bash
cloudflared tunnel --url http://localhost:8000
```
Chiqqan `https://xxxx.trycloudflare.com` manzilni `.env` dagi `WEBAPP_URL` ga yozing.
(ngrok ham bo'ladi, lekin bepul versiyada ogohlantirish sahifasi chiqishi mumkin.)

## 3. Ishga tushirish (2 ta alohida terminal)
```bash
./run_server.sh      # Django: ilova + API + admin   (CMD: run_server.bat)
./run_bot.sh         # Telegram bot                  (CMD: run_bot.bat)
```
Admin panel uchun bir marta: `python manage.py createsuperuser`, so'ng `https://.../admin/`.

## Nimalar ishlaydi
- **Bot:** /start -> telefon (kontakt tugmasi) -> hisob raqami -> nom (Uy/Ofis) -> manzil (GPS tugma yoki matn). Menyu: balans, murojaat (mavzu + matn + rasm), AI yordamchi, murojaatlarim.
- **Mini App:** balans, oylik sarf diagrammasi, operatsiyalar, ko'rsatkich + rasm, arizalar (holat + operator javobi), AI chat, bir nechta hisob, xaritadan manzil belgilash (Leaflet).
- **Admin:** hisoblar, tranzaksiya qo'shish, ko'rsatkichlar, arizalarga javob. Holat yoki javob o'zgarsa, foydalanuvchiga Telegramda xabar boradi.
- **Xavfsizlik:** Telegram initData HMAC bilan tekshiriladi, har foydalanuvchi faqat o'z hisobini ko'radi.
- Testlar: `python manage.py test`

## Payme ulash (tayyor, sizning kalitlaringiz kerak)
1. Payme merchant kabinetida **Endpoint URL**: `https://SIZNING-DOMEN/api/payme/`, account maydon nomi: `account`.
2. `.env`: `PAYME_MERCHANT_ID`, `PAYME_KEY`, `PAYME_TEST=1` (sinov) yoki `0` (jang).
3. Ilovada "Payme" tugmasi checkout sahifasini ochadi; to'lov muvaffaqiyatli bo'lsa Payme serveri `/api/payme/` ni chaqiradi va balans to'ldiriladi (qaytarish ham ishlaydi).
4. Payme sandbox ("Merchant API tester") bilan hamma metodlarni bir marta o'zingiz tekshirib chiqing: kod hujjat bo'yicha yozilgan va lokal testdan o'tgan, lekin Payme'ning o'z serveriga qarshi sinalmagan.
5. Click hali ulanmagan: u faqat `DEMO_PAYMENTS=1` rejimida ko'rinadi.

## Xavfsizlik (tuzatilgan)
- Yuklangan fayl Pillow bilan tekshiriladi (faqat JPG/PNG/WEBP), nomi tasodifiy qilinadi; soxta "rasm" rad etiladi.
- Rasmlar ochiq emas: `/media/...` faqat admin yoki vaqtinchalik imzolangan havola bilan ochiladi.
- AI chatga daqiqasiga `CHAT_PER_MINUTE` xabar limiti bor (OpenAI xarajatidan himoya).
- `DEBUG=0` bo'lsa, standart `SECRET_KEY` yoki `DEV_AUTH=1` bilan server ishga tushmaydi.
- Productionda statik fayllar uchun: `python manage.py collectstatic --noinput`.

## Hali sizning ma'lumotingiz kerak bo'lgan joylar
1. **Hisob tekshiruvi / haqiqiy balans:** kiritilgan hisob raqami Hududgaz billing bazasi bilan solishtirilmaydi, balans shu tizim tranzaksiyalaridan hisoblanadi. Buning uchun billing API hujjati kerak.
2. **Tarif:** `GAS_TARIFF` vaqtinchalik (1800 so'm). Haqiqiy tarifni `.env` ga yozing.
3. **AI:** `OPENAI_API_KEY` bo'lmasa oddiy FAQ rejimi. 104 raqamini ishlatishdan oldin tekshirib oling.
4. **Production joylash:** gunicorn + nginx, PostgreSQL (`POSTGRES_*`).
