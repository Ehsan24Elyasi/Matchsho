## ADDED Requirements

### Requirement: Explicit two-person group formation
The system SHALL allow an eligible solo user to send another eligible solo user a request naming a mutually accepted target capacity. The sender's action SHALL count as consent to that exact proposal, and the receiver's acceptance SHALL create one group containing exactly those two users. Final acceptance SHALL revalidate eligibility, current questionnaire revisions, agreed capacity, and the absence of existing memberships. A request originally addressed to a solo user SHALL NOT silently become consent to join a subsequently formed group. The system SHALL enforce at most one current group membership per user in the database.

#### Scenario: Two solo users form a group
- **WHEN** the recipient accepts a still-valid proposal from another solo user for a mutually accepted capacity
- **THEN** one transaction SHALL mark the request accepted and create one group with the two users and that exact target capacity

#### Scenario: A participant joins elsewhere before acceptance
- **WHEN** either participant joins another group after a solo proposal was sent
- **THEN** the original proposal SHALL require explicit refresh and the appropriate group-consent workflow before any admission
- **AND** accepting it directly SHALL NOT merge groups or transfer existing members

### Requirement: Unanimous group admission with revision-bound consent
Joining an existing group SHALL use an admission proposal approved by the candidate and every current member. A group containing an inactive, suspended, or pending-closure member SHALL be unavailable for new admissions until membership is resolved; those members SHALL NOT be omitted from the consent snapshot. The proposal SHALL identify the group, target capacity, candidate, membership revision, and questionnaire revisions used for compatibility validation. The system SHALL commit membership only after every required approval refers to that exact snapshot and current eligibility passes. Membership changes, relevant answer revisions, or a target-capacity change SHALL clear stale approvals and expose a reconfirmation state. Refreshing a proposal SHALL display the changed membership and capacity before collecting approvals against the new snapshot. Group-to-group merging SHALL be prohibited in the pilot.

#### Scenario: Every existing member participates in admission
- **WHEN** two of three group members approve a candidate who also accepted
- **THEN** the proposal SHALL remain pending and the candidate SHALL not become a member
- **AND** the third member's valid approval SHALL trigger atomic final validation and admission

#### Scenario: Approval becomes stale after a member joins
- **WHEN** one candidate joins a group while another proposal has approvals from the previous membership revision
- **THEN** the other proposal SHALL require reconfirmation from the candidate and the full current membership
- **AND** old approvals SHALL not authorize admission

#### Scenario: Existing groups cannot be implicitly merged
- **WHEN** users in two different existing groups attempt to accept a request between them
- **THEN** the server SHALL reject the merge and SHALL preserve both memberships and capacities

### Requirement: Capacity and eligibility use current transactional state
All membership-changing operations SHALL share one transaction policy that serializes conflicting operations on affected participants, groups, proposals, and rooms in a documented deterministic order. The bounded pilot may implement this with one shared transaction-level domain lock acquired by every competing mutation. After obtaining the required locks, the operation SHALL reread membership, assignment, capacity, proposal status, approval revisions, and eligibility from current database state. It SHALL NOT use previously loaded relationship collections to authorize a write. Final admission SHALL enforce member count no greater than target capacity, unique user membership, absence of assigned participants, and current bilateral compatibility with every member. Failure SHALL roll back status, membership, audit, and notification-event changes together.

#### Scenario: Two candidates compete for the last place
- **WHEN** two independent PostgreSQL connections simultaneously finalize different admissions into a three-member group with capacity four
- **THEN** at most one admission SHALL succeed and committed membership SHALL not exceed four
- **AND** the other operation SHALL return a conflict or reconfirmation result without partial membership

#### Scenario: Allocation races with admission
- **WHEN** final admission and administrative allocation target the same group concurrently on independent PostgreSQL connections
- **THEN** the serialized result SHALL either allocate the complete admitted membership or reject admission after allocation
- **AND** committed occupancy SHALL equal the actual assigned membership

### Requirement: Single-winner request state transitions
A proposal SHALL have a pending state and terminal accepted, rejected, cancelled, or expired outcome, with a recorded reason where relevant. Pending proposals whose snapshot changes SHALL remain nonterminal but require reconfirmation. Only the authenticated candidate or applicable members SHALL approve their own consent; only the initiator SHALL cancel, and the receiver for a direct proposal or any required participant for an admission proposal SHALL be able to reject. Terminal transitions SHALL use a locked row or equivalent conditional write and SHALL release active-request uniqueness. Accepted state, new membership, audit event, and notification events SHALL commit atomically. Repeating an identical terminal action SHALL return the recorded result without duplicate effects; attempting a competing terminal action SHALL return a conflict.

