from django.test import TestCase
from ..models import Tournament, Team, Match

class ModelTests(TestCase):
    """Test model creation and validation"""
    # Move model-specific tests here

class SignalTests(TestCase):
    def setUp(self):
        self.tournament = TournamentFactory()
        self.team1 = TeamFactory(tournament=self.tournament)
        self.team2 = TeamFactory(tournament=self.tournament)

    def test_result_creation_signal(self):
        """Test result is automatically created with match"""
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team1,
            team_away=self.team2,
            match_date=timezone.now(),
            stage='GROUP',
            status='SCHEDULED'
        )

        # Verify result was created by signal
        self.assertTrue(hasattr(match, 'result'))
        self.assertEqual(match.result.team_home, self.team1)
        self.assertEqual(match.result.team_away, self.team2)
        self.assertEqual(match.result.home_score, 0)
        self.assertEqual(match.result.away_score, 0)