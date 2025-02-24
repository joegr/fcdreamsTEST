from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.text import slugify
import uuid
import random
import string
from django.conf import settings
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
import logging
import json
from datetime import datetime

# Create a custom tournament logger
tournament_logger = logging.getLogger('tournament.state')
tournament_logger.setLevel(logging.INFO)

# Add custom formatter for tournament events
class TournamentLogFormatter(logging.Formatter):
    def format(self, record):
        if hasattr(record, 'tournament_data'):
            record.msg = json.dumps({
                'timestamp': datetime.now().isoformat(),
                'event': record.event_type,
                'tournament': record.tournament_data,
                'details': record.msg
            })
        return super().format(record)

# Set up file handler
handler = logging.FileHandler('tournament_events.log')
handler.setFormatter(TournamentLogFormatter())
tournament_logger.addHandler(handler)

def get_system_user():
    """Get or create system user for orphaned teams"""
    system_user, _ = User.objects.get_or_create(
        username='system',
        defaults={
            'email': 'system@example.com',
            'is_active': False
        }
    )
    return system_user

def get_admin_user():
    """Get or create admin user for orphaned teams"""
    admin_user, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'is_staff': True,
            'is_superuser': True,
            'email': 'admin@example.com'
        }
    )
    if created:
        admin_user.set_password('admin123')  # Set a default password
        admin_user.save()
    return admin_user.id  # Return ID to avoid circular imports

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
    datetime = models.DateTimeField(default=timezone.now)
    start_date = models.DateTimeField(default=timezone.now)
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
    group_stage_complete = models.BooleanField(default=False)
    knockout_stage_complete = models.BooleanField(default=False)

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

    def log_state_change(self, event_type, details):
        """Log tournament state changes"""
        tournament_logger.info(
            details,
            extra={
                'event_type': event_type,
                'tournament_data': {
                    'id': self.id,
                    'name': self.name,
                    'status': self.status,
                    'teams': list(self.team_set.values_list('name', flat=True))
                }
            }
        )

@receiver(pre_save, sender=Tournament, dispatch_uid='log_tournament_update')
def log_tournament_update(sender, instance, **kwargs):
    if instance.id:  # Only log updates, not creation
        old_instance = Tournament.objects.get(id=instance.id)
        if old_instance.status != instance.status:
            instance.log_state_change(
                'STATUS_CHANGE',
                f"Tournament status changed from {old_instance.status} to {instance.status}"
            )


class Team(models.Model):
    slug = models.SlugField(
        unique=True, 
        editable=False,
        default=''
    )
    name = models.CharField(max_length=100)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    manager = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        default=get_admin_user
    )
    player_count = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(14)
        ]
    )
    registration_code = models.CharField(
        max_length=8,
        unique=True,
        blank=True,
        null=True  # Null when registration complete
    )
    registration_complete = models.BooleanField(default=False)
    registration_expires = models.DateTimeField(null=True, blank=True)
    strength_rating = models.IntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

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
        if not self.registration_code and not self.registration_complete:
            self.registration_code = self._generate_unique_code()
        super().save(*args, **kwargs)

    def _generate_unique_code(self):
        """Generate a unique registration code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not Team.objects.filter(registration_code=code).exists():
                return code

    def expire_registration(self):
        """Expire registration code"""
        self.registration_code = None
        self.registration_expires = None
        self.save()

    def __str__(self):
        return f"{self.name} ({self.player_count} players)"

class Match(models.Model):
    STAGE_CHOICES = [
        ('GROUP', 'Group Stage'),
        ('RO16', 'Round of 16'),
        ('QUARTER', 'Quarter Final'),
        ('SEMI', 'Semi Final'),
        ('FINAL', 'Final')
    ]
    
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('PENDING', 'Pending Confirmation'),
        ('CONFIRMED', 'Confirmed'),
        ('DISPUTED', 'Disputed')
    ]

    slug = models.SlugField(unique=True, editable=False, default='')
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    team_home = models.ForeignKey(Team, related_name='home_matches', on_delete=models.CASCADE)
    team_away = models.ForeignKey(Team, related_name='away_matches', on_delete=models.CASCADE)
    match_date = models.DateTimeField(default=timezone.now)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    dispute_reason = models.TextField(blank=True)
    group = models.CharField(max_length=1, null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if not self.slug:
            self.slug = f"{self.stage}-{self.team_home}-{self.team_away}"
        super().save(*args, **kwargs)
        
        # Result creation is now handled by the create_match_result signal

    def clean(self):
        if self.team_home == self.team_away:
            raise ValidationError("A team cannot play against itself")
        if self.team_home.tournament != self.tournament or self.team_away.tournament != self.tournament:
            raise ValidationError("Teams must belong to this tournament")

    class Meta:
        unique_together = ['tournament', 'team_home', 'team_away', 'stage']
        constraints = [
            models.CheckConstraint(
                check=~models.Q(team_home=models.F('team_away')),
                name='no_self_matches'
            )
        ]
        indexes = [
            models.Index(fields=['tournament', 'stage', 'group']),
        ]

    def __str__(self):
        return f"{self.stage}: {self.team_home} vs {self.team_away}"

    def log_match_result(self):
        """Log match results"""
        result = self.result
        self.tournament.log_state_change(
            'MATCH_COMPLETED',
            {
                'match_id': self.id,
                'stage': self.stage,
                'home_team': self.team_home.name,
                'away_team': self.team_away.name,
                'score': f"{result.home_score}-{result.away_score}",
                'winner': self.team_home.name if result.home_score > result.away_score else self.team_away.name
            }
        )

    def get_winner(self):
        """Get the winning team of the match"""
        if self.status != 'CONFIRMED':
            return None
        result = self.result
        if result.home_score > result.away_score:
            return self.team_home
        elif result.away_score > result.home_score:
            return self.team_away
        return None

    def get_group_points(self, team):
        """Get points for a team in this group match"""
        if self.status != 'CONFIRMED':
            return 0
        result = self.result
        if team == self.team_home:
            if result.home_score > result.away_score:
                return 3
            elif result.home_score == result.away_score:
                return 1
        elif team == self.team_away:
            if result.away_score > result.home_score:
                return 3
            elif result.home_score == result.away_score:
                return 1
        return 0

class Result(models.Model):
    match = models.OneToOneField(Match, on_delete=models.CASCADE)
    team_home = models.ForeignKey(Team, related_name='home_results', on_delete=models.CASCADE)
    team_away = models.ForeignKey(Team, related_name='away_results', on_delete=models.CASCADE)
    home_score = models.IntegerField(default=0)
    away_score = models.IntegerField(default=0)
    home_confirmed = models.BooleanField(default=False)
    away_confirmed = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)
    extra_time = models.BooleanField(default=False)
    penalties = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.home_confirmed and self.away_confirmed:
            self.confirmed = True
            # Update match status when both teams confirm
            self.match.status = 'CONFIRMED'
            self.match.home_score = self.home_score
            self.match.away_score = self.away_score
            self.match.save()
        else:
            self.confirmed = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.match} - {self.home_score}:{self.away_score}"

