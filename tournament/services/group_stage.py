from typing import List, Dict
from django.db.models import Q
from ..models import Tournament, Team, Match
import random
from datetime import timedelta

class GroupStageService:
    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        self.teams = list(Team.objects.filter(
            tournament=tournament,
            registration_complete=True
        ))
        self.groups = None

    def get_qualified_teams(self) -> List[Team]:
        """Get teams qualified for knockout stage based on group standings"""
        standings = self.get_group_standings()
        qualified_teams = []
        
        # Get top 2 teams from each group
        for group_standings in standings.values():
            qualified_teams.extend([
                stats['team'] for stats in group_standings[:2]
            ])
        
        return qualified_teams

    def is_group_stage_complete(self) -> bool:
        """Check if all group matches are confirmed"""
        if self.tournament.status != 'GROUP_STAGE':
            return False
        
        return not Match.objects.filter(
            tournament=self.tournament,
            stage='GROUP',
            status__in=['SCHEDULED', 'PENDING', 'DISPUTED']
        ).exists()

    def get_group_standings(self) -> Dict[int, List[Dict]]:
        """Calculate standings for each group"""
        if self.groups is None:
            self.generate_groups()

        standings = {}
        
        for group_num, teams in self.groups.items():
            team_stats = []
            for team in teams:
                stats = {
                    'team': team,
                    'points': 0,
                    'goals_for': 0,
                    'goals_against': 0,
                    'goal_difference': 0,
                    'matches_played': 0,
                    'wins': 0,
                    'draws': 0,
                    'losses': 0
                }
                
                # Calculate home match stats
                home_matches = Match.objects.filter(
                    tournament=self.tournament,
                    team_home=team,
                    stage='GROUP',
                    status='CONFIRMED'
                )
                for match in home_matches:
                    stats['matches_played'] += 1
                    stats['goals_for'] += match.home_score
                    stats['goals_against'] += match.away_score
                    if match.home_score > match.away_score:
                        stats['wins'] += 1
                        stats['points'] += 3
                    elif match.home_score == match.away_score:
                        stats['draws'] += 1
                        stats['points'] += 1
                    else:
                        stats['losses'] += 1

                # Calculate away match stats
                away_matches = Match.objects.filter(
                    tournament=self.tournament,
                    team_away=team,
                    stage='GROUP',
                    status='CONFIRMED'
                )
                for match in away_matches:
                    stats['matches_played'] += 1
                    stats['goals_for'] += match.away_score
                    stats['goals_against'] += match.home_score
                    if match.away_score > match.home_score:
                        stats['wins'] += 1
                        stats['points'] += 3
                    elif match.away_score == match.home_score:
                        stats['draws'] += 1
                        stats['points'] += 1
                    else:
                        stats['losses'] += 1

                stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
                team_stats.append(stats)

            # Sort by points, then goal difference, then goals scored
            team_stats.sort(
                key=lambda x: (-x['points'], -x['goal_difference'], -x['goals_for'])
            )
            standings[group_num] = team_stats

        return standings

    def generate_groups(self) -> Dict[int, List[Team]]:
        """Generate groups for the tournament"""
        if len(self.teams) != self.tournament.number_of_groups * self.tournament.teams_per_group:
            raise ValueError(
                f"Need {self.tournament.number_of_groups * self.tournament.teams_per_group} teams, "
                f"but got {len(self.teams)}"
            )

        random.shuffle(self.teams)
        self.groups = {}
        
        for i in range(self.tournament.number_of_groups):
            start_idx = i * self.tournament.teams_per_group
            end_idx = start_idx + self.tournament.teams_per_group
            self.groups[i] = self.teams[start_idx:end_idx]

        return self.groups

    def generate_matches(self) -> List[Match]:
        """Generate round-robin matches for each group"""
        if self.groups is None:
            self.generate_groups()

        matches = []
        base_date = self.tournament.datetime
        match_day = 0

        for group_num, teams in self.groups.items():
            # Round-robin format: each team plays against every other team once
            for i in range(len(teams)):
                for j in range(i + 1, len(teams)):
                    match = Match.objects.create(
                        tournament=self.tournament,
                        team_home=teams[i],
                        team_away=teams[j],
                        match_date=base_date + timedelta(days=match_day),
                        stage='GROUP',
                        status='PENDING'
                    )
                    matches.append(match)
                    match_day += 1

        return matches