"""Command line entry point: ``governed-mcp``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from governed_mcp.app import ConfigError, build_http_app, build_server
from governed_mcp.config import Settings
from governed_mcp.devkeys import DEV_AUDIENCE, DEV_ISSUER, mint_from_dir, write_dev_keys
from governed_mcp.servers import REGISTRY


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="governed-mcp", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run one MCP server behind the gateway")
    serve.add_argument("server", choices=sorted(REGISTRY))
    serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")

    keys = sub.add_parser("dev-keys", help="create a local signing key and JWKS for HTTP testing")
    keys.add_argument("--out", type=Path, default=Path(".dev"))

    token = sub.add_parser("dev-token", help="mint a short-lived token signed by the local dev key")
    token.add_argument("--dir", type=Path, default=Path(".dev"))
    token.add_argument("--sub", default="alex@example.test")
    token.add_argument("--role", action="append", dest="roles", default=None)
    token.add_argument("--ttl", type=int, default=900)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.from_env()
    try:
        if args.command == "serve":
            if args.transport == "stdio":
                build_server(args.server, settings, "stdio").run("stdio")
            else:
                app = build_http_app(args.server, settings)
                uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
        elif args.command == "dev-keys":
            key_path, jwks_path = write_dev_keys(args.out)
            print(f"private key: {key_path} (0600, git-ignored)")
            print(f"jwks:        {jwks_path}")
            print(f"issuer:      {DEV_ISSUER}")
            print(f"audience:    {DEV_AUDIENCE}")
        elif args.command == "dev-token":
            print(mint_from_dir(args.dir, subject=args.sub, roles=args.roles or ["reader"], ttl_s=args.ttl))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
