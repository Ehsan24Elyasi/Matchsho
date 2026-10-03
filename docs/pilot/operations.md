# Matchsho pilot operations

This runbook supports one institution, one allocation cycle and a limited invited cohort. Completing code or local tests does **not** authorize real users. Start a local record from `artifacts/pilot/release-record.example.json`. The designated institution operator must complete `artifacts/pilot/release-record.json`; `python scripts/release_gate.py artifacts/pilot/release-record.json` fails while a required external check is pending. Generated records/reports stay out of Git; CI publishes reports as artifacts.

## Local isolated stack

Requirements: Docker Compose v2, Python 3.11+, free loopback ports 8080/8025 and subnet 172.30.88.0/24. Use a separate project/environment for each disposable dataset. Never copy the real backend `.env` into a test.

```sh
python scripts/prepare_dev.py --output .env.pilot-local
docker compose --env-file .env.pilot-local -p matchsho-pilot-local config --quiet
docker compose --env-file .env.pilot-local -p matchsho-pilot-local up --build -d --wait --wait-timeout 180
docker compose --env-file .env.pilot-local -p matchsho-pilot-local exec -T matchsho-backend python create_admin.py
```

Open http://localhost:8080 and the local-only Mailpit sink http://localhost:8025. Read the generated operator credential from the restricted env file. This sink is not real delivery evidence. API and database ports are private. `migrate` completes before API/worker start; replicas never run their own schema migrations. The runtime image must use Python 3.11 and PostgreSQL 16.

Production uses **only** `compose.production.yaml`. Development disables DB TLS explicitly and never claims production security. Dedicated dev credentials and fixture files must not be committed.

Each API container runs one Uvicorn process. `ARGON2_CONCURRENCY=2` bounds simultaneous64MiB password hashing/verification without reducing Argon2 cost; the shared PostgreSQL limiter remains independent. Increase container memory before increasing process count or hashing concurrency.

## Production configuration and trust boundary

1. Fill a restricted file outside the checkout using `.env.production.example`; generate independent random signing and Fernet outbox keys. Store age decryption keys separately from the application host.
2. Supply immutable scanned `BACKEND_IMAGE` and `FRONTEND_IMAGE` references (`registry/name@sha256:...`), exact source revision, institution, cycle, pools and support contact.
3. Set PostgreSQL `DATABASE_URL` with `sslmode=verify-full&sslrootcert=/run/db-ca/root.crt` and URL-encode credentials. Mount the issuing CA as `DB_CA_DIRECTORY/root.crt`. Verify actual hostname and invalid-CA rejection on the target host.
4. Configure the public HTTPS origin and allowed public hostname plus `127.0.0.1` for health checks. Mount certificate/key as `TLS_DIRECTORY/fullchain.pem` and `privkey.pem`, readable by container UID/GID 101. Keep the private key readable only by its owner/group.
5. Nginx terminates HTTPS directly on 8443, published as 443. It overwrites `X-Forwarded-For`, `X-Real-IP`, `X-Forwarded-Proto`, `X-Forwarded-Host`, request ID and strips `Forwarded`. Uvicorn trusts **only** the frontend's fixed private IP 172.30.88.10. Backend port is not published. Do not insert another proxy/load balancer without redesigning and testing this chain.
6. Outbound SMTP uses STARTTLS with certificate verification. Set host, port, username, password and sender. Preserve previous outbox keys through `OUTBOX_KEYS_JSON` during key rotation until pending events/retained backups no longer need them.
7. Do not print `docker compose config` output with real credentials. Use `config --quiet`.

```sh
docker compose --env-file /secure/matchsho.env -f compose.production.yaml config --quiet
docker compose --env-file /secure/matchsho.env -f compose.production.yaml pull
docker compose --env-file /secure/matchsho.env -f compose.production.yaml run --rm --no-deps migrate
docker compose --env-file /secure/matchsho.env -f compose.production.yaml up -d --wait
```

