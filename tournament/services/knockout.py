from typing import List, Dict, Optional
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

    def generate_matches(self, teams: List[Team]) -> List[Match]:
        """Generate knockout matches for any number of teams (must be power of 2)"""
        if not teams or len(teams) & (len(teams) - 1) != 0:  # Check if power of 2
            raise ValueError("Number of teams must be a power of 2")
            
        matches = []
        # When transitioning from GROUP_STAGE, we need to start with RO16
        stage = 'RO16' if self.tournament.status == 'GROUP_STAGE' else self._determine_stage(len(teams))
        
        # Pair teams: 1st vs last, 2nd vs second-last, etc.
        for i in range(len(teams) // 2):
            match = Match.objects.create(
                tournament=self.tournament,
                team_home=teams[i],
                team_away=teams[-(i+1)],
                match_date=self.tournament.datetime + timedelta(days=i),
                stage=stage,
                status='SCHEDULED'
            )
            matches.append(match)
        return matches

    def _determine_stage(self, num_teams: int) -> str:
        """Determine stage based on number of teams"""
        stage_map = {
            32: 'RO16',
            16: 'QUARTER',
            8: 'SEMI',
            4: 'FINAL'
        }
        return stage_map.get(num_teams, 'UNKNOWN')

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
        current_stage = self.get_current_stage()
        if not current_stage:
            raise ValueError("No active knockout stage found")

        winners = self.get_stage_winners(current_stage)
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

    def get_current_stage(self) -> Optional[str]:
        """Get the current knockout stage"""
        stages = ['RO16', 'QUARTER', 'SEMI', 'FINAL']
        for stage in stages:
            if Match.objects.filter(
                tournament=self.tournament,
                stage=stage,
                status__in=['SCHEDULED', 'PENDING']
            ).exists():
                return stage
        return None

    def is_stage_complete(self, stage: str) -> bool:
        """Check if all matches in a stage are completed"""
        matches = Match.objects.filter(
            tournament=self.tournament,
            stage=stage
        )
        return matches.exists() and not matches.filter(
            status__in=['SCHEDULED', 'PENDING']
        ).exists()

    def get_stage_winners(self, stage: str) -> List[Team]:
        """Get winners from a specific stage"""
        matches = Match.objects.filter(
            tournament=self.tournament,
            stage=stage,
            status='CONFIRMED'
        )
        
        winners = []
        for match in matches:
            winner = match.team_home if match.home_score > match.away_score else match.team_away
            winners.append(winner)
        return winners

    def generate_next_stage_matches(self, winners: List[Team]) -> List[Match]:
        """Generate matches for next stage based on winners"""
        stage_progression = {
            'GROUP': 'RO16',  # Add GROUP to progression
            'RO16': 'QUARTER',
            'QUARTER': 'SEMI',
            'SEMI': 'FINAL'
        }
        
        current_matches = Match.objects.filter(
            tournament=self.tournament,
            team_home__in=winners,
            status='CONFIRMED'
        ).first()
        
        if not current_matches:
            raise ValueError("No completed matches found with winners")
        
        current_stage = current_matches.stage
        next_stage = stage_progression.get(current_stage)
        
        if not next_stage:
            raise ValueError(f"No next stage after {current_stage}")
        
        # Create matches for next stage
        matches = []
        for i in range(0, len(winners), 2):
            match = Match.objects.create(
                tournament=self.tournament,
                team_home=winners[i],
                team_away=winners[i+1],
                match_date=self.tournament.datetime + timedelta(days=i//2),
                stage=next_stage,
                status='SCHEDULED'
            )
            matches.append(match)
        return matches

    def _get_next_stage(self, current_stage: str) -> str:
        stages = {
            'RO16': 'QUARTER',
            'QUARTER': 'SEMI',
            'SEMI': 'FINAL',
            'FINAL': None
        }
        return stages.get(current_stage) 