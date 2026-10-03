## ADDED Requirements

### Requirement: Operator-controlled pilot enrollment roster
The pilot SHALL use one operator-managed university or dormitory roster containing a unique student identifier, the operator-approved delivery email, assigned housing pool and allocation-cycle eligibility. Enrollment SHALL require possession of a one-time invitation delivered to that exact roster email. Knowledge of a student identifier or use of an arbitrary email SHALL NOT establish eligibility. Imports SHALL report duplicate/conflicting rows without silently overwriting existing claims.

#### Scenario: Attempt to claim another student's identity
- **WHEN** a caller submits a known roster student identifier with a different email address
- **THEN** the system sends no invitation to that address, grants no access and returns the generic enrollment response.

#### Scenario: Conflicting roster import
- **WHEN** an operator imports duplicate identifiers or an already claimed identifier with a conflicting email
- **THEN** the operator receives a row-level conflict report and affected records are not silently replaced.

### Requirement: Pending enrollment cannot access the pilot
Enrollment initiation SHALL create only a pending intent or disabled pending account. The recipient SHALL activate credentials by completing the invitation at the approved email; an unauthenticated initiator's chosen password SHALL NOT become an active password merely because another person verifies an email. Discovery, requests and allocation SHALL require active enrollment, verified delivery email, active user status, assigned housing pool and the active allocation cycle. Existing accounts SHALL require explicit roster reconciliation rather than automatic approval.

#### Scenario: Pending or unreconciled account
- **WHEN** a pending enrollment or legacy account attempts to discover users, invite a roommate or join an allocation
- **THEN** the request is denied with an actionable eligibility state and no other student's data is exposed.

### Requirement: Housing scope is enforced by the backend
The system SHALL have one active allocation cycle for the pilot and operator-assigned housing pools. A student SHALL NOT self-edit pool or cycle eligibility. Discovery and request eligibility SHALL be restricted to mutually permitted users in the same active cycle and housing pool, with any configured pool admission rules checked by the server. Operator changes affecting active membership or allocation SHALL require conflict resolution and a reason before committing.

#### Scenario: Direct cross-pool request
- **WHEN** a student submits another housing pool's user identifier directly to a profile or request endpoint
- **THEN** the API rejects access or treats the target as unavailable without leaking pool membership details.

### Requirement: Public profiles expose a minimal explicit projection
All peer-facing profile, match, request, group, notification and export responses SHALL use an explicit safe projection. Raw questionnaire answers, student identifiers, email addresses, recovery state and administrator notes SHALL NOT be visible to other students, including accepted peers and group members. The owner SHALL be able to inspect their own submitted information through an authenticated self-service view. Legacy endpoints SHALL enforce the same rules or be removed.

#### Scenario: Pending and accepted relationships
- **WHEN** a student reads another student's profile before requesting, while pending, after acceptance or as a group member
- **THEN** none of these relationships reveals raw answers, student identifier or email through the API or rendered page.

### Requirement: Discovery and explanations require separate consent
Discovery SHALL require an explicit opt-in explaining the use of questionnaire data to generate a heuristic compatibility score. Category explanations SHALL require both participants to opt in separately and SHALL contain only approved non-sensitive summaries. Raw answers and tobacco, religion or other sensitive-trait explanations SHALL NOT be disclosed, even when both participants opted in. Withdrawing discovery consent SHALL immediately remove future discoverability and prevent new requests while preserving explicitly explained existing membership history.

#### Scenario: Only one person opts into explanations
- **WHEN** two eligible discoverable users are matched but only one opted into category explanations
- **THEN** the result contains the permitted general score without category-level disclosure.

#### Scenario: Both people opt in with sensitive answers
- **WHEN** both participants opt into explanations and a sensitive questionnaire dimension contributed to internal eligibility
- **THEN** no output names, infers through a category label, or reproduces that sensitive answer.

### Requirement: Account correction follows field authority
Students SHALL edit permitted display fields and questionnaire responses through authenticated self-service. Student identity, approved delivery email, housing pool and cycle eligibility corrections SHALL require operator review with a reason. Changing the approved email SHALL require verification of the replacement approved address and SHALL NOT redirect pending recovery messages automatically. Operators SHALL receive an impact preview for corrections affecting existing requests, groups or allocations.

