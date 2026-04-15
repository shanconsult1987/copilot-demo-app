# Copilot Demo App

A simple Flask API used to demonstrate GitHub Copilot features, now secured
with **Microsoft Entra ID (Azure AD)** JWT authentication.

---

## Table of contents

1. [App overview](#app-overview)
2. [Authentication design](#authentication-design)
3. [Register the app in Microsoft Entra ID](#register-the-app-in-microsoft-entra-id)
4. [Environment variables](#environment-variables)
5. [Run locally](#run-locally)
6. [API reference](#api-reference)
7. [Run tests](#run-tests)

---

## App overview

| Route | Method | Auth required | Description |
|-------|--------|---------------|-------------|
| `/` | GET | ❌ | Health-check / welcome message |
| `/api/data` | GET | ✅ Bearer token | Returns a demo JSON payload |
| `/api/add` | POST | ✅ Bearer token | Adds two numbers passed in the request body |

---

## Authentication design

Protected routes require an **OAuth 2.0 Bearer token** issued by Microsoft
Entra ID in the `Authorization` request header:

```
Authorization: Bearer <access-token>
```

`auth.py` validates every token by:

1. Fetching the public signing keys from the Entra ID JWKS endpoint
   (`https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys`).
2. Verifying the JWT signature with RS256.
3. Validating the `iss` (issuer), `aud` (audience), `exp` (expiry), and
   `nbf` (not-before) claims.
4. Keys are cached in-process to avoid a round-trip on every request.

---

## Register the app in Microsoft Entra ID

### Step 1 — Create an app registration for the API

1. Open [Azure Portal → Microsoft Entra ID → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
2. Click **New registration**.
3. Name: e.g. `copilot-demo-api`.
4. **Supported account types**: choose the option that matches your users
   (single tenant is the most restrictive and recommended for internal apps).
5. **Redirect URI**: leave blank for a pure API — it is not needed.
6. Click **Register**.
7. Copy the **Application (client) ID** and **Directory (tenant) ID** from the
   Overview page — you will need them as environment variables.

### Step 2 — Expose an API scope (optional but recommended)

1. In your app registration, click **Expose an API**.
2. Set the **Application ID URI** (e.g. `api://<your-client-id>`).
3. Add a scope, e.g. `access_as_user`.
4. Grant admin consent if required.

Client applications that call this API should request the scope
`api://<your-client-id>/access_as_user` when acquiring tokens.

### Step 3 — Register a client app (for local testing)

If you want to test with the **OAuth 2.0 client-credentials** or
**authorization-code** flow:

1. Create a second app registration for the caller (e.g. `copilot-demo-client`).
2. Under **Authentication**, add a redirect URI:
   - For local testing with tools like Postman: `https://oauth.pstmn.io/v1/callback`
   - For a local SPA: `http://localhost:5000`
3. Under **API permissions**, add the scope you exposed in Step 2 and grant
   admin consent.

---

## Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_TENANT_ID` | ✅ | Directory (tenant) ID from your Entra ID app registration |
| `AZURE_CLIENT_ID` | ✅ | Application (client) ID of *this API's* app registration |
| `AZURE_AUTHORITY` | ❌ | Override the authority URL (default: `https://login.microsoftonline.com/<tenant>`) |
| `AZURE_CLIENT_ID_AUDIENCE` | ❌ | Expected `aud` claim (default: `AZURE_CLIENT_ID`) — set to the App ID URI if configured |

> **Never commit `.env` to source control.** It is listed in `.gitignore`.

---

## Run locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and fill in AZURE_TENANT_ID and AZURE_CLIENT_ID

# 3. Start the app
python app.py
```

The app listens on `http://localhost:5000` by default.

### Get an access token for local testing

Using the [Azure CLI](https://learn.microsoft.com/cli/azure/):

```bash
# Log in if you haven't already
az login

# Acquire a token for the API (replace <client-id> with AZURE_CLIENT_ID)
TOKEN=$(az account get-access-token --resource api://<client-id> --query accessToken -o tsv)

# Call a protected endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/data
```

---

## API reference

### `GET /`

Public health-check endpoint.

**Response** `200 OK`
```
Copilot Demo App 🚀
```

---

### `GET /api/data`

Returns a greeting message. **Requires authentication.**

**Headers**
```
Authorization: Bearer <access-token>
```

**Response** `200 OK`
```json
{"message": "Hello from Copilot demo!"}
```

**Error responses**

| Status | Reason |
|--------|--------|
| 401 | Missing, expired, or invalid Bearer token |

---

### `POST /api/add`

Adds two numbers. **Requires authentication.**

**Headers**
```
Authorization: Bearer <access-token>
Content-Type: application/json
```

**Body**
```json
{"a": 3, "b": 7}
```

**Response** `200 OK`
```json
{"result": 10}
```

**Error responses**

| Status | Reason |
|--------|--------|
| 400 | `a` or `b` is not a number |
| 401 | Missing, expired, or invalid Bearer token |

---

## Run tests

```bash
python -m pytest test_app.py -v
```

Tests use a locally-generated RSA key pair and a mocked JWKS client, so they
**do not require a live Entra ID tenant**.
