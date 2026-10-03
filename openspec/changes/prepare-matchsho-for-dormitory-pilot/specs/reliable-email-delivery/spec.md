## ADDED Requirements

### Requirement: Business state and delivery intent commit together
Authentication invitation, verification and recovery messages and configured request/status email notifications SHALL use a PostgreSQL transactional outbox. The corresponding business change and delivery intent SHALL commit atomically with a unique stable event identifier. A successful enqueue response SHALL describe the message as queued rather than delivered. Rolled-back transactions SHALL NOT leave sendable events.

#### Scenario: Process stops immediately after enrollment commit
- **WHEN** the API process stops after committing a pending enrollment and its invitation event
- **THEN** a worker can deliver that event after restart without repeating enrollment creation.

#### Scenario: Business transaction is rolled back
- **WHEN** the operation fails before its transaction commits
- **THEN** no worker can send the related message.

### Requirement: Persisted recovery material is encrypted
Token validation records SHALL store only token hashes. Outbox payloads containing invitation, verification or recovery links SHALL be encrypted with authenticated encryption under a dedicated configured key separate from the JWT signing secret. Envelope metadata SHALL identify the encryption-key version, stable event identifier and expiry. Production startup SHALL reject missing or invalid encryption configuration. Plaintext tokens and links SHALL NOT appear in outbox metadata, logs, audit, operator views or exports.

#### Scenario: Reading the outbox table without its key
- **WHEN** an operator or diagnostic process reads outbox database rows
- **THEN** no plaintext usable invitation or recovery credential is present.

### Requirement: Workers use durable leases and bounded claims
One or more independent worker processes SHALL atomically claim due events using PostgreSQL row locking with skip-locked behavior and finite leases. Claims SHALL be committed before SMTP work, and SMTP network calls SHALL NOT hold the business database transaction open. A worker SHALL renew or finish only its owned lease; expired claims SHALL become available for recovery. Worker crashes SHALL NOT lose pending events.

#### Scenario: Two workers claim the same queue
- **WHEN** two workers concurrently poll due events
- **THEN** one event has at most one current lease owner and distinct events can progress independently.

#### Scenario: Worker dies before delivery
- **WHEN** a worker stops after claiming an event and before completing it
- **THEN** another worker can retry the event after the lease expires.

### Requirement: Delivery retries stop at explicit boundaries
Transient SMTP/network failures SHALL schedule durable retries with an initial delay of 30 seconds, exponential growth capped at 15 minutes, and at most six delivery attempts by default. Permanent recipient rejection SHALL become terminal without unlimited retries. Expired, used or superseded authentication tokens SHALL make their events non-sendable even if attempts remain. Exhaustion and expiry SHALL expose a safe terminal status.

#### Scenario: SMTP recovers after a temporary outage
- **WHEN** SMTP fails transiently and becomes available before the retry and token-expiry limits
- **THEN** the same queued event is retried and marked accepted without requiring the user to repeat registration.

#### Scenario: Reset link expires while queued
- **WHEN** a password-reset event reaches token expiry before successful SMTP acceptance
- **THEN** its payload is not sent, the event becomes expired, and the user can initiate a new rate-limited recovery request.

### Requirement: Duplicate delivery has bounded safe semantics
Enqueue SHALL deduplicate retries of the same logical business event using its stable event identifier. SMTP sends SHALL reuse a stable Message-ID. The system SHALL document at-least-once transport semantics rather than promising exactly-once delivery. A retry after an ambiguous SMTP result SHALL use the same still-valid one-time token and SHALL NOT create another account or repeat the underlying business transition.

#### Scenario: Crash after SMTP accepted a message
- **WHEN** SMTP accepted an event but the worker stopped before recording success
- **THEN** recovery can send a duplicate message with the same event identity while the underlying account or request operation occurs only once.

### Requirement: Stale tokens and superseded recipients cannot be sent
Before sending an authentication event, the worker SHALL verify the referenced account/enrollment, purpose, token state and approved recipient binding remain valid. Resend SHALL reuse a valid outstanding event/token within policy or atomically supersede previous events when issuing a new token. A changed approved email or cancelled enrollment SHALL cancel queued messages directed to the old binding. Status notifications SHALL omit unnecessary student identity and questionnaire information.

#### Scenario: Enrollment email is corrected before a retry
- **WHEN** an authorized correction replaces an enrollment's approved email while an old event is queued
- **THEN** the worker cancels that event rather than sending its credential to either an unverified replacement or the obsolete recipient.

### Requirement: Delivery state supports operational recovery
Outbox events SHALL expose pending, leased, retry-scheduled, SMTP-accepted, expired, cancelled and terminal-failure states to authorized operational tooling. SMTP acceptance SHALL NOT be labeled as proven inbox delivery. Operators SHALL see event purpose, age, attempt count, sanitized failure and recipient reference without link contents. A retry operation SHALL be audited and SHALL recheck expiry, token validity, recipient binding and delivery rate limits.

#### Scenario: Operator retries a terminal authentication event
- **WHEN** an operator requests retry of an event whose token is already expired
- **THEN** retry is rejected with a safe reason and no expired link is sent.

### Requirement: Sensitive delivery payloads are erased promptly
The worker or maintenance process SHALL erase encrypted authentication delivery payloads after SMTP acceptance or terminal expiry/cancellation/failure. A minimal non-secret delivery receipt SHALL be retained for at most 30 days by default. Reopening a terminal event after payload erasure SHALL require a fresh authorized issuance rather than restoring the old secret. Key rotation SHALL preserve decryption for still-sendable events until completion or expiry, then retire unused old keys through the operator procedure.

#### Scenario: Completed event inspected later
- **WHEN** an accepted or terminal authentication event is inspected after its completion cleanup
- **THEN** the event retains only permitted operational metadata and contains no recoverable delivery credential payload.

### Requirement: Worker health and delivery failures are observable
The system SHALL provide a worker heartbeat, pending age, retry count and terminal-failure observations. Operator alerts SHALL fire when the worker heartbeat is absent, a deliverable event remains pending more than five minutes, or an authentication event reaches terminal failure. SMTP outages SHALL NOT falsely mark the whole API unready. Operator recovery instructions SHALL distinguish queue, worker, encryption configuration and SMTP failures.

#### Scenario: API is healthy while SMTP is unavailable
- **WHEN** API and database operations succeed but SMTP delivery fails
- **THEN** queued work remains durable, delivery alerts identify the problem, and the API continues serving unrelated valid operations.

### Requirement: Local and production delivery are verifiable
The supported local stack SHALL provide a mail-capture service and run the same outbox worker path as production. Production SHALL use authenticated TLS-protected SMTP where required by its provider and SHALL NOT fall back to printing authentication links. The launch checklist SHALL require a real invitation, verification and recovery email to reach the designated test inbox with usable links before admitting real students.

#### Scenario: Browser enrollment in the local stack
- **WHEN** an invited test student completes the supported local enrollment flow
- **THEN** the mail-capture inbox receives the worker-delivered invitation and the browser can consume its link through the same-origin application.
