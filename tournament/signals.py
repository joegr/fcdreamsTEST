from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from .models import Match, Result, Tournament
from .services.tournament import TournamentService
from pydantic import BaseModel, Field
from typing import List, Optional
import logging
import os
import json
from threading import Lock
from .services.notification import notify_team_for_confirmation, notify_match_confirmation

logger = logging.getLogger('tournament.state')

class SingletonGroupStageManager:
    _instance = None
    _instance_lock = Lock()
    _managers = {}
    _managers_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_manager(cls, tournament_id):
        with cls._managers_lock:
            if tournament_id not in cls._managers:
                from tournament.services.group_stage import GroupStageManager
                cls._managers[tournament_id] = GroupStageManager(tournament_id)
            return cls._managers[tournament_id]

    @classmethod
    def clear_manager(cls, tournament_id):
        with cls._managers_lock:
            if tournament_id in cls._managers:
                del cls._managers[tournament_id]
    
    @classmethod
    def cleanup_inactive_tournaments(cls):
        """Clean up managers for completed tournaments"""
        with cls._managers_lock:
            from .models import Tournament
            active_tournament_ids = set(
                Tournament.objects.filter(is_active=True).values_list('id', flat=True)
            )
            inactive_managers = [
                tid for tid in cls._managers.keys() 
                if tid not in active_tournament_ids
            ]
            for tid in inactive_managers:
                del cls._managers[tid]

# Create singleton instance
gsm_factory = SingletonGroupStageManager()

@receiver(post_save, sender=Match)
def create_match_result(sender, instance, created, **kwargs):
    """Create Result object when Match is created"""
    if created and not hasattr(instance, 'result'):
        Result.objects.create(
            match=instance,
            home_score=0,
            away_score=0,
            is_confirmed=False
        )
@receiver(post_save, sender=Match)
def handle_match_completion(sender, instance, **kwargs):
    """Handle match completion and logging"""
    if instance.status == 'CONFIRMED':
        # Log match result only
        instance.log_match_result()

@receiver(post_save, sender=Result)
def handle_result_confirmation(sender, instance, created, **kwargs):
    """Handle match result confirmation and tournament progression"""
    if not created and instance.home_team_confirmed and instance.away_team_confirmed:
        try:
            match = instance.match
            # Only process if match isn't already confirmed
            if match.status != 'CONFIRMED':
                match.status = 'CONFIRMED'
                match.home_score = instance.home_score
                match.away_score = instance.away_score
                match.save()
                
                # Notify both teams
                notify_match_confirmation(match)
                
                # Check tournament progression
                tournament_service = TournamentService(match.tournament)
                tournament_service.handle_result_confirmation(instance)
        except Exception as e:
            logger.error(f"Error handling result confirmation: {e}")
    elif not created and (instance.home_team_confirmed or instance.away_team_confirmed):
        # Notify other team to confirm
        match = instance.match
        if instance.home_team_confirmed:
            notify_team_for_confirmation(match.team_away)
        else:
            notify_team_for_confirmation(match.team_home)

@receiver(pre_save, sender=Match)
def validate_match(sender, instance, **kwargs):
    """Ensure that a team does not play against itself."""
    if instance.team_home == instance.team_away:
        raise ValueError("A team cannot play against itself")