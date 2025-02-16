from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta
from .models import Tournament, Team, Match, Result
from .services.tournament import TournamentService
from .services.group_stage import GroupStageService
from rest_framework.test import APITestCase
from rest_framework import status

class TournamentViewsTestCase(TestCase):
    def setUp(self):
        # Create admin user
        self.admin_user = User.objects.create_user(
            'admin', 'admin@test.com', 'adminpass', 
            is_staff=True
        )
        
        # Create regular users
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'pass123')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'pass123')
        
        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            datetime=timezone.now() + timedelta(days=30),
            number_of_groups=2,
            teams_per_group=4,
            is_active=True,
            status='REGISTRATION'
        )
        
        # Create teams
        self.team1 = Team.objects.create(
            name="user1 FC",
            manager=self.user1,
            tournament=self.tournament,
            player_count=8,
            registration_complete=True
        )
        
        self.team2 = Team.objects.create(
            name="user2 FC",
            manager=self.user2,
            tournament=self.tournament,
            player_count=8,
            registration_complete=True
        )
        
        self.client = Client()

    def test_signup_creates_team(self):
        """Test that signing up creates a team automatically"""
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'password1': 'testpass123',
            'password2': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 302)  # Redirect after signup
        
        # Check if team was created
        new_user = User.objects.get(username='newuser')
        team = Team.objects.filter(manager=new_user).first()
        
        self.assertIsNotNone(team)
        self.assertEqual(team.name, 'newuser FC')
        self.assertEqual(team.player_count, 0)
        self.assertFalse(team.registration_complete)

    def test_admin_dashboard_access(self):
        """Test admin dashboard access restrictions"""
        admin_url = reverse('admin_dashboard')
        
        # Test unauthenticated access
        response = self.client.get(admin_url)
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        # Test non-staff access
        self.client.login(username='user1', password='pass123')
        response = self.client.get(admin_url)
        self.assertEqual(response.status_code, 302)  # Redirect to manager dashboard
        
        # Test staff access
        self.client.login(username='admin', password='adminpass')
        response = self.client.get(admin_url)
        self.assertEqual(response.status_code, 200)

    def test_tournament_creation(self):
        """Test tournament creation with enough teams"""
        self.client.login(username='admin', password='adminpass')
        
        # Create 6 more teams to have 8 total
        for i in range(6):
            user = User.objects.create_user(f'user{i+3}', f'user{i+3}@test.com', 'pass123')
            Team.objects.create(
                name=f"Team {i+3}",
                manager=user,
                tournament=None,
                player_count=8,
                registration_complete=True
            )
        
        response = self.client.post(reverse('tournament_admin'), {
            'create_tournament': 'true'
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Check if new tournament was created
        new_tournament = Tournament.objects.latest('id')
        self.assertEqual(
            Team.objects.filter(tournament=new_tournament).count(), 
            8
        )

    def test_login_redirect(self):
        """Test login redirects to appropriate dashboard"""
        login_url = reverse('login')
        
        # Test admin redirect
        response = self.client.post(login_url, {
            'username': 'admin',
            'password': 'adminpass'
        })
        self.assertRedirects(response, reverse('admin_dashboard'))
        
        # Test team manager redirect
        response = self.client.post(login_url, {
            'username': 'user1',
            'password': 'pass123'
        })
        self.assertRedirects(response, reverse('player_dashboard'))
        
        # Test new user redirect
        new_user = User.objects.create_user('newuser', 'new@test.com', 'pass123')
        response = self.client.post(login_url, {
            'username': 'newuser',
            'password': 'pass123'
        })
        self.assertRedirects(response, reverse('manager_dashboard'))

    def test_player_dashboard_content(self):
        """Test player dashboard shows correct content"""
        self.client.login(username='user1', password='pass123')
        
        # Create some matches
        match1 = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team1,
            team_away=self.team2,
            match_date=timezone.now() + timedelta(days=1),
            stage='GROUP',
            status='SCHEDULED'
        )
        
        match2 = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team2,
            team_away=self.team1,
            match_date=timezone.now() - timedelta(days=1),
            stage='GROUP',
            status='CONFIRMED',
            home_score=2,
            away_score=1
        )
        
        response = self.client.get(reverse('player_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check context data
        self.assertEqual(response.context['team'], self.team1)
        self.assertEqual(len(response.context['upcoming_matches']), 1)
        self.assertEqual(len(response.context['recent_matches']), 1)
        self.assertEqual(response.context['tournament'], self.tournament)

    def test_tournament_admin_view(self):
        """Test tournament admin view functionality"""
        self.client.login(username='admin', password='adminpass')
        
        response = self.client.get(reverse('tournament_admin'))
        self.assertEqual(response.status_code, 200)
        
        # Check context data
        self.assertTrue('available_teams' in response.context)
        self.assertTrue('tournaments' in response.context)
        self.assertTrue('pending_teams' in response.context)
        self.assertTrue('pending_matches' in response.context)
        
        # Test tournament creation with insufficient teams
        response = self.client.post(reverse('tournament_admin'), {
            'create_tournament': 'true'
        })
        self.assertEqual(response.status_code, 302)
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("Not enough eligible teams" in str(m) for m in messages))

class GroupStageTestCase(TestCase):
    def setUp(self):
        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            datetime=timezone.now() + timedelta(days=30),
            number_of_groups=2,
            teams_per_group=4,
            is_active=True,
            status='REGISTRATION'
        )
        
        # Create 8 teams (2 groups of 4)
        self.teams = []
        for i in range(8):
            user = User.objects.create_user(f'user{i}', f'user{i}@test.com', 'pass123')
            team = Team.objects.create(
                name=f"Team {i}",
                manager=user,
                tournament=self.tournament,
                player_count=8,
                registration_complete=True
            )
            self.teams.append(team)

    def test_group_generation(self):
        """Test group stage generation"""
        group_service = GroupStageService(self.tournament)
        groups = group_service.generate_groups()
        
        # Test correct number of groups
        self.assertEqual(len(groups), 2)
        
        # Test correct number of teams per group
        for group_num, teams in groups.items():
            self.assertEqual(len(teams), 4)
        
        # Test all teams are assigned
        assigned_teams = []
        for teams in groups.values():
            assigned_teams.extend(teams)
        self.assertEqual(set(assigned_teams), set(self.teams))

    def test_match_generation(self):
        """Test match generation for group stage"""
        group_service = GroupStageService(self.tournament)
        group_service.generate_groups()
        matches = group_service.generate_matches()
        
        # Each team plays against every other team in their group once
        # In a group of 4, each team plays 3 matches
        # With 2 groups, total matches = 2 * (4 * 3/2) = 12
        self.assertEqual(len(matches), 12)
        
        # Test match properties
        for match in matches:
            self.assertEqual(match.tournament, self.tournament)
            self.assertEqual(match.stage, 'GROUP')
            self.assertIn(match.team_home, self.teams)
            self.assertIn(match.team_away, self.teams)
            self.assertNotEqual(match.team_home, match.team_away)

    def test_group_standings(self):
        """Test group standings calculation"""
        group_service = GroupStageService(self.tournament)
        groups = group_service.generate_groups()
        matches = group_service.generate_matches()
        
        # Simulate some match results
        match = matches[0]
        match.status = 'CONFIRMED'
        match.home_score = 2
        match.away_score = 1
        match.save()
        
        standings = group_service.get_group_standings()
        
        # Test standings structure
        self.assertEqual(len(standings), 2)  # Two groups
        
        # Find the group containing the teams from the match
        for group_num, group_standings in standings.items():
            if match.team_home in [s['team'] for s in group_standings]:
                # Test winning team stats
                winner_stats = next(s for s in group_standings if s['team'] == match.team_home)
                self.assertEqual(winner_stats['points'], 3)
                self.assertEqual(winner_stats['goals_for'], 2)
                self.assertEqual(winner_stats['goals_against'], 1)
                self.assertEqual(winner_stats['goal_difference'], 1)
                
                # Test losing team stats
                loser_stats = next(s for s in group_standings if s['team'] == match.team_away)
                self.assertEqual(loser_stats['points'], 0)
                self.assertEqual(loser_stats['goals_for'], 1)
                self.assertEqual(loser_stats['goals_against'], 2)
                self.assertEqual(loser_stats['goal_difference'], -1)

class TournamentModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            datetime=timezone.now(),
            number_of_groups=2,
            teams_per_group=4,
            organizer=self.user
        )

    def test_tournament_slug_generation(self):
        """Test that tournament slugs are generated correctly"""
        self.assertTrue(self.tournament.slug.startswith(timezone.now().strftime('%Y%m%d')))
        self.assertIn('tournament', self.tournament.slug)
        self.assertIn(self.tournament.name.lower(), self.tournament.slug)

class TeamModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            datetime=timezone.now()
        )

    def test_team_slug_generation(self):
        """Test that team slugs are generated correctly and uniquely"""
        team1 = Team.objects.create(
            name="Test Team",
            tournament=self.tournament,
            manager=self.user
        )
        team2 = Team.objects.create(
            name="Test Team",  # Same name
            tournament=self.tournament,
            manager=self.user
        )
        
        self.assertNotEqual(team1.slug, team2.slug)
        self.assertTrue(team1.slug.startswith(timezone.now().strftime('%Y%m%d')))
        self.assertIn('team', team1.slug)

class MatchResultTests(APITestCase):
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(username='manager1', password='12345')
        self.user2 = User.objects.create_user(username='manager2', password='12345')
        
        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            datetime=timezone.now(),
            status='GROUP_STAGE'
        )
        
        # Create teams
        self.team1 = Team.objects.create(
            name="Team 1",
            tournament=self.tournament,
            manager=self.user1,
            registration_complete=True
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            tournament=self.tournament,
            manager=self.user2,
            registration_complete=True
        )
        
        # Create match
        self.match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team1,
            team_away=self.team2,
            match_date=timezone.now() + timedelta(days=1),
            stage='GROUP',
            status='SCHEDULED'
        )

    def test_result_creation(self):
        """Test that a Result is automatically created with a Match"""
        self.assertTrue(hasattr(self.match, 'result'))
        self.assertIsNotNone(self.match.result)
        self.assertTrue(self.match.result.slug.startswith(timezone.now().strftime('%Y%m%d')))

    def test_result_submission(self):
        """Test the result submission process"""
        self.client.force_authenticate(user=self.user1)
        
        # Submit result as home team
        response = self.client.post(f'/api/matches/{self.match.slug}/submit-result/', {
            'home_score': 2,
            'away_score': 1,
            'extra_time': False,
            'penalties': False
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify result state
        result = Result.objects.get(match=self.match)
        self.assertTrue(result.home_team_confirmed)
        self.assertFalse(result.away_team_confirmed)
        self.assertEqual(result.home_score, 2)
        self.assertEqual(result.away_score, 1)
        
        # Submit result as away team
        self.client.force_authenticate(user=self.user2)
        response = self.client.post(f'/api/matches/{self.match.slug}/submit-result/', {
            'home_score': 2,
            'away_score': 1,
            'extra_time': False,
            'penalties': False
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify match is confirmed
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, 'CONFIRMED')

    def test_result_dispute(self):
        """Test handling of disputed results"""
        self.client.force_authenticate(user=self.user1)
        
        # Home team submission
        response = self.client.post(f'/api/matches/{self.match.slug}/submit-result/', {
            'home_score': 2,
            'away_score': 1
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Away team submits different score
        self.client.force_authenticate(user=self.user2)
        response = self.client.post(f'/api/matches/{self.match.slug}/submit-result/', {
            'home_score': 1,
            'away_score': 2
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify match is marked as disputed
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, 'DISPUTED')

    def test_unauthorized_submission(self):
        """Test that only team managers can submit results"""
        unauthorized_user = User.objects.create_user(username='unauthorized', password='12345')
        self.client.force_authenticate(user=unauthorized_user)
        
        response = self.client.post(f'/api/matches/{self.match.slug}/submit-result/', {
            'home_score': 2,
            'away_score': 1
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
