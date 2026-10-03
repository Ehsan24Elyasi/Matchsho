## ADDED Requirements

### Requirement: Domain rules have maintainable module boundaries
The implementation SHALL retain the current FastAPI, PostgreSQL, and browser application architecture while separating backend API routing from authentication, matching, group, allocation, and email services, and separating frontend API/session access, routing, rendering, and feature workflows. Eligibility, transition authorization, and capacity invariants SHALL each have one authoritative implementation reused by relevant entry points. Framework replacement, microservices, Redis, Kubernetes adoption, and multitenancy SHALL not be prerequisites for this pilot.

#### Scenario: A domain rule is used by multiple entry points
- **WHEN** matching, invitation creation, invitation acceptance, or allocation evaluates an overlapping eligibility or capacity rule
- **THEN** it invokes the shared authoritative rule with the required transactional context instead of maintaining conflicting copies in route handlers or UI code

#### Scenario: Application modules are exercised in isolation
- **WHEN** the project runs its focused unit and integration suites
- **THEN** routing, services, and browser feature modules can be tested without starting unrelated UI workflows or importing a monolithic application script for each test

### Requirement: Deployed browser traffic uses a coherent same-origin stack
Production and the documented Compose profile SHALL route browser API requests through same-origin `/api` at Nginx, with matching API prefix handling, cookies, CSRF, CORS, CSP, and authentication behavior. Separate-origin development SHALL require an explicit development configuration. Backend ports SHALL not need public exposure for the documented stack to work. The reverse proxy and application SHALL enforce the trusted-proxy requirements of `identity-and-session-security`.

#### Scenario: A clean Compose deployment supports browser login
- **WHEN** a fresh isolated database and the documented Compose stack start and a browser opens the published frontend port
- **THEN** registration or invitation activation, verification through the test email sink, sign-in, authenticated reads, and a protected mutation succeed through real Nginx without editing frontend source or exposing a second backend port

#### Scenario: A client spoofs forwarded identity
- **WHEN** an external client sends arbitrary forwarded-IP headers through the published proxy
- **THEN** the application's effective network identity follows the trusted-proxy policy and the spoofed headers cannot reset or bypass rate limits or falsify the attributed client address

### Requirement: Production configuration fails closed
Production startup SHALL validate required secrets, public origin, cookie security, trusted proxy configuration, mail settings, and parsed database URL options. Remote production PostgreSQL connections SHALL require certificate and hostname verification equivalent to `sslmode=verify-full` with the configured trust chain; merely containing an `sslmode` key SHALL not satisfy validation. An isolated local development database SHALL use an explicit development profile rather than a production-mode bypass. Diagnostics SHALL identify invalid configuration without exposing credentials.

#### Scenario: An insecure database URL is supplied
- **WHEN** production is configured with missing TLS options, `sslmode=disable`, `allow`, `prefer`, or an option that does not verify the server identity
- **THEN** startup fails with a redacted actionable configuration error before accepting traffic

#### Scenario: Certificate verification fails
- **WHEN** the configured remote database presents an untrusted certificate or a certificate for another hostname
- **THEN** the connection is rejected and readiness remains false

### Requirement: Migrations preserve existing data and gate readiness
Database changes SHALL use new immutable Alembic revisions, provide preflight checks for incompatible or inconsistent existing records, and document any explicit operator remediation. Upgrades SHALL preserve existing records without silently fabricating eligibility, questionnaire meaning, membership, or consent. Readiness SHALL require both a working database connection and the schema revision supported by the running release; liveness SHALL not require database availability. Migrations SHALL run as a controlled release step before incompatible application traffic is admitted.

#### Scenario: Upgrade a representative existing database
- **WHEN** the migration suite upgrades a restored fixture containing users, legacy questionnaire answers, pending invitations, groups, and allocations
- **THEN** records remain traceable, legacy answers are marked for required recompletion, and inconsistent data causes an actionable preflight failure instead of silent destructive correction

#### Scenario: Schema is missing or incompatible
- **WHEN** the database answers `SELECT 1` but its schema revision is absent, behind, or unsupported by the release
- **THEN** readiness fails while liveness accurately reflects whether the process is running

