## ADDED Requirements

### Requirement: Responsive Persian visual system
The web application SHALL use one documented set of typography, spacing, color, focus, control, and surface tokens across the landing page, student pages, and operator pages. Persian content SHALL use RTL layout, correct regular and bold font weights, readable form widths, and responsive result grids without horizontal page overflow at widths 360, 390, 768, 1280, and 1440 CSS pixels. Person cards SHALL use consistent avatar sizing and distinguish users through their displayed names and deterministic initials or an approved avatar, without requiring personal photographs.

#### Scenario: Desktop and mobile layouts remain readable
- **WHEN** a student opens the main pages at each supported viewport width
- **THEN** text, controls, and navigation remain inside the viewport, the regular font uses its regular-weight asset, and a desktop results page uses multiple columns where the content width permits

#### Scenario: Long names and mixed-direction identifiers
- **WHEN** a page displays a long Persian name, a Latin email address, or a numeric identifier
- **THEN** the layout wraps or truncates with an accessible full value, preserves the identifier direction, and does not overlap adjacent controls

### Requirement: Landing page and navigation work at first paint
The landing page SHALL present its main heading and primary action fully within the initial viewport at 1280 by 720 and 390 by 844 CSS pixels at 100 percent zoom. Decorative content SHALL not reserve a preceding full-screen block or cover interactive content. The mobile menu SHALL be closed initially, hidden at the desktop breakpoint, and explicitly opened and closed by an accessible button. The application SHALL use one shared navigation component with the active item derived from the current route.

#### Scenario: Landing page opens without scrolling
- **WHEN** the landing page finishes its initial resource load at either acceptance viewport
- **THEN** the primary heading and action are visible without scrolling, and the mobile menu is absent from the desktop layout

#### Scenario: Mobile menu and active destination
- **WHEN** a keyboard or touch user opens the mobile menu and selects a destination
- **THEN** the menu closes, its expanded state is updated, focus is moved appropriately, and only the current destination is marked active in the visible shared navigation

### Requirement: Questionnaire communicates meaning and preserves work
The questionnaire SHALL display understandable behavior and preference questions from the active questionnaire schema, descriptive response labels, the meaning of range endpoints, required versus optional status, purpose of sensitive questions, and completion progress. Editing SHALL prefill the owner's saved answers. Authenticated unfinished answers SHALL be stored as an owner-scoped, schema-versioned draft so navigation and refresh do not silently lose work; raw answers SHALL not be stored in browser localStorage, persistent URL state, or browser telemetry. A draft from an incompatible schema SHALL require explicit review and re-answering instead of silently reinterpreting numeric values.

#### Scenario: Edit an existing questionnaire
- **WHEN** a student opens questionnaire editing with a compatible saved response
- **THEN** saved values and meaningful labels are shown, and saving updates the response without erasing unanswered optional fields through an unrelated navigation event

#### Scenario: Resume an unfinished draft
- **WHEN** a student answers questions, receives confirmation that the draft is saved, and refreshes or returns through navigation
- **THEN** the same authenticated owner can resume those answers and no other account can read the draft

#### Scenario: Questionnaire version has changed
- **WHEN** an old draft or response cannot be represented by the current schema
- **THEN** the page explains that completion is required again and does not present a compatibility score based on silently converted answers

### Requirement: Core journeys are keyboard and assistive-technology accessible
The application SHALL use semantic links, buttons, form labels, fieldsets, and native or equivalently accessible radio groups for registration, sign-in, questionnaire completion, profile selection, invitations, and operator actions. All interactive controls SHALL be keyboard reachable, radio choices SHALL support expected arrow-key behavior, focus SHALL remain visible, and dialogs SHALL manage focus and restore it when closed. Errors SHALL be associated with the affected controls and announced; asynchronous outcomes SHALL use an accessible live status region. Normal text SHALL meet a 4.5:1 contrast ratio and large text and meaningful control boundaries SHALL meet 3:1.

#### Scenario: Complete the student journey with a keyboard
- **WHEN** a student uses only Tab, Shift+Tab, arrow keys, Enter, Space, and Escape to sign in, complete the questionnaire, open a profile, and send an invitation
- **THEN** every operation is reachable, the current focus is visible, and no clickable-only card or display-none input blocks the journey

#### Scenario: Correct a validation failure
- **WHEN** a form submission fails validation
- **THEN** an error summary or the first invalid field receives useful focus, each error names its field, and screen-reader status announces the failure without relying only on color

### Requirement: Routes are recoverable and fetch each resource once
Entity pages SHALL include a non-sensitive entity identifier in their route and load authorized data from that identifier. One route dispatcher SHALL handle clicks, refresh, direct links, and browser back and forward navigation. Each transition SHALL trigger at most one request per required feature resource, excluding explicit retry, pagination, or data invalidation. A superseded route response SHALL not overwrite the active page. Missing, inaccessible, and invalid identifiers SHALL result in an appropriate state without leaking entity data.

#### Scenario: Refresh and history preserve the selected profile
- **WHEN** a student opens an authorized profile, refreshes its URL, then navigates back and forward
- **THEN** the same selected profile is reconstructed from the route and the correct navigation state is displayed

#### Scenario: A route transition does not duplicate reads
- **WHEN** a navigation action changes the route to requests or matches
- **THEN** the feature resource is requested once and a resulting hash or history event does not trigger a second equivalent request

#### Scenario: A stale response arrives after navigation
- **WHEN** a slow profile response completes after the user has navigated to another profile
- **THEN** it cannot replace the content or available actions for the current profile

