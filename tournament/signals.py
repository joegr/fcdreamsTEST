from django.db.models.signals import post_save
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

logger = logging.getLogger(__name__)

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
    """Create a Result record when a Match is created"""
    if created:
        Result.objects.create(match=instance)

@receiver(post_save, sender=Result)
def handle_result_confirmation(sender, instance, **kwargs):
    """Trigger tournament service to handle result confirmation"""
    try:
        tournament_service = TournamentService(instance.match.tournament)
        tournament_service.handle_result_confirmation(instance)
    except Exception as e:
        logger.error(f"Error handling result confirmation: {e}")