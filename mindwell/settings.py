from pathlib import Path
import json
import os

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(f'{name} must be a boolean.')


DEBUG = env_bool('DJANGO_DEBUG')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set.')
if not DEBUG and (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5):
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must be a strong, randomly generated value in production.'
    )

ALLOWED_HOSTS = ['*']

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        'DJANGO_ALLOWED_HOSTS must contain at least one host when DEBUG is disabled.'
    )
if not DEBUG and '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must not contain a wildcard in production.')

SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', default=not DEBUG)
SESSION_COOKIE_SECURE = env_bool('DJANGO_SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = env_bool('DJANGO_CSRF_COOKIE_SECURE', default=not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS')
SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD')

CSRF_TRUSTED_ORIGINS = [
    'https://oboe-capillary-flannels.ngrok-free.dev',
    'http://127.0.0.1:8000',
    'http://localhost:8000',
]

INSTALLED_APPS = [
    
    'daphne',
    
    # Django Core Apps
    'accounts', 
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third Party & Features
    'channels',
    'django_extensions',
    
    # Local Apps 
    'appointments',   
    'consultations',    
    'messaging',         
    'admin_panel',
    'ai_service',
    'core',
    'mindwell',     
]

ASGI_APPLICATION = "mindwell.asgi.application"

try:
    import redis

    r = redis.Redis(
        host="127.0.0.1",
        port=6379,
        db=0,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    r.ping()

    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [("127.0.0.1", 6379)],
            },
        },
    }

except Exception:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }


LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'home'
AUTH_USER_MODEL = 'accounts.CustomUser'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'mindwell.middleware.PreferredLanguageMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mindwell.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.role_layout',          
                'mindwell.context_processors.language_switch_urls',
            ],
        },
    },
]

WSGI_APPLICATION = 'mindwell.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr'
LANGUAGES = [
    ('fr', 'Français'),
    ('ar', 'العربية'),
    ('en', 'English'),
]
USE_I18N = True
USE_L10N = True
USE_TZ = True
TIME_ZONE = 'Africa/Algiers'

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'mindwell' / 'static',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = os.getenv(
    'DJANGO_EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)

_raw_ice_servers = os.getenv('DJANGO_WEBRTC_ICE_SERVERS')
if _raw_ice_servers:
    try:
        WEBRTC_ICE_SERVERS = json.loads(_raw_ice_servers)
    except json.JSONDecodeError as error:
        raise ImproperlyConfigured('DJANGO_WEBRTC_ICE_SERVERS must contain valid JSON.') from error
    if not isinstance(WEBRTC_ICE_SERVERS, list) or any(
        not isinstance(server, dict) for server in WEBRTC_ICE_SERVERS
    ):
        raise ImproperlyConfigured('DJANGO_WEBRTC_ICE_SERVERS must be a JSON list of server objects.')
else:
    WEBRTC_ICE_SERVERS = [
        {'urls': 'stun:stun.l.google.com:19302'},
        {'urls': 'stun:stun1.l.google.com:19302'},
    ]

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")
