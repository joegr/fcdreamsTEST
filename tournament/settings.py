import os
from pathlib import Path

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# ...existing code...

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'tournament': {
            'format': '%(message)s'
        }
    },
    'handlers': {
        'tournament_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'tournament_events.log'),
            'formatter': 'tournament'
        }
    },
    'loggers': {
        'tournament.state': {
            'handlers': ['tournament_file'],
            'level': 'INFO',
            'propagate': True,
        }
    }
}

# Ensure logs directory exists
os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)

# Authentication settings
AUTH_USER_MODEL = 'auth.User'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

# Team registration settings
TEAM_REGISTRATION_EXPIRY_HOURS = 48
MAX_PLAYERS_PER_TEAM = 14
MIN_PLAYERS_PER_TEAM = 8

# Tournament settings
DEFAULT_TOURNAMENT_GROUPS = 2
DEFAULT_TEAMS_PER_GROUP = 4
MIN_TOURNAMENT_TEAMS = 2

# Model validation settings
TEAM_NAME_MAX_LENGTH = 100
TOURNAMENT_NAME_MAX_LENGTH = 100
PSN_ID_MAX_LENGTH = 255
REGISTRATION_CODE_LENGTH = 8

# Time zone and locale settings (if not already set)
TIME_ZONE = 'UTC'
USE_TZ = True

# ...existing code...
