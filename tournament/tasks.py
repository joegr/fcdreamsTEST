from celery import shared_task
from .models import Team

@shared_task
def validate_team_registration(team_id):
    team = Team.objects.get(id=team_id)
    player_count = team.player_set.count()
    
    if 8 <= player_count <= 14:
        team.is_registration_complete = True
        team.save()
        return True
    return False

