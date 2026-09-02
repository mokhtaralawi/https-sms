"""
Django settings for httpsms project.

Self-Hosted SMS Gateway Platform
"""

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
)

# Read .env file if present
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-14clxfmi#dp@_6kr+6lr%6sazvjye4alyxv4^8d$pso%g&-6jk",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "SECRET_KEY is not set to a secure value. Generate one with "
        "`python -c \"from django.core.management.utils import get_random_secret_key; "
        "print(get_random_secret_key())\"` and set it in .env (only required when DEBUG=False)."
    )

ALLOWED_HOSTS = env("ALLOWED_HOSTS", default=["*"])

# Application definition

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "channels",
    # Local apps
    "core",
    "accounts",
    "customers",
    "api_keys",
    "devices",
    "messaging",
    "webhooks",
    "usage",
    "notifications",
    "audit",
    "dashboard",
    "otp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "httpsms.middleware.AuditMiddleware",
]

ROOT_URLCONF = "httpsms.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "httpsms.wsgi.application"
ASGI_APPLICATION = "httpsms.asgi.application"

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASE_URL = env("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    # Fallback to SQLite for local development during setup
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Redis / Celery config
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 5
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Celery Beat schedule
CELERY_BEAT_SCHEDULE = {
    "requeue-stale-sending-messages": {
        "task": "messaging.tasks.requeue_stale_sending_messages",
        "schedule": 60.0,
    },
    "check-expired-messages": {
        "task": "messaging.tasks.check_expired_messages",
        "schedule": 300.0,
    },
    "mark-offline-devices": {
        "task": "devices.tasks.mark_offline_devices",
        "schedule": 60.0,
    },
    "daily-usage-report": {
        "task": "usage.tasks.generate_daily_report",
        "schedule": 86400.0,
    },
}

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Cache (Redis-backed for rate limiting and device registry)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "api_keys.jwt_auth.FlexibleJWTAuthentication",
        "api_keys.authentication.APIKeyAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/day",
        "user": "1000/day",
        "login": "10/min",
        "otp": "5/min",
        "api": "1000/hour",
    },
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# JWT settings
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("ACCESS_TOKEN_LIFETIME", default=60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("REFRESH_TOKEN_LIFETIME", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# CORS
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True

# Security
if env("TRUSTED_PROXY", default=False):
    # Behind nginx/Caddy so Django trusts X-Forwarded-Proto for SECURE_SSL_REDIRECT.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = env("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Webhook settings
WEBHOOK_SECRET = env("WEBHOOK_SECRET", default="")
WEBHOOK_TIMEOUT = env("WEBHOOK_TIMEOUT", default=10)
WEBHOOK_MAX_RETRIES = env("WEBHOOK_MAX_RETRIES", default=5)
WEBHOOK_BASE_DELAY = env("WEBHOOK_BASE_DELAY", default=300)

# Rate limiting keys
RATE_LIMIT_DEFAULT_RPS = env("RATE_LIMIT_DEFAULT_RPS", default=10)
RATE_LIMIT_DEFAULT_PER_MIN = env("RATE_LIMIT_DEFAULT_PER_MIN", default=300)
RATE_LIMIT_DEFAULT_PER_HOUR = env("RATE_LIMIT_DEFAULT_PER_HOUR", default=5000)
RATE_LIMIT_DEFAULT_PER_DAY = env("RATE_LIMIT_DEFAULT_PER_DAY", default=100000)
RATE_LIMIT_DEFAULT_PER_MONTH = env("RATE_LIMIT_DEFAULT_PER_MONTH", default=2000000)

# OTP settings
OTP_CODE_LENGTH = env("OTP_CODE_LENGTH", default=6)
OTP_EXPIRY_SECONDS = env("OTP_EXPIRY_SECONDS", default=300)
OTP_MAX_ATTEMPTS = env("OTP_MAX_ATTEMPTS", default=5)

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "app.log",
            "maxBytes": 10485760,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "httpsms": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}

# Drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Self-Hosted SMS Gateway API",
    "DESCRIPTION": "Professional self-hosted SMS Gateway platform",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}
