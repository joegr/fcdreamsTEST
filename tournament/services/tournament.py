from typing import Optional, List, Dict
from django.db.models import Q
import random
import string
from ..models import Tournament, Team, Match, Result
from .group_stage import GroupStageService
from .knockout import KnockoutService
import logging

logger = logging.getLogger(__name__)

class TournamentService:
    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        self.group_service = GroupStageService(tournament)
        self.knockout_service = KnockoutService(tournament)

    @staticmethod
    def generate_registration_code(length: int = 8) -> str:
        """Generate a unique registration code for a team."""
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(random.choice(chars) for _ in range(length))
            if not Team.objects.filter(registration_code=code).exists():
                return code

    @staticmethod
    def validate_team_registration(team: Team) -> str:
        """
        Validate team registration based on player count.
        Returns registration status.
        """
        player_count = team.player_set.count()
        if player_count < 8:
            return 'INCOMPLETE'
        elif player_count > 14:
            return 'OVER_LIMIT'
        return 'VALID'

    @staticmethod
    def process_match_result(
        match: Match,
        submitting_team: Team,
        our_score: int,
        opponent_score: int,
        extra_time: bool = False,
        penalties: bool = False
    ) -> Result:
        """
        Process a match result submission from a team.
        Creates a Result object and updates match if both teams have submitted.
        """
        # Create the result submission
        result = Result.objects.create(
            match=match,
            submitting_team=submitting_team,
            home_score=our_score if submitting_team == match.team_home else opponent_score,
            away_score=opponent_score if submitting_team == match.team_home else our_score,
            extra_time=extra_time,
            penalties=penalties
        )

        # Check if both teams have submitted results
        match_results = Result.objects.filter(match=match)
        if match_results.count() == 2:
            # Verify results match
            if TournamentService._verify_matching_results(match_results):
                match.home_score = result.home_score
                match.away_score = result.away_score
                match.extra_time = extra_time
                match.penalties = penalties
                match.status = 'CONFIRMED'
                match.save()
            else:
                match.status = 'DISPUTED'
                match.save()

        return result

    @staticmethod
    def _verify_matching_results(results) -> bool:
        """
        Verify that two result submissions for a match match each other.
        """
        if len(results) != 2:
            return False

        result1, result2 = results
        return (
            result1.home_score == result2.home_score and
            result1.away_score == result2.away_score and
            result1.extra_time == result2.extra_time and
            result1.penalties == result2.penalties
        )

    @staticmethod
    def get_tournament_standings(tournament: Tournament) -> list:
        """
        Get overall tournament standings.
        Returns list of teams with their statistics.
        """
        teams = Team.objects.filter(tournament=tournament)
        standings = []

        for team in teams:
            stats = {
                'team': team,
                'matches_played': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'goals_for': 0,
                'goals_against': 0,
            }

            # Get all confirmed matches for the team
            matches = Match.objects.filter(
                Q(team_home=team) | Q(team_away=team),
                tournament=tournament,
                status='CONFIRMED'
            )

            for match in matches:
                stats['matches_played'] += 1
                if team == match.team_home:
                    stats['goals_for'] += match.home_score
                    stats['goals_against'] += match.away_score
                    if match.home_score > match.away_score:
                        stats['wins'] += 1
                    elif match.home_score < match.away_score:
                        stats['losses'] += 1
                    else:
                        stats['draws'] += 1
                else:
                    stats['goals_for'] += match.away_score
                    stats['goals_against'] += match.home_score
                    if match.away_score > match.home_score:
                        stats['wins'] += 1
                    elif match.away_score < match.home_score:
                        stats['losses'] += 1
                    else:
                        stats['draws'] += 1

            stats['points'] = (stats['wins'] * 3) + stats['draws']
            stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
            standings.append(stats)

        # Sort standings by points, goal difference, then goals scored
        standings.sort(
            key=lambda x: (-x['points'], -x['goal_difference'], -x['goals_for'])
        )
        return standings

    @staticmethod
    def check_tournament_completion(tournament: Tournament) -> bool:
        """
        Check if a tournament is complete (all matches played and confirmed).
        """
        unfinished_matches = Match.objects.filter(
            tournament=tournament,
            status__in=['SCHEDULED', 'PENDING', 'DISPUTED']
        ).exists()
        
        if not unfinished_matches and tournament.status == 'KNOCKOUT':
            final_match = Match.objects.filter(
                tournament=tournament,
                stage='FINAL',
                status='CONFIRMED'
            ).first()
            
            if final_match:
                tournament.status = 'COMPLETED'
                tournament.save()
                return True
                
        return False

    def handle_result_confirmation(self, result: Result) -> None:
        """Central handler for result confirmations"""
        if not (result.home_team_confirmed and result.away_team_confirmed):
            return

        match = result.match
        
        # Update match with confirmed result
        match.home_score = result.home_score
        match.away_score = result.away_score
        match.extra_time = result.extra_time
        match.penalties = result.penalties
        match.status = 'CONFIRMED'
        match.save()

        # Handle tournament stage transitions
        if self.tournament.status == 'GROUP_STAGE':
            self._handle_group_stage_progression()
        elif self.tournament.status == 'KNOCKOUT':
            self._handle_knockout_stage_progression()

    def _handle_group_stage_progression(self) -> None:
        """Handle group stage completion and transition"""
        if self.group_service.is_group_stage_complete():
            try:
                qualified_teams = self.group_service.get_qualified_teams()
                self.knockout_service.generate_matches(qualified_teams)
                self.tournament.status = 'KNOCKOUT'
                self.tournament.save()
            except Exception as e:
                logger.error(f"Failed to transition to knockout stage: {e}")
                raise

    def _handle_knockout_stage_progression(self) -> None:
        """Handle knockout stage progression"""
        try:
            current_stage = self.knockout_service.get_current_stage()
            if current_stage and self.knockout_service.is_stage_complete(current_stage):
                if current_stage == 'FINAL':
                    self.tournament.status = 'COMPLETED'
                    self.tournament.save()
                else:
                    winners = self.knockout_service.get_stage_winners(current_stage)
                    self.knockout_service.generate_next_stage_matches(winners)
        except Exception as e:
            logger.error(f"Failed to progress knockout stage: {e}")
            raise 