### Requirement: CI verifies security and concurrency on the deployed runtime
Continuous integration SHALL build and test Python 3.11 application images against PostgreSQL 16, including migrations from empty and representative existing databases. It SHALL exercise sensitive data access, eligibility enforcement, revocable sessions, account recovery, shared rate limits, trusted proxy handling, durable email, and domain invariants. PostgreSQL concurrency tests SHALL use independent connections and coordinated competing transactions for acceptance versus acceptance, cancellation or rejection, membership changes, allocation, release, and departure. SQLite-only tests SHALL not constitute evidence for transactional correctness.

#### Scenario: Competing operations target the last available place
- **WHEN** independent PostgreSQL transactions attempt conflicting membership or allocation operations under controlled overlap
- **THEN** the resulting state satisfies capacity and membership invariants, exactly the allowed transition wins, and retries or losers receive a defined response without duplicate side effects

#### Scenario: Recovery and privacy regressions are introduced
- **WHEN** a change exposes a private field, accepts a revoked session, permits stale eligibility, or loses a committed outbox message after process failure
- **THEN** the relevant CI regression test fails and blocks the release candidate

### Requirement: Browser acceptance covers real proxy behavior and access needs
The release suite SHALL run Playwright journeys against built frontend and backend images through real Nginx, using a disposable PostgreSQL database and test email sink. It SHALL cover the complete student and operator journeys, direct links and refresh, browser history, conflicts, nonempty and empty states, server errors, keyboard operation, and supported viewport widths 360, 390, 768, 1280, and 1440. Assertions SHALL include critical geometry and accessibility behavior; screenshots alone SHALL not constitute functional evidence. Asset-size reports and failure traces SHALL be retained with the release evidence.

#### Scenario: A student and operator complete a pilot workflow
- **WHEN** the acceptance suite activates an eligible student, verifies email, completes the questionnaire, proposes and consents to membership, and obtains operator allocation
- **THEN** each role sees the authorized current state and the workflow completes without direct database modification or manual source edits

#### Scenario: A UI regression hides the main action or breaks keyboard input
- **WHEN** the landing action falls outside the specified first viewport or the questionnaire cannot be completed by keyboard
- **THEN** an explicit acceptance assertion fails at the affected viewport and retains a diagnostic trace

### Requirement: Builds are reproducible and scanned before release
Backend and frontend dependency versions SHALL be locked reproducibly, and the release SHALL identify source revision, lockfile hashes, and immutable container image digests. CI SHALL run lint, static or syntax checks, dependency vulnerability scanning, secret scanning, and container scanning. Unresolved applicable critical or high severity vulnerabilities and detected usable secrets SHALL block a pilot release. A scanner result claimed to be inapplicable SHALL include reproducible justification in the release record. Images SHALL continue to run without root privileges and production artifacts SHALL not embed secrets.

#### Scenario: A vulnerable dependency or secret enters the build
- **WHEN** a scanner detects an applicable critical or high vulnerability or a usable secret in source, image layers, or generated frontend artifacts
- **THEN** the release gate fails and identifies the affected component without printing the secret value

#### Scenario: Rebuild a release candidate
- **WHEN** the documented build is run from the recorded revision and lockfiles
- **THEN** it resolves the pinned dependency set, emits traceable image digests and a component inventory, and runs the same required checks

### Requirement: Operators can detect and investigate failures
The deployed application, proxy, database-dependent readiness, and email worker SHALL expose structured, correlated operational records and measurable health. Required measurements SHALL include API latency and errors, authentication throttling, domain conflicts, outbox depth, oldest pending mail age, retry and terminal-failure counts, and worker heartbeat. Logs SHALL redact passwords, tokens, raw questionnaire answers, and unnecessary student identifiers. Configured alerts SHALL cover sustained API failure, readiness loss, worker loss, excessive pending-mail age, and backup failure, with a documented owner and response steps.

#### Scenario: Mail delivery stops while the API remains available
- **WHEN** the worker stops or SMTP repeatedly fails beyond the configured alert threshold
- **THEN** the operator receives an actionable alert, can identify affected delivery states through authorized tooling, and can follow a documented recovery procedure without copying message tokens from logs

#### Scenario: Investigate a failed request
- **WHEN** an operator investigates a reported request identifier
- **THEN** correlated records reveal the relevant release, route, outcome, and authorized audit reference without revealing private questionnaire content or authentication secrets

