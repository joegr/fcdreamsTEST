from typing import Optional, List, Dict
from django.db.models import Q
import random
import string
from ..models import Tournament, Team, Match, Result
from .group_stage import GroupStageService
from .knockout import KnockoutService
import logging
from datetime import datetime, timedelta, timezone

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
            team_home=submitting_team if submitting_team == match.team_home else match.team_home,
            team_away=match.team_away,
            home_score=our_score if submitting_team == match.team_home else opponent_score,
            away_score=opponent_score if submitting_team == match.team_home else our_score,
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
            if self.group_service.is_group_stage_complete():
                qualified_teams = self.group_service.get_qualified_teams()
                self.create_knockout_matches(qualified_teams, 'RO16')
                self.tournament.status = 'KNOCKOUT'
            else:
                try:
                    qualified_teams = self.group_service.get_qualified_teams()
                    # Create RO16 matches
                    self.knockout_service.generate_matches(qualified_teams)
                    self.tournament.status = 'KNOCKOUT'
                except Exception as e:
                    logger.error(f"Failed to transition to knockout stage: {e}")
                    raise
        elif self.tournament.status == 'KNOCKOUT':
            try:
                if match.stage == 'FINAL' and self.knockout_service.is_stage_complete('FINAL'):
                    self.tournament.status = 'COMPLETED'
                    self.tournament.save()
                elif self.knockout_service.is_stage_complete(match.stage):
                    winners = self.knockout_service.get_stage_winners(match.stage)
                    self.knockout_service.generate_next_stage_matches(winners)
            except Exception as e:
                logger.error(f"Failed to progress knockout stage: {e}")
                raise

    def create_knockout_matches(self, teams: List[Team], stage: str) -> List[Match]:
        """Create knockout stage matches"""
        if len(teams) % 2 != 0:
            raise ValueError("Need even number of teams for knockout stage")
            
        # First, delete any existing unplayed matches for this stage
        Match.objects.filter(
            tournament=self.tournament,
            stage=stage,
            status='SCHEDULED'
        ).delete()
            
        matches = []
        # Pair teams: 1st vs last, 2nd vs second-last, etc.
        for i in range(len(teams) // 2):
            team_home = teams[i]
            team_away = teams[-(i+1)]

            if team_home.id == team_away.id:
                raise ValueError("A team cannot play against itself")

            match = Match.objects.create(
                tournament=self.tournament,
                team_home=team_home,
                team_away=team_away,
                home_score=0,  # Initialize scores
                away_score=0,  # Initialize scores
                match_date=self.tournament.datetime + timedelta(days=i),
                stage=stage,
                status='SCHEDULED'
            )
            matches.append(match)
        
        return matches

    def get_stage_winners(self, stage: str) -> List[Team]:
        """Get winning teams from a specific stage"""
        stage_matches = Match.objects.filter(
            tournament=self.tournament,
            stage=stage,
            status='CONFIRMED'
        )
        
        winners = []
        for match in stage_matches:
            if match.home_score > match.away_score:
                winners.append(match.team_home)
            else:
                winners.append(match.team_away)
        return winners

    def get_tournament_winner(self) -> Optional[Team]:
        """Get the tournament winner"""
        final_match = Match.objects.filter(
            tournament=self.tournament,
            stage='FINAL',
            status='CONFIRMED'
        ).first()
        
        if final_match:
            return final_match.team_home if final_match.home_score > final_match.away_score else final_match.team_away
        return None

    def handle_team_registration(self, team: Team) -> None:
        """Handle team registration process"""
        if not team.registration_code:
            raise ValueError("Invalid registration code")
        
        if team.registration_expires and team.registration_expires < timezone.now():
            raise ValueError("Registration code has expired")
        
        # Set registration expiry (e.g., 24 hours from now)
        team.registration_expires = timezone.now() + timedelta(hours=24)
        team.save()

    def complete_registration(self, team: Team) -> None:
        """Complete team registration"""
        team.registration_complete = True
        team.expire_registration()  # Clear registration code
        team.save() 

    def generate_knockout_matches(self) -> List[Match]:
        """Generate knockout stage matches"""
        qualified_teams = self.group_service.get_qualified_teams()
        matches = []

        # Ensure we have an even number of teams
        if len(qualified_teams) % 2 != 0:
            raise ValueError("Need even number of teams for knockout stage")

        # Shuffle teams to randomize pairing
        random.shuffle(qualified_teams)

        # Create matches ensuring no team plays against itself
        for i in range(0, len(qualified_teams), 2):
            try:
                team_home = qualified_teams[i]
                team_away = qualified_teams[i + 1]

                # Check for self-match
                if team_home.id == team_away.id:
                    raise ValueError("A team cannot play against itself")

                match = Match.objects.create(
                    tournament=self.tournament,
                    team_home=team_home,
                    team_away=team_away,
                    home_score=0,  # Initialize scores
                    away_score=0,  # Initialize scores
                    stage='KNOCKOUT',
                    status='SCHEDULED'
                )
                matches.append(match)

            except ValueError as e:
                logger.warning(f"Skipping match creation due to error: {e}")

        return matches

    def create_match(self, team_home: Team, team_away: Team) -> Match:
        """Create a match between two teams"""
        match = Match.objects.create(
            tournament=self.tournament,
            team_home=team_home,
            team_away=team_away,
            home_score=0,  # Initialize scores
            away_score=0,  # Initialize scores
            stage='GROUP',
            status='SCHEDULED'
        )
        return match