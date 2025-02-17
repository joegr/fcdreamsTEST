Feature: Knockout Stage Management
  As a Tournament Admin
  I want to manage the progression of knockout rounds
  So that the tournament can conclude successfully

  Background:
    Given the group stages are completed
    And qualifying teams have been determined

  Scenario: Manage knockout round progression
    Given a knockout round is in progress
    When all matches in the current round have confirmed results
    Then the system should:
      | Action                                    |
      | Validate all match results are confirmed  |
      | Calculate winning teams                   |
      | Generate next round matchups              |
      | Notify advancing teams                    |

  Scenario: Record knockout match result
    Given I am a team manager in the knockout rounds
    When I submit a match result:
      | Field Name     | Value         |
      | Match ID       | RO16-01       |
      | Our Score      | 2             |
      | Opponent Score | 1             |
      | Extra Time     | Yes           |
      | Penalties      | No            |
    Then the system should require opposing team confirmation
    And use OCR to verify both submitted results
    And only proceed when results match
    
  Scenario: Tournament Completion
    Given all knockout rounds are completed
    When the final match result is confirmed
    Then the system should:
      | Action                        |
      | Declare tournament winner     |
      | Generate final standings      |
      | Close tournament status       |
      | Notify all participating teams|