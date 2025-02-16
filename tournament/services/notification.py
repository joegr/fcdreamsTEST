from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger('tournament.state')

def notify_team_for_confirmation(team):
    """Notify team to confirm match result"""
    logger.info(
        f"Match confirmation required",
        extra={
            'event_type': 'CONFIRMATION_REQUIRED',
            'tournament_data': {
                'id': team.tournament.id,
                'name': team.tournament.name,
                'team': team.name,
                'manager_email': team.manager.email
            }
        }
    )

def notify_match_confirmation(match):
    """Notify both teams that match is confirmed"""
    logger.info(
        f"Match result confirmed",
        extra={
            'event_type': 'MATCH_CONFIRMED',
            'tournament_data': {
                'id': match.tournament.id,
                'name': match.tournament.name,
                'home_team': match.team_home.name,
                'away_team': match.team_away.name,
                'score': f"{match.home_score}-{match.away_score}"
            }
        }
    ) 