## ADDED Requirements

### Requirement: Single-pilot allocation eligibility
The pilot SHALL use one configured institution, one active allocation cycle, and operator-assigned housing pools. Each allocatable room SHALL belong to the active cycle and explicitly permit a housing pool. Each allocated member SHALL have verified active roster eligibility for that cycle and permitted pool. A room with unspecified restrictions or unresolved migration conflicts SHALL be unavailable for new allocations. The system SHALL retain the group-level room-assignment model; individual bed numbering and multi-institution tenancy SHALL not be prerequisites for this pilot.

#### Scenario: A member is outside a room's pool
- **WHEN** an administrator attempts to allocate a group containing a member whose verified housing pool is not permitted by the target room
- **THEN** the entire allocation SHALL fail without assigning any member or changing occupancy

#### Scenario: A legacy room has no reviewed eligibility
- **WHEN** an administrator attempts a new allocation to a migrated room without an explicit active-cycle pool policy
- **THEN** the server SHALL reject the allocation and identify the required operator review
- **AND** existing assignments SHALL remain intact pending reconciliation

### Requirement: Administrative authority for final allocation
Only administrators SHALL create, move, or remove final room allocations or alter room restrictions and capacities. Ordinary group members SHALL NOT directly unassign the whole group, including through legacy routes. Group creation and matching SHALL be described as roommate planning and SHALL NOT claim a reserved room. An allocation SHALL require the target room's physical capacity to equal the group's agreed target capacity, enough remaining places for every member, and current eligibility for every member. A partially filled group SHALL occupy only the number of places equal to its current members, and an assigned group SHALL be closed to self-service admission. For new allocations, a room SHALL host at most one group; unused places in that room SHALL not be assigned to an unrelated group without a separately specified consent workflow. Existing multi-group rooms SHALL be preserved and flagged for reviewed reconciliation, not silently evicted. New writes SHALL enforce the one-group invariant under a room lock or the shared transaction-level domain lock serializing every allocation and membership write, and any database uniqueness constraint SHALL be installed only after legacy conflicts are resolved.

#### Scenario: A student attempts whole-group unassignment
- **WHEN** any ordinary member calls the current or legacy room-unassignment endpoint
- **THEN** the server SHALL deny the operation and SHALL preserve the group's allocation and all members' places

#### Scenario: The room size differs from agreed capacity
- **WHEN** an administrator attempts to assign a group that agreed to a four-person room to an eight-person room
- **THEN** the operation SHALL fail without silently changing the group's accepted target capacity

#### Scenario: An incomplete group is assigned
- **WHEN** an administrator assigns an eligible three-member group targeting capacity four to a compatible room with at least three places available
- **THEN** the group SHALL occupy three places and SHALL become unavailable for self-service admission

### Requirement: Atomic allocation and authoritative occupancy
Assignment, move, unassignment, membership removal, and room-capacity edits SHALL run within transactions using a common deterministic lock policy for affected groups and rooms. A shared transaction-level domain lock is permitted for the bounded pilot when every competing mutation acquires it before reading mutable state. The server SHALL refresh current memberships and assignments after obtaining locks. Authoritative room occupancy SHALL equal the count of all current members of groups assigned to that room, including suspended, inactive, or pending-closure accounts until an explicit departure or removal commits. A stored occupancy counter, if retained, SHALL be a transactionally maintained cache checked against that count. The database and service SHALL prevent negative occupancy, occupancy greater than room capacity, multiple assignments for one group, and multiple current memberships for one user. Moves SHALL release the old places and acquire the new places in one transaction; a failed move SHALL preserve the original assignment.

#### Scenario: Two administrators compete for remaining places
- **WHEN** two independent PostgreSQL connections allocate groups that together exceed a room's remaining capacity
- **THEN** only an admissible allocation SHALL commit and authoritative occupancy SHALL never exceed capacity

#### Scenario: Another group attempts to take spare places
- **WHEN** a room already hosts a partially filled group and an administrator attempts to assign an unrelated group to its unused places
- **THEN** the server SHALL reject the new allocation and preserve the first group's assignment even when the arithmetic sum would fit

