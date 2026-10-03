# Matchsho

Matchsho (مچ‌شو) helps invited students find compatible roommates and lets a dormitory operator manage groups and room allocation. The pilot supports one institution, one active allocation cycle and a limited cohort. Completing local tests does not authorize admission of real students.

## Current pilot

- Roster-controlled email activation; the recipient chooses the password.
- Argon2id, HttpOnly cookies, CSRF, database-backed revocable sessions and rotating refresh tokens.
- Private versioned questionnaire, server drafts, bilateral preferences and explicit matching consent.
- Purpose-aware profile access and two-way blocks; peer DTOs expose only allowed display fields.
- Unanimous, revision-bound group admission and individual departures that preserve roommates' places.
- Audited operator allocation, move, reconciliation, support and delivery queues.
- Encrypted transactional email outbox and an independent delivery/retention worker.
- Persian RTL interface, keyboard-accessible controls, fingerprinted assets and a same-origin `/api`.

The authoritative API contract is [docs/pilot/api-contract.md](docs/pilot/api-contract.md). Deployment and release requirements are in [docs/pilot/operations.md](docs/pilot/operations.md). Local test reports, screenshots and release records are generated artifacts excluded from Git; see [artifacts/pilot/README.md](artifacts/pilot/README.md).

## Architecture

```text
Browser -> Nginx -> /api -> FastAPI -> PostgreSQL 16
                              |           |
                              +-- outbox -+-> independent worker -> SMTP
```

`backend/pilot/` separates identity, privacy, matching, invitations, housing and delivery. `frontend/js/` separates API/session/router/UI and features. Production ships only `frontend/dist/`, built from the original landing design, shared dashboard styles, local fonts and verified artwork.

## Isolated local stack

Use Docker Compose v2 and Python 3.11+. Choose unused loopback ports. Generate dedicated synthetic credentials instead of copying an existing backend environment or database:

```sh
python scripts/prepare_dev.py --output .env.pilot-local
docker compose --env-file .env.pilot-local -p matchsho-pilot-local config --quiet
docker compose --env-file .env.pilot-local -p matchsho-pilot-local up --build -d --wait --wait-timeout 180
docker compose --env-file .env.pilot-local -p matchsho-pilot-local exec -T matchsho-backend python create_admin.py
```

The defaults are frontend `http://localhost:8080` and local Mailpit `http://localhost:8025`. The current review session uses frontend port **8088** because 8080 was occupied. The generated env file contains the local operator credential and must stay out of Git. API and database ports are private. Emails reach the test sink through the same outbox worker used in deployment; authentication links are not written to application logs.

Compose runs the advisory-locked migration job before API/worker startup. Outside Compose, configure a disposable database and run `python -m pilot.migrate` from `backend/` explicitly before starting the API. `start.sh` starts only the API. Never run migrations automatically from each API replica. Preserve existing data and perform preflight/reconciliation before upgrading a real database.

## Frontend and tests

```sh
cd frontend
npm ci --ignore-scripts
npm run build
npm test
npm run test:contrast
npm run test:e2e
```

The production build uses shared CSS and browser ES modules; there is no Tailwind build step. The default API is same-origin `/api`. The optional test server supports an explicit `API_TARGET` development proxy; see [frontend/README.md](frontend/README.md).

Backend dependencies are locked with hashes in `backend/requirements.lock` and `backend/requirements-dev.lock`. Install them in an isolated **Python 3.11** environment. Backend tests use disposable SQLite files and separate random PostgreSQL schemas; PostgreSQL concurrency evidence requires `TEST_DATABASE_URL` and `SECURITY_TEST_DATABASE_URL` pointing to a dedicated database whose name ends in `_test`. Never point tests at a real application database.

CI in `.github/workflows/ci.yml` runs Python3.11/PostgreSQL16 regression and migration tests, lint, dependency/secret/image scans and Playwright behind the built Nginx image with a disposable DB/mail sink. Local UI fixture tests complement the actual stack journey. Test evidence does not imply remote CI has run for the uncommitted checkout.

## Real deployment

Follow [docs/pilot/operations.md](docs/pilot/operations.md) and the Persian [operator guide](docs/pilot/operator-fa.md). Use `compose.production.yaml`, independently generated keys, immutable scanned registry images, HTTPS, Secure cookies, explicit trusted peers and PostgreSQL `sslmode=verify-full` with the issuing CA mounted. Production uses same-origin access; do not enable development CORS settings or publish the API directly. SMTP requires verified TLS.

Kubernetes is optional; render the templates with `scripts/render_k8s.py` using release-specific migration-job names and actual image/proxy/DNS values. Do not apply unrendered templates. No deployment has been authorized solely by this README.

Daily encrypted off-host backups, a measured isolated restore with a current independent erasure ledger, delivered alerts, real SMTP receipt and institutional roster/policy/support sign-off are required before launch. Start a local release record from `artifacts/pilot/release-record.example.json`, record actual evidence in `artifacts/pilot/release-record.json`, and run:

```sh
python scripts/release_gate.py artifacts/pilot/release-record.json
```

The gate deliberately fails while required evidence or the designated operator's admission authorization is missing. Rollback to the old API without privacy/session guards is prohibited; destructive automatic downgrade is disabled. Read the runbook before rotating signing/HMAC or outbox keys.

## Privacy and license

Peer responses exclude email, student ID and raw questionnaire answers. The owner and authorized operator have separate minimal views; matching explanations require consent and exclude sensitive categories. Retention and account closure behavior are described in [the privacy notice](frontend/privacy.html) and the operator guide. Confirm the institution's actual support contact and policy before admitting students.

MIT. See [LICENSE .txt](LICENSE%20.txt).