Bootstrap the first operator as a one-off job, supplying `ADMIN_EMAIL` and `ADMIN_PASSWORD` from the secret manager via inherited environment, never literal command arguments. Run `docker compose ... run --rm --no-deps -e ADMIN_EMAIL -e ADMIN_PASSWORD matchsho-backend python create_admin.py`. Remove bootstrap secrets afterward. The existing operator's password is not reset on rerun.

`/api/health/live` is process health; `/api/health/ready` requires DB and supported schema. SMTP failure is measured separately and must not make every healthy API replica unready. Nginx liveness is `/healthz`.

## Signing and encryption key rotation

The current release also uses `SECRET_KEY` for HMAC identifiers in throttle buckets, outbox recipient bindings and the deletion ledger. Replacing it is **not a supported JWT-only rotation**: it invalidates sessions, changes quota keys, makes old queued recipient bindings fail verification, and prevents matching existing erased-identity tombstones. Draining mail alone does not solve the ledger problem; erased student identifiers cannot be recovered to recompute their digests.

Keep the current signing/HMAC secret available only through the secret manager for this release and controlled restores. Before a planned change, close admission and mutations, stop outbound workers, export a fresh independent erasure ledger and take an encrypted backup. First deploy a reviewed migration that separates JWT signing from stable/versioned HMAC verification and preserves matching of every existing tombstone. Prove old-token rejection, closed-identity reimport rejection, erasure replay and pending-message handling in an isolated restore before reopening. The current release contains no automatic migration for this operation. For suspected signing-key compromise, take the service offline and revoke sessions immediately; keep enrollment and outbound delivery closed until that migration and recovery review are complete. Never bypass ledger mismatch checks or delete tombstones to make a rotation succeed.

Fernet outbox-key rotation is separate and supported through `OUTBOX_KEYS_JSON`. First distribute a keyring containing both old and new versions to **all** API and worker processes while the old version remains active. After every process can decrypt both versions, switch `OUTBOX_KEY_VERSION` and its matching `OUTBOX_KEY` to the new version. Confirm old queued events finish or expire and retain old decrypt keys, under restricted access, until retained backups no longer require them. Never change the bytes behind an existing version label or remove an old key while its payloads remain sendable. Use controlled synthetic messages to verify each phase; do not print payloads, links or keys as evidence.

## Release, migration and rollback

Record source, both lockfile hashes, image digests, supported Alembic revision, test artifacts and prior compatible image. To regenerate backend locks, use an isolated Python 3.11 environment with `pip==25.3` and `pip-tools==7.5.2`, then run `pip-compile --allow-unsafe --generate-hashes --strip-extras` for both requirements inputs; review changed versions and rerun scans. The pip pin belongs only to this disposable lock compiler; runtime images remove package-install tooling. Uvicorn access logging is disabled in every deployment entrypoint because it includes query strings; use the application's sanitized structured events and Nginx's path-only access logs.

For this initial pilot migration, put the previous deployment in maintenance/offline mode first. Take and verify the pre-migration encrypted backup. Run `python -m pilot.preflight` against the nominated source in restricted maintenance context, resolve reported inconsistency through approved reconciliation, and run `python -m pilot.migrate`. Its PostgreSQL advisory lock prevents overlapping release migrations. Never edit already-applied Alembic revision files.

Deploy the API and worker, confirm readiness, then serve the matching fingerprinted frontend. HTML revalidates; only content-hashed assets are immutable. Run the published-edge browser smoke and copied-token/privacy checks before admission. During a later expand/migrate/contract change, explicitly state which old/new schema revisions each image supports; remove old columns only after every process has moved and the rollback window has closed.

Rollback uses a **recorded schema-compatible** image. Stop/review if the old image lacks session revocation or peer privacy guards. There is no automatic Alembic downgrade or database replacement. If schema compatibility is absent, keep maintenance mode and follow the approved isolated restore/reconciliation plan. Rehearse failed migration, two successive releases and compatible rollback in staging; record timestamps. A documentation command is not evidence that rehearsal happened.