#### Scenario: Correcting an assigned student's housing pool
- **WHEN** an operator attempts a pool correction that conflicts with an active allocation
- **THEN** the system displays the conflict and requires the allocation workflow to resolve it rather than silently moving the student.

### Requirement: Deactivation and deletion preserve individual allocation safety
Students SHALL request deactivation or deletion without contacting a database administrator. Such requests SHALL revoke sessions and remove the account from discovery and new requests immediately. Unassigned membership and pending requests SHALL be resolved using the group lifecycle rules. An assigned student's account SHALL enter a visible pending-exit state until an operator removes only that student's assignment; other members' beds SHALL remain allocated. After the operational exit, deletion SHALL remove personal profile, answers and credentials while retaining only required pseudonymous allocation/audit records within the retention policy. The requester SHALL receive a reference and acknowledgement of the pending process before access is revoked.

#### Scenario: Assigned student requests deletion
- **WHEN** a member of an allocated group requests account deletion
- **THEN** their discovery and authentication access end immediately, the operator receives an individual exit case, and no other group member loses their assignment.

### Requirement: Retention and erasure have testable pilot bounds
The launch operator SHALL publish a pilot retention policy before enabling real enrollment. Initial policy bounds SHALL be 90 days for audit events and closed allocation history, 30 days for report content, and 30 days for backup copies. Audit age SHALL begin at event creation, allocation-history age at closure, and report age at creation. Active allocation records SHALL retain only operationally necessary data until closure. Scheduled erasure SHALL enforce configured periods within these bounds; unresolved reports approaching expiry SHALL be escalated before their contents expire. Restore procedures SHALL replay pending erasures before opening restored data to users or outbound workers. These operational defaults SHALL NOT be represented as a legal compliance determination.

#### Scenario: Expired retained data
- **WHEN** retained report, audit or closed-allocation records pass their configured retention boundary
- **THEN** scheduled processing removes or irreversibly anonymizes the relevant data and records only a non-identifying maintenance result.

#### Scenario: Restore contains a previously deleted account
- **WHEN** a backup containing personal data erased after that backup is restored
- **THEN** erasure records are reapplied before user access or message sending is enabled.

### Requirement: Blocking prevents unwanted discovery and requests
An authenticated student SHALL block another student. Blocking SHALL remove mutual discovery and prevent new direct requests in both directions, cancel pending requests between them with a generic unavailability reason, and hide block-specific reasons from the blocked person. Blocking SHALL NOT silently evict anyone from an existing group or room; shared-group/allocation conflicts SHALL provide an operator support path.

#### Scenario: Blocked user bypasses the interface
- **WHEN** a blocked participant calls profile or invitation endpoints directly
- **THEN** the target remains unavailable and no new request is created.

### Requirement: Reports produce reviewed cases without automatic punishment
Students SHALL submit a bounded report with a category, optional description and relevant user/request reference. Report creation SHALL provide an acknowledgement and visible case status. Reports SHALL be accessible only to the reporter and authorized operators, SHALL be rate limited, and SHALL NOT automatically suspend, penalize matching or release an allocation. Operator action SHALL require a reason and auditable status transition; report text SHALL be safely rendered.

#### Scenario: Unverified complaint against an allocated user
- **WHEN** a complaint is submitted about an allocated student
- **THEN** an operator case is created while the student's eligibility and allocation remain unchanged until an authorized reviewed action occurs.

### Requirement: Operator privacy access is limited and audited
Operator views SHALL provide identity verification, enrollment, group, allocation and support information needed for their role. Raw questionnaire answers SHALL be excluded from normal operator responses, audit views and exports. Access to student identity records and all sensitive administrative mutations SHALL be authorized and audited with actor, purpose or reason, target and result. Public privacy text SHALL accurately describe actual visibility, use, consent and retention.

#### Scenario: Operator inspects a student's history
- **WHEN** an authorized operator opens the student operational record
- **THEN** permitted enrollment and allocation history is available, raw questionnaire answers are absent, and sensitive identity access is recorded.
