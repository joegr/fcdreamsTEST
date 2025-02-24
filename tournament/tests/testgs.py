# tournament/tests/test_group_stage.py
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from datetime import date
from ..models import Tournament, Team, Match, Result
from ..group_stage import GroupStageManager, MatchStatus

class GroupStageTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create admin user
        self.admin = User.objects.create_superuser('admin', 'admin@test.com', 'adminpass')
        
        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            datetime=date.today(),
            number_of_groups=2,
            teams_per_group=4,
            is_active=True
        )
        
        # Create team managers
        self.manager1 = User.objects.create_user('manager1', 'manager1@test.com', 'pass123')
        self.manager2 = User.objects.create_user('manager2', 'manager2@test.com', 'pass123')
        
        # Create teams
        self.team1 = Team.objects.create(
            name="Team 1",
            manager=self.manager1,
            email="team1@test.com",
            contact_phone="1234567890",
            registration_code="T1",
            tournament=self.tournament,
            player_count=11
        )
        
        self.team2 = Team.objects.create(
            name="Team 2",
            manager=self.manager2,
            email="team2@test.com",
            contact_phone="0987654321",
            registration_code="T2",
            tournament=self.tournament,
            player_count=11
        )
        
        # Create match
        self.match = Match.objects.create(
            tournament=self.tournament,
            match_id="GS-A-01",
            team1=self.team1,
            team2=self.team2,
            match_date=date.today()
        )

    def test_submit_match_result(self):
        self.client.login(username='manager1', password='pass123')
        
        # Create dummy image file
        image_file = SimpleUploadedFile(
            "score.jpg",
            b"file_content",
            content_type="image/jpeg"
        )
        
        response = self.client.post(
            reverse('submit-result'),
            {
                'match_id': 'GS-A-01',
                'score': 2,
                'opponent_score': 1,
                'score_img': image_file,
            }
        )
        
        self.assertEqual(response.status_code, 200)
        result = Result.objects.get(match=self.match, team=self.team1)
        self.assertEqual(result.score, 2)
        self.assertEqual(result.opponent_score, 1)
        self.assertFalse(result.confirmed)

    def test_verify_matching_results(self):
        # Get the automatically created result for team 1 and update it
        result = self.match.result
        result.score = 2
        result.opponent_score = 1
        result.score_img = SimpleUploadedFile("score1.jpg", b"file_content")
        result.save()
        
        # Submit matching result from team 2
        self.client.login(username='manager2', password='pass123')
        response = self.client.post(
            reverse('submit-result'),
            {
                'match_id': 'GS-A-01',
                'score': 1,
                'opponent_score': 2,
                'score_img': SimpleUploadedFile("score2.jpg", b"file_content"),
            }
        )
        
        self.assertEqual(response.status_code, 200)
        self.match.refresh_from_db()
        self.assertTrue(self.match.confirmed)

    def test_group_completion(self):
        gsm = GroupStageManager(self.tournament)
        
        # Create and confirm all matches
        matches = Match.objects.filter(tournament=self.tournament)
        for match in matches:
            match.confirmed = True
            match.save()
            
        self.assertTrue(gsm.check_group_completion())
        
        # Verify standings calculation
        standings = gsm.get_group_standings('A')
        self.assertTrue(len(standings) > 0)

    def test_handle_mismatched_results(self):
        # Get the automatically created result for team 1 and update it
        result = self.match.result
        result.score = 2
        result.opponent_score = 1
        result.score_img = SimpleUploadedFile("score1.jpg", b"file_content")
        result.save()
        
        # Submit conflicting result from team 2
        self.client.login(username='manager2', password='pass123')
        response = self.client.post(
            reverse('submit-result'),
            {
                'match_id': 'GS-A-01',
                'score': 2,
                'opponent_score': 0,  # Different score
                'score_img': SimpleUploadedFile("score2.jpg", b"file_content"),
            }
        )
        
        self.assertEqual(response.status_code, 200)
        self.match.refresh_from_db()
        self.assertFalse(self.match.confirmed)