For a repeatable local rehearsal after building `matchsho-backend:local-test` and `matchsho-frontend:local-test`, run `python scripts/release_rehearsal.py --confirm-disposable --report artifacts/pilot/evidence/release-rehearsal-local.json`. This creates a uniquely named stack with its own PostgreSQL and loopback port, injects a transactional migration failure, checks the startup gate, builds a harmless fingerprinted frontend variation, rejects an incompatible client protocol before mutation, and restores the original guarded frontend. It cleans up only its own containers/volumes. Its synthetic second release verifies the mechanism; target-host rollout and rollback of the nominated production images remain separate launch evidence.

## Optional Kubernetes

Kubernetes is not needed for the pilot. Render examples using `python scripts/render_k8s.py --release <unique-id> --backend-image <digest-ref> --frontend-image <digest-ref> --proxy-cidr <actual-private-pod-cidr> --dns-resolver <cluster-DNS-IP> --output <new-directory>`. Install the runtime secret (uppercase config keys as above), DB CA secret `matchsho-db-ca` with `root.crt`, and TLS secret `matchsho-tls`.

Enforce the supplied NetworkPolicy with a capable CNI before traffic. The frontend LoadBalancer preserves client IP (`externalTrafficPolicy: Local`) and terminates TLS itself. Only frontend pods may connect to the API. The proxy CIDR is explicit, never `*`. Apply network policy/config, create the unique `matchsho-migrate-<release>` Job, wait for completion, and only then roll deployments. Do not reapply a different template under an old Job name. Verify health probes on the actual cluster and confirm load-balancer client identity before launch.

## Alert ownership and action

The designated support operator owns application alerts; the deployment operator owns DB, backup and TLS incidents. Fill actual names/on-call destination in the release record. Run `scripts/pilot_alerts.py` every minute through the host scheduler using a restricted operator account, `OPS_EMAIL`, `OPS_PASSWORD` and HTTPS `OPS_ALERT_WEBHOOK` from the secret manager.

```sh
python scripts/pilot_alerts.py --origin https://YOUR-HOST --backup-report /var/lib/matchsho-evidence/backup.json --state /var/lib/matchsho-evidence/alerts.json
```

The script stores no credentials, sends only alert names, and notifies on a meaningful change/recovery. An unsuccessful delivery preserves old state so the next run retries. `--dry-run` evaluates without sending or updating state. Exit 1 means an actionable incident; the scheduler itself must alert if the script fails to run. Test by stopping the staging worker, observing delivery at the real operator destination, then restoring it; this receipt is required launch evidence.

| Signal | Threshold | Response |
|---|---|---|
| API readiness loss | check fails; operator verifies persistence | Check DB connectivity, certificate and supported schema; do not hide by changing liveness |
| Worker loss | heartbeat older than 120s | Check process, DB, key version and SMTP; restart after cause fixed |
| Pending email | oldest >300s | Check delivery dashboard and provider health; do not read encrypted payloads |
| Terminal mail | any terminal failure | Correct provider/config cause; operator-safe retry only when source token remains valid |
| Backup failure | failed report or no verified backup within24h | Restore backup job/offhost credentials; prohibit new release until backup+drill usable |
| API latency/5xx/conflicts/429 | inspect API metrics and structured logs | Correlate request ID, endpoint and release; preserve no secrets/answers in logs |

Keep access/application logs bounded, restrict read access, and avoid exporting query strings or raw request bodies. Log request IDs and outcome; do not attach authentication links to incident reports.

## Encrypted off-host backup and safe restore

Provisional RPO=24h, RTO=4h, backup retention=30d, drill before launch and monthly. Operator host needs PostgreSQL16 client tools, `age`, `rclone` and the release's Python environment. Configure a real off-host rclone backend (S3/B2/Azure/SFTP/Swift/Drive/OneDrive) with a dedicated prefix ending `/matchsho-backups`. Local, alias and root destinations are rejected. Grant remote credentials access only to this prefix; private decryption keys belong to a separate controlled location.

Load `SOURCE_DATABASE_URL` securely, then schedule daily:
```sh
python scripts/pilot_backup.py --destination backup:institution/matchsho-backups --recipient age1PUBLIC-RECIPIENT --report /var/lib/matchsho-evidence/backup.json --prune-expired
```

