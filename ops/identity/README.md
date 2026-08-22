# Identity signing keys & authorization

## Local development
```bash
scripts/dev_gen_jwt_key.sh   # writes ops/identity/jwt_private_key.pem (gitignored)
```
`compose.yaml` mounts that key into `backend` read-only. It is never committed.

## Production
The private key is injected as a secret (`IDENTITY_JWT_PRIVATE_KEY`, PEM), not a repo
mount. `compose.prod.yaml` sets `DJANGO_PRODUCTION=1` (settings fail closed if the key is
absent, or if `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` use dev defaults) and drops the dev
mount. In Kubernetes, mount the secret to a tmpfs path and point
`IDENTITY_JWT_PRIVATE_KEY_FILE` at it, or pass `IDENTITY_JWT_PRIVATE_KEY` from the secret.

## Key rotation (no downtime)
Two keys may be published in the JWKS at once, distinguished by `kid`:
1. generate a new key, set it as `IDENTITY_JWT_PRIVATE_KEY` with a new `IDENTITY_JWT_KID`;
2. keep the old public key as `IDENTITY_JWT_PREVIOUS_PUBLIC_KEY` + `IDENTITY_JWT_PREVIOUS_KID`
   so tokens signed before the switch still verify;
3. after the old TTL window elapses, drop the previous key.
New tokens sign with the current key; operations selects the verifying key by `kid`.

## The committed dev key was removed
The earlier `jwt_dev_private_key.pem` was committed. If this repo was pushed anywhere:
- treat that key as compromised and rotate (generate a fresh prod key; never reuse it);
- purge it from history with `git filter-repo --path ops/identity/jwt_dev_private_key.pem --invert-paths`
  (or BFG), then force-push and have collaborators re-clone.

## Authorization lifecycle & revocation SLO
`employee.service.set_employee_role` is the only path that changes staff membership: it
atomically flips the group, bumps `User.authz_version`, appends `EmployeeRoleAudit`, and
publishes `identity.authz_changed.v1` through the outbox. Operations projects it into
`EmployeeAuthorization` and requires, for every request: `token.authz_version ==
projected authz_version`, `role_active`, and `user_active` — failing closed for an
unknown or stale subject.

**Revocation SLO:** a revocation is enforced once the `identity.authz_changed.v1` event
reaches operations (outbox relay + bridge + consumer). Target ≤ 5s under normal load;
until then the short token TTL (default 600s) is the outer bound. Sensitive command
endpoints must reject when the authorization projection is missing or older than the
token, never silently accept.