### Requirement: Interface states preserve the truth of server outcomes
All data-driven pages SHALL distinguish loading, successful empty results, unauthorized access, forbidden access, not found, conflict, and retryable transport or server errors. A failed request SHALL never be represented as an empty group, empty request list, or lost record. Mutations SHALL prevent accidental duplicate submission, announce success only after a confirmed result, and refresh authoritative state after a conflict. Retry SHALL preserve user input where appropriate and SHALL not create a duplicate mutation.

#### Scenario: Group lookup fails
- **WHEN** the group endpoint returns a timeout or server error
- **THEN** the page displays a recoverable failure and retry action instead of saying that the student has no group

#### Scenario: The invitation changed while the page was open
- **WHEN** an acceptance action returns a state or capacity conflict
- **THEN** the page explains the conflict, reloads the authoritative request and group state, and does not show acceptance as successful

### Requirement: Matching and group decisions are understandable
Match cards and profile pages SHALL show only authorized profile information and consented, non-sensitive compatibility explanations from the matching contract. The score SHALL be labeled as a compatibility indicator, not a probability or guarantee of a successful relationship. Invitation and group controls SHALL explain the proposed members, capacity, consent requirements, current status, expiry, and the effect of each available action. Unavailable actions SHALL have a human-readable reason derived from the current server state.

#### Scenario: Review a suggested roommate
- **WHEN** a student opens a suggestion
- **THEN** the page displays the general alignment indicator and provides category explanations only where the matching consent contract permits, without revealing raw questionnaire responses or a student number, and it displays an invitation action only when the server indicates eligibility

#### Scenario: Review a membership or allocation action
- **WHEN** a student reviews a proposed membership change or departure from an allocated room
- **THEN** the page identifies the affected membership, distinguishes a pending review from a completed change, and never describes a student's departure action as permission to release every member's room

### Requirement: Student account and notification workflows are usable
Students SHALL have discoverable pages for account information correction, session management, withdrawal or account deletion requests, blocking, reporting, and support contact. Sensitive actions SHALL follow the backend authorization and reauthentication contracts. Durable notifications SHALL expose unread state, event time in the configured pilot timezone, a link to the current authorized entity state, and readable notices for invitations, membership decisions, allocation decisions, and operator responses. Marking a notification read SHALL not perform the linked domain action.

#### Scenario: Act on an old notification
- **WHEN** a student follows a notification for an invitation that has expired or been resolved
- **THEN** the linked page shows its current state and does not offer an obsolete acceptance action

#### Scenario: Request help or withdraw
- **WHEN** a student submits a supported account or safety request
- **THEN** the interface confirms receipt, displays its review status and reference, and identifies the support route without promising that a pending review is already complete

### Requirement: Operators can complete pilot work without direct database edits
Authorized operators SHALL have searchable, server-paginated views of students, eligibility verification, invitations requiring attention, groups ready for review, room allocations, support reports, withdrawal requests, and audit history. Operators SHALL be able to perform authorized verification, review, allocation correction, and resolution actions through the interface with a required reason where specified by the domain contract. Sensitive action confirmation SHALL state the affected people and resulting capacity before submission. Exports SHALL respect operator authorization, prevent spreadsheet formula execution, and exclude unnecessary sensitive fields.

#### Scenario: Resolve an allocation problem
- **WHEN** an operator finds a student and prepares an allocation correction
- **THEN** the interface shows current membership, allocation history, affected occupants, and the projected capacity; the confirmed authorized action is recorded with the operator's reason

#### Scenario: Review a large queue
- **WHEN** an operator searches or filters a queue with more records than its page size
- **THEN** the server returns a bounded page, the interface provides next and previous navigation, and the filter state remains visible

### Requirement: Dynamic content is rendered safely
Untrusted names, profile fields, reasons, messages, and server errors SHALL be rendered with context-safe DOM APIs or an equivalently enforced escaping mechanism. URL destinations SHALL use allowlisted schemes and expected application routes. Text escaping SHALL not be reused as attribute or URL escaping. Content Security Policy SHALL remain a defense in depth measure, and sanitization tests SHALL not depend on CSP blocking execution.

#### Scenario: A name contains markup and attribute delimiters
- **WHEN** a card or profile renders a name containing quotation marks, angle brackets, an event attribute string, or a script-like payload
- **THEN** it appears as inert text, does not create unexpected attributes or nodes, and cannot change a link destination or execute behavior even in a test environment without CSP

### Requirement: Initial assets have measurable budgets and respect motion preferences
At a cold browser cache, the landing page's automatically fetched initial HTML, CSS, JavaScript, fonts, and images SHALL total no more than 600 KiB of transferred encoded response bodies, excluding API responses, under the documented acceptance fixture. A logo asset SHALL be at most 40 KiB and an avatar image at most 80 KiB. Images SHALL declare dimensions, below-the-fold media SHALL be deferred, production assets SHALL be versioned, and the page SHALL not impose a timed splash before useful content. Reduced-motion preferences SHALL disable nonessential animation; essential content and the primary action SHALL remain visible without waiting for decorative JavaScript.

#### Scenario: Measure a fresh landing load
- **WHEN** the acceptance browser loads the landing page with its cache disabled at 390 by 844 and 1280 by 720
- **THEN** the saved resource-size report meets the total and individual asset budgets and includes the fonts and all automatically loaded hero resources

#### Scenario: Use reduced motion or fail decorative scripting
- **WHEN** reduced motion is enabled or a decorative script fails to initialize
- **THEN** the page remains readable and actionable without a mandatory delay, and nonessential motion is absent when reduced motion is enabled
