from django import forms
from .models import Manager, Tournament, Team, Match, Result

class ManagerSignUpForm(forms.ModelForm):
    class Meta:
        model = Manager
        fields = ['user', 'psn_id']

class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'datetime', 'number_of_groups', 'teams_per_group', 'is_active']

class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'manager', 'email', 'contact_phone', 'registration_code', 'tournament', 'player_count']

class MatchForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ['tournament', 'match_id', 'team1', 'team2', 'match_date', 'confirmed']

class ResultForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = ['match', 'team', 'score', 'opponent_score', 'score_img', 'confirmed']