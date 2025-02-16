from typing import List, Dict
from django.utils import timezone
from django.db.models import Q
from tournament.models import Tournament, Team, Match
from datetime import timedelta

class GroupStageService:
    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        self.teams = list(Team.objects.filter(
            tournament=tournament,
            registration_complete=True
        ).order_by('id'))  # Ensure consistent ordering
        self.groups = None

    def get_qualified_teams(self) -> List[Team]:
        """Get teams qualified for knockout stage based on group standings"""
        standings = self.get_group_standings()
        qualified_teams = []

        # Validate we have correct number of groups
        if len(standings) != 8:
            raise ValueError(f"Expected 8 groups, got {len(standings)}")

        # Get top 2 teams from each group
        for group_num in range(8):
            if group_num not in standings:
                raise ValueError(f"Missing group {group_num}")

            group_standings = standings[group_num]
            if len(group_standings) < 2:
                raise ValueError(f"Group {group_num} has insufficient teams")

            # Get top 2 from each group
            top_two = sorted(
                group_standings,
                key=lambda x: (-x['points'], -x['goal_difference'], -x['goals_for'])
            )[:2]

            # Add both teams to qualified list
            qualified_teams.extend([stats['team'] for stats in top_two])

        return qualified_teams

    def is_group_stage_complete(self) -> bool:
        """Check if all group stage matches are completed"""
        return not Match.objects.filter(
            tournament=self.tournament,
            stage='GROUP',
            status__in=['SCHEDULED', 'PENDING']
        ).exists()

    def get_group_standings(self) -> Dict:
        standings = {}
        for group in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
            standings[group] = []
            group_matches = Match.objects.filter(
                tournament=self.tournament,
                match_id__startswith=f'GS-{group}-'
            )
            for team in self.teams:
                team_stats = self._calculate_team_stats(team, group_matches)
                standings[group].append(team_stats)
        return standings

    def _calculate_team_stats(self, team: Team, matches) -> Dict:
        stats = {
            'team': team,
            'points': 0,
            'goals_for': 0, 
            'goals_against': 0,
            'goal_difference': 0
        }

        for match in matches:
            if not match.confirmed:
                continue
                
            if match.team_home == team:
                stats['goals_for'] += match.home_score or 0
                stats['goals_against'] += match.away_score or 0
                if match.home_score > match.away_score:
                    stats['points'] += 3
                elif match.home_score == match.away_score:
                    stats['points'] += 1
            elif match.team_away == team:
                stats['goals_for'] += match.away_score or 0
                stats['goals_against'] += match.home_score or 0
                if match.away_score > match.home_score:
                    stats['points'] += 3
                elif match.home_score == match.away_score:
                    stats['points'] += 1

        stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
        return stats

    def generate_groups(self) -> Dict[int, List[Team]]:
        """Generate groups for the tournament"""
        if len(self.teams) != self.tournament.number_of_groups * self.tournament.teams_per_group:
            raise ValueError(
                f"Need {self.tournament.number_of_groups * self.tournament.teams_per_group} teams, "
                f"but got {len(self.teams)}"
            )

        # Sort teams by strength rating for seeding
        sorted_teams = sorted(self.teams, key=lambda t: t.strength_rating, reverse=True)
        self.groups = {i: [] for i in range(self.tournament.number_of_groups)}
        
        # Distribute teams using snake draft to balance groups
        for i, team in enumerate(sorted_teams):
            group_num = i % self.tournament.number_of_groups
            if i // self.tournament.number_of_groups % 2 == 1:
                group_num = self.tournament.number_of_groups - 1 - group_num
            self.groups[group_num].append(team)

        return self.groups

    def generate_matches(self) -> List[Match]:
        """Generate all group stage matches"""
        if not self.groups:
            self.generate_groups()

        matches = []
        base_date = self.tournament.datetime
        match_count = 0
        
        # Calculate matches per group
        matches_per_group = len(self.teams) // self.tournament.number_of_groups
        matches_per_group = (matches_per_group * (matches_per_group - 1)) // 2
        
        for group_num, teams in self.groups.items():
            group_teams = sorted(teams, key=lambda t: t.id)
            group_base_date = base_date + timedelta(days=group_num * 7)  # One week per group
            
            # Generate round-robin matches for this group
            for i in range(len(group_teams)):
                for j in range(i + 1, len(group_teams)):
                    match_date = group_base_date + timedelta(
                        days=match_count % matches_per_group
                    )
                    
                    match = Match.objects.create(
                        tournament=self.tournament,
                        team_home=group_teams[i],
                        team_away=group_teams[j],
                        match_date=match_date,
                        stage='GROUP',
                        status='SCHEDULED'
                    )
                    matches.append(match)
                    match_count += 1

        return matches

    def create_group_matches(self):
        """Create matches for all teams within their groups"""
        if not self.groups:
            raise ValueError("Groups must be assigned before creating matches")

        matches = []
        start_date = self.tournament.start_date
        match_spacing = timedelta(days=4)  # 4 days between matches
        current_date = start_date

        for group_num, group_teams in self.groups.items():
            # Generate all possible pairings within group
            pairings = self._generate_group_pairings(group_teams)
            
            for home_team, away_team in pairings:
                match = Match.objects.create(
                    tournament=self.tournament,
                    team_home=home_team,
                    team_away=away_team,
                    match_date=current_date,
                    stage='GROUP',
                    group=group_num
                )
                matches.append(match)
                current_date += match_spacing

        return matches

    def _generate_group_pairings(self, group_teams):
        """Generate round-robin pairings for teams in a group"""
        pairings = []
        teams = list(group_teams)
        
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                pairings.append((teams[i], teams[j]))
        
        return pairings

    def _get_team_stats(self, team):
        """Helper to get team's statistics"""
        standings = self.get_group_standings()
        for group_standings in standings.values():
            for stats in group_standings:
                if stats['team'] == team:
                    return stats
        return {'points': 0, 'goal_difference': 0}

def visualize_standings(standings):
    """Visualize the standings in a readable format."""
    print("Standings:")
    for group_num, group in standings.items():
        print(f"Group {group_num + 1}:")
        for team_stats in group:
            print(f"  Team: {team_stats['team'].name}, Points: {team_stats['points']}, "
                  f"Goal Difference: {team_stats['goal_difference']}, Goals For: {team_stats['goals_for']}")