### Requirement: Backups are useful only after an isolated restore drill
The pilot SHALL define a provisional recovery point objective of 24 hours and recovery time objective of 4 hours, take at least daily encrypted backups retained for 30 days, and restrict backup and restore access. Before admission of real pilot traffic and at least monthly thereafter, an operator SHALL restore a real backup into a separate isolated database, validate schema and data integrity, and run student and operator smoke workflows against that restored copy. The record SHALL include timestamps, recovered backup age, restore duration, checks, and the responsible operator. A backup command succeeding alone SHALL not satisfy the recovery gate.

#### Scenario: Prove the recovery objective
- **WHEN** the operator performs the required restore drill from the configured backup location
- **THEN** the recovered backup is no older than 24 hours, service validation finishes within 4 hours, and the restored users, groups, allocations, and audit history pass integrity and smoke checks

#### Scenario: Protect the original database during a drill
- **WHEN** a restore command is prepared
- **THEN** its documented guard verifies a separate target database and prevents accidental replacement of the running pilot database

### Requirement: Releases and rollback preserve API and asset compatibility
A release SHALL have a documented deployment order, immutable image references, a release-specific migration execution identity, and a rollback compatibility decision. Supplied Kubernetes migration examples SHALL use a distinct job identity per release so repeated deployment does not require mutation of an existing immutable job template; Kubernetes operation itself SHALL not be required for the Compose pilot. Frontend assets SHALL use content fingerprints with immutable caching while entry documents are revalidated, preventing a new API from being paired with accidentally cached old application code. Rollback SHALL use a schema-compatible previous image or an explicitly reviewed recovery plan and SHALL not automatically downgrade or destroy live data.

#### Scenario: Deploy two successive releases
- **WHEN** the documented release procedure deploys a new candidate after a previous successful release
- **THEN** its migration step executes with the intended unique release identity, entry documents reference the matching asset fingerprints, and readiness prevents unsupported API-schema combinations from serving traffic

#### Scenario: Roll back a failed release candidate
- **WHEN** the operator rehearses rollback on staging
- **THEN** the selected compatible image restores the expected workflows and data remains intact; if rollback is incompatible, the procedure stops and names the reviewed recovery path instead of running a destructive downgrade

### Requirement: Pilot performance is demonstrated within a stated envelope
The release SHALL include a repeatable staging load run of 50 concurrent simulated users for 10 minutes after warm-up, with recorded machine resources, database size, workload mix, and rate-limit configuration. Within that workload, read and matching API p95 latency SHALL be at most 500 milliseconds, ordinary transactional write API p95 SHALL be at most 1 second, and HTTP 5xx responses SHALL be at most 1 percent. Credential hashing and external SMTP latency SHALL be measured separately without weakening password hashing or making email delivery synchronous to satisfy the ordinary-write budget. The run SHALL produce zero capacity, membership, request-state, or privacy invariant violations. User-facing collections SHALL use bounded server pagination with a maximum page size of 100, and matching SHALL apply eligibility before ranking with query and latency evidence appropriate to the pilot size.

#### Scenario: Run the documented staging workload
- **WHEN** the performance harness executes the 50-user workload for the full measurement interval
- **THEN** the saved report includes latency distributions, failure counts, resource use, invariant checks, and separately reported authentication and email-worker measurements that meet the stated acceptance envelope

#### Scenario: A caller requests an unbounded collection
- **WHEN** a requests or operator-list endpoint receives no limit or a limit exceeding the supported maximum
- **THEN** it returns a bounded page with continuation information or a validation error and never loads an unbounded result into the response

### Requirement: Real pilot launch requires an evidence record
The release SHALL maintain a traceable acceptance checklist covering all 30 audit findings and distinguishing implemented code, automated verification, staging evidence, and operator-owned launch evidence. The first real pilot SHALL remain gated until the designated operator records production HTTPS and cookie verification, database TLS verification, real SMTP delivery, an approved student roster and dormitory allocation policy, support ownership, restore and rollback drills, working alerts, and review of unresolved release risks. Completing development artifacts or tests SHALL not be represented as completion of these external checks. The initial operating plan SHALL identify one university or dormitory, its allocation period, a limited invited cohort, and a named operator.

#### Scenario: Code checks pass but SMTP or roster approval is missing
- **WHEN** a release candidate has green CI but lacks required real-environment evidence
- **THEN** the release record states which operator checks remain pending and does not mark the pilot as launched or approve admission of real users

#### Scenario: Authorize the limited pilot
- **WHEN** the designated operator records all required evidence and confirms the approved cohort and rules
- **THEN** the release checklist identifies the exact deployable revision, verification dates, responsible operator, and rollback route for that limited pilot
