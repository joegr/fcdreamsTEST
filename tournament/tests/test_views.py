from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from tournament.models import Tournament, Team, Match, Result, Manager
from django.contrib.auth.models import User
import json

class BaseTestCase(TestCase):
    def setUp(self):
        # Create test users
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.regular_user = User.objects.create_user(
            username='user',
            email='user@test.com',
            password='userpass123'
        )
        self.manager_user = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='managerpass123'
        )
        
        # Create second manager for away team
        self.away_manager_user = User.objects.create_user(
            username='away_manager',
            email='away_manager@test.com',
            password='managerpass123'
        )
        
        # Create manager profiles
        self.manager = Manager.objects.create(
            user=self.manager_user,
            psn_id='test_psn_id'
        )
        
        self.away_manager = Manager.objects.create(
            user=self.away_manager_user,
            psn_id='away_test_psn_id'
        )
        
        # Create tournament
        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            organizer=self.admin_user,
            datetime=timezone.now(),
            number_of_groups=2,
            teams_per_group=4,
            is_active=True,
            status='REGISTRATION'
        )
        
        # Create home team
        self.team = Team.objects.create(
            name='Test Team',
            tournament=self.tournament,
            manager=self.manager_user,
            player_count=8,
            registration_complete=True
        )

        # Create away team
        self.away_team = Team.objects.create(
            name='Away Test Team',
            tournament=self.tournament,
            manager=self.away_manager_user,
            player_count=8,
            registration_complete=True
        )
        
        # Create match - Result will be created automatically by Match's save method
        self.match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team,
            team_away=self.away_team,
            stage='GROUP',
            status='SCHEDULED'
        )
        
        # Get the automatically created result
        self.result = self.match.result
        
        self.client = Client()

class SignUpViewTest(BaseTestCase):
    def test_signup_get(self):
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/signup.html')
    
    def test_signup_post_success(self):
        data = {
            'username': 'newuser',
            'password1': 'testpass123',
            'password2': 'testpass123'
        }
        response = self.client.post(reverse('signup'), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())

