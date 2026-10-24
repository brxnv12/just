import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


DEBUG = env_bool("DEBUG", True)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key-change-me")
if not DEBUG and SECRET_KEY == "dev-only-insecure-key-change-me":
    raise RuntimeError("Productionda .env ichida SECRET_KEY ni o'zgartiring")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]

WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
CSRF_TRUSTED_ORIGINS = [WEBAPP_URL] if WEBAPP_URL.startswith("https://") else []
CSRF_TRUSTED_ORIGINS += [
    "https://*.trycloudflare.com",
    "https://*.ngrok-free.app",
    "https://*.ngrok-free.dev",
    "https://*.loca.lt",
]

# --- Telegram / ilova sozlamalari ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEV_AUTH = env_bool("DEV_AUTH", DEBUG)          # brauzerda Telegramsiz sinash
if DEV_AUTH and not DEBUG:
    raise RuntimeError("DEV_AUTH=1 faqat DEBUG=1 bilan ishlaydi (xavfsizlik uchun)")
DEMO_PAYMENTS = env_bool("DEMO_PAYMENTS", True)  # Payme/Click ulanmaguncha demo
GAS_TARIFF = Decimal(os.getenv("GAS_TARIFF", "1800"))
INIT_DATA_MAX_AGE = 60 * 60 * 24                 # initData necha soniya amal qiladi
CHAT_PER_MINUTE = int(os.getenv("CHAT_PER_MINUTE", "15"))
# Payme (https://developer.help.paycom.uz)
PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID", "")
PAYME_KEY = os.getenv("PAYME_KEY", "")
PAYME_TEST = env_bool("PAYME_TEST", True)
PAYME_ACCOUNT_FIELD = os.getenv("PAYME_ACCOUNT_FIELD", "account")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "gas_app.apps.GasAppConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # tunnel/nginx ortida
USE_X_FORWARDED_HOST = True

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER", ""),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["gas_app.auth.TelegramAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}
