from .base import *

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
AUTH_COOKIE_SECURE = False
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "login": "1000/min",
        "refresh": "1000/min",
        "password_reset": "1000/min",
        "mfa": "1000/min",
    },
}
