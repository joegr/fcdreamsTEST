from typing import List, Dict
from django.db.models import Q
from datetime import timedelta
from django.utils import timezone
from ..models import Tournament, Team, Match
from .group_stage import GroupStageService

class KnockoutService:
    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        self.group_service = GroupStageService(tournament)

    def get_qualified_teams(self) -> List[Team]:
        standings = self.group_service.get_group_standings()
        qualified_teams = []
        
        # Get top 2 teams from each group
        for group_standings in standings.values():
            qualified_teams.extend([
                stats['team'] for stats in group_standings[:2]
            ])
        
        return qualified_teams

    def generate_matches(self, qualified_teams: List[Team]) -> List[Match]:
        """Generate semifinal matches from qualified teams"""
        if len(qualified_teams) != 4:
            raise ValueError("Need exactly 4 teams for knockout stage")
            
        # Create semifinals: 1st vs 4th, 2nd vs 3rd
        matches = []
        for i in range(0, 4, 2):
            match = Match.objects.create(
                tournament=self.tournament,
                team_home=qualified_teams[i],
                team_away=qualified_teams[i+1],
                match_date=self.tournament.datetime,
                stage='SEMIFINAL',
                status='SCHEDULED'
            )
            matches.append(match)
        return matches

    def generate_final(self, finalists: List[Team]) -> Match:
        """Generate final match between two teams"""
        if len(finalists) != 2:
            raise ValueError("Need exactly 2 teams for final")
            
        return Match.objects.create(
            tournament=self.tournament,
            team_home=finalists[0],
            team_away=finalists[1],
            match_date=self.tournament.datetime,
            stage='FINAL',
            status='SCHEDULED'
        )

    def advance_knockout_stage(self) -> List[Match]:
        current_stage = self._get_current_stage()
        if not current_stage:
            raise ValueError("No active knockout stage found")

        winners = self._get_stage_winners(current_stage)
        next_stage = self._get_next_stage(current_stage)
        
        if not next_stage:
            if current_stage == 'FINAL':
                self.tournament.status = 'COMPLETED'
                self.tournament.save()
                return []
            raise ValueError("Invalid stage progression")

        matches = []
        base_date = max(
            Match.objects.filter(
                tournament=self.tournament,
                stage=current_stage
            ).values_list('match_date', flat=True)
        ) + timedelta(days=3)

        # Create matches for next round
        for i in range(0, len(winners), 2):
            match = Match.objects.create(
                tournament=self.tournament,
                team_home=winners[i],
                team_away=winners[i+1],
                match_date=base_date + timedelta(days=i//2),
                stage=next_stage
            )
            matches.append(match)

        return matches

    def _get_current_stage(self) -> str:
        stages = ['RO16', 'QUARTER', 'SEMI', 'FINAL']
        for stage in stages:
            if Match.objects.filter(
                tournament=self.tournament,
                stage=stage,
                status__in=['SCHEDULED', 'PENDING']
            ).exists():
                return stage
        return None

    def _get_next_stage(self, current_stage: str) -> str:
        stages = {
            'RO16': 'QUARTER',
            'QUARTER': 'SEMI',
            'SEMI': 'FINAL',
            'FINAL': None
        }
        return stages.get(current_stage)

    def _get_stage_winners(self, stage: str) -> List[Team]:
        matches = Match.objects.filter(
            tournament=self.tournament,
            stage=stage,
            status='CONFIRMED'
        )
        
        winners = []
        for match in matches:
            if match.home_score > match.away_score:
                winners.append(match.team_home)
            elif match.away_score > match.home_score:
                winners.append(match.team_away)
            elif match.penalties:
                # In case of penalties, assume the home team won
                # (this should be extended with a penalties_winner field)
                winners.append(match.team_home)
                
        return winners 