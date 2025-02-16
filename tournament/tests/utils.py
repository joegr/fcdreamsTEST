from django.utils import timezone
from ..models import Tournament, Team, Match

def create_test_tournament():
    """Create a test tournament with teams"""
    tournament = Tournament.objects.create(
        name="Test Tournament",
        datetime=timezone.now()
    )
    return tournament

def create_test_match(tournament, team1, team2):
    """Create a test match between two teams"""
    match = Match.objects.create(
        tournament=tournament,
        team_home=team1,
        team_away=team2,
        match_date=timezone.now()
    )
    return match 