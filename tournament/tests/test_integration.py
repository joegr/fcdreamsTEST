
from django.test import TestCase
from tournament.models import Tournament, Team, Match
from tournament.services.tournament import TournamentService
from tournament.services.group_stage import GroupStageService
from tournament.tests.factories import TournamentFactory, TeamFactory


# Move TournamentProgressionTest here
# Keep the integration test that verifies full tournament flow
class TournamentProgressionTest(TestCase):
    def setUp(self):
        """Set up tournament with 32 teams"""
        self.tournament = TournamentFactory()
        
        # Create teams with explicit tournament to avoid creating multiple tournaments
        self.teams = TeamFactory.create_batch(
            size=32,
            tournament=self.tournament
        )
        
        self.tournament_service = TournamentService(self.tournament)
        self.group_service = GroupStageService(self.tournament)

    def test_group_stage(self):
        """Test group stage progression"""
        groups = self.group_service.generate_groups()
        self.assertEqual(len(groups), 8)
        
        matches = self.group_service.generate_matches()
        self.assertEqual(len(matches), 48)
        
        # Simulate all group matches
        for match in matches:
            self._simulate_match(match)
        
        # Verify group stage completion
        self.assertTrue(self.group_service.is_group_stage_complete())
        qualified_teams = self.group_service.get_qualified_teams()
        self.assertEqual(len(qualified_teams), 16)
        return qualified_teams

    def test_knockout_progression(self):
        """Test complete knockout stage progression"""
        qualified_teams = self.test_group_stage()
        
        # Test each knockout round
        stages = [
            ('RO16', 16, 8),
            ('QUARTER', 8, 4),
            ('SEMI', 4, 2),
            ('FINAL', 2, 1)
        ]
        
        current_teams = qualified_teams
        for stage, num_teams, expected_matches in stages:
            self.assertEqual(len(current_teams), num_teams)
            
            matches = self.tournament_service.create_knockout_matches(
                current_teams, stage
            )
            self.assertEqual(len(matches), expected_matches)
            
            # Simulate matches
            for match in matches:
                self._simulate_match(match)
            
            if stage != 'FINAL':
                current_teams = self.tournament_service.get_stage_winners(stage)
        
        # Verify tournament completion
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.status, 'COMPLETED')

    def _simulate_match(self, match):
        """Simulate match with deterministic outcome"""
        result = match.result
        if match.team_home.strength_rating > match.team_away.strength_rating:
            result.home_score, result.away_score = 2, 0
        else:
            result.home_score, result.away_score = 0, 2
        
        result.home_team_confirmed = result.away_team_confirmed = True
        result.save()