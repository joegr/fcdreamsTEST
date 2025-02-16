import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'your-default-secret-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = int(os.environ.get('DEBUG', 0))

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost 127.0.0.1 0.0.0.0').split(' ')

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'tournament'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'

INSTALLED_APPS = [
    ...
    'tournament',
    ...
] 

# LOGIN_REDIRECT_URL = 'user_dashboard'
LOGIN_URL = 'login' 

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'tournament/templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
] 

# Add to existing settings
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'tournament': {
            '()': 'tournament.models.TournamentLogFormatter',
        },
    },
    'handlers': {
        'tournament_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'tournament_events.log',
            'formatter': 'tournament',
        },
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'tournament.state': {
            'handlers': ['tournament_file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
} 