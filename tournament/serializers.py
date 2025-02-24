from rest_framework import serializers
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
    home_score = serializers.SerializerMethodField()
    away_score = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = ['id', 'tournament', 'team_home', 'team_away', 'match_date',
                 'home_score', 'away_score', 'stage', 'status']

    def get_home_score(self, obj):
        return obj.result.home_score if hasattr(obj, 'result') else 0

    def get_away_score(self, obj):
        return obj.result.away_score if hasattr(obj, 'result') else 0

class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = [
            'id', 
            'match',
            'team_home',
            'team_away', 
            'home_score',
            'away_score',
            'home_confirmed',
            'away_confirmed',
            'confirmed',
            'extra_time',
            'penalties'
        ]
    
    def validate(self, data):
        if data.get('penalties') and not data.get('extra_time'):
            raise serializers.ValidationError(
                "Penalties can only occur after extra time"
            )
        return data

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