from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from .models import Tournament, Team, Match, Result

class TournamentSerializer(serializers.ModelSerializer):
    team_count = serializers.SerializerMethodField()
    stage = serializers.SerializerMethodField()
    
    class Meta:
        model = Tournament
        fields = ['id', 'name', 'datetime', 'number_of_groups', 'teams_per_group', 
                 'status', 'team_count', 'stage']

    def get_team_count(self, obj):
        return obj.team_set.filter(registration_complete=True).count()
        
    def get_stage(self, obj):
        if obj.status == 'KNOCKOUT':
            match_count = Match.objects.filter(
                tournament=obj,
                status__in=['SCHEDULED', 'PENDING'],
                stage__in=['QUARTER', 'SEMI', 'FINAL']
            ).count()
            if match_count == 2:
                return 'Semi Finals'
            elif match_count == 1:
                return 'Final'
        return obj.get_status_display()

class MatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = ['id', 'tournament', 'team_home', 'team_away', 'match_date',
                 'home_score', 'away_score', 'stage', 'status']

class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ['id', 'match', 'submitting_team', 'home_score', 'away_score']
        
    def validate(self, data):
        submitting_team = self.context['request'].user.team_set.first()
        match = data['match']
        
        if not submitting_team:
            raise ValidationError({
                "non_field_errors": ["You must be registered as a team manager"]
            })
            
        if submitting_team not in [match.team_home, match.team_away]:
            raise ValidationError({
                "non_field_errors": [f"Your team is not playing in this match"]
            })
            
        if match.status not in ['SCHEDULED', 'PENDING']:
            raise ValidationError({
                "non_field_errors": [f"Match cannot accept new results"]
            })
            
        if Result.objects.filter(match=match, submitting_team=submitting_team).exists():
            raise ValidationError({
                "non_field_errors": ["Result already submitted"]
            })
        
        data['submitting_team'] = submitting_team
        return data

    def validate_home_score(self, value):
        if value < 0:
            raise ValidationError("Score cannot be negative")
        return value

    def validate_away_score(self, value):
        if value < 0:
            raise ValidationError("Score cannot be negative")
        return value

class MatchResultSerializer(serializers.Serializer):
    our_score = serializers.IntegerField(min_value=0)
    opponent_score = serializers.IntegerField(min_value=0)
    extra_time = serializers.BooleanField(default=False)
    penalties = serializers.BooleanField(default=False)

    def validate(self, data):
        if data['penalties'] and not data['extra_time']:
            raise serializers.ValidationError("Penalties can only occur after extra time")
        return data

class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'name', 'player_count', 'registration_complete']