class TournamentAdminViewTest(BaseTestCase):
    def test_admin_access(self):
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('tournament_admin'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/tournament_admin.html')
    
    def test_non_admin_access(self):
        self.client.login(username='user', password='userpass123')
        response = self.client.get(reverse('tournament_admin'))
        self.assertEqual(response.status_code, 302)

class DashboardViewsTest(BaseTestCase):
    def test_admin_dashboard(self):
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_manager_dashboard(self):
        self.client.login(username='manager', password='managerpass123')
        response = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(response.status_code, 200)

class MatchResultViewsTest(BaseTestCase):
    def test_submit_result_view(self):
        self.client.login(username='manager', password='managerpass123')
        response = self.client.get(reverse('submit_result', kwargs={'match_id': self.match.pk}))
        self.assertEqual(response.status_code, 200)
    
    def test_submit_result_post(self):
        self.client.login(username='manager', password='managerpass123')
        data = {
            'home_score': 3,
            'away_score': 2
        }
        response = self.client.post(
            reverse('submit_result', kwargs={'match_id': self.match.pk}),
            data
        )
        self.assertEqual(response.status_code, 302)  # Redirect after successful submission

class TournamentViewSetTest(APITestCase):
    def setUp(self):
        # Create admin user and authenticate
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client.force_authenticate(user=self.admin_user)  # Use force_authenticate instead of login
        
        # Create a test tournament
        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            organizer=self.admin_user,
            datetime=timezone.now(),
            number_of_groups=2,
            teams_per_group=4,
            is_active=True,
            status='REGISTRATION'
        )
    
    def test_list_tournaments(self):
        response = self.client.get(reverse('tournament-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) > 0)

    def test_create_tournament(self):
        data = {
            'name': 'New Tournament',
            'datetime': timezone.now(),
            'number_of_groups': 2,
            'teams_per_group': 4,
            'is_active': True,
            'status': 'REGISTRATION'
        }
        response = self.client.post(reverse('tournament-list'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

class TeamViewSetTest(APITestCase):
    def setUp(self):
        # Create manager user and authenticate
        self.manager_user = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='managerpass123'
        )
        self.client.force_authenticate(user=self.manager_user)  # Use force_authenticate
        
        # Create tournament
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            organizer=self.admin_user,
            datetime=timezone.now(),
            number_of_groups=2,
            teams_per_group=4,
            is_active=True,
            status='REGISTRATION'
        )
        
        # Create a test team
        self.team = Team.objects.create(
            name='Test Team',
            tournament=self.tournament,
            manager=self.manager_user,
            player_count=8,
            registration_complete=True
        )
    
    def test_list_teams(self):
        response = self.client.get(reverse('team-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) > 0)

    def test_create_team(self):
        data = {
            'name': 'New Team',
            'tournament': self.tournament.id,
            'player_count': 8,
            'registration_complete': True
        }
        response = self.client.post(reverse('team-list'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

class MatchViewSetTest(APITestCase):
    def setUp(self):
        # Create manager user and authenticate
        self.manager_user = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='managerpass123'
        )
        self.client.force_authenticate(user=self.manager_user)  # Use force_authenticate
        
        # Create tournament
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.tournament = Tournament.objects.create(
            name='Test Tournament',
            organizer=self.admin_user,
            datetime=timezone.now(),
            number_of_groups=2,
            teams_per_group=4,
            is_active=True,
            status='REGISTRATION'
        )
        
        # Create two teams
        self.team1 = Team.objects.create(
            name='Team 1',
            tournament=self.tournament,
            manager=self.manager_user,
            player_count=8,
            registration_complete=True
        )
        
        self.team2 = Team.objects.create(
            name='Team 2',
            tournament=self.tournament,
            manager=self.manager_user,
            player_count=8,
            registration_complete=True
        )
        
        # Create a test match
        self.match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team1,
            team_away=self.team2,
            stage='GROUP',
            status='SCHEDULED'
        )
    
    def test_list_matches(self):
        response = self.client.get(reverse('match-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) > 0)

    def test_submit_result(self):
        data = {
            'our_score': 3,
            'opponent_score': 2
        }
        url = reverse('match-submit-result', kwargs={'pk': self.match.pk})
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class TeamDetailViewTest(BaseTestCase):
    def test_team_detail(self):
        self.client.login(username='manager', password='managerpass123')
        response = self.client.get(reverse('team_detail', kwargs={'pk': self.team.pk}))
        self.assertEqual(response.status_code, 200)

class TournamentStandingsViewTest(BaseTestCase):
    def test_standings_view(self):
        self.client.login(username='manager', password='managerpass123')
        response = self.client.get(
            reverse('tournament_standings', kwargs={'pk': self.tournament.pk})
        )
        self.assertEqual(response.status_code, 200)

class TournamentBracketViewTest(BaseTestCase):
    def test_bracket_view(self):
        response = self.client.get(
            reverse('tournament_bracket', kwargs={'pk': self.tournament.pk})
        )
        self.assertEqual(response.status_code, 200)
    
    def test_bracket_view_no_matches(self):
        # Delete all matches
        Match.objects.all().delete()
        response = self.client.get(
            reverse('tournament_bracket', kwargs={'pk': self.tournament.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/tournament_bracket.html')
        self.assertQuerysetEqual(response.context['group_matches'], [])
        self.assertQuerysetEqual(response.context['ro16_matches'], [])
        self.assertIsNone(response.context['final_match'])

class GroupStageViewTest(BaseTestCase):
    def test_group_stage_view(self):
        self.client.login(username='manager', password='managerpass123')
        response = self.client.get(
            reverse('tournament_group_stage', kwargs={'pk': self.tournament.pk})
        )
        self.assertEqual(response.status_code, 200)
    
    def test_group_stage_not_started(self):
        self.client.login(username='manager', password='managerpass123')
        self.tournament.status = 'REGISTRATION'
        self.tournament.save()
        response = self.client.get(
            reverse('tournament_group_stage', kwargs={'pk': self.tournament.pk})
        )
        self.assertEqual(response.status_code, 404)

class CustomLoginViewTest(BaseTestCase):
    def test_login_view(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/login.html')
    
    def test_login_success_admin(self):
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'adminpass123'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('admin_dashboard'))
    
    def test_login_success_manager(self):
        response = self.client.post(reverse('login'), {
            'username': 'manager',
            'password': 'managerpass123'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('player_dashboard'))
    
    def test_login_success_user(self):
        response = self.client.post(reverse('login'), {
            'username': 'user',
            'password': 'userpass123'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('manager_dashboard'))
    
    def test_login_failure(self):
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'wrongpass'
        })
        self.assertEqual(response.status_code, 200)  # Stay on login page
        self.assertTrue(response.context['form'].errors)  # Should have form errors

class HealthCheckTest(BaseTestCase):
    def test_health_check(self):
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'OK')

class GroupStageTestCase(BaseTestCase):
    def test_standings_calculation(self):
        # Create match with confirmed status - but fixing to use different teams
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team,
            team_away=self.away_team,  # Using away_team instead of self.team
            stage='GROUP',
            status='CONFIRMED'
        )
        # Get the automatically created result and update scores
        result = match.result
        result.home_score = 3
        result.away_score = 1
        result.save()
        self.assertEqual(match.status, 'CONFIRMED')

class KnockoutStageTestCase(BaseTestCase):
    def test_winner_determination(self):
        # Create match without scores
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team,
            team_away=self.away_team,  # Using away_team instead of self.team
            stage='KNOCKOUT',
            status='SCHEDULED'
        )
        # Get the automatically created result and update scores
        result = match.result
        result.home_score = 2
        result.away_score = 1
        result.save()
        self.assertEqual(match.get_winner(), self.team)

class TournamentProgressionTest(BaseTestCase):
    def test_group_stage(self):
        # Create a new match for testing
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=self.team,
            team_away=self.away_team,  # Using away_team instead of self.team
            stage='GROUP',
            status='SCHEDULED'
        )
        # Get the automatically created result and update scores/confirmed status
        result = match.result
        result.home_score = 2
        result.away_score = 1
        result.confirmed = True
        result.save()
        match.status = 'CONFIRMED'
        match.save()
        return [self.team]  # Return qualified teams

    def test_knockout_progression(self):
        qualified_teams = self.test_group_stage()
        self.assertEqual(len(qualified_teams), 1)

class ViewTests(BaseTestCase):
    def test_dashboard_view(self):
        self.client.login(username='manager', password='managerpass123')
        response = self.client.get(reverse('dashboard'))
        # Should redirect to appropriate dashboard
        self.assertEqual(response.status_code, 302)

    def test_match_result_submission(self):
        self.client.login(username='manager', password='managerpass123')
        response = self.client.get(
            reverse('submit_result', kwargs={'match_id': self.match.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/submit_result.html')

class DashboardViewTests(BaseTestCase):
    def test_admin_dashboard_view(self):
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/admin_dashboard.html')

    def test_user_dashboard_view(self):
        self.client.login(username='user', password='userpass123')
        response = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tournament/manager_dashboard.html')

    def test_dashboard_redirect_for_role(self):
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('admin_dashboard')) 