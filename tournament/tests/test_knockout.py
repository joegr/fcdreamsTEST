def test_manage_knockout_round_progression(self):
    """Test managing knockout round progression."""
    tournament_service = TournamentService(self.tournament)
    qualified_teams = tournament_service.group_service.get_qualified_teams()

    # Simulate generating knockout matches
    knockout_matches = tournament_service.generate_knockout_matches()
    self.assertEqual(len(knockout_matches), len(qualified_teams) // 2)

    # Simulate confirming match results
    for match in knockout_matches:
        match.home_score = 3
        match.away_score = 1
        match.status = 'CONFIRMED'
        match.save()

    # Verify winners
    winners = tournament_service.get_stage_winners('KNOCKOUT')
    self.assertEqual(len(winners), len(knockout_matches))

def test_record_knockout_match_result(self):
    """Test recording a match result for the knockout stage."""
    match = Match.objects.create(
        tournament=self.tournament,
        team_home=self.teams[0],
        team_away=self.teams[1],
        home_score=0,
        away_score=0,
        stage='KNOCKOUT',
        status='SCHEDULED'
    )

    # Simulate submitting a match result
    match.home_score = 2
    match.away_score = 1
    match.status = 'CONFIRMED'
    match.save()

    # Verify that the match result is recorded correctly
    self.assertEqual(match.home_score, 2)
    self.assertEqual(match.away_score, 1)
    self.assertEqual(match.status, 'CONFIRMED')

def test_tournament_completion(self):
    """Test the completion of the tournament."""
    tournament_service = TournamentService(self.tournament)
    qualified_teams = tournament_service.group_service.get_qualified_teams()

    # Simulate knockout progression
    knockout_matches = tournament_service.generate_knockout_matches()
    for match in knockout_matches:
        match.home_score = 1
        match.away_score = 0
        match.status = 'CONFIRMED'
        match.save()

    # Final match
    final_match = Match.objects.create(
        tournament=self.tournament,
        team_home=qualified_teams[0],
        team_away=qualified_teams[1],
        home_score=2,
        away_score=3,
        stage='FINAL',
        status='CONFIRMED'
    )

    # Verify tournament winner
    winner = tournament_service.get_tournament_winner()
    self.assertEqual(winner, final_match.team_away)  # Assuming team_away wins 