"""Test settings: eager celery + in-memory channels + in-memory cache."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")

from httpsms.settings import *  # noqa: F401,F403

DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

# Run Celery tasks synchronously
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# In-memory channel layer for WebSocket tests
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Use LocMemCache to avoid Redis dependency
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "httpsms-test-cache",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Keep audit middleware from interfering with test counts (it creates rows; tests don't depend on counts)
# but we want audit tests: keep enabled.

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "1000/min",
    "user": "10000/min",
    "login": "20/min",
    "otp": "100/min",
    "api": "1000000/hour",
}

# Faster webhook retries
WEBHOOK_MAX_RETRIES = 3
WEBHOOK_BASE_DELAY = 1