"""A throwaway local signing key, so the HTTP transport can be exercised without an IdP.

Never used in production: there the server only ever sees the identity provider's public
JWKS. The private key is written with 0600 permissions to a git-ignored folder.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

DEV_ISSUER = "https://idp.example.test"
DEV_AUDIENCE = "governed-mcp"
KEY_FILE = "dev-signing-key.pem"
JWKS_FILE = "jwks.json"


def new_keypair(kid: str | None = None) -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid or uuid.uuid4().hex[:16], "use": "sig", "alg": "RS256"})
    return key, {"keys": [jwk]}


def write_dev_keys(out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    key, jwks = new_keypair()
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    key_path, jwks_path = out / KEY_FILE, out / JWKS_FILE
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    jwks_path.write_text(json.dumps(jwks, indent=2) + "\n", encoding="utf-8")
    return key_path, jwks_path


def mint_token(
    key: rsa.RSAPrivateKey | bytes,
    kid: str,
    *,
    subject: str,
    roles: list[str],
    issuer: str = DEV_ISSUER,
    audience: str = DEV_AUDIENCE,
    client_id: str = "local-mcp-client",
    ttl_s: int = 3600,
    extra: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "azp": client_id,
        "roles": roles,
        "iat": now,
        "nbf": now,
        "exp": now + ttl_s,
        **(extra or {}),
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def mint_from_dir(out: Path, *, subject: str, roles: list[str], ttl_s: int = 3600) -> str:
    key = serialization.load_pem_private_key((out / KEY_FILE).read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError("dev signing key must be RSA")
    kid = json.loads((out / JWKS_FILE).read_text(encoding="utf-8"))["keys"][0]["kid"]
    return mint_token(key, kid, subject=subject, roles=roles, ttl_s=ttl_s)
