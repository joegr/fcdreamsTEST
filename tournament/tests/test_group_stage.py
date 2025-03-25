from django.test import TestCase
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from tournament.models import Tournament, Team, Match, Result
from tournament.services.group_stage import GroupStageService
from tournament.services.tournament import TournamentService
from tournament.tests.factories import TournamentFactory, TeamFactory, UserFactory
import factory

class GroupStageTestCase(TestCase):
    def setUp(self):
        """Setup tournament with teams in group stage"""
        self.tournament = TournamentFactory(
            number_of_groups=8,
            teams_per_group=4
        )
        
        # Create 32 teams (8 groups × 4 teams)
        self.teams = [
            TeamFactory(
                tournament=self.tournament,
                registration_complete=True
            ) for _ in range(32)
        ]
        
        self.service = GroupStageService(self.tournament)

    def test_tournament_setup(self):
        """Test tournament initialization"""
        self.assertEqual(self.tournament.team_set.count(), 32)
        self.assertEqual(self.tournament.number_of_groups, 8)
        self.assertEqual(self.tournament.teams_per_group, 4)

    def test_group_assignment(self):
        """Test team group assignments"""
        groups = self.service.generate_groups()
        self.assertEqual(len(groups), 8)
        for group in groups.values():
            self.assertEqual(len(group), 4)

    def test_match_generation(self):
        """Test group stage match creation"""
        self.service.create_group_matches()
        expected_matches = 8 * (4 * 3 // 2)  # 8 groups × 6 matches per group
        self.assertEqual(self.tournament.match_set.count(), expected_matches)

    def test_result_processing(self):
        """Test match result handling"""
        match = self.tournament.match_set.first()
        result = Result.objects.get(match=match)
        result.home_score = 2
        result.away_score = 1
        result.home_confirmed = True
        result.away_confirmed = True
        result.save()
        
        standings = self.service.get_group_standings(match.group)
        winner = next(t for t in standings if t['team'] == match.team_home)
        self.assertEqual(winner['points'], 3)

    def test_group_completion(self):
        """Test group stage completion"""
        matches = self.tournament.match_set.all()
        for match in matches:
            result = Result.objects.get(match=match)
            result.home_score = 1
            result.away_score = 0
            result.home_confirmed = True
            result.away_confirmed = True
            result.save()
            
        self.assertTrue(self.service.is_group_stage_complete())
        qualified = self.service.get_qualified_teams()
        self.assertEqual(len(qualified), 16)