from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


def load_env_file(path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not os.environ.get(key):
            os.environ[key] = value


load_env_file(PROJECT_ROOT / ".env")
load_env_file(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_str(name, default=""):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def env_list(name, default=""):
    raw_value = os.getenv(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def env_int(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def env_path(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return Path(default)
    return Path(value).expanduser()


def has_real_email_credentials(username, password):
    username = (username or "").strip().lower()
    password = (password or "").strip()
    if not username or not password:
        return False

    placeholder_usernames = {"yourgmail@gmail.com", "example@gmail.com"}
    placeholder_passwords = {"your_16_char_app_password", "app-password"}

    if username in placeholder_usernames or username.startswith("your"):
        return False
    if password in placeholder_passwords or password.startswith("your_"):
        return False

    return True


def secret_key_is_placeholder(value):
    normalized = (value or "").strip()
    if not normalized:
        return True

    placeholders = {
        "change-me",
        "django-insecure-change-me",
        "your-secret-key",
        "your-secret-key-here",
    }
    return normalized in placeholders


SECRET_KEY = env_str("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", default=False)

default_allowed_hosts = "127.0.0.1,localhost,testserver" if DEBUG else ""
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default_allowed_hosts)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

if not DEBUG and secret_key_is_placeholder(SECRET_KEY):
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY to a long random value before starting Django in production."
    )

if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Set DJANGO_ALLOWED_HOSTS before starting Django in production."
    )

INSTALLED_APPS = [
    "import_export",
    "phonenumber_field",
    "app_web",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

SITE_ID = 1

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["email", "username*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {
            "access_type": "online",
            "prompt": "select_account",
        },
    }
}
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_FORMS = {"signup": "app_web.forms.CustomSignupForm"}
ACCOUNT_SIGNUP_REDIRECT_URL = "/profile/"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "app_web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "app_web.context_processors.cart_processor",
                "app_web.context_processors.support_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "app.wsgi.application"

db_engine = os.getenv("DJANGO_DB_ENGINE", "sqlite").strip().lower()

if db_engine in {"mysql", "django.db.backends.mysql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("MYSQL_DATABASE", "deepsmoke"),
            "USER": os.getenv("MYSQL_USER", ""),
            "PASSWORD": os.getenv("MYSQL_PASSWORD", ""),
            "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.getenv("MYSQL_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
            "CONN_MAX_AGE": env_int("DJANGO_DB_CONN_MAX_AGE", 60),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LANGUAGE_CODE = "uk-ua"
TIME_ZONE = "Europe/Kyiv"
USE_I18N = True
USE_TZ = True

STATIC_URL = env_str("DJANGO_STATIC_URL", "/static/")
STATIC_ROOT = env_path("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles")

MEDIA_URL = env_str("DJANGO_MEDIA_URL", "/media/")
MEDIA_ROOT = env_path("DJANGO_MEDIA_ROOT", BASE_DIR / "media")

PHONENUMBER_DEFAULT_REGION = "UA"
EMAIL_HOST = env_str("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "30"))
EMAIL_FILE_PATH = env_path("EMAIL_FILE_PATH", PROJECT_ROOT / "runtime" / "sent_emails")
EMAIL_CREDENTIALS_CONFIGURED = has_real_email_credentials(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_CREDENTIALS_CONFIGURED
    else "django.core.mail.backends.filebased.EmailBackend",
)
if EMAIL_BACKEND.endswith("filebased.EmailBackend"):
    EMAIL_FILE_PATH.mkdir(parents=True, exist_ok=True)
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER if EMAIL_CREDENTIALS_CONFIGURED else "noreply@vapeland.local",
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
IMPORT_EXPORT_USE_TRANSACTIONS = True
IMPORT_EXPORT_SKIP_ADMIN_CONFIRM = False

TELEGRAM_BOT_TOKEN = env_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = env_str("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_TIMEOUT = env_int("TELEGRAM_API_TIMEOUT", 5)
NOVA_POSHTA_API_KEY = env_str("NOVA_POSHTA_API_KEY", "")
SUPPORT_TELEGRAM_URL = env_str("SUPPORT_TELEGRAM_URL", "")
SUPPORT_INSTAGRAM_URL = env_str("SUPPORT_INSTAGRAM_URL", "")
SUPPORT_PHONE = env_str("SUPPORT_PHONE", "")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = env_str("DJANGO_SESSION_COOKIE_SAMESITE", "Lax")
    CSRF_COOKIE_SAMESITE = env_str("DJANGO_CSRF_COOKIE_SAMESITE", "Lax")
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = env_str("DJANGO_SECURE_REFERRER_POLICY", "same-origin")
    X_FRAME_OPTIONS = "DENY"
