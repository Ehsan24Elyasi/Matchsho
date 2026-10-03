# Pilot verification artifacts

This directory keeps only the release-record template in Git. Copy `release-record.example.json` to a new local `release-record.json` and fill it with the nominated release's actual identities and evidence. Do not replace an existing operator record without preserving it.

`evidence/`, `private/` and `release-record.json` are generated local artifacts excluded from Git. Test screenshots and frontend reports under `docs/pilot/evidence/` are also excluded. The CI workflow creates its output directories and publishes reports through GitHub Actions artifacts.

Application code, automated tests, deployment files and operational scripts remain versioned. The template contains no local credentials, machine-specific image identity or prior successful verification claims. Run `python scripts/release_gate.py artifacts/pilot/release-record.json` after supplying actual evidence.
