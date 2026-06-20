import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "False") == "True"

def get_env_list(name, default=""):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]

# Backend domain
ALLOWED_HOSTS = get_env_list(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1"
)
# Frontend domain
CORS_ALLOWED_ORIGINS = get_env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ALLOW_CREDENTIALS = os.getenv('CORS_ALLOW_CREDENTIALS', 'True') == 'True'

# Frontend domain(s) trusted for unsafe (POST/PUT/PATCH/DELETE) cross-origin requests.
CSRF_TRUSTED_ORIGINS = get_env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,https://intervai-coach-production.up.railway.app,https://fypproo.netlify.app"
)

# ── Security: cookies ─────────────────────────────────────────────────────────
# Secure cookies require HTTPS. Enable them in production (DEBUG=False) only, so
# local development over plain HTTP still works.
SESSION_COOKIE_SECURE = not DEBUG          # Only send session cookie over HTTPS
SESSION_COOKIE_HTTPONLY = True             # Block JS access to the session cookie
SESSION_COOKIE_SAMESITE = 'Lax'

CSRF_COOKIE_SECURE = not DEBUG             # Only send CSRF cookie over HTTPS
CSRF_COOKIE_HTTPONLY = False               # Frontend JS must read the CSRF token
CSRF_COOKIE_SAMESITE = 'Lax'

# ── Security: HTTPS / transport hardening (production only) ────────────────────
# Railway (and most PaaS) terminate TLS at a proxy and forward the original
# scheme in the X-Forwarded-Proto header. Without this, Django thinks every
# request is plain HTTP and the secure-cookie / SSL-redirect logic misbehaves.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True              # Redirect all HTTP traffic to HTTPS

    # HTTP Strict Transport Security — tell browsers to only use HTTPS.
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Applied in all environments — cheap, no downside.
SECURE_CONTENT_TYPE_NOSNIFF = True         # Block MIME-type sniffing
X_FRAME_OPTIONS = 'DENY'                    # Reject framing (clickjacking defence)

# Application definition

INSTALLED_APPS = [
    'rest_framework',
    'corsheaders',

    'users',
    'resumes',
    'quizzes',
    'interviews',
    'profiles',
    'payments',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    # CorsMiddleware must stay at the top, before anything that can return a
    # response (e.g. CommonMiddleware redirects), so CORS headers are attached.
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

if os.getenv('DATABASE_URL'):
    # Production: use DATABASE_URL from Railway
    DATABASES = {
        'default': dj_database_url.config(default=os.getenv('DATABASE_URL'))
    }
else:
    # Development: use individual PostgreSQL env vars
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB', 'intervai_db'),
            'USER': os.getenv('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.User'

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Rate limiting — throttles brute-force against login / register / OTP and
    # abuse of authenticated endpoints. Tune the rates to taste.
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/min',    # unauthenticated requests (login, register, OTP)
        'user': '120/min',   # authenticated requests
    },
}

# ── Simple JWT ────────────────────────────────────────────────────────────────
# Explicit token lifetimes + refresh rotation with blacklisting, instead of
# relying on library defaults.
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
}

EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
)

EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
# SSL (port 465) is an alternative to TLS (port 587). They are mutually
# exclusive — only one may be True. If SSL is requested, force TLS off so
# Django doesn't raise "EMAIL_USE_TLS/EMAIL_USE_SSL are mutually exclusive".
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
if EMAIL_USE_SSL:
    EMAIL_USE_TLS = False

EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')

# Fail fast instead of hanging the gunicorn worker forever when the SMTP host
# is unreachable (e.g. the platform blocks outbound port 587). Without this,
# a blocked connection holds the worker open until it is SIGKILL'd.
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))  # seconds

DEFAULT_FROM_EMAIL = os.getenv(
    'DEFAULT_FROM_EMAIL',
    EMAIL_HOST_USER or 'IntervAI Coach <no-reply@intervai.local>'
)

# ── Brevo (HTTP email API) ────────────────────────────────────────────────────
# Primary email provider for production. Brevo sends over HTTPS (port 443), so
# it works on hosts that block outbound SMTP (Railway). Its key advantage for an
# FYP: it delivers to ANY recipient once you verify a single sender email — no
# domain ownership required (unlike Resend's sandbox, which only mails the
# account owner). When BREVO_API_KEY is set, users.services routes mail here.
BREVO_API_KEY = os.getenv('BREVO_API_KEY', '')
# The verified sender. Verify this address in Brevo (Senders & IPs → Senders);
# it can be your own Gmail — Brevo sends you a confirmation link to click once.
BREVO_FROM_EMAIL = os.getenv('BREVO_FROM_EMAIL', 'IntervAI Coach <wayalyasin0483@gmail.com>')

# ── Resend (HTTP email API) ───────────────────────────────────────────────────
# Used for sending email in production where outbound SMTP is blocked (Railway).
# When RESEND_API_KEY is set, users.services routes mail through the Resend HTTP
# API (port 443) instead of SMTP. When it's empty, the app falls back to the
# Django EMAIL_BACKEND above (console locally / SMTP), so local dev is unchanged.
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
# The verified sender. For quick testing use Resend's sandbox sender
# 'onboarding@resend.dev' (no domain setup needed). To send from your own
# address, verify a domain in Resend and set it here.
RESEND_FROM_EMAIL = os.getenv('RESEND_FROM_EMAIL', 'IntervAI Coach <onboarding@resend.dev>')

# ── Logging ───────────────────────────────────────────────────────────────────
# Send application errors to the console (captured by Railway logs) so we can
# log full exceptions server-side while returning generic messages to clients.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
