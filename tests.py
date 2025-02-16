from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import timedelta

from tournament.models import Tournament, Team, Match, Result
from tournament.services.group_stage import GroupStageService
from tournament.services.knockout import KnockoutService
from tournament.services.tournament import TournamentService
from tournament.signals import create_match_result  # Import the signal

# Ensure the signal is connected for tests
from django.db.models.signals import post_save
post_save.connect(create_match_result, sender=Match)

class TournamentStagesTest(TestCase):
	@classmethod
	def setUpTestData(cls):
		# Set up non-modified data for all test methods
		settings.TESTING = True

	def setUp(self):
		# Ensure signals are connected
		post_save.connect(create_match_result, sender=Match)
		
		# Create tournament
		self.tournament = Tournament.objects.create(
			name="Test Tournament",
			datetime=timezone.now(),
			number_of_groups=2,
			teams_per_group=4,
			status='GROUP_STAGE'
		)
		
		# Create 8 teams (2 groups of 4)
		self.teams = []
		for i in range(8):
			user = User.objects.create_user(f'user{i}', f'user{i}@test.com', 'pass123')
			team = Team.objects.create(
				name=f"Team {i}",
				tournament=self.tournament,
				manager=user,
				registration_complete=True
			)
			self.teams.append(team)
		
		# Generate groups and matches
		self.group_service = GroupStageService(self.tournament)
		self.groups = self.group_service.generate_groups()
		self.matches = self.group_service.generate_matches()

	def simulate_group_matches(self):
		"""Simulate all group stage matches with results"""
		for match in self.matches:
			# Get or create the result object (should be auto-created with match)
			result = match.result
			
			# Simulate home team confirmation
			result.home_score = 2
			result.away_score = 1
			result.home_team_confirmed = True
			result.save()
			
			# Simulate away team confirmation
			result.away_team_confirmed = True
			result.save()
			
			# Update match status
			match.status = 'CONFIRMED'
			match.home_score = result.home_score
			match.away_score = result.away_score
			match.save()

	def test_complete_tournament_flow(self):
		"""Test complete tournament flow from groups to knockout stage"""
		# Simulate group stage matches
		self.simulate_group_matches()
		
		# Check if group stage is complete
		self.assertTrue(self.group_service.is_group_stage_complete())
		
		# Transition to knockout stage
		self.group_service.transition_to_knockout_stage()
		
		# Verify tournament status
		self.tournament.refresh_from_db()
		self.assertEqual(self.tournament.status, 'KNOCKOUT')
		
		# Verify knockout matches were created
		knockout_matches = Match.objects.filter(
			tournament=self.tournament,
			stage__in=['QUARTER', 'SEMI', 'FINAL']
		)
		self.assertTrue(knockout_matches.exists())

	def test_group_stage_standings(self):
		"""Test detailed group standings calculation"""
		self.simulate_group_matches()
		
		standings = self.group_service.get_group_standings()
		
		# Verify standings structure
		self.assertEqual(len(standings), 2)  # Two groups
		
		for group_num, group_standings in standings.items():
			# Verify each group has 4 teams
			self.assertEqual(len(group_standings), 4)
			
			# Verify standings are ordered by points
			points = [team_stats['points'] for team_stats in group_standings]
			self.assertEqual(points, sorted(points, reverse=True))
			
			# Verify point calculations
			for team_stats in group_standings:
				expected_points = (team_stats['wins'] * 3) + team_stats['draws']
				self.assertEqual(team_stats['points'], expected_points)
				
				# Verify goal difference calculation
				self.assertEqual(
					team_stats['goal_difference'],
					team_stats['goals_for'] - team_stats['goals_against']
				)

	def tearDown(self):
		# Disconnect signals to prevent interference between tests
		post_save.disconnect(create_match_result, sender=Match)
		
		# Clean up created objects
		Result.objects.all().delete()
		Match.objects.all().delete()
		Team.objects.all().delete()
		Tournament.objects.all().delete()
		User.objects.all().delete()

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
	"""Test view functionality"""
	
	def test_dashboard_views(self):
		"""Test dashboard rendering"""
		pass  # Add tests

class SignalTests(TestCase):
	"""Test signal behavior"""
	
	def test_result_creation_signal(self):
		"""Test result is created with match"""
		tournament = Tournament.objects.create(
			name="Test Tournament",
			datetime=timezone.now()
		)
		team1 = Team.objects.create(name="Team 1", tournament=tournament)
		team2 = Team.objects.create(name="Team 2", tournament=tournament)
		
		match = Match.objects.create(
			tournament=tournament,
			team_home=team1,
			team_away=team2,
			match_date=timezone.now()
		)
		
		# Verify result was created
		self.assertTrue(hasattr(match, 'result'))
		self.assertIsNotNone(match.result)