#### Scenario: Acceptance and cancellation race
- **WHEN** accept and cancel run concurrently against one pending proposal using independent PostgreSQL connections
- **THEN** exactly one terminal outcome SHALL commit
- **AND** an accepted outcome SHALL have its committed membership while a cancelled outcome SHALL not create membership

#### Scenario: A client retries after a lost response
- **WHEN** the authorized actor retries the same successful final acceptance
- **THEN** the server SHALL return the recorded accepted result without adding members, creating another group, or duplicating domain notifications

### Requirement: Pending requests are retained only while meaningful
Successful admission SHALL NOT indiscriminately reject every pending request involving the admitted users. Requests still meaningful for the current group and remaining capacity SHALL be retained with refreshed consent requirements. Proposals that now imply prohibited group merging, involve blocked or inactive users, or cannot fit SHALL become unavailable with an explicit reason and a suitable cancelled or expired terminal outcome when irrecoverable. Availability SHALL also be rechecked at read and action time. The system SHALL not label a system-invalidated proposal as a human rejection.

#### Scenario: A group still has room after one acceptance
- **WHEN** one candidate joins a group whose capacity still permits a different pending candidate
- **THEN** the other proposal SHALL remain available for renewed approvals against current membership rather than being automatically rejected

#### Scenario: A retained proposal is no longer actionable
- **WHEN** a pending proposal would now require merging two groups or admitting to a full assigned group
- **THEN** the UI and API SHALL identify its current unavailability and SHALL refuse acceptance without altering memberships
- **AND** any terminal invalidation SHALL record the system reason separately from a participant rejection

### Requirement: Expiry and participant notifications
New direct and admission proposals SHALL expire seven days after creation, using server UTC time. Reconfirmation SHALL NOT extend the original expiry; a new invitation SHALL be required after expiration. The system SHALL enforce expiry during reads and actions as well as scheduled cleanup, and expiration SHALL clear active-request uniqueness. Creation, renewed-consent requirements, acceptance, rejection, cancellation, and expiration SHALL create durable in-app notifications and transactional email-outbox events according to notification preferences. Notification content SHALL exclude questionnaire answers and private constraint reasons.

#### Scenario: An expired request is acted on before cleanup
- **WHEN** acceptance is attempted more than seven days after proposal creation before the cleanup worker has run
- **THEN** the API SHALL expire or reject the proposal as expired and SHALL not admit the candidate
- **AND** a new legitimate request SHALL not be blocked by the expired active-request key

#### Scenario: Email delivery is temporarily unavailable
- **WHEN** a proposal becomes accepted while SMTP is unavailable
- **THEN** its membership change and durable notification/outbox records SHALL commit together and email retry SHALL not recreate the admission

### Requirement: Safe departure and migration of legacy invitations
A member of an unassigned group SHALL be able to leave without changing another member's membership. The departure SHALL increment membership revision, invalidate pending approval snapshots, and delete an empty group. A member of an assigned group SHALL submit an individual departure request for operator review instead of releasing the whole group's room. Migration SHALL preserve existing groups and assignments, increment or initialize membership revisions, and cancel legacy pending invitations with the explicit reason `policy_upgrade` because they lack current consent snapshots. The system SHALL notify affected users and allow new proposals under the updated rules.

#### Scenario: Departure from an unassigned group
- **WHEN** one of three members leaves an unassigned group
- **THEN** the two others SHALL remain in that group and stale admission approvals SHALL require reconfirmation

#### Scenario: Assigned departure cannot release others' places
- **WHEN** an assigned member requests to leave
- **THEN** the system SHALL create a reviewable individual departure request and SHALL preserve the existing assignment until an administrator resolves it

#### Scenario: Legacy invitations are upgraded without assumed consent
- **WHEN** the policy migration processes old pending invitations
- **THEN** those invitations SHALL become cancelled with reason `policy_upgrade`, active uniqueness SHALL be cleared, and existing accepted memberships SHALL be preserved
