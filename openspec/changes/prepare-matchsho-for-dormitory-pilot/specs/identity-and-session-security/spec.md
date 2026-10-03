## ADDED Requirements

### Requirement: Database-backed revocable sessions
The system SHALL bind every access and refresh token to a stable random session identifier and the current user authentication version. Every authenticated request SHALL validate token signature, type, expiry, active user, authentication version, and a non-revoked unexpired database session. Access tokens SHALL expire after 15 minutes by default; sessions SHALL have a seven-day absolute lifetime by default. Tokens without the required session/version claims SHALL be rejected after migration.

#### Scenario: Copied token references a revoked session
- **WHEN** an authenticated request begins after its session revocation transaction has committed
- **THEN** the API returns 401 even if the copied token's signature and expiration remain valid.

#### Scenario: Legacy token after deployment
- **WHEN** a client presents a token issued before session/version claims were required
- **THEN** the client is required to sign in again without receiving protected data.

### Requirement: Logout and credential recovery revoke access atomically
Logout SHALL revoke the current session before clearing its cookies. Password reset SHALL consume the one-time reset token, change the password hash, increment the user authentication version, and revoke all user sessions in one transaction. Suspension and completed account deactivation SHALL also revoke all sessions. Login, refresh and recovery SHALL serialize against the same user security state and revalidate it after acquiring locks.

#### Scenario: Password reset races with login or refresh
- **WHEN** password reset overlaps login with the old password or refresh from an existing session
- **THEN** no session usable after reset commits is issued from the old credential or authentication version.

#### Scenario: Logout affects the selected device
- **WHEN** a user logs out of one active session
- **THEN** that session's access and refresh tokens fail on subsequent requests while independent active sessions remain valid.

### Requirement: Refresh tokens rotate within one session
The system SHALL rotate the refresh credential atomically without extending the session's absolute lifetime. A consumed refresh credential SHALL NOT issue a second set of credentials; detected replay SHALL revoke that credential's stable session, including a successfully rotated branch, so subsequent requests require a fresh login. Browser clients SHALL coordinate concurrent refreshes and SHALL distinguish an expired/revoked session from a transient service failure. Refresh transactions SHALL NOT create a replacement session after reset or suspension.

#### Scenario: Simultaneous refresh requests
- **WHEN** two workers receive the same refresh credential concurrently
- **THEN** at most one rotation succeeds and no duplicate session or independently valid refresh branch is created.

#### Scenario: A consumed refresh token is replayed
- **WHEN** a previously consumed refresh credential is presented again
- **THEN** its stable session is revoked and later access or refresh requests associated with that session are rejected, including credentials from an earlier successful rotation.

### Requirement: Owners can inspect and revoke their sessions
An authenticated owner SHALL be able to list their current sessions using minimal device, creation, last-use and expiry metadata and revoke one or all of their own sessions. Session secrets SHALL NOT be returned. One user SHALL NOT inspect or revoke another user's sessions through these self-service endpoints. Revocation SHALL apply the same immediate database checks as logout.

#### Scenario: Remove a lost-device session
- **WHEN** the authenticated owner revokes a listed session belonging to their lost device
- **THEN** subsequent requests from that session fail while the owner receives the resulting current session state without any token disclosure.

### Requirement: Secure credential and cookie handling
Passwords SHALL remain Argon2-hashed and SHALL NOT appear in logs, audit events or responses. Production authentication cookies SHALL be Secure, HttpOnly and SameSite-protected. All cookie-authenticated state-changing operations, including authentication and recovery operations, SHALL validate CSRF. Role checks SHALL use current database authorization rather than a stale token claim. Sensitive authentication responses SHALL use no-store caching.

#### Scenario: State change without CSRF proof
- **WHEN** a request with authentication cookies attempts a state-changing operation without valid CSRF proof
- **THEN** the API rejects it without mutating account, session, membership or allocation state.

#### Scenario: Removed administrator role
- **WHEN** an administrator's role is removed while an access token remains unexpired
- **THEN** the next administrative request is denied.

