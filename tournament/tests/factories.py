import factory
from django.utils import timezone
from django.contrib.auth.models import User
from tournament.models import Match, Tournament, Team
from factory.django import DjangoModelFactory

class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f'user_{n}')
    email = factory.LazyAttribute(lambda o: f'{o.username}@example.com')

class TournamentFactory(DjangoModelFactory):
    class Meta:
        model = Tournament
    
    name = factory.Sequence(lambda n: f'Tournament {n}')
    datetime = factory.LazyFunction(timezone.now)
    number_of_groups = 8
    teams_per_group = 4

class TeamFactory(DjangoModelFactory):
    class Meta:
        model = Team
    
    name = factory.Sequence(lambda n: f'Team {n}')
    manager = factory.SubFactory(UserFactory)
    tournament = factory.SubFactory(TournamentFactory)
    registration_complete = True

class MatchFactory(DjangoModelFactory):
    class Meta:
        model = Match
    
    tournament = factory.SubFactory(TournamentFactory)
    team_home = factory.SubFactory(TeamFactory)
    team_away = factory.SubFactory(TeamFactory)
    stage = 'GROUP'
    status = 'SCHEDULED'
    match_date = factory.LazyFunction(timezone.now)
    slug = factory.LazyAttribute(lambda o: f"{o.stage}-{o.team_home.id}-{o.team_away.id}")