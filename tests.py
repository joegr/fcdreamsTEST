from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
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
	match_date = factory.LazyAttribute(lambda obj: obj.tournament.datetime + timedelta(days=1))
	stage = 'GROUP'
	status = 'SCHEDULED'

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