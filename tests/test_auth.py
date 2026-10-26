import base64
import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from governed_mcp.devkeys import DEV_AUDIENCE, DEV_ISSUER, mint_token, new_keypair
from governed_mcp.gateway.auth import JWTVerifier, RemoteJWKS, StaticJWKS

KEY, JWKS = new_keypair(kid="test-key")
KID = "test-key"


@pytest.fixture
def verifier() -> JWTVerifier:
    return JWTVerifier(issuer=DEV_ISSUER, audience=DEV_AUDIENCE, keys=StaticJWKS(JWKS))


def token(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {"subject": "alex@example.test", "roles": ["reader"]}
    kwargs.update(overrides)
    return mint_token(KEY, KID, **kwargs)


def test_valid_token_maps_to_access_token(verifier: JWTVerifier) -> None:
    access = verifier.verify(token(extra={"scope": "mcp.read mcp.write"}))
    assert access is not None
    assert access.subject == "alex@example.test"
    assert access.client_id == "local-mcp-client"
    assert access.scopes == ["mcp.read", "mcp.write"]
    assert access.resource == DEV_AUDIENCE
    assert access.claims is not None and access.claims["roles"] == ["reader"]


@pytest.mark.anyio
async def test_async_protocol_method(verifier: JWTVerifier) -> None:
    assert await verifier.verify_token(token()) is not None
    assert await verifier.verify_token("not-a-jwt") is None


@pytest.mark.parametrize(
    "bad",
    [
        {"audience": "some-other-api"},
        {"issuer": "https://evil.example.test"},
        {"ttl_s": -120},
        {"extra": {"nbf": int(time.time()) + 3600}},
    ],
    ids=["wrong-audience", "wrong-issuer", "expired", "not-yet-valid"],
)
def test_rejects_claims_that_do_not_match(verifier: JWTVerifier, bad: dict[str, Any]) -> None:
    assert verifier.verify(token(**bad)) is None


def test_rejects_missing_subject(verifier: JWTVerifier) -> None:
    now = int(time.time())
    claims = {"iss": DEV_ISSUER, "aud": DEV_AUDIENCE, "iat": now, "exp": now + 60}
    assert verifier.verify(jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": KID})) is None


def test_rejects_token_signed_by_another_key_with_same_kid(verifier: JWTVerifier) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert verifier.verify(mint_token(other, KID, subject="x", roles=["admin"])) is None


def test_rejects_unknown_kid(verifier: JWTVerifier) -> None:
    assert verifier.verify(mint_token(KEY, "rotated-away", subject="x", roles=["admin"])) is None


def test_rejects_tampered_payload(verifier: JWTVerifier) -> None:
    header, payload, sig = token().split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["roles"] = ["admin"]
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    assert verifier.verify(f"{header}.{forged}.{sig}") is None


def test_rejects_alg_none(verifier: JWTVerifier) -> None:
    now = int(time.time())
    claims = {"iss": DEV_ISSUER, "aud": DEV_AUDIENCE, "sub": "x", "iat": now, "exp": now + 60}
    unsigned = jwt.encode(claims, key=None, algorithm="none", headers={"kid": KID})  # type: ignore[arg-type]
    assert verifier.verify(unsigned) is None


def test_rejects_hs256_key_confusion(verifier: JWTVerifier) -> None:
    """Signing with HS256 using the public key as the shared secret must not work."""
    public_pem = KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    now = int(time.time())
    claims = {"iss": DEV_ISSUER, "aud": DEV_AUDIENCE, "sub": "x", "iat": now, "exp": now + 60}
    # Build the HS256 token by hand: PyJWT itself refuses to use a PEM as an HMAC secret.
    import hashlib
    import hmac

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    signing_input = (
        f"{b64(json.dumps({'alg': 'HS256', 'kid': KID}).encode())}.{b64(json.dumps(claims).encode())}"
    )
    sig = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    assert verifier.verify(f"{signing_input}.{b64(sig)}") is None


def test_refuses_symmetric_algorithms_in_config() -> None:
    with pytest.raises(ValueError, match="symmetric"):
        JWTVerifier(issuer="i", audience="a", keys=StaticJWKS(JWKS), algorithms=("RS256", "HS256"))


def test_remote_jwks_requires_https() -> None:
    with pytest.raises(ValueError, match="https"):
        RemoteJWKS("http://idp.example.test/jwks")
