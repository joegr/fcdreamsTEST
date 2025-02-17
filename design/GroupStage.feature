Feature: Group Stage Management
  As a Tournament Admin
  I want to manage the group stage matches and progression
  So that the tournament can advance properly

  Background:
    Given all teams have completed registration
    And the group stage has been initialized

  Scenario: Record group stage match result
    Given I am a team manager
    When I submit a match result for my team:
      | Field Name     | Value         |
      | Match ID       | GS-A-01       |
      | Our Score      | 2             |
      | Opponent Score | 1             |
      | Match Date     | 2024-07-05    |
    Then the system should mark the result as "Pending Confirmation"
    And notify the opposing team manager to confirm

  Scenario: Verify match results using OCR
    Given a match result has been submitted
    When the opposing team manager uploads their match result
    Then the system should OCR process both submissions
    And compare the scores
    And if scores match:
      | Action                    |
      | Mark match as confirmed   |
      | Update group standings    |
      | Notify both managers      |
    And if scores don't match:
      | Action                    |
      | Flag for admin review     |
      | Notify both managers      |

  Scenario: Calculate group stage completion
    Given all group stage matches have confirmed results
    When the system checks group completion
    Then it should calculate final group standings
    And determine qualifying teams
    And generate round of 16 matches
    And notify all qualifying teams