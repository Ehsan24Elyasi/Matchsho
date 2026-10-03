"""Record source/lock hashes and confirm built runtime Python files match the workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ops_common import now, run, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image", default="matchsho-backend:local-test")
    parser.add_argument("--frontend-image", default="matchsho-frontend:local-test")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    code = ("import hashlib,json; from pathlib import Path; root=Path('/app'); "
            "print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() "
            "for p in root.rglob('*.py') if '__pycache__' not in p.parts}))")
    image_sources = json.loads(run(["docker", "run", "--rm", "--entrypoint", "python", args.backend_image, "-c", code], timeout=120))
    mismatches = []
    for path, digest in image_sources.items():
        source = root / "backend" / path
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            mismatches.append(path)
    image_metadata = {}
    for kind, image in (("backend", args.backend_image), ("frontend", args.frontend_image)):
        record = json.loads(run(["docker", "image", "inspect", image]))[0]
        image_metadata[kind] = {"requested": image, "id": record["Id"], "repo_digests": record.get("RepoDigests", []),
                                "user": record["Config"].get("User"), "created": record["Created"]}
    locks = {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
             for path in ("backend/requirements.lock", "backend/requirements-dev.lock", "frontend/package-lock.json")}
    frontend_manifest = json.loads(run(["docker", "run", "--rm", "--entrypoint", "cat", args.frontend_image,
                                       "/usr/share/nginx/html/asset-manifest.json"]))
    report = {"kind": "local-image-source-identity", "created_at": now(), "status": "passed" if not mismatches else "failed",
              "git_head": run(["git", "-C", str(root), "rev-parse", "HEAD"]),
              "workspace_has_uncommitted_changes": bool(run(["git", "-C", str(root), "status", "--porcelain"])),
              "images": image_metadata, "lockfile_sha256": locks, "frontend_manifest": frontend_manifest,
              "runtime_python_sha256": image_sources, "source_mismatches": mismatches,
              "production_release_authorized": False}
    write_report(args.output, report)
    print(json.dumps({"status": report["status"], "source_mismatches": mismatches, "report": str(args.output)}))
    raise SystemExit(bool(mismatches))


if __name__ == "__main__":
    main()