#### Scenario: Suspension does not free physical occupancy
- **WHEN** an assigned student's account is suspended or enters pending closure without a committed individual removal
- **THEN** that student's current membership SHALL continue to count toward room occupancy and no place SHALL become available through the account-state change

#### Scenario: A move cannot be completed
- **WHEN** an administrator moves a group to a room that becomes full before the transaction obtains its locks
- **THEN** the transaction SHALL fail and the group's previous room and occupancy SHALL remain unchanged

#### Scenario: Capacity is reduced below occupancy
- **WHEN** an administrator attempts to set room capacity below the authoritative assigned-member count
- **THEN** the server SHALL reject the edit without changing the room, groups, or assignments

### Requirement: Individual departure preserves other allocations
An assigned student SHALL be able to submit a departure request and track its pending, approved, or rejected outcome. An administrator SHALL resolve the request with a recorded reason. Approval or an independently justified administrative member removal SHALL remove only the selected member, release exactly one occupied place, increment the group's membership revision, and preserve all other memberships and their assignment. A group reduced to zero members SHALL have its assignment and empty group removed atomically. Rejected departure requests SHALL preserve every membership and allocation. Duplicate approval SHALL not release another place.

#### Scenario: One student leaves a four-person assigned group
- **WHEN** an administrator approves that student's departure
- **THEN** exactly that student's membership SHALL be removed, the other three members SHALL keep their group and room, and occupancy SHALL decrease by one

#### Scenario: An approval is retried
- **WHEN** an administrator retries approval of an already-approved departure request
- **THEN** the API SHALL return its recorded outcome without another occupancy decrement or duplicate notification

#### Scenario: The last member leaves
- **WHEN** an administrator removes the last member of an assigned group
- **THEN** the membership, group assignment, and empty group SHALL be removed in one transaction and the room occupancy SHALL decrease by one

### Requirement: Allocation audit and operator feedback
Every final allocation, move, whole-group unassignment, individual removal, departure resolution, and room-policy change SHALL record the authenticated administrator, UTC timestamp, operation reason, affected identifiers, and minimal before-and-after state in the same transaction. Before-and-after state SHALL cover affected memberships, room assignment, target capacity, and affected room occupancy as applicable, without recording questionnaire answers or credentials. Participants SHALL receive durable notices of their own changed allocation or departure outcome. Failed operations SHALL present actionable conflict information to the operator without claiming success or showing stale state as current.

#### Scenario: An operator moves a group
- **WHEN** a move commits successfully
- **THEN** an audit entry SHALL identify the actor, reason, previous and new rooms, affected members, and both rooms' before-and-after occupancy
- **AND** participants SHALL have durable notices identifying their new assignment

#### Scenario: An allocation fails validation
- **WHEN** a move or assignment fails because eligibility or capacity changed
- **THEN** the operator SHALL receive a conflict response suitable for refreshing current state
- **AND** the UI SHALL not show a successful assignment or substitute a generic empty state

### Requirement: Migration and reconciliation preserve occupied places
Before enabling new allocation writes, migration tooling SHALL produce a report of duplicate memberships, conflicting assignments, overcapacity, mismatched cached occupancy, missing room policies, and roster or pool mismatches. Migration SHALL preserve existing groups and assignments and SHALL NOT silently evict users, choose substitute rooms, infer eligibility, or rewrite historical migrations. Unresolved conflicts SHALL block new allocation operations for affected groups and rooms until an administrator records a reviewed reconciliation. Reconciliation SHALL use audited service operations, and occupancy backfill SHALL be calculated from actual current assigned memberships.

#### Scenario: Existing occupancy and memberships disagree
- **WHEN** preflight finds a room with cached occupancy three but four currently assigned members
- **THEN** it SHALL report the disagreement and prevent unreviewed new allocations affecting that room
- **AND** reconciliation SHALL set occupancy from reviewed membership truth rather than remove a member to fit the cache

#### Scenario: A legacy allocation violates the new pool policy
- **WHEN** preflight finds existing assigned members whose verified eligibility does not match the room policy
- **THEN** it SHALL flag the allocation for operator resolution while preserving occupied places
- **AND** the pilot release evidence SHALL identify unresolved affected records before opening new allocation writes
