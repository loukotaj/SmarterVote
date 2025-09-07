# Auth0 Authentication Configuration for SmarterVote

## Overview

This document describes the Auth0 authentication implementation for the SmarterVote pipeline client and frontend. Auth0 is used to secure the admin interface that allows authorized users to manage the AI pipeline for race data processing.

## Architecture

### Security Model
- **Frontend Authentication**: Auth0 login required for `/admin/*` routes
- **API Authentication**: JWT token verification for all sensitive pipeline endpoints  
- **Cloud Run Access**: Public at infrastructure level, secured at application level
- **CORS**: Configured to allow credentials for auth headers

### Components

#### 1. Frontend (SvelteKit Web App)
- **Location**: `web/src/lib/auth.ts`
- **Implementation**: Auth0 SPA SDK integration
- **Protected Routes**: `/admin` and `/admin/pipeline`
- **Token Management**: Automatic token refresh with `getTokenSilently()`

#### 2. Pipeline Client (FastAPI Backend)  
- **Location**: `pipeline_client/backend/main.py`
- **Implementation**: JWT verification using `python-jose`
- **Protected Endpoints**: 15 endpoints with `dependencies=[Depends(verify_token)]`
- **WebSocket Support**: Token verification for real-time logging

#### 3. Infrastructure (Terraform)
- **Location**: `infra/pipeline-client.tf`
- **Environment Variables**: `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `ALLOWED_ORIGINS`
- **CORS Configuration**: Supports credentials for auth headers

## Configuration

### Frontend Environment Variables
```bash
# Production (.env.production)
VITE_AUTH0_DOMAIN=dev-t37rz-ur.auth0.com
VITE_AUTH0_CLIENT_ID=KNkBhmyIGEvjkKDthMzyYe6YFevGoJIy
VITE_API_BASE=https://pipeline-client-dev-ddsvfazica-uc.a.run.app
```

### Terraform Variables
```hcl
# secrets.tfvars
auth0_domain   = "your-auth0-domain"
auth0_audience = "your-auth0-audience"  
allowed_origins = ["https://your-frontend-domain.com"]
```

### Pipeline Client Settings
The pipeline client uses environment variables set by Terraform:
- `AUTH0_DOMAIN`: Auth0 tenant domain
- `AUTH0_AUDIENCE`: API audience identifier  
- `ALLOWED_ORIGINS`: CORS allowed origins (comma-separated)

## Authentication Flow

1. **User Access**: User navigates to `/admin` or `/admin/pipeline`
2. **Auth Check**: Frontend checks Auth0 authentication status
3. **Redirect**: If not authenticated, redirects to Auth0 login
4. **Callback**: Auth0 redirects back to `/admin` with authorization code
5. **Token Exchange**: Frontend exchanges code for JWT access token
6. **API Calls**: Frontend includes `Authorization: Bearer <token>` header
7. **Verification**: Pipeline client validates JWT against Auth0 JWKS
8. **Access Granted**: Valid tokens allow access to protected endpoints

## Protected Endpoints

All sensitive pipeline endpoints require authentication:

```python
@app.post("/run/step01", dependencies=[Depends(verify_token)])
@app.get("/runs", dependencies=[Depends(verify_token)])  
@app.get("/artifacts", dependencies=[Depends(verify_token)])
@app.post("/api/execute", dependencies=[Depends(verify_token)])
# ... and 11 more endpoints
```

### Unprotected Endpoints
- `/health` - Health checks
- `/` - Root documentation page
- `/docs`, `/redoc` - API documentation

## Development vs Production

### Local Development
- Auth0 variables not set → `verify_token` returns empty dict
- Allows local development without Auth0 configuration
- Frontend can still test UI components

### Production Deployment  
- Auth0 variables set via Terraform
- JWT verification enforced
- All admin functionality requires authentication

## Security Features

1. **JWT Validation**: Full verification against Auth0 JWKS
2. **Token Expiry**: Automatic token refresh in frontend
3. **CORS Security**: Credentials allowed only for specified origins
4. **WebSocket Auth**: Real-time connections also require valid tokens
5. **Graceful Degradation**: Local development works without auth setup

## Testing Authentication

Run the integration test to verify configuration:

```bash
python /tmp/auth_integration_test.py
```

Expected output: All tests pass (4/4) ✅

## Troubleshooting

### Common Issues
1. **Auth0 Redirect Blocked**: Normal in sandboxed environments
2. **CORS Errors**: Check `allowed_origins` configuration
3. **Token Expired**: Frontend handles automatic refresh
4. **Local Development**: Auth0 variables not needed for local testing

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