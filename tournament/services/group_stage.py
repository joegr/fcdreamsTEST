from typing import List, Dict, Optional
from django.utils import timezone
from django.db.models import Q
from tournament.models import Tournament, Team, Match
from datetime import timedelta
import heapq
import itertools

class GroupStageService:
    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        self.teams = list(Team.objects.filter(
            tournament=tournament,
            registration_complete=True
        ).order_by('id'))
        self.groups = None
        self._pq = []  # Priority queue for standings
        self._entry_finder = {}  # Track team entries
        self._counter = itertools.count()  # Unique sequence count
        self.REMOVED = '<removed>'  # Placeholder for removed teams

    def _add_team_to_standings(self, team: Team, points: int, goal_diff: int, goals_for: int):
        """Add or update team in standings priority queue"""
        if team in self._entry_finder:
            self._remove_team(team)
        count = next(self._counter)
        # Priority tuple: (-points, -goal_diff, -goals_for) for max heap behavior
        priority = (-points, -goal_diff, -goals_for)
        entry = [priority, count, team]
        self._entry_finder[team] = entry
        heapq.heappush(self._pq, entry)

    def _remove_team(self, team: Team):
        """Remove team from standings"""
        entry = self._entry_finder.pop(team)
        entry[-1] = self.REMOVED

    def _get_next_team(self) -> Optional[Team]:
        """Get next team from standings queue"""
        while self._pq:
            priority, count, team = heapq.heappop(self._pq)
            if team is not self.REMOVED:
                del self._entry_finder[team]
                return team, priority
        return None

    def get_group_standings(self, group_letter=None) -> List[Dict]:
        """Get standings using priority queue"""
        # Clear existing queue
        self._pq = []
        self._entry_finder = {}
        
        matches = Match.objects.filter(
            tournament=self.tournament,
            stage='GROUP',
            status='CONFIRMED'
        )
        if group_letter:
            matches = matches.filter(group=group_letter)

        # Calculate team statistics
        team_stats = {}
        for match in matches:
            for team, is_home in [(match.team_home, True), (match.team_away, False)]:
                if team not in team_stats:
                    team_stats[team] = {'points': 0, 'goals_for': 0, 'goals_against': 0}
                
                goals_for = match.home_score if is_home else match.away_score
                goals_against = match.away_score if is_home else match.home_score
                
                team_stats[team]['goals_for'] += goals_for
                team_stats[team]['goals_against'] += goals_against
                
                if goals_for > goals_against:
                    team_stats[team]['points'] += 3
                elif goals_for == goals_against:
                    team_stats[team]['points'] += 1

        # Add teams to priority queue
        for team, stats in team_stats.items():
            self._add_team_to_standings(
                team,
                stats['points'],
                stats['goals_for'] - stats['goals_against'],
                stats['goals_for']
            )

        # Extract sorted standings
        standings = []
        while True:
            result = self._get_next_team()
            if not result:
                break
            team, (neg_points, neg_goal_diff, neg_goals_for) = result
            standings.append({
                'team': team,
                'points': -neg_points,
                'goal_difference': -neg_goal_diff,
                'goals_for': -neg_goals_for,
                'goals_against': team_stats[team]['goals_against']
            })

        return standings

    def get_qualified_teams(self) -> List[Team]:
        """Get teams qualified for knockout stage using priority queue"""
        if not self.is_group_stage_complete():
            raise ValueError("Group stage is not complete")

        qualified = []
        for group_letter in range(self.tournament.number_of_groups):
            standings = self.get_group_standings(str(group_letter))
            qualified.extend([s['team'] for s in standings[:2]])  # Top 2 from each group

        return qualified

    def is_group_stage_complete(self) -> bool:
        """Check if all group stage matches are completed"""
        # Get all group stage matches
        group_matches = Match.objects.filter(
            tournament=self.tournament,
            stage='GROUP'
        )

        # Calculate expected number of matches
        teams_per_group = self.tournament.teams_per_group
        matches_per_group = (teams_per_group * (teams_per_group - 1)) // 2  # n(n-1)/2 for round robin
        total_expected_matches = matches_per_group * self.tournament.number_of_groups

        # Check if we have all matches and they're all confirmed
        completed_matches = group_matches.filter(status='CONFIRMED').count()
        
        # For testing purposes, create matches if they don't exist
        if group_matches.count() == 0:
            self.create_group_matches()
            return False

        # All matches must exist and be confirmed
        return (group_matches.count() == total_expected_matches and 
                completed_matches == total_expected_matches)

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
        """Create matches for group stage"""
        if not hasattr(self, 'groups') or not self.groups:
            self.generate_groups()  # Ensure groups are generated
        
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