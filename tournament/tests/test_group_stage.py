from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from ..models import Tournament, Team, Match, Result
from ..services.group_stage import GroupStageService
from ..services.tournament import TournamentService
import factory

class GroupStageTestCase(TestCase):
    def setUp(self):
        """Setup tournament with teams in group stage"""
        self.tournament = Tournament.objects.create(
            name="Test Tournament 2024",
            datetime=timezone.now(),
            number_of_groups=2,
            teams_per_group=4,
            status='GROUP_STAGE'
        )
        
        # Create 8 teams (2 groups of 4)
        self.teams = []
        self.managers = []
        for i in range(8):
            manager = User.objects.create_user(
                username=f'manager{i}',
                email=f'manager{i}@test.com',
                password='testpass123'
            )
            self.managers.append(manager)
            
            team = Team.objects.create(
                name=f"Team {chr(65 + i)}",
                tournament=self.tournament,
                manager=manager,
                registration_complete=True
            )
            self.teams.append(team)
        
        self.group_service = GroupStageService(self.tournament)
        self.tournament_service = TournamentService(self.tournament)

    def test_match_result_submission(self):
        """Test match result submission and confirmation flow"""
        # Generate group matches
        matches = self.group_service.generate_matches()
        match = matches[0]
        
        # Submit result from home team
        home_result = {
            'score': 2,
            'opponent_score': 1,
            'match_date': match.match_date
        }
        match.result.confirm_result(match.team_home, home_result)
        
        # Verify pending status
        self.assertEqual(match.status, 'PENDING')
        self.assertTrue(match.result.home_team_confirmed)
        self.assertFalse(match.result.away_team_confirmed)

    def test_result_verification(self):
        """Test OCR verification of match results"""
        match = self.group_service.generate_matches()[0]
        
        # Create mock result images
        home_image = SimpleUploadedFile(
            "home_result.jpg",
            b"file_content",
            content_type="image/jpeg"
        )
        away_image = SimpleUploadedFile(
            "away_result.jpg",
            b"file_content",
            content_type="image/jpeg"
        )
        
        # Submit results with images
        match.result.submit_result_image(match.team_home, home_image, {'score': 2, 'opponent_score': 1})
        match.result.submit_result_image(match.team_away, away_image, {'score': 1, 'opponent_score': 2})
        
        # Verify match confirmation
        match.refresh_from_db()
        self.assertEqual(match.status, 'CONFIRMED')
        self.assertEqual(match.home_score, 2)
        self.assertEqual(match.away_score, 1)

    def test_group_completion(self):
        """Test group stage completion and progression"""
        matches = self.group_service.generate_matches()
        
        # Simulate all matches with results
        for match in matches:
            # Home team wins with 2-1
            result = match.result
            result.home_score = 2
            result.away_score = 1
            result.home_team_confirmed = True
            result.away_team_confirmed = True
            result.save()
            
            match.status = 'CONFIRMED'
            match.home_score = 2
            match.away_score = 1
            match.save()
        
        # Verify group completion
        self.assertTrue(self.group_service.is_group_stage_complete())
        
        # Verify standings calculation
        standings = self.group_service.get_group_standings()
        self.assertEqual(len(standings), 2)  # 2 groups
        
        # Verify qualification
        qualified_teams = self.group_service.get_qualified_teams()
        self.assertEqual(len(qualified_teams), 4)  # Top 2 from each group

    def test_knockout_stage_generation(self):
        """Test generation of knockout stage after group completion"""
        # Complete group stage
        self.test_group_completion()
        
        # Verify tournament status change
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.status, 'KNOCKOUT')
        
        # Verify RO16 matches
        knockout_matches = Match.objects.filter(
            tournament=self.tournament,
            stage='RO16'
        )
        self.assertEqual(len(knockout_matches), 2)  # 4 teams = 2 matches 