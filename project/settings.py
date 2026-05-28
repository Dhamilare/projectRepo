import os
import logging
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# CORE
# ─────────────────────────────────────────────────────────────────────────────
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = ['*']

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

LOCAL_APPS = [
    "projectRepo",
]

THIRD_PARTY_APPS = [
    "django_extensions",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS + THIRD_PARTY_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
]

ROOT_URLCONF = "project.urls"

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
                "projectRepo.context_processors.global_context",
            ],
        },
    },
]

WSGI_APPLICATION = "project.wsgi.application"


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE  (PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="project_db"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="Klassnics@1759"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 10},
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────

AUTH_USER_MODEL = "projectRepo.User"

AUTHENTICATION_BACKENDS = [
    "projectRepo.backends.MicrosoftEntraBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/auth/login/"

SESSION_COOKIE_AGE = 28800          # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True


# ─────────────────────────────────────────────────────────────────────────────
# STATIC / MEDIA
# ─────────────────────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ─────────────────────────────────────────────────────────────────────────────
# CACHE  (Redis)
# ─────────────────────────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "mspkb",
        "TIMEOUT": 300,
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# MICROSOFT ENTRA ID  (Azure AD)
# ─────────────────────────────────────────────────────────────────────────────
_TENANT = config("AZURE_TENANT_ID", default="common")

MICROSOFT_AUTH = {
    "CLIENT_ID": config("AZURE_CLIENT_ID", default=""),
    "CLIENT_SECRET": config("AZURE_CLIENT_SECRET", default=""),
    "TENANT_ID": _TENANT,
    "REDIRECT_URI": config(
        "AZURE_REDIRECT_URI", default="http://localhost:8000/auth/callback/"
    ),
    "SCOPES": ["User.Read", "email"],
    "AUTHORITY": f"https://login.microsoftonline.com/{_TENANT}",
    "GRAPH_ENDPOINT": "https://graph.microsoft.com/v1.0",
}


# ─────────────────────────────────────────────────────────────────────────────
# OAUTH2 EMAIL TRANSMISSION CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "projectRepo.email_backends.GraphOAuth2Backend"
EMAIL_SENDER = config("EMAIL_SENDER")
DEFAULT_FROM_EMAIL = EMAIL_SENDER


# ─────────────────────────────────────────────────────────────────────────────
# INTERNATIONALIZATION
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─────────────────────────────────────────────────────────────────────────────
# APP-LEVEL SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
ARTICLES_PER_PAGE = 20
SEARCH_SUGGESTIONS_LIMIT = 8
SEARCH_SUGGESTIONS_CACHE_TTL = 120   # seconds
RECENT_ARTICLES_COUNT = 10
MAX_ATTACHMENT_SIZE_MB = 20
ALLOWED_ATTACHMENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]

DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY HEADERS
# ─────────────────────────────────────────────────────────────────────────────
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module}:{lineno} — {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 1024 * 1024 * 5,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "security_file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "security.log",
            "maxBytes": 1024 * 1024 * 5,
            "backupCount": 10,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO", "propagate": True},
        "projectRepo": {"handlers": ["console", "file"], "level": "DEBUG", "propagate": False},
        "security": {"handlers": ["security_file"], "level": "WARNING", "propagate": False},
    },
}