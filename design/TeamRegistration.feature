Feature: Team Registration and Validation
  As a Team Manager
  I want to register my team and monitor player registrations
  So that we can participate in the tournament

  Background:
    Given there is an active tournament "Champions Cup 2024"
    And the registration period is open

  Scenario: Register as team manager
    When I navigate to "Tournament Registration"
    And I submit the following team details:
      | Field Name     | Value            |
      | Team Name      | Victory United   |
      | Manager Name   | John Doe         |
      | Email         | john@united.com   |
      | Contact Phone | +1234567890      |
    Then I should receive a team registration confirmation
    And I should receive a unique team registration code
    And the system should create a team entry in the tournament

  Scenario: Monitor player registrations
    Given I am a registered team manager
    And my team "Victory United" is in the tournament
    When I view "Team Registration Status"
    Then I should see a list of registered players
    And I should see the current player count
    And I should see registration status warnings:
      | Warning Type        | Condition          |
      | Insufficient Players| Count < 8          |
      | Too Many Players    | Count > 14         |

  Scenario: Close team registration
    Given I am a registered team manager
    And my team has between 8 and 14 players
    When I click "Finalize Team Registration"
    Then the system should validate player count asynchronously
    And lock the team roster
    And notify the tournament admin of completion