## ADDED Requirements

### Requirement: Versioned behavior and preference questionnaire
The system SHALL publish a versioned questionnaire that separates actual behavior, accepted roommate behavior, importance, and a hard-requirement flag. Version 2 SHALL require usual sleep time, usual wake time, cleaning frequency, guest frequency, and usual room noise/activity. Time values SHALL use local quarter-hour slots and accepted time intervals SHALL support crossing midnight. Cleaning, guest, and noise questions SHALL use versioned, explicitly labelled categorical options and nonempty accepted-option sets. Importance SHALL be 1, 2, or 3, defaulting to 2; hard requirements SHALL default to false. Actual behavior and accepted values SHALL require explicit answers rather than inferred defaults. An optional tobacco question SHALL allow no answer. New pilot questionnaires SHALL NOT collect beliefs or religious affiliation.

#### Scenario: A student supplies actual habits and expectations
- **WHEN** a student submits the current questionnaire with all core behaviors, accepted values, and valid importance values
- **THEN** the server SHALL persist the questionnaire version and a new answer revision and return the saved answers to that student
- **AND** editing SHALL load those saved answers without substituting defaults

#### Scenario: Invalid or ambiguous input is rejected
- **WHEN** a submission omits a core behavior, supplies an empty accepted set, uses an unknown option, or supplies an invalid time slot
- **THEN** the server SHALL return field-specific validation errors and SHALL NOT replace the previously saved complete revision

#### Scenario: Overnight preferences are interpreted consistently
- **WHEN** a student accepts sleep times from 23:00 through 01:00 and another student's usual sleep time is 00:30
- **THEN** the accepted interval SHALL include 00:30 despite crossing midnight

### Requirement: Shared eligibility before scoring
The system SHALL use one purpose-aware authorization and eligibility policy across discovery, profile visibility, request creation, and final request acceptance. The following joinability conditions SHALL apply to discovery and new admissions. Current members SHALL retain access to safe profiles of their existing group, and request participants SHALL retain authorized historical request context after assignment, without gaining new invitation permission or any private fields. Eligible participants SHALL have an active account, verified roster eligibility for the active pilot cycle, verified email, a complete current questionnaire, and current discoverability consent. The policy SHALL enforce compatible operator-assigned housing pools, no block in either direction, no shared existing group, no assigned participant, and available capacity in the target group. A solo participant SHALL only receive other eligible solos or unassigned groups with space; a grouped participant SHALL only recruit eligible solos. Group-to-group joining SHALL be unavailable. Discovery SHALL evaluate these conditions before selecting or limiting results.

#### Scenario: Unusable candidates do not occupy results
- **WHEN** the candidate population contains users in full groups, assigned users, blocked users, unverified roster entries, and eligible users
- **THEN** only eligible solo candidates and eligible groups with space SHALL occupy returned result slots

#### Scenario: Eligibility changes after discovery
- **WHEN** a candidate becomes assigned, blocked, inactive, or otherwise ineligible after a result was displayed
- **THEN** request creation or acceptance SHALL recheck current eligibility and refuse the operation without a partial group change

### Requirement: Bilateral hard constraints and explainable alignment score
The system SHALL evaluate each participant's hard requirements against the other's actual behavior before scoring. A failed hard requirement or unknown value needed by a hard requirement SHALL exclude the pairing. For remaining pairs, each answered directed preference SHALL contribute its importance to the denominator and SHALL contribute that same importance to the numerator only when the other participant's actual behavior belongs to the accepted values or interval. The reported score SHALL equal the nearest integer to 100 multiplied by numerator divided by denominator, with half values rounded upward. An optional unknown value SHALL exclude only the corresponding unassessable directed preference from scoring. The system SHALL label the result as preference alignment, SHALL NOT describe it as success probability, and SHALL expose the scoring version. Results SHALL sort by descending alignment and ascending stable profile or group identifier on ties; no minimum score SHALL override hard constraints or eligibility.

#### Scenario: Importance alone does not create compatibility
- **WHEN** two users both give sleep importance 3 but their actual sleep times violate the other's accepted interval
- **THEN** the sleep preferences SHALL earn no satisfied weight
- **AND** the pair SHALL be excluded if either violated sleep preference is a hard requirement

#### Scenario: Score calculation is reproducible
- **WHEN** assessed directed preferences have a combined weight of 20 and satisfied preferences have a combined weight of 15
- **THEN** the result SHALL report alignment 75 with the active scoring version

#### Scenario: An optional unknown does not defeat a hard requirement
- **WHEN** a user has not answered the optional tobacco behavior and a candidate requires an answer satisfying a hard tobacco preference
- **THEN** the pairing SHALL be excluded without revealing that tobacco preference as the reason

### Requirement: Group compatibility and explicit target capacity
A group containing any suspended, inactive, or pending-closure member SHALL be unavailable for new admissions until its membership is resolved; such members SHALL NOT be omitted from consent or compatibility checks. The system SHALL evaluate a solo candidate against every current member of a group and SHALL exclude the candidate if any pair fails eligibility or a hard requirement. A group's displayed alignment with a candidate SHALL be the minimum eligible pairwise score. Accepted room capacities SHALL be separate from the weighted questionnaire and SHALL be selected from capacities configured in active rooms for the participant's eligible housing pool. A new group SHALL have an explicitly selected target capacity present in every founding member's accepted set. Each later entrant SHALL explicitly accept that target capacity. The server SHALL NOT silently choose the minimum preference or reinterpret a previous answer as consent to a different capacity. Group formation SHALL NOT reserve a room.

#### Scenario: Average scores cannot hide one incompatible member
- **WHEN** a candidate has pairwise scores 95, 80, and 45 with a group's three members and no hard conflict
- **THEN** the group result SHALL report alignment 45
- **AND** if any one pair instead has a hard conflict the group SHALL not be offered to that candidate

#### Scenario: Room-size preferences have no common value
- **WHEN** two solo users have disjoint accepted capacities or the requested capacity is absent from eligible configured inventory
- **THEN** group creation SHALL fail with a capacity-selection error and SHALL NOT derive an alternative capacity

### Requirement: Peer privacy and opt-in explanations
Peer profile, match, request, and group responses SHALL NOT include raw questionnaire answers, student identifiers, email addresses, exact habit values, optional tobacco answers, or private constraint failure reasons. This restriction SHALL apply equally to unrelated users, pending requests, accepted requests, and current group members. A discoverable user SHALL consent to the generic alignment score being visible to authorized matching peers. Non-sensitive category explanations SHALL be included only when both participants explicitly opted into the current explanation policy; otherwise the response SHALL contain no category explanations. The allowlist SHALL be limited to sleep schedule, cleaning, guest, and noise compatibility summaries and SHALL exclude exact values and tobacco-related reasons. A group explanation SHALL require the candidate's consent and the consent of every group member whose comparison contributes to it. Arbitrary compatibility lookup between two other users SHALL be forbidden.

#### Scenario: A pending or accepted request does not reveal private information
- **WHEN** a user reads a peer profile before sending, while pending, after acceptance, or as a group member
- **THEN** all response bodies SHALL omit peer student identifiers, email, raw answers, and exact habit values

#### Scenario: Explanations require both opt-ins
- **WHEN** both users consent to discovery but only one opts into category explanations
- **THEN** authorized discovery SHALL show the generic score without category explanations
- **AND** withdrawing explanation consent SHALL suppress explanations in subsequent responses

#### Scenario: Another pair's score is private
- **WHEN** a user requests the compatibility score between two accounts neither of which is their own
- **THEN** the API SHALL reject the request without returning a score or private questionnaire data

### Requirement: Questionnaire migration preserves meaning and existing occupancy
The migration SHALL retain legacy questionnaire data privately under its original version without converting importance answers into invented actual behavior. Existing users SHALL require completion of the current questionnaire and consent before discovery or new admissions. Updating answers SHALL increment the answer revision and invalidate outstanding admission approvals that relied on the old revision. Questionnaire changes SHALL NOT automatically dissolve a group, evict a member, change a group's target capacity, or release an assigned place. The UI SHALL explain required recompletion and the separate operator process for changing existing allocation.

#### Scenario: A legacy account upgrades
- **WHEN** an account with only version 1 answers opens matching after migration
- **THEN** it SHALL be prompted to complete version 2 and SHALL be absent from discovery until completion
- **AND** any existing group membership and room allocation SHALL remain intact

#### Scenario: A member changes a relevant answer
- **WHEN** a group member saves a new questionnaire revision after approving a pending candidate
- **THEN** final admission SHALL require fresh compatibility validation and renewed approvals against the new revision
- **AND** the existing membership and room allocation SHALL not change automatically
