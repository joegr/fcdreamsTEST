from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, TemplateView, DetailView, ListView, View
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Count, Q
from .models import Tournament, Team, Match, Result
from .serializers import (
    TournamentSerializer,
    TeamSerializer,
    MatchSerializer,
    MatchResultSerializer,
    ResultSerializer
)
from .services.group_stage import GroupStageService
from .services.knockout import KnockoutService
from .tasks import validate_team_registration
from .services.tournament import TournamentService
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden, HttpResponse
from django.contrib import messages
from django.urls import reverse
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.db import models
from django.contrib.auth.views import LoginView
from django.utils import timezone
from django.urls import reverse
import matplotlib.pyplot as plt
import io
from django.core.serializers.json import DjangoJSONEncoder
import json
from rest_framework import serializers
from heapq import heappush, heappop
from dataclasses import dataclass
from typing import List
import itertools
from django.db import connection
from django.http import Http404

class SignUpView(CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        
        # Get the first active tournament
        tournament = Tournament.objects.filter(is_active=True).first()
        if tournament:
            # Create a team with user's name + FC
            team_name = f"{user.username} FC"
            Team.objects.create(
                name=team_name,
                manager=user,
                tournament=tournament,
                player_count=0,
                registration_complete=False
            )
        
        return response

@dataclass
class TeamCard:
    team: Team
    points: int = 0
    goal_difference: int = 0
    goals_for: int = 0
    goals_against: int = 0
    matches_played: int = 0
    entry_count: int = 0  # For stable sorting
    REMOVED = '<removed>'  # Placeholder for removed teams
    
    def __post_init__(self):
        self.entry_count = next(itertools.count())
    
    def __lt__(self, other):
        # For heapq sorting: higher points/goals first (use negative)
        return (-self.points, -self.goal_difference, -self.goals_for, 
                self.entry_count) < (-other.points, -other.goal_difference, 
                -other.goals_for, other.entry_count)

class TournamentStandings:
    def __init__(self):
        self.team_heap = []  # List of entries arranged in a heap
        self.entry_finder = {}  # Mapping of teams to entries
        self.counter = itertools.count()  # Unique sequence count
        
    def add_team(self, team_card: TeamCard):
        'Add a new team or update existing team stats'
        if team_card.team in self.entry_finder:
            self.remove_team(team_card.team)
        entry = team_card
        self.entry_finder[team_card.team] = entry
        heappush(self.team_heap, entry)
    
    def remove_team(self, team: Team):
        'Mark an existing team as REMOVED'
        entry = self.entry_finder.pop(team)
        entry.team = TeamCard.REMOVED
    
    def pop_team(self):
        'Remove and return the highest ranked team'
        while self.team_heap:
            team_card = heappop(self.team_heap)
            if team_card.team is not TeamCard.REMOVED:
                del self.entry_finder[team_card.team]
                return team_card
        raise KeyError('pop from an empty tournament standings')

class TournamentAdminView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'tournament/tournament_admin.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournaments = Tournament.objects.all()
        
        tournament_cards = []
        for tournament in tournaments:
            standings = TournamentStandings()
            
            # Get all matches in tournament
            matches = Match.objects.filter(
                tournament=tournament,
                status='CONFIRMED'
            ).select_related('team_home', 'team_away')
            
            # Process all teams
            team_stats = {}
            for match in matches:
                for team, is_home in [(match.team_home, True), (match.team_away, False)]:
                    if team not in team_stats:
                        team_stats[team] = TeamCard(team=team)
                    
                    card = team_stats[team]
                    card.matches_played += 1
                    
                    if is_home:
                        card.goals_for += match.home_score or 0
                        card.goals_against += match.away_score or 0
                        if match.home_score > match.away_score:
                            card.points += 3
                        elif match.home_score == match.away_score:
                            card.points += 1
                    else:
                        card.goals_for += match.away_score or 0
                        card.goals_against += match.home_score or 0
                        if match.away_score > match.home_score:
                            card.points += 3
                        elif match.home_score == match.away_score:
                            card.points += 1
                            
                    card.goal_difference = card.goals_for - card.goals_against
            
            # Add all teams to heap
            for card in team_stats.values():
                standings.add_team(card)
            
            # Extract sorted teams
            sorted_teams = []
            while standings.team_heap:
                try:
                    sorted_teams.append(standings.pop_team())
                except KeyError:
                    break
            
            tournament_cards.append({
                'tournament': tournament,
                'teams': sorted_teams,
                'total_matches': Match.objects.filter(tournament=tournament).count(),
                'completed_matches': matches.count()
            })
        
        context['tournament_cards'] = tournament_cards
        return context

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, "You don't have permission to access this page")
            return redirect('manager_dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            # Get all teams without a tournament or in inactive tournaments
            available_teams = Team.objects.filter(
                Q(tournament__isnull=True) | 
                Q(tournament__is_active=False)
            ).filter(
                registration_complete=True  # Only include teams that have completed registration
            )
            
            context['available_teams_count'] = available_teams.count()
            context['can_create_tournament'] = available_teams.count() >= 8
            context['available_teams'] = available_teams
            
            # Get active tournaments
            context['tournaments'] = Tournament.objects.filter(is_active=True)
            context['pending_teams'] = Team.objects.filter(
                player_count__lt=8,
                registration_complete=False
            )
            context['pending_matches'] = Match.objects.filter(
                status='PENDING'
            )
            
        except Exception as e:
            messages.error(self.request, f"Error loading dashboard: {str(e)}")
            context['error'] = str(e)
            
        return context

    def post(self, request, *args, **kwargs):
        try:
            if 'create_tournament' in request.POST:
                # Get eligible teams
                available_teams = Team.objects.filter(
                    Q(tournament__isnull=True) | 
                    Q(tournament__is_active=False)
                ).filter(
                    registration_complete=True
                )
                
                if available_teams.count() >= 8:
                    # Create new tournament
                    tournament = Tournament.objects.create(
                        name=f"Tournament {Tournament.objects.count() + 1}",
                        organizer=request.user,
                        datetime=timezone.now(),
                        number_of_groups=2,
                        teams_per_group=4,
                        is_active=True,
                        status='REGISTRATION'
                    )
                    
                    # Assign first 8 teams to this tournament
                    teams_to_assign = available_teams[:8]
                    teams_to_assign.update(tournament=tournament)
                    
                    # Generate all matches in pending status
                    group_service = GroupStageService(tournament)
                    group_service.generate_groups()
                    group_service.generate_matches()
                    
                    messages.success(
                        request, 
                        f"Tournament created successfully with {teams_to_assign.count()} teams!"
                    )
                else:
                    messages.error(
                        request, 
                        f"Not enough eligible teams. Need 8, but only have {available_teams.count()}"
                    )
                    
        except Exception as e:
            messages.error(request, f"Error creating tournament: {str(e)}")
            
        return redirect('tournament_admin')

class TournamentViewSet(viewsets.ModelViewSet):

    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'destroy']:
            return [IsAdminUser()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def start_group_stage(self, request, pk=None):
        tournament = self.get_object()
        if tournament.status != 'REGISTRATION':
            return Response(
                {"error": "Tournament must be in registration status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        group_service = GroupStageService(tournament)
        try:
            group_service.generate_groups()
            group_service.generate_matches()
            tournament.status = 'GROUP_STAGE'
            tournament.save()
            return Response({"status": "Group stage started"})
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def start_knockout_stage(self, request, pk=None):
        tournament = self.get_object()
        if tournament.status != 'GROUP_STAGE':
            return Response(
                {"error": "Tournament must be in group stage"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        knockout_service = KnockoutService(tournament)
        try:
            knockout_service.generate_round_of_16()
            tournament.status = 'KNOCKOUT'
            tournament.save()
            return Response({"status": "Knockout stage started"})
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def group_info(self, request, pk=None):
        tournament = self.get_object()
        if tournament.status not in ['GROUP_STAGE', 'KNOCKOUT']:
            return Response(
                {"error": "Tournament is not in or past group stage"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        group_service = GroupStageService(tournament)
        standings = group_service.get_group_standings()
        
        return Response({
            "standings": standings,
            "groups": {
                group_num: [team.id for team in teams] 
                for group_num, teams in group_service.groups.items()
            }
        })

class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Team.objects.filter(manager=self.request.user)

    def perform_create(self, serializer):
        # Check if user already has a team
        if Team.objects.filter(manager=self.request.user).exists():
            raise serializers.ValidationError({"detail": "You already have a team"})
        
        # Get active tournament
        tournament = Tournament.objects.filter(is_active=True).first()
        if not tournament:
            raise serializers.ValidationError({"detail": "No active tournament available"})
            
        serializer.save(
            manager=self.request.user,
            tournament=tournament
        )

    @action(detail=True, methods=['post'])
    def complete_registration(self, request, pk=None):
        team = self.get_object()
        task = validate_team_registration.delay(team.id)
        return Response({'task_id': task.id})

class MatchViewSet(viewsets.ModelViewSet):
    queryset = Match.objects.all()
    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post'], url_path='submit-result')
    def submit_result(self, request, pk=None):
        match = self.get_object()
        serializer = MatchResultSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the submitting team
        team = Team.objects.filter(manager=request.user).first()
        if not team or team not in [match.team_home, match.team_away]:
            return Response(
                {"error": "Not authorized to submit result for this match"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get or create result
        try:
            result = Result.objects.get(match=match)
            
            # Update the result based on which team is submitting
            if team == match.team_home:
                result.home_score = serializer.validated_data.get('home_score', result.home_score)
                result.away_score = serializer.validated_data.get('away_score', result.away_score)
                result.home_confirmed = True
            else:
                result.home_score = serializer.validated_data.get('home_score', result.home_score)
                result.away_score = serializer.validated_data.get('away_score', result.away_score)
                result.away_confirmed = True
                
            result.save()
            
        except Result.DoesNotExist:
            # This shouldn't happen as results are created with matches
            return Response(
                {"error": "Match result not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({"status": "Result submitted successfully"}, status=status.HTTP_200_OK)

class ResultViewSet(viewsets.ModelViewSet):
    queryset = Result.objects.all()
    serializer_class = ResultSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        team = self.request.user.team_set.first()
        match = serializer.validated_data.get('match')
        
        if team == match.team_home:
            serializer.save(home_confirmed=True)
        elif team == match.team_away:
            serializer.save(away_confirmed=True)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def confirm_result(self, request, pk=None):
        result = self.get_object()
        team = request.user.team_set.first()
        match = result.match
        
        if team not in [match.team_home, match.team_away]:
            return Response(
                {"error": "Not authorized to confirm this match result"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Set the appropriate confirmation flag
        if team == match.team_home:
            result.home_confirmed = True
        else:
            result.away_confirmed = True
            
        result.save()
        
        # Update match status if both teams have confirmed results
        if result.home_confirmed and result.away_confirmed:
            match.status = 'CONFIRMED'
            match.save()
        
        return Response({"status": "Result confirmed"})

class AdminDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'tournament/admin_dashboard.html'
    
    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        if self.raise_exception or self.request.user.is_authenticated:
            return HttpResponseForbidden()
        return redirect('login')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tournaments'] = Tournament.objects.all()
        context['pending_teams'] = Team.objects.filter(
            player_count__lt=8
        )
        context['pending_matches'] = Match.objects.filter(
            status='PENDING'
        )
        return context

class ManagerDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'tournament/manager_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['managed_teams'] = Team.objects.filter(manager=self.request.user)
        context['upcoming_matches'] = Match.objects.filter(
            Q(team_home__manager=self.request.user) | 
            Q(team_away__manager=self.request.user),
            status='SCHEDULED'
        )
        context['pending_results'] = Match.objects.filter(
            Q(team_home__manager=self.request.user) | 
            Q(team_away__manager=self.request.user),
            status='PENDING'
        )
        return context

class PlayerDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'tournament/player_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get the user's team
        context['team'] = Team.objects.filter(manager=user).first()
        
        if context['team']:
            # Get upcoming matches
            context['upcoming_matches'] = Match.objects.filter(
                models.Q(team_home=context['team']) | 
                models.Q(team_away=context['team']),
                status='SCHEDULED'
            ).order_by('match_date')
            
            # Get recent results
            context['recent_matches'] = Match.objects.filter(
                models.Q(team_home=context['team']) | 
                models.Q(team_away=context['team']),
                status='CONFIRMED'
            ).order_by('-match_date')[:5]
            
            # Get tournament info
            context['tournament'] = context['team'].tournament
            
        return context

class TeamDetailView(LoginRequiredMixin, DetailView):
    model = Team
    template_name = 'tournament/team_detail.html'
    context_object_name = 'team'

    def get_queryset(self):
        return Team.objects.filter(manager=self.request.user)

class MatchResultSubmissionView(LoginRequiredMixin, DetailView):
    model = Match
    template_name = 'tournament/submit_result.html'
    context_object_name = 'match'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = self.get_object()
        tournament = match.tournament

        # Get all knockout matches
        knockout_matches = Match.objects.filter(
            tournament=tournament,
            stage__in=['SEMI', 'FINAL']
        ).select_related('team_home', 'team_away')

        # Prepare tournament data for Chart.js
        tournament_data = {
            'teams': [],
            'matches': []
        }

        for m in knockout_matches:
            match_data = {
                'stage': m.stage,
                'team_home': m.team_home.name if m.team_home else 'TBD',
                'team_away': m.team_away.name if m.team_away else 'TBD',
                'status': m.status,
            }
            if m.status == 'CONFIRMED':
                match_data.update({
                    'home_score': m.home_score,
                    'away_score': m.away_score
                })
            tournament_data['matches'].append(match_data)
            if m.team_home and m.team_home.name not in tournament_data['teams']:
                tournament_data['teams'].append(m.team_home.name)
            if m.team_away and m.team_away.name not in tournament_data['teams']:
                tournament_data['teams'].append(m.team_away.name)

        context['tournament_data'] = json.dumps(tournament_data, cls=DjangoJSONEncoder)
        return context

class MatchResultConfirmationView(LoginRequiredMixin, DetailView):
    model = Match
    template_name = 'tournament/confirm_result.html'
    context_object_name = 'match'

    def post(self, request, *args, **kwargs):
        match = self.get_object()
        team = request.user.team_set.first()

        if not team or team not in [match.team_home, match.team_away]:
            return HttpResponseForbidden("Not authorized to confirm result for this match")

        result = get_object_or_404(Result, match=match, submitting_team=team)
        
        try:
            result.confirmed = True
            result.save()

            # Check if both teams have confirmed
            if match.results.filter(confirmed=True).count() == 2:
                match.status = 'CONFIRMED'
                match.save()
                messages.success(request, "Match result confirmed")
            else:
                messages.info(request, "Result confirmed. Waiting for opponent confirmation")
            
            return redirect('manager_dashboard')
        except Exception as e:
            messages.error(request, f"Error confirming result: {str(e)}")
            return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = self.get_object()
        team = self.request.user.team_set.first()
        
        context['result'] = get_object_or_404(
            Result,
            match=match,
            submitting_team__in=[match.team_home, match.team_away]
        )
        context['is_home_team'] = team == match.team_home
        
        return context

class TournamentStandingsView(LoginRequiredMixin, DetailView):
    model = Tournament
    template_name = 'tournament/standings.html'
    context_object_name = 'tournament'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournament = self.get_object()
        
        # Get all teams for this tournament
        context['teams'] = Team.objects.filter(
            tournament=tournament
        ).order_by('-registration_complete', '-player_count')
        
        return context

class TournamentBracketView(DetailView):
    model = Tournament
    template_name = 'tournament/tournament_bracket.html'
    context_object_name = 'tournament'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournament = self.get_object()

        # Get matches organized by stage
        context['group_matches'] = Match.objects.filter(
            tournament=tournament,
            stage='GROUP'
        ).order_by('match_date')

        context['ro16_matches'] = Match.objects.filter(
            tournament=tournament,
            stage='RO16'
        ).order_by('match_date')

        context['quarter_matches'] = Match.objects.filter(
            tournament=tournament,
            stage='QUARTER'
        ).order_by('match_date')

        context['semi_matches'] = Match.objects.filter(
            tournament=tournament,
            stage='SEMI'
        ).order_by('match_date')

        context['final_match'] = Match.objects.filter(
            tournament=tournament,
            stage='FINAL'
        ).first()

        return context

class GroupStageView(LoginRequiredMixin, DetailView):
    """Display group stage standings and matches"""
    model = Tournament
    template_name = 'tournament/group_stage.html'
    context_object_name = 'tournament'

    def get_object(self, queryset=None):
        tournament = super().get_object(queryset)
        if tournament.status == 'REGISTRATION':
            raise Http404("Group stage not started yet")
        return tournament

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournament = self.get_object()
        service = GroupStageService(tournament)
        
        context.update({
            'groups': service.get_group_standings(),
            'matches': Match.objects.filter(
                tournament=tournament,
                stage='GROUP'
            ).select_related(
                'team_home',
                'team_away', 
                'result'
            ).order_by('match_date')
        })
        
        return context

class UserDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'tournament/user_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get teams managed by the user
        context['teams'] = Team.objects.filter(manager=self.request.user)
        # Get matches for teams managed by the user
        context['matches'] = Match.objects.filter(
            Q(team_home__manager=self.request.user) | 
            Q(team_away__manager=self.request.user)
        )
        context['tournaments'] = Tournament.objects.filter(is_active=True)
        return context

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    
    def get_success_url(self):
        user = self.request.user
        if user.is_staff:
            return reverse('admin_dashboard')
        elif Team.objects.filter(manager=user).exists():
            return reverse('player_dashboard')
        return reverse('manager_dashboard')

def generate_bracket_image(tournament):
    fig, ax = plt.figure(figsize=(12, 8)), plt.axes()
    ax.set_axis_off()
    
    # Get matches by stage
    semifinals = Match.objects.filter(tournament=tournament, stage='SEMI')
    final = Match.objects.filter(tournament=tournament, stage='FINAL').first()
    
    # Draw semifinals
    y_positions = [2, 6]
    for i, match in enumerate(semifinals):
        ax.text(0.1, y_positions[i], f"{match.team_home.name if match.team_home else 'TBD'}")
        ax.text(0.1, y_positions[i]-0.5, f"{match.team_away.name if match.team_away else 'TBD'}")
        if match.status == 'CONFIRMED':
            ax.text(0.3, y_positions[i]-0.25, f"{match.home_score} - {match.away_score}")
    
    # Draw final
    if final:
        ax.text(0.6, 4, f"{final.team_home.name if final.team_home else 'TBD'}")
        ax.text(0.6, 3.5, f"{final.team_away.name if final.team_away else 'TBD'}")
        if final.status == 'CONFIRMED':
            ax.text(0.8, 3.75, f"{final.home_score} - {final.away_score}")
    
    # Draw connecting lines
    ax.plot([0.25, 0.4], [2, 3.75], 'k-')
    ax.plot([0.25, 0.4], [6, 3.75], 'k-')
    ax.plot([0.4, 0.55], [3.75, 3.75], 'k-')
    
    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf

def submit_result(request, match_id):
    match = Match.objects.get(id=match_id)
    tournament = match.tournament
    
    if request.method == 'POST':
        serializer = ResultSerializer(data=request.POST, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return redirect('tournament_bracket', tournament_id=tournament.id)
    
    # Generate bracket visualization
    bracket_image = generate_bracket_image(tournament)
    response = HttpResponse(bracket_image.getvalue(), content_type='image/png')
    
    context = {
        'match': match,
        'tournament': tournament,
        'bracket_image_url': f'/tournament/{tournament.id}/bracket/image/'
    }
    return render(request, 'tournament/submit_result.html', context)

def bracket_image(request, tournament_id):
    tournament = Tournament.objects.get(id=tournament_id)
    bracket_image = generate_bracket_image(tournament)
    return HttpResponse(bracket_image.getvalue(), content_type='image/png')

class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.is_staff:
            return redirect('admin_dashboard')
        elif Team.objects.filter(manager=request.user).exists():
            return redirect('manager_dashboard')
        else:
            return redirect('user_dashboard')

class SubmitResultView(LoginRequiredMixin, CreateView):
    model = Result
    template_name = 'tournament/submit_result.html'
    fields = ['home_score', 'away_score']

    def get_success_url(self):
        return reverse('dashboard')

    def form_valid(self, form):
        match = get_object_or_404(Match, id=self.kwargs.get('match_id'))
        form.instance.match = match
        form.instance.team_home = match.team_home
        form.instance.team_away = match.team_away
        return super().form_valid(form)

class MatchResultView(LoginRequiredMixin, DetailView):
    """Handle match result submission and confirmation"""
    model = Match
    template_name = 'tournament/match_result.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = self.get_object()
        user_team = self.request.user.team_set.first()
        
        context.update({
            'user_team': user_team,
            'can_submit': match.status == 'SCHEDULED',
            'is_home_team': user_team == match.team_home,
            'result': match.result
        })
        
        return context
        
    def post(self, request, *args, **kwargs):
        match = self.get_object()
        user_team = request.user.team_set.first()
        
        if match.status != 'SCHEDULED':
            messages.error(request, "Match result cannot be submitted")
            return redirect('match_detail', pk=match.pk)
            
        try:
            score = int(request.POST['score'])
            if score < 0:
                raise ValueError("Score cannot be negative")
                
            result = match.result
            if user_team == match.team_home:
                result.home_score = score
                result.home_confirmed = True
            else:
                result.away_score = score  
                result.away_confirmed = True
            result.save()
            
            messages.success(request, "Result submitted successfully")
            return redirect('match_detail', pk=match.pk)
            
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('match_detail', pk=match.pk)

def health_check(request):
    try:
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return HttpResponse("OK", status=200)
    except Exception as e:
        return HttpResponse(str(e), status=500)