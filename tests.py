from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import timedelta
import random
import factory
from factory.django import DjangoModelFactory
from tournament.models import Tournament, Team, Match, Result
from tournament.services.group_stage import GroupStageService
from tournament.services.knockout import KnockoutService
from tournament.services.tournament import TournamentService
from tournament.signals import create_match_result  # Import the signal

# Ensure the signal is connected for tests
from django.db.models.signals import post_save
post_save.connect(create_match_result, sender=Match)

# Base User Factory
class UserFactory(DjangoModelFactory):
	class Meta:
		model = User
		django_get_or_create = ('username',)

	username = factory.Sequence(lambda n: f'user_{n:03d}')
	email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
	password = 'testpass123'

	@factory.post_generation
	def set_password(self, create, extracted, **kwargs):
		self.set_password(self.password)
		self.save()

# Tournament Factory (depends only on User)
class TournamentFactory(DjangoModelFactory):
	class Meta:
		model = Tournament

	name = factory.Sequence(lambda n: f'Tournament_{n:03d}')
	datetime = factory.LazyFunction(timezone.now)
	number_of_groups = 8
	teams_per_group = 4
	status = 'GROUP_STAGE'
	organizer = factory.SubFactory(UserFactory)

# Team Factory (depends on Tournament and User)
class TeamFactory(DjangoModelFactory):
	class Meta:
		model = Team
		django_get_or_create = ('name', 'tournament')

	name = factory.Sequence(lambda n: f'Team_{chr(65 + (n % 26))}_{n // 26}')
	tournament = factory.SubFactory(TournamentFactory)
	manager = factory.SubFactory(UserFactory)
	registration_complete = True
	strength_rating = factory.Sequence(lambda n: 100 - n)

# Match Factory (depends on Tournament)
class MatchFactory(DjangoModelFactory):
    class Meta:
        model = Match
        
    tournament = factory.SubFactory(TournamentFactory)
    team_home = factory.SubFactory(TeamFactory)
    team_away = factory.SubFactory(TeamFactory) 
    stage = 'GROUP'
    status = 'SCHEDULED'
    match_date = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def group(self, create, extracted, **kwargs):
        if not create:
            return
            
        if extracted:
            self.group = extracted
        else:
            # Default to group A if not specified
            self.group = 'A'
            
    class Params:
        # Allow overriding tournament teams belong to
        same_tournament = factory.Trait(
            team_home=factory.SubFactory(TeamFactory, tournament=factory.SelfAttribute('..tournament')),
            team_away=factory.SubFactory(TeamFactory, tournament=factory.SelfAttribute('..tournament'))
        )

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
		# Generate group matches
		matches = self.group_service.create_group_matches()
		
		# Confirm all group matches with random scores
		for match in matches:
			match.home_score = 2  # Simple score for testing
			match.away_score = 1
			match.status = 'CONFIRMED'
			match.save()
			
			# Update the automatically created result
			result = match.result
			result.home_score = match.home_score
			result.away_score = match.away_score
			result.confirmed = True
			result.save()
		
		# Now we can get qualified teams
		qualified_teams = self.group_service.get_qualified_teams()
		self.assertEqual(len(qualified_teams), 16)  # For 8 groups, top 2 from each
		
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

class ModelTests(TestCase):
	"""Test model creation and validation"""
	
	def test_tournament_creation(self):
		"""Test tournament creation with validation"""
		pass  # Add tests

class ServiceTests(TestCase):
	"""Test service layer functionality"""
	
	def test_group_stage_service(self):
		"""Test group stage operations"""
		pass  # Add tests

class APITests(APITestCase):
	"""Test API endpoints"""
	
	def test_result_submission(self):
		"""Test result submission endpoint"""
		pass  # Add tests

class ViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tournament = TournamentFactory()
        self.user = UserFactory()
        self.team = TeamFactory(
            tournament=self.tournament,
            manager=self.user
        )
        self.client.force_login(self.user)

    def test_dashboard_view(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')

    def test_match_result_submission(self):
        match = MatchFactory(
            tournament=self.tournament,
            team_home=self.team,
            team_away=TeamFactory(tournament=self.tournament)
        )
        response = self.client.post(
            reverse('submit-result'),
            {
                'match': match.id,
                'home_score': 2,
                'away_score': 1
            }
        )
        self.assertEqual(response.status_code, 200)

class SignalTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.team1 = Team.objects.create(name="Team 1", tournament=self.tournament)
        self.team2 = Team.objects.create(name="Team 2", tournament=self.tournament)

    def test_result_creation_signal(self):
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team1,
            team_away=self.team2,
            stage='GROUP'
        )
        self.assertTrue(hasattr(match, 'result'))
        self.assertEqual(match.result.home_score, 0)
        self.assertEqual(match.result.away_score, 0)

from django.core import mail
from datetime import date

