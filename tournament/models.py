from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.text import slugify
import uuid

class Manager(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    psn_id = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.user.username} ({self.psn_id})"

class Tournament(models.Model):
    slug = models.SlugField(
        unique=True, 
        editable=False,
        default=''
    )
    name = models.CharField(max_length=100)
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    datetime = models.DateTimeField()
    number_of_groups = models.IntegerField(default=2)
    teams_per_group = models.IntegerField(default=4)
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('REGISTRATION', 'Registration'),
            ('GROUP_STAGE', 'Group Stage'),
            ('KNOCKOUT', 'Knockout Stage'),
            ('COMPLETED', 'Completed')
        ],
        default='REGISTRATION'
    )

    def clean(self):
        if self.number_of_groups * self.teams_per_group < 2:
            raise ValidationError("Tournament must have at least 2 teams")

    def save(self, *args, **kwargs):
        if not self.slug:
            timestamp = timezone.now().strftime('%Y%m%d%H%M')
            unique_id = str(uuid.uuid4())[:8]
            self.slug = f"{timestamp}_tournament_{slugify(self.name)}_{unique_id}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Team(models.Model):
    slug = models.SlugField(
        unique=True, 
        editable=False,
        default=''
    )
    name = models.CharField(max_length=100)
    manager = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    player_count = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(14)
        ]
    )
    registration_complete = models.BooleanField(default=False)

    class Meta:
        unique_together = ['tournament', 'name']

    def clean(self):
        super().clean()
        if self.player_count < 0:
            raise ValidationError({"player_count": "Player count cannot be negative"})
        if self.player_count > 14:
            raise ValidationError({"player_count": "Team cannot have more than 14 players"})

    def update_player_count(self, increment=True):
        """
        Update player count and registration status.
        increment=True adds a player, False removes a player
        Returns True if update was successful, False otherwise.
        """
        new_count = self.player_count + (1 if increment else -1)
        
        # Validate new count
        if new_count < 0:
            raise ValueError("Cannot remove player: Team has no players")
        if new_count > 14:
            raise ValueError("Cannot add player: Team already has maximum players (14)")
            
        # Update count and status
        self.player_count = new_count
        self.registration_complete = 8 <= new_count <= 14
        self.save()

    def save(self, *args, **kwargs):
        if not self.slug:
            timestamp = timezone.now().strftime('%Y%m%d%H%M')
            unique_id = str(uuid.uuid4())[:8]
            self.slug = f"{timestamp}_team_{slugify(self.name)}_{unique_id}"
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.player_count} players)"

class Match(models.Model):
    slug = models.SlugField(
        unique=True, 
        editable=False,
        default=''
    )
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    team_home = models.ForeignKey(Team, related_name='home_matches', on_delete=models.CASCADE, blank=True, null=True)
    team_away = models.ForeignKey(Team, related_name='away_matches', on_delete=models.CASCADE, blank=True, null=True)
    match_date = models.DateTimeField()
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    stage = models.CharField(
        max_length=20,
        choices=[
            ('GROUP', 'Group Stage'),
            ('RO16', 'Round of 16'),
            ('QUARTER', 'Quarter Final'),
            ('SEMI', 'Semi Final'),
            ('FINAL', 'Final')
        ],
        default='GROUP',
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('SCHEDULED', 'Scheduled'),
            ('PENDING', 'Pending Confirmation'),
            ('CONFIRMED', 'Confirmed'),
            ('DISPUTED', 'Disputed')
        ],
        default='SCHEDULED'
    )
    extra_time = models.BooleanField(default=False)
    penalties = models.BooleanField(default=False)

    class Meta:
        unique_together = ['tournament', 'team_home', 'team_away', 'stage']

    def clean(self):
        if self.team_home == self.team_away:
            raise ValidationError("A team cannot play against itself")
        if self.team_home.tournament != self.tournament or self.team_away.tournament != self.tournament:
            raise ValidationError("Teams must belong to this tournament")

    def save(self, *args, **kwargs):
        if not self.slug:
            timestamp = timezone.now().strftime('%Y%m%d%H%M')
            unique_id = str(uuid.uuid4())[:8]
            home_name = self.team_home.name if self.team_home else 'tbd'
            away_name = self.team_away.name if self.team_away else 'tbd'
            self.slug = f"{timestamp}_match_{slugify(home_name)}_{slugify(away_name)}_{unique_id}"
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.team_home} vs {self.team_away}"

class Result(models.Model):
    slug = models.SlugField(
        unique=True, 
        editable=False,
        default=''
    )
    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name='result')
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    extra_time = models.BooleanField(default=False)
    penalties = models.BooleanField(default=False)
    home_team_confirmed = models.BooleanField(default=False)
    away_team_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            timestamp = timezone.now().strftime('%Y%m%d%H%M')
            unique_id = str(uuid.uuid4())[:8]
            self.slug = f"{timestamp}_result_{self.match.slug}_{unique_id}"
        super().save(*args, **kwargs)

    def confirm_result(self, team, score_data):
        """Confirm result for a team"""
        is_home = team == self.match.team_home
        if is_home:
            self.home_team_confirmed = True
            if not self.home_score:
                self.home_score = score_data['score']
        else:
            self.away_team_confirmed = True
            if not self.away_score:
                self.away_score = score_data['score']

        self.extra_time = score_data.get('extra_time', False)
        self.penalties = score_data.get('penalties', False)
        self.save()

        # If both teams confirmed and scores match, update match status
        if self.home_team_confirmed and self.away_team_confirmed:
            self.match.status = 'CONFIRMED'
            self.match.home_score = self.home_score
            self.match.away_score = self.away_score
            self.match.save()

    def __str__(self):
        return f"{self.match} - {self.match.team_home} vs {self.match.team_away}"