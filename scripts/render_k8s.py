"""Render optional Kubernetes examples with immutable images and release-specific jobs."""
from __future__ import annotations

import argparse
import ipaddress
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--proxy-cidr", required=True, help="Actual frontend pod CIDR; NetworkPolicy MUST be enforced")
    parser.add_argument("--dns-resolver", required=True, help="Actual cluster DNS service IP")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", args.release):
        parser.error("Use a unique DNS-safe release id <=36 characters.")
    for value in (args.backend_image, args.frontend_image):
        if not re.fullmatch(r"[a-zA-Z0-9.:/_-]+@sha256:[a-f0-9]{64}", value):
            parser.error("Both images must be immutable sha256 digests.")
    network = ipaddress.ip_network(args.proxy_cidr)
    dns_resolver = str(ipaddress.ip_address(args.dns_resolver))
    if network.prefixlen == 0 or not network.is_private:
        parser.error("Proxy CIDR must be private and narrower than /0.")
    if args.output.exists():
        parser.error("Output directory already exists; release manifests are immutable.")
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True)
    for source in (root / "k8s").glob("*.yaml"):
        content = source.read_text(encoding="utf-8-sig")
        for old, value in {"__RELEASE_ID__": args.release, "__BACKEND_IMAGE__": args.backend_image,
                           "__FRONTEND_IMAGE__": args.frontend_image, "__PROXY_CIDR__": str(network)}.items():
            content = content.replace(old, value)
        (args.output / source.name).write_text(content, encoding="utf-8")
    nginx = (root / "frontend/nginx.production.conf").read_text(encoding="utf-8-sig")
    nginx = nginx.replace("resolver 127.0.0.11", f"resolver {dns_resolver}")
    config = f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: matchsho-nginx-{args.release}\ndata:\n  default.conf: |\n"
    config += "".join(f"    {line}\n" for line in nginx.splitlines())
    (args.output / "nginx-config.yaml").write_text(config, encoding="utf-8")
    print(f"Rendered {args.output}; apply NetworkPolicy, ConfigMap, migration Job, then deployments.")

if __name__ == "__main__":
    main()