The command streams `pg_dump` directly through age, uploads ciphertext, downloads/verifies it with rclone, and removes only matching expired encrypted backup files inside the guarded prefix. No plaintext dump is written. A failed command cannot produce a passing report.

The deletion ledger must be replicated independently of old backups. After erasures and before every drill export `python -m pilot.maintenance --export-erasure-ledger /secure/current-erasure-ledger.json`, encrypt/upload it to a separate restricted off-host ledger object, and verify freshness. Never restore an old dump using only the ledger contained in that dump. The current drill requires a reachable source for identity verification; disaster recovery without the source needs a separately reviewed identity/ledger recovery procedure and remains closed to users.

Download the encrypted backup and its saved report. Provision a separate empty DB named `matchsho_restore_<drill>` with separate credentials and no app/worker clients. Set `RESTORE_DATABASE_URL`, `SOURCE_DATABASE_URL` and `NO_OUTBOUND_EMAIL=true`. Deny outbound SMTP at the restore network as well. The harness refuses the live identity, nonempty targets, wrong confirmation, old backups and ledgers older than one hour.

```sh
python scripts/pilot_restore.py --backup /secure/backup.dump.age --backup-report /secure/backup.json --identity /secure/age-key.txt --ledger /secure/current-erasure-ledger.json --confirm-target matchsho_restore_drill --report /secure/restore-evidence.json --smoke python scripts/restore_smoke.py
```

The harness atomically restores, migrates forward, reapplies current erasures, checks preflight invariants, and runs the required student/operator smoke against the restored DB. It never enables the worker or authorizes traffic. An operator must inspect the report, compare recovered users/groups/allocations/audit history and confirm age<=24h and total duration<=4h. Plain ledger/report files must remain restricted and be removed under the retention policy. A successful backup upload without this drill does not pass the recovery gate.

## Staging performance envelope

Use `scripts/pilot_load.py --fixture /secure/load-fixture.json --confirm-fixture <fixture-id> --report <path>`. The private fixture requires `disposable:true`, `fixture_id`, loopback/HTTPS `origin`, 50 `users` (email/password plus optional path bindings), `reads`, draft PUT `writes` (objects with path/method/body), `draft_sleep_times`, `invariant_command` and `write_snapshot_command` (argv arrays), `machine`, `database_size` and `rate_limit_configuration`. Provision users via roster/claim API and the test mail sink before measuring; `scripts/prepare_load.py` creates the private fixture and snapshot helper for the isolated local stack.

The harness warms up30s, measures600s at50 simultaneous sessions, uses an80/20 read/write mix, reports aggregate and matching-specific p95 plus per-endpoint request/success counts, and checks invariants before/after. It sends and verifies protocol3. Reads and matching each must meet500ms p95, ordinary writes1s p95, 5xx<=1%, and zero unexpected HTTP, protocol, invariant or privacy violations. The draft/matching fixture expects no conflicts (`expected_conflicts:[]`); successful requests must exercise every endpoint. The initial50-way credential-hashing batch is recorded separately with a60s request deadline to accommodate bounded Argon2 admission; ordinary requests retain a10s deadline. Real SMTP timing is a separate delivery record. The full run and representative fixture are required staging evidence; short developer smoke does not satisfy it.

Each request is deep-copied, and each actor alternates their private draft sleep value between23:15 and23:00. The first measured value differs from that actor's actual post-warmup baseline. Repeating identical JSON is insufficient: ORM dirty checking may skip the UPDATE. After warm-up, a barrier pauses all actors while a read-only database snapshot is captured. Postflight verifies the PostgreSQL table-update delta covers all successful measured writes, all50 draft timestamps advance, final values match the last successful requests, and published-answer hashes remain unchanged. Public evidence records aggregate counts/hashes and fixture/harness hashes, not credentials or answer rows. `load-write-precheck.json` proves two changed requests cause exactly two database updates; a constant-body preliminary run cannot satisfy acceptance.