### Requirement: One-time recovery and verification tokens
Recovery and verification tokens SHALL be unpredictable, purpose-bound, hashed in the token table and consumed atomically. Verification tokens SHALL expire within 24 hours and password-reset tokens within one hour. Superseded, expired or already consumed tokens SHALL be rejected uniformly. Recovery SHALL send messages only to the account's approved delivery email.

#### Scenario: Concurrent token consumption
- **WHEN** two requests attempt to consume the same reset or verification token
- **THEN** exactly one successful state transition is possible and the other request has no side effects.

### Requirement: Atomic throttling shared by all workers
Authentication throttling SHALL use PostgreSQL-backed atomic counters keyed separately by action, effective client IP and a normalized account or enrollment identifier. Identifier keys SHALL use a keyed digest instead of storing plaintext email addresses in limiter records. Attempts SHALL be charged before expensive hashing, account creation or email enqueue, and persisted independently of failed business transactions. Expired buckets SHALL be removed by scheduled maintenance. A limiter storage failure SHALL fail protected authentication operations with retryable 503.

#### Scenario: Concurrent attempts reach the shared limit
- **WHEN** requests to two API workers consume the remaining allowance concurrently
- **THEN** no more than the configured allowance proceeds to expensive authentication work and excess attempts receive 429 with Retry-After.

### Requirement: Explicit authentication abuse limits
Default limits SHALL be 20 login attempts per normalized account and 200 per client IP in 15 minutes; three registration attempts per enrollment identity and 60 per IP in one hour; three combined resend/recovery email requests per recipient and 60 per IP in one hour with a 60-second recipient cooldown; and 200 invitation-activation/verification/reset token submissions per IP in 15 minutes. These values SHALL be configurable and the pilot's shared-campus-IP onboarding SHALL be tested. Successful login SHALL NOT reset an IP allowance or another account's allowance.

#### Scenario: Successful unrelated login between attacks
- **WHEN** failed attempts against account B are interleaved with successful logins to account A from the same IP
- **THEN** B's account allowance and the shared IP allowance remain consumed until their normal expiry.

### Requirement: Authentication responses resist account enumeration
Login errors SHALL use a uniform invalid-credentials response and perform a dummy password check for unknown accounts. Enrollment initiation and password-recovery requests SHALL use the same accepted response shape for unknown, unavailable and valid identities, subject to the same rate limits. The API SHALL NOT disclose a roster entry's delivery email or eligibility through these public responses.

#### Scenario: Unknown and enrolled addresses
- **WHEN** a caller submits validly formatted enrollment or recovery requests for unknown and registered identities
- **THEN** the public status and message do not reveal which identity exists or received a message.

### Requirement: Explicit trusted proxy chain
The deployment SHALL declare the trusted ingress and frontend proxy addresses. The public ingress SHALL overwrite incoming forwarded headers; frontend Nginx SHALL forward a single validated client address; the API server SHALL trust forwarded metadata only from its configured private proxy peers. The API port SHALL NOT be publicly exposed. IP throttling and audit SHALL use the same resolved address.

#### Scenario: Client supplies a forged forwarding chain
- **WHEN** a client sends fabricated X-Forwarded-For or X-Real-IP values through the public entry point
- **THEN** neither the effective throttle key nor the audited client address changes to the fabricated value.

### Requirement: Security events are observable without secrets
The system SHALL record authentication revocation, reset completion, administrative security changes and abuse-limit failures with request correlation and minimal actor/session references. Passwords, tokens, cookie contents, recovery links and questionnaire answers SHALL be excluded. Expected invalid credentials SHALL NOT be reported as internal application crashes; storage failures SHALL remain distinguishable for operators.

#### Scenario: Investigating failed account recovery
- **WHEN** an operator inspects correlated logs and permitted audit events for a recovery failure
- **THEN** the operator can distinguish rate limiting, invalid token and service failure without obtaining a usable credential or raw questionnaire data.
