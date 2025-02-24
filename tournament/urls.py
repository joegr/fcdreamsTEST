from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SignUpView, TournamentAdminView,
    TournamentViewSet, TeamViewSet,
    MatchViewSet, ResultViewSet,
    ManagerDashboardView, TeamDetailView,
    MatchResultSubmissionView, MatchResultConfirmationView,
    TournamentStandingsView, TournamentBracketView,
    GroupStageView, UserDashboardView,
    CustomLoginView, AdminDashboardView,
    PlayerDashboardView, submit_result, bracket_image,
    DashboardView, SubmitResultView, health_check
)
from django.contrib.auth import views as auth_views

# Set up DRF router
router = DefaultRouter()
router.register(r'tournaments', TournamentViewSet, basename='tournament')
router.register(r'teams', TeamViewSet, basename='team')
router.register(r'matches', MatchViewSet, basename='match')
router.register(r'results', ResultViewSet, basename='result')

urlpatterns = [
    # Authentication paths
    path('signup/', SignUpView.as_view(), name='signup'),
    
    # Admin paths
    path('tournament-admin/', TournamentAdminView.as_view(), name='tournament_admin'),
    
    # Manager paths
    path('dashboard/', ManagerDashboardView.as_view(), name='manager_dashboard'),
    path('team/<int:pk>/', TeamDetailView.as_view(), name='team_detail'),
    
    # Match paths
    path('match/<int:pk>/submit/', MatchResultSubmissionView.as_view(), name='submit_result'),
    path('match/<int:pk>/confirm/', MatchResultConfirmationView.as_view(), name='confirm_result'),
    
    # Tournament paths
    path('tournament/<int:pk>/standings/', TournamentStandingsView.as_view(), name='tournament_standings'),
    path('tournament/<int:pk>/bracket/', TournamentBracketView.as_view(), name='tournament_bracket'),
    path('tournament/<int:pk>/group-stage/', 
         GroupStageView.as_view(), 
         name='tournament_group_stage'),
    
    # User paths
    path('dashboard/', UserDashboardView.as_view(), name='user_dashboard'),
    
    # Dashboard paths
    path('admin-dashboard/', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('manager-dashboard/', ManagerDashboardView.as_view(), name='manager_dashboard'),
    path('player-dashboard/', PlayerDashboardView.as_view(), name='player_dashboard'),
    
    # API paths
    path('api/', include(router.urls)),
    path('api-auth/', include('rest_framework.urls')),
    
    # Override the default login view
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    
    # New paths
    path('match/<int:match_id>/submit/', submit_result, name='submit_result'),
    path('tournament/<int:tournament_id>/bracket/image/', bracket_image, name='bracket_image'),
    
    # Suggested paths
    path('', DashboardView.as_view(), name='dashboard'),
    path('submit-result/', SubmitResultView.as_view(), name='submit-result'),
    path('health/', health_check, name='health_check'),
]