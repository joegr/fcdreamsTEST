Feature: Tournament Creation and Management
  As a Tournament Admin
  I want to create and manage a Champions League style tournament
  So that I can organize FIFA competitions effectively

  Background:
    Given I am logged in as a Tournament Admin
    And I am on the tournament management dashboard

  Scenario: Create a new tournament
    When I click "Create New Tournament"
    And I enter the following tournament details:
      | Field Name           | Value                    |
      | Tournament Name      | Champions Cup 2024       |
      | Start Date          | 2024-07-01               |
      | End Date            | 2024-07-30               |
      | Number of Groups    | 8                        |
      | Teams per Group     | 4                        |
      | Registration Fee    | 100                      |
    And I click "Create Tournament"
    Then I should see "Tournament created successfully"
    And the system should create group stage placeholders
    And the registration period should be opened

  Scenario: Monitor team registration status
    Given there is an active tournament "Champions Cup 2024"
    When I view "Registration Status"
    Then I should see the following for each registered team:
      | Status              |
      | Manager Registered  |
      | Players Count       |
      | Registration Valid  |
    And teams with less than 8 players should be marked "Incomplete"
    And teams with more than 14 players should be marked "Over Limit"