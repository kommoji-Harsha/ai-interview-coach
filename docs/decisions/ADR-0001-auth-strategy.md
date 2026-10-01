# ADR-0001: Authentication Strategy

## Context
The platform requires user accounts to track progress, save resumes, and manage interview history. We need an authentication mechanism that is secure, scalable, and easy to integrate with a FastAPI backend and a Next.js frontend.

## Options Considered
1. **Server-side Sessions (Cookies):** Traditional, secure against XSS, but requires database/Redis lookups on every request and harder to integrate if mobile clients are added later.
2. **JSON Web Tokens (JWT) via Bearer Header:** Stateless, scales easily, works seamlessly across web and mobile.

## Decision
We will use **JWT Authentication** (Access & Refresh tokens).
- Tokens will be passed via the `Authorization: Bearer <token>` header.
- The access token will be short-lived (e.g., 15 minutes).
- The refresh token will be long-lived and stored securely on the client.

## Consequences
- **Pros:** No database lookup required to authenticate API requests. Very fast.
- **Cons:** Cannot instantly revoke a specific access token without building a blacklist (we accept this risk for the 15-minute window; refresh tokens can be revoked).
