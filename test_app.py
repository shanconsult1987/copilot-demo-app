"""
Tests for the Copilot Demo App.

Auth tests use monkeypatching so they do NOT require a live Azure AD tenant.
The JWT validation logic in auth.py is tested by injecting a locally-generated
RSA key pair and a fake JWKS endpoint.
"""

import json
import os
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

import app as flask_app_module
from app import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_rsa_key():
    """Generate a fresh RSA key pair for test tokens."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )


def _make_token(private_key, *, tenant_id, client_id, extra_claims=None, expired=False):
    """Create a signed JWT that matches what Entra ID would produce."""
    now = int(time.time())
    payload = {
        "sub": "test-user-id",
        "oid": "test-object-id",
        "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "aud": client_id,
        "iat": now - 60,
        "nbf": now - 60,
        "exp": now - 1 if expired else now + 3600,
        "tid": tenant_id,
        "name": "Test User",
        "upn": "test@example.com",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, private_key, algorithm="RS256")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_CLIENT_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    """Ensure auth env vars are set for every test."""
    monkeypatch.setenv("AZURE_TENANT_ID", FAKE_TENANT_ID)
    monkeypatch.setenv("AZURE_CLIENT_ID", FAKE_CLIENT_ID)


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def rsa_key():
    return _generate_rsa_key()


@pytest.fixture()
def mock_jwks_client(rsa_key, monkeypatch):
    """Patch auth._get_jwks_client so tokens signed by rsa_key validate."""
    import auth

    signing_key_mock = MagicMock()
    signing_key_mock.key = rsa_key.public_key()

    jwks_mock = MagicMock()
    jwks_mock.get_signing_key_from_jwt.return_value = signing_key_mock

    monkeypatch.setattr(auth, "_get_jwks_client", lambda: jwks_mock)
    # Also reset module-level cache so the monkeypatch takes effect cleanly.
    monkeypatch.setattr(auth, "_jwks_client", None)
    return jwks_mock


# ---------------------------------------------------------------------------
# Public route tests
# ---------------------------------------------------------------------------

class TestHomeRoute:
    def test_home_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Copilot Demo App" in resp.data


# ---------------------------------------------------------------------------
# Protected route — missing / malformed token
# ---------------------------------------------------------------------------

class TestProtectedRouteNoToken:
    def test_get_data_no_auth_returns_401(self, client):
        resp = client.get("/api/data")
        assert resp.status_code == 401

    def test_get_data_bad_scheme_returns_401(self, client):
        resp = client.get("/api/data", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 401

    def test_add_no_auth_returns_401(self, client):
        resp = client.post(
            "/api/add",
            data=json.dumps({"a": 1, "b": 2}),
            content_type="application/json",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected route — valid token
# ---------------------------------------------------------------------------

class TestProtectedRouteValidToken:
    def test_get_data_valid_token_returns_200(self, client, rsa_key, mock_jwks_client):
        token = _make_token(rsa_key, tenant_id=FAKE_TENANT_ID, client_id=FAKE_CLIENT_ID)
        resp = client.get("/api/data", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "Hello from Copilot demo!"

    def test_add_valid_token_returns_correct_result(self, client, rsa_key, mock_jwks_client):
        token = _make_token(rsa_key, tenant_id=FAKE_TENANT_ID, client_id=FAKE_CLIENT_ID)
        resp = client.post(
            "/api/add",
            data=json.dumps({"a": 3, "b": 7}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["result"] == 10


# ---------------------------------------------------------------------------
# Protected route — expired / tampered token
# ---------------------------------------------------------------------------

class TestProtectedRouteInvalidToken:
    def test_expired_token_returns_401(self, client, rsa_key, mock_jwks_client):
        token = _make_token(
            rsa_key, tenant_id=FAKE_TENANT_ID, client_id=FAKE_CLIENT_ID, expired=True
        )
        resp = client.get("/api/data", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_tampered_token_returns_401(self, client, rsa_key, mock_jwks_client):
        token = _make_token(rsa_key, tenant_id=FAKE_TENANT_ID, client_id=FAKE_CLIENT_ID)
        # Corrupt the middle of the signature to guarantee the decoded bytes differ.
        header, payload, sig = token.split(".")
        mid = len(sig) // 2
        # Flip one character to a different base64url character.
        replacement = "A" if sig[mid] != "A" else "B"
        tampered = f"{header}.{payload}.{sig[:mid]}{replacement}{sig[mid + 1:]}"
        resp = client.get("/api/data", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.status_code == 401

    def test_wrong_audience_returns_401(self, client, rsa_key, mock_jwks_client):
        token = _make_token(
            rsa_key, tenant_id=FAKE_TENANT_ID, client_id="wrong-audience"
        )
        resp = client.get("/api/data", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Input validation — /api/add
# ---------------------------------------------------------------------------

class TestAddEndpointValidation:
    def test_non_numeric_input_returns_400(self, client, rsa_key, mock_jwks_client):
        token = _make_token(rsa_key, tenant_id=FAKE_TENANT_ID, client_id=FAKE_CLIENT_ID)
        resp = client.post(
            "/api/add",
            data=json.dumps({"a": "foo", "b": 2}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
