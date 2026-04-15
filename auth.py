"""
Azure AD (Microsoft Entra ID) JWT validation for Flask.

Validates Bearer tokens on protected routes by:
 1. Fetching the JWKS from the Entra ID OIDC well-known endpoint.
 2. Verifying the token signature, issuer and audience.
 3. Caching the public keys in-process to avoid per-request network calls.
"""

import os
import functools
from typing import Callable

import requests
import jwt
from jwt import PyJWKClient, InvalidTokenError
from flask import request, jsonify


# ---------------------------------------------------------------------------
# Configuration (read once at module load so tests can monkeypatch os.environ)
# ---------------------------------------------------------------------------

def _get_config() -> dict:
    tenant_id = os.environ.get("AZURE_TENANT_ID", "")
    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    authority = os.environ.get(
        "AZURE_AUTHORITY",
        f"https://login.microsoftonline.com/{tenant_id}",
    )
    # The audience is the client-id (App ID URI) of *this* API.
    audience = os.environ.get("AZURE_CLIENT_ID_AUDIENCE", client_id)

    return {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "authority": authority,
        "audience": audience,
        "issuer_v1": f"https://sts.windows.net/{tenant_id}/",
        "issuer_v2": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "jwks_uri": f"{authority}/discovery/v2.0/keys",
    }


def _build_jwks_client(jwks_uri: str) -> PyJWKClient:
    """Return a caching PyJWKClient for the given JWKS URI."""
    return PyJWKClient(jwks_uri, cache_keys=True)


# Module-level cache; re-created if tenant/authority env vars change.
_jwks_client: PyJWKClient | None = None
_jwks_uri_used: str | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_uri_used  # noqa: PLW0603
    cfg = _get_config()
    uri = cfg["jwks_uri"]
    if _jwks_client is None or uri != _jwks_uri_used:
        _jwks_client = _build_jwks_client(uri)
        _jwks_uri_used = uri
    return _jwks_client


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------

def require_auth(f: Callable) -> Callable:
    """Flask route decorator that requires a valid Entra ID Bearer token.

    Returns 401 if the Authorization header is missing or the token is
    invalid / expired.  The decoded token claims are attached to
    ``request.token_claims`` for use by the route handler.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return (
                jsonify({"error": "Missing or invalid Authorization header"}),
                401,
            )

        token = auth_header[len("Bearer "):]
        cfg = _get_config()

        if not cfg["tenant_id"] or not cfg["client_id"]:
            # Auth is mis-configured – fail closed.
            return jsonify({"error": "Authentication not configured"}), 500

        try:
            client = _get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)

            # Try v2 issuer first; fall back to v1 for enterprise tenants.
            for issuer in (cfg["issuer_v2"], cfg["issuer_v1"]):
                try:
                    claims = jwt.decode(
                        token,
                        signing_key.key,
                        algorithms=["RS256"],
                        audience=cfg["audience"],
                        options={
                            "verify_exp": True,
                            "verify_nbf": True,
                            "verify_iss": True,
                            "require": ["exp", "iss", "aud", "sub"],
                        },
                        issuer=issuer,
                    )
                    break  # Validation succeeded.
                except InvalidTokenError:
                    continue
            else:
                # Both issuers failed.
                return jsonify({"error": "Token validation failed"}), 401
        except InvalidTokenError:
            return jsonify({"error": "Token validation failed"}), 401

        # Attach decoded claims to the request context for downstream use.
        request.token_claims = claims  # type: ignore[attr-defined]
        return f(*args, **kwargs)

    return decorated
