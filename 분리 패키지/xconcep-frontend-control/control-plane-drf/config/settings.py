from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-only-change-me')
DEBUG = os.getenv('DJANGO_DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = [x.strip() for x in os.getenv('DJANGO_ALLOWED_HOSTS', '*').split(',') if x.strip()]
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.messages', 'django.contrib.staticfiles', 'corsheaders',
    'rest_framework', 'api',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'corsheaders.middleware.CorsMiddleware',
    'api.middleware.InternalApiTokenMiddleware', 'api.middleware.CorporateAuthMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'
DB_ENGINE = os.getenv('DB_ENGINE', 'mysql')
if DB_ENGINE == 'sqlite':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
else:
    mysql_options = {'charset': 'utf8mb4'}
    if os.getenv('MYSQL_SSL_CA', '').strip():
        mysql_options['ssl'] = {'ca': os.getenv('MYSQL_SSL_CA').strip()}
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.mysql', 'NAME': os.getenv('MYSQL_DATABASE', 'xconcep'),
        'USER': os.getenv('MYSQL_USER', 'xconcep'), 'PASSWORD': os.getenv('MYSQL_PASSWORD', 'xconcep'),
        'HOST': os.getenv('MYSQL_HOST', 'mysql'), 'PORT': os.getenv('MYSQL_PORT', '3306'),
        'OPTIONS': mysql_options, 'CONN_MAX_AGE': int(os.getenv('MYSQL_CONN_MAX_AGE', '60')),
        'CONN_HEALTH_CHECKS': True,
    }}
AUTH_MODE = os.getenv('AUTH_MODE', 'disabled').strip().lower()
AUTH_REQUIRED_MODES = {'internal_db', 'corporate_db'}
if AUTH_MODE not in {'disabled', *AUTH_REQUIRED_MODES}:
    raise RuntimeError('AUTH_MODE must be disabled, internal_db, or corporate_db')
AUTH_TOKEN_TTL_SECONDS = int(os.getenv('AUTH_TOKEN_TTL_SECONDS', '28800'))
INTERNAL_AUTH_BOOTSTRAP_ENABLED = os.getenv('INTERNAL_AUTH_BOOTSTRAP_ENABLED', 'false').lower() == 'true'
INTERNAL_AUTH_USERNAME = os.getenv('INTERNAL_AUTH_USERNAME', 'internal_admin').strip()
INTERNAL_AUTH_PASSWORD = os.getenv('INTERNAL_AUTH_PASSWORD', '')
INTERNAL_AUTH_DISPLAY_NAME = os.getenv('INTERNAL_AUTH_DISPLAY_NAME', '내부 테스트 관리자').strip()
INTERNAL_AUTH_EMAIL = os.getenv('INTERNAL_AUTH_EMAIL', 'internal-admin@example.test').strip()
AUTH_DB_TABLE = os.getenv('AUTH_DB_TABLE', 'employees').strip()
AUTH_DB_ID_COLUMN = os.getenv('AUTH_DB_ID_COLUMN', 'id').strip()
AUTH_DB_USERNAME_COLUMN = os.getenv('AUTH_DB_USERNAME_COLUMN', 'username').strip()
AUTH_DB_PASSWORD_COLUMN = os.getenv('AUTH_DB_PASSWORD_COLUMN', 'password_hash').strip()
AUTH_DB_DISPLAY_NAME_COLUMN = os.getenv('AUTH_DB_DISPLAY_NAME_COLUMN', 'display_name').strip()
AUTH_DB_EMAIL_COLUMN = os.getenv('AUTH_DB_EMAIL_COLUMN', 'email').strip()
AUTH_DB_ACTIVE_COLUMN = os.getenv('AUTH_DB_ACTIVE_COLUMN', 'is_active').strip()
AUTH_DB_PASSWORD_SCHEME = os.getenv('AUTH_DB_PASSWORD_SCHEME', 'django_hash').strip().lower()
AUTH_DB_USERNAME_CASE_SENSITIVE = os.getenv('AUTH_DB_USERNAME_CASE_SENSITIVE', 'false').lower() == 'true'
if AUTH_MODE == 'corporate_db':
    auth_engine = os.getenv('AUTH_DB_ENGINE', 'mysql').strip().lower()
    if auth_engine == 'sqlite':
        DATABASES['corporate_auth'] = {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('AUTH_DB_NAME', str(BASE_DIR / 'corporate-auth.sqlite3')),
        }
    elif auth_engine == 'mysql':
        auth_options = {
            'charset': 'utf8mb4',
            'connect_timeout': int(os.getenv('AUTH_DB_CONNECT_TIMEOUT', '5')),
        }
        if os.getenv('AUTH_DB_SSL_CA', '').strip():
            auth_options['ssl'] = {'ca': os.getenv('AUTH_DB_SSL_CA').strip()}
        DATABASES['corporate_auth'] = {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('AUTH_DB_NAME', ''),
            'USER': os.getenv('AUTH_DB_USER', ''),
            'PASSWORD': os.getenv('AUTH_DB_PASSWORD', ''),
            'HOST': os.getenv('AUTH_DB_HOST', ''),
            'PORT': os.getenv('AUTH_DB_PORT', '3306'),
            'OPTIONS': auth_options,
            'CONN_MAX_AGE': int(os.getenv('AUTH_DB_CONN_MAX_AGE', '60')),
            'CONN_HEALTH_CHECKS': True,
        }
    else:
        raise RuntimeError('AUTH_DB_ENGINE must be mysql for production (sqlite is test-only)')
AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/storage/'
MEDIA_ROOT = Path(os.getenv('STORAGE_PATH', '/app/storage'))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
REST_FRAMEWORK = {'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'], 'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser','rest_framework.parsers.FormParser','rest_framework.parsers.MultiPartParser']}
CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL', 'false').lower() == 'true'
INTERNAL_API_TOKEN = os.getenv('INTERNAL_API_TOKEN', '').strip()
MAX_IMAGE_UPLOAD_BYTES = int(os.getenv('MAX_IMAGE_UPLOAD_MB', '12')) * 1024 * 1024
MAX_AUDIO_UPLOAD_BYTES = int(os.getenv('MAX_AUDIO_UPLOAD_MB', '30')) * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('MAX_REQUEST_UPLOAD_MB', '128')) * 1024 * 1024
AGENT_GATEWAY_URL = os.getenv('AGENT_GATEWAY_URL', 'http://agent-layer:8010')
KNOWLEDGE_SERVICE_URL = os.getenv('KNOWLEDGE_SERVICE_URL', 'http://knowledge-service:8020')
QDRANT_URL = os.getenv('QDRANT_URL', 'http://qdrant:6333')
SYNC_PIPELINE = os.getenv('SYNC_PIPELINE', 'true').lower() == 'true'
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'false').lower() == 'true'
