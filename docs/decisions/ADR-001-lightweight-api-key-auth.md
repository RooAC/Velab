# ADR-001: Lightweight API Key Auth for Production Hardening

## Status
Accepted

## Date
2026-06-04

## Context
Velab is entering production trial hardening. The current backend exposes sessions, document upload/delete, feedback, bundle access, and Jira sync APIs without authentication. A full enterprise IAM system is still a larger product decision, but trial deployments need a concrete protection boundary now.

Key constraints:
- Keep local development friction low.
- Avoid storing browser-readable tokens.
- Protect backend APIs even if they are called directly.
- Protect Next.js proxy routes before they can read or mutate project data.
- Leave a future path for user, role, tenant, and audit expansion.

## Decision
Use a lightweight opt-in API key scheme for Sprint 7 hardening:

- Backend checks `Authorization: Bearer <AUTH_API_KEY>` or `X-API-Key: <AUTH_API_KEY>` when `AUTH_ENABLED=true`.
- Next.js stores a successful login as an httpOnly cookie and forwards `BACKEND_API_KEY` to backend services server-side.
- Local development remains open by default with `AUTH_ENABLED=false`.
- Production deployments must set `AUTH_ENABLED=true`, `AUTH_API_KEY`, `AUTH_LOGIN_PASSWORD`, and matching `BACKEND_API_KEY`.

This is not a complete identity provider. It is a deployment guardrail that closes the unauthenticated API surface while preserving the codebase's current architecture.

## Alternatives Considered

### Full username/password accounts and roles
- Pros: Proper long-term user model, can support audit and multi-tenant authorization.
- Cons: Requires schema, migrations, password reset, admin UX, role policy, and rollout planning.
- Rejected for this sprint: too large for immediate production trial hardening.

### Frontend-only login gate
- Pros: Fast to implement.
- Cons: Backend remains callable directly.
- Rejected: does not protect data or mutating APIs.

### Backend-only API key
- Pros: Protects backend direct access.
- Cons: Browser-facing Next routes would still be open if they forward server credentials for every request.
- Rejected as incomplete without a browser session gate.

## Consequences
- Production gets a real access boundary quickly.
- Existing tests and local development keep working without credentials.
- Later work still needs first-class users, tenant ownership fields, role checks, and audit logs.
- Session cookies must be set with `httpOnly`, `sameSite=lax`, and `secure` in production.
