from pathlib import Path

import pytest

from governed_mcp.cli import main
from governed_mcp.devkeys import DEV_AUDIENCE, DEV_ISSUER
from governed_mcp.gateway.auth import JWTVerifier, StaticJWKS


def test_dev_keys_and_token_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dev-keys", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "dev-signing-key.pem").stat().st_mode & 0o777 == 0o600
    capsys.readouterr()
    assert main(["dev-token", "--dir", str(tmp_path), "--role", "operator", "--sub", "lee@example.test"]) == 0
    token = capsys.readouterr().out.strip()
    verifier = JWTVerifier(DEV_ISSUER, DEV_AUDIENCE, StaticJWKS.from_file(tmp_path / "jwks.json"))
    access = verifier.verify(token)
    assert access is not None
    assert access.subject == "lee@example.test"
    assert access.claims is not None and access.claims["roles"] == ["operator"]


def test_unknown_stdio_role_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOVERNED_MCP_ROLE", "superuser")
    monkeypatch.setenv("GOVERNED_MCP_POLICY_DIR", str(Path(__file__).parent.parent / "policies"))
    assert main(["serve", "tickets", "--transport", "stdio"]) == 2
