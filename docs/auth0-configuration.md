# Auth0 Authentication Configuration for SmarterVote

## Overview

This document describes the Auth0 authentication implementation for the SmarterVote admin frontend and protected API endpoints. Auth0 secures the admin interface that allows authorized users to manage race data processing.

## Architecture

### Security Model

- **Frontend Authentication**: Auth0 login required for `/admin/*` routes
- **API Authentication**: JWT token verification or `X-Admin-Key` for protected endpoints
- **Cloud Run Access**: Public at infrastructure level, secured at application level
- **CORS**: Configured to allow credentials for auth headers

### Components

#### 1. Frontend (SvelteKit Web App)

- **Location**: `web/src/lib/auth.ts`
- **Implementation**: Auth0 SPA SDK integration
- **Protected Routes**: `/admin` and `/admin/pipeline`
- **Token Management**: Automatic token refresh with `getTokenSilently()`

#### 2. Races API (FastAPI Backend)

- **Location**: `services/races-api`
- **Implementation**: JWT verification using PyJWT with `cryptography` support
- **Protected Endpoints**: Admin race, queue, run, analytics, durable agent, and public race data endpoints use `dependencies=[Depends(verify_token)]`
- **Live Updates**: Frontend polls `/runs/{run_id}` and `/runs/{run_id}/logs?since=N`

#### 3. Pipeline Client (Local Runner)

- **Location**: `pipeline_client/backend/main.py`
- **Implementation**: Same Auth0 helper, normally disabled locally with `SKIP_AUTH=true`
- **Protected Endpoints**: Local runner/debug endpoints only

#### 4. Infrastructure (Terraform)

- **Location**: `infra/races-api.tf`
- **Environment Variables**: `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `ALLOWED_ORIGINS`
- **CORS Configuration**: Supports credentials for auth headers

## Configuration

### Frontend Environment Variables

```bash
# Production (.env.production)
VITE_AUTH0_DOMAIN=dev-t37rz-ur.auth0.com
VITE_AUTH0_CLIENT_ID=KNkBhmyIGEvjkKDthMzyYe6YFevGoJIy
VITE_AUTH0_AUDIENCE=your-api-audience
VITE_RACES_API_URL=https://races-api-dev-ddsvfazica-uc.a.run.app
```

### Terraform Variables

```hcl
# secrets.tfvars
auth0_domain   = "your-auth0-domain"
auth0_audience = "your-auth0-audience"
allowed_origins = ["https://your-frontend-domain.com"]
```

### API Settings

The protected APIs use environment variables set by Terraform:

- `AUTH0_DOMAIN`: Auth0 tenant domain
- `AUTH0_AUDIENCE`: API audience identifier
- `ALLOWED_ORIGINS`: CORS allowed origins (comma-separated)
- `ADMIN_API_KEY`: Optional service/admin key accepted via `X-Admin-Key`

## Authentication Flow

1. **User Access**: User navigates to `/admin` or `/admin/pipeline`
2. **Auth Check**: Frontend checks Auth0 authentication status
3. **Redirect**: If not authenticated, redirects to Auth0 login
4. **Callback**: Auth0 redirects back to `/admin` with authorization code
5. **Token Exchange**: Frontend exchanges code for JWT access token
6. **API Calls**: Frontend includes `Authorization: Bearer <token>` header
7. **Verification**: API validates JWT against Auth0 JWKS
8. **Access Granted**: Valid tokens allow access to protected endpoints

## Protected Endpoints

Protected routes require authentication:

```python
@router.post("/api/races/queue", dependencies=[Depends(verify_token)])
@app.get("/runs", dependencies=[Depends(verify_token)])
# ... and more endpoints
```

The public race read endpoints (`/races`, `/races/summaries`, `/races/chamber_forecasts`, and `/races/{race_id}`) are also protected by the same dependency when served through `races-api`. Normal public traffic reads JSON bundled into the Cloudflare Pages deployment. `VITE_PUBLIC_DATA_URL` is reserved for a separately public static origin and is not required by the current deployment.

### Unprotected Endpoints

- `/health` - Health checks
- `/docs`, `/redoc` - API documentation

## Development vs Production

### Local Development

- Set `SKIP_AUTH=true` in the root `.env` to bypass verification.
- Without `SKIP_AUTH=true`, missing `AUTH0_DOMAIN` or `AUTH0_AUDIENCE` returns `503`.
- Non-browser tools can use `X-Admin-Key` when `ADMIN_API_KEY` is configured.
- Frontend UI components can still be tested without Auth0 by using local dev mode.

### Production Deployment

- Auth0 variables are set via Terraform.
- JWT verification is enforced unless `X-Admin-Key` matches `ADMIN_API_KEY`.
- `SKIP_AUTH` must not be enabled in deployed environments.

## Security Features

1. **JWT Validation**: Full verification against Auth0 JWKS
2. **Token Expiry**: Automatic token refresh in frontend
3. **CORS Security**: Credentials allowed only for specified origins
4. **Polling Auth**: Run status and log polling use the same bearer token
5. **Local Bypass**: Local development works with `SKIP_AUTH=true`

## Testing Authentication

Run the relevant tests:

```powershell
$env:PYTHONPATH = "."
python -m pytest services/races-api/test_races_api.py tests/test_races_api_admin.py -v
```

## Troubleshooting

### Common Issues

1. **Auth0 Redirect Blocked**: Normal in sandboxed environments
2. **CORS Errors**: Check `allowed_origins` configuration
3. **Token Expired**: Frontend handles automatic refresh
4. **Local Development**: Set `SKIP_AUTH=true` for local API testing without Auth0

### Verification Steps

1. Check Terraform outputs for service URLs
2. Verify environment variables in Cloud Run console
3. Test API endpoints return 401 without valid token
4. Confirm frontend redirects to Auth0 login

## Screenshots

The Auth0 integration is working correctly as evidenced by:

- Admin pages automatically redirect to Auth0 for authentication
- Browser security correctly blocks external redirects in sandboxed environments
- This behavior confirms the authentication flow is properly implemented

![Auth0 Redirect](https://github.com/user-attachments/assets/18935a7a-31ec-4f91-ab4c-c04523e12583)