class GroupStageTestCase(TestCase):
    def setUp(self):
        self.tournament = TournamentFactory(number_of_groups=8, teams_per_group=4)
        self.teams = [TeamFactory(tournament=self.tournament) for _ in range(32)]
        self.service = GroupStageService(self.tournament)

    def test_group_creation(self):
        groups = self.service.generate_groups()
        self.assertEqual(len(groups), 8)
        for group in groups.values():
            self.assertEqual(len(group), 4)

    def test_match_generation(self):
        matches = self.service.create_group_matches()
        expected_matches = 8 * 6  # 8 groups × 6 matches per group (4 teams play each other once)
        self.assertEqual(len(matches), expected_matches)
        
        # Verify match properties
        first_match = matches[0]
        self.assertEqual(first_match.stage, 'GROUP')
        self.assertEqual(first_match.status, 'SCHEDULED')
        self.assertNotEqual(first_match.team_home, first_match.team_away)

    def test_standings_calculation(self):
        """Test group standings calculation"""
        # Create a match in group A
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.teams[0],
            team_away=self.teams[1],
            stage='GROUP',
            group='A',
            status='CONFIRMED'
        )
        
        # Update the result
        result = match.result
        result.home_score = 2
        result.away_score = 1
        result.home_confirmed = True
        result.away_confirmed = True
        result.save()
        
        # Get standings for group A
        standings = self.service.get_group_standings('A')
        
        # Find the winning team's stats
        winner_stats = next(s for s in standings if s['team'] == self.teams[0])
        loser_stats = next(s for s in standings if s['team'] == self.teams[1])
        
        # Verify points and goals
        self.assertEqual(winner_stats['points'], 3)
        self.assertEqual(winner_stats['goals_for'], 2)
        self.assertEqual(winner_stats['goals_against'], 1)
        self.assertEqual(winner_stats['goal_difference'], 1)
        
        self.assertEqual(loser_stats['points'], 0)
        self.assertEqual(loser_stats['goals_for'], 1)
        self.assertEqual(loser_stats['goals_against'], 2)
        self.assertEqual(loser_stats['goal_difference'], -1)

class KnockoutStageTestCase(TestCase):
    def setUp(self):
        self.tournament = TournamentFactory()
        self.teams = [TeamFactory(tournament=self.tournament) for _ in range(16)]
        self.service = KnockoutService(self.tournament)

    def test_knockout_bracket_generation(self):
        matches = self.service.generate_knockout_matches(self.teams, 'RO16')
        self.assertEqual(len(matches), 8)

    def test_winner_determination(self):
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.teams[0],
            team_away=self.teams[1],
            status='CONFIRMED',
            stage='RO16'
        )
        
        # Update the result
        result = match.result
        result.home_score = 2
        result.away_score = 1
        result.home_confirmed = True
        result.away_confirmed = True
        result.save()
        
        winner = self.service.get_match_winner(match)
        self.assertEqual(winner, self.teams[0])

class ViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory()
        self.tournament = TournamentFactory()
        self.team = TeamFactory(tournament=self.tournament, manager=self.user)

    def test_dashboard_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')

    def test_match_result_submission(self):
        self.client.force_login(self.user)
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team,
            team_away=TeamFactory(tournament=self.tournament),
            match_date=timezone.now()
        )
        response = self.client.post(
            reverse('submit-result'),
            {
                'match': match.id,
                'home_score': 2,
                'away_score': 1,
                'score_img': SimpleUploadedFile("score.jpg", b"file_content")
            }
        )
        self.assertEqual(response.status_code, 200)
        match.refresh_from_db()
        self.assertEqual(match.status, 'PENDING')

class APITests(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.tournament = TournamentFactory()
        self.client.force_authenticate(user=self.user)

    def test_tournament_list(self):
        response = self.client.get(reverse('tournament-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_team_creation(self):
        data = {
            'name': 'New Team',
            'tournament': self.tournament.id
        }
        response = self.client.post(reverse('team-list'), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

class DashboardViewTests(TestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create test tournament
        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            status='REGISTRATION'
        )
        
        # Create test team managed by user
        self.team = Team.objects.create(
            name='Test Team',
            tournament=self.tournament,
            manager=self.user
        )
        
        # Create some matches
        self.match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team,
            team_away=Team.objects.create(
                name='Opponent Team',
                tournament=self.tournament
            ),
            stage='GROUP',
            group='A'
        )

    def test_user_dashboard_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('user_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/user_dashboard.html')
        self.assertIn('teams', response.context)
        self.assertIn('matches', response.context)
        self.assertIn('tournaments', response.context)

    def test_manager_dashboard_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/manager_dashboard.html')
        self.assertIn('managed_teams', response.context)
        self.assertIn('upcoming_matches', response.context)
        self.assertIn('pending_results', response.context)

    def test_admin_dashboard_view(self):
        # Make user an admin
        self.user.is_staff = True
        self.user.save()
        
        self.client.force_login(self.user)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/admin_dashboard.html')
        self.assertIn('tournaments', response.context)
        self.assertIn('pending_teams', response.context)
        self.assertIn('pending_matches', response.context)

    def test_dashboard_redirect_for_role(self):
        self.client.force_login(self.user)
        
        # Test manager redirect
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('manager_dashboard'))
        
        # Test admin redirect
        self.user.is_staff = True
        self.user.save()
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('admin_dashboard'))
        
        # Create a new user without a team for the user redirect test
        regular_user = User.objects.create_user(
            username='regularuser',
            password='testpass123'
        )
        self.client.force_login(regular_user)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('user_dashboard'))

    def test_unauthorized_access(self):
        # Test admin dashboard access by non-admin
        self.client.force_login(self.user)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 403)