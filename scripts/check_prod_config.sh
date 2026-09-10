#!/usr/bin/env bash
# CI guard: the production compose must render from a clean checkout (no repo-root .env),
# inject the signing key only as a read-only secret file, keep the legacy in-storefront ops
# consumer out of production, and fail fast when any required production variable is missing.
# Wire into CI as a required check.
set -euo pipefail

# a throwaway key file only so `config` can resolve the secret source, and an empty env-file
# so nothing outside the explicit ${VAR:?} set can satisfy a required variable during interpolation
TMPKEY="$(mktemp)"; EMPTY_ENV="$(mktemp)"
trap 'rm -f "$TMPKEY" "$EMPTY_ENV"' EXIT
printf 'dummy\n' > "$TMPKEY"

# every mandatory ${VAR:?} referenced by a service that is part of the default production render
MANDATORY=(
  DJANGO_SECRET_KEY DJANGO_ALLOWED_HOSTS DATABASE_URL REDIS_URL CART_REDIS_URL RABBITMQ_URL
  IDENTITY_JWT_KID IDENTITY_JWT_KEY_FILE
  POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
  RABBITMQ_ADMIN_USER RABBITMQ_ADMIN_PASSWORD RABBITMQ_ERLANG_COOKIE
  STOREFRONT_MQ_PASSWORD OPERATIONS_MQ_PASSWORD BRIDGE_MQ_PASSWORD OPERATIONS_COMMANDS_MQ_PASSWORD
  OPERATIONS_SECRET_KEY OPERATIONS_ALLOWED_HOSTS OPERATIONS_DATABASE_URL OPERATIONS_RABBITMQ_URL
  OPERATIONS_BRIDGE_CONSUME_URL OPERATIONS_BRIDGE_PUBLISH_URL OPERATIONS_COMMANDS_RABBITMQ_URL
)

# CI dummy values (non-dev) so the render can complete; the negative loop below removes them one
# at a time to prove each is genuinely required
export DJANGO_SECRET_KEY=ci-django-secret
export DJANGO_ALLOWED_HOSTS=app.example.com
export DATABASE_URL=postgres://u:p@db:5432/storefront
export REDIS_URL=redis://redis:6379/1
export CART_REDIS_URL=redis://redis:6379/0
export RABBITMQ_URL=amqp://u:p@rabbitmq:5672/storefront
export IDENTITY_JWT_KID=prod-1 IDENTITY_JWT_KEY_FILE="$TMPKEY"
export POSTGRES_DB=storefront POSTGRES_USER=storefront POSTGRES_PASSWORD=ci-pg
export RABBITMQ_ADMIN_USER=ci RABBITMQ_ADMIN_PASSWORD=ci RABBITMQ_ERLANG_COOKIE=ci
export STOREFRONT_MQ_PASSWORD=ci OPERATIONS_MQ_PASSWORD=ci BRIDGE_MQ_PASSWORD=ci
export OPERATIONS_COMMANDS_MQ_PASSWORD=ci
export OPERATIONS_SECRET_KEY=ci-ops-secret OPERATIONS_ALLOWED_HOSTS=ops.example.com
export OPERATIONS_DATABASE_URL=postgres://u:p@operations-db:5432/operations
export OPERATIONS_RABBITMQ_URL=amqp://u:p@rabbitmq:5672/operations
export OPERATIONS_BRIDGE_CONSUME_URL=amqp://u:p@rabbitmq:5672/storefront
export OPERATIONS_BRIDGE_PUBLISH_URL=amqp://u:p@rabbitmq:5672/operations
export OPERATIONS_COMMANDS_RABBITMQ_URL=amqp://u:p@rabbitmq:5672/storefront

PROD=(--env-file "$EMPTY_ENV" -f compose.yaml -f compose.prod.yaml)
rendered=$(docker compose "${PROD[@]}" config)
rendered_json=$(docker compose "${PROD[@]}" config --format json)
fail=0

# no dev fallbacks / no dev signing material / secret injected as a file / no inline key
grep -q "ops-dev-insecure" <<<"$rendered" && { echo "FAIL: ops-dev-insecure fallback present"; fail=1; }
grep -q "definitions.dev.json" <<<"$rendered" && { echo "FAIL: dev RabbitMQ definitions mounted"; fail=1; }
grep -q "jwt_private_key.pem" <<<"$rendered" && { echo "FAIL: dev signing-key mount present"; fail=1; }
grep -q "identity_jwt_private_key" <<<"$rendered" || { echo "FAIL: signing key not injected as a secret"; fail=1; }
grep -Eq "IDENTITY_JWT_PRIVATE_KEY:[[:space:]]*[^\"'[:space:]]" <<<"$rendered" && { echo "FAIL: inline private key in env"; fail=1; }

# legacy in-storefront projection consumer must not run in production
grep -q "run_ops_consumer" <<<"$rendered" && { echo "FAIL: legacy ops consumer present in production"; fail=1; }

grep -B3 -A3 'published: "9090"' <<<"$rendered" | grep -q 'host_ip: 127.0.0.1' || {
  echo "FAIL: prometheus 9090 not bound to loopback"; fail=1; }

# nothing may be reachable from outside the host: TLS is terminated by an ingress in front of this stack, so a port published on 0.0.0.0 would serve the app in the clear
RENDERED_JSON="$rendered_json" python3 - <<'PORTS' || fail=1
import json, os

exposed = [
    f"{name}:{p.get('published')}"
    for name, spec in sorted(json.loads(os.environ["RENDERED_JSON"])["services"].items())
    for p in (spec.get("ports") or [])
    if p.get("host_ip") not in ("127.0.0.1", "::1")
]
if exposed:
    print("FAIL: published outside loopback: " + ", ".join(exposed))
    raise SystemExit(1)
PORTS

# the ingress terminates TLS and the hop to nginx is plain http, so overwriting these two turns the redirect below into a loop and collapses every client into one rate-limit bucket
PROXY_PARAMS=frontend/nginx/proxy_params.conf
grep -Eq 'proxy_set_header[[:space:]]+X-Forwarded-Proto[[:space:]]+\$scheme;' "$PROXY_PARAMS" && {
  echo "FAIL: X-Forwarded-Proto forced to \$scheme; the ingress value is lost"; fail=1; }
grep -Eq 'proxy_set_header[[:space:]]+X-Forwarded-For[[:space:]]+\$proxy_add_x_forwarded_for;' "$PROXY_PARAMS" || {
  echo "FAIL: X-Forwarded-For does not append to the chain the ingress sent"; fail=1; }
grep -Eq 'map[[:space:]]+\$http_x_forwarded_proto[[:space:]]+\$forwarded_proto' frontend/nginx/default.conf || {
  echo "FAIL: \$forwarded_proto is not derived from the header the ingress sent"; fail=1; }
grep -A4 'map[[:space:]]\+\$http_x_forwarded_proto' frontend/nginx/default.conf | grep -q '\$scheme' || {
  echo "FAIL: no scheme fallback for a request that arrives without a proxy"; fail=1; }

# migrations are a deployment step, not something every process races on startup
RENDERED_JSON="$rendered_json" python3 - <<'MIGRATE' || fail=1
import json, os

GUARD = {"backend/Dockerfile": "storefront", "services/order_operations/Dockerfile": "operations"}
services = json.loads(os.environ["RENDERED_JSON"])["services"]
migrators, runtime_migrating = {}, []
for name, spec in sorted(services.items()):
    side = GUARD.get((spec.get("build") or {}).get("dockerfile", ""))
    if not side:
        continue
    env = spec.get("environment") or {}
    runs = str(env.get("RUN_MIGRATIONS", "")) == "1"
    if runs:
        migrators.setdefault(side, []).append(name)
    if runs and spec.get("restart") not in (None, "no"):
        runtime_migrating.append(name)
for side in sorted(GUARD.values()):
    found = migrators.get(side, [])
    if len(found) != 1:
        print(f"FAIL: {side} needs exactly one migration service, found {found or 'none'}")
        raise SystemExit(1)
if runtime_migrating:
    print("FAIL: a long-running service migrates on startup: " + ", ".join(runtime_migrating))
    raise SystemExit(1)

# the migrator must run once and exit, or the services waiting on it never start
for side, (job,) in ((side, migrators[side]) for side in sorted(migrators)):
    spec = services[job]
    if spec.get("restart") not in (None, "no") or spec.get("command") != ["true"]:
        print(f"FAIL: {job} is not a one-shot job (restart={spec.get('restart')!r}, "
              f"command={spec.get('command')!r})")
        raise SystemExit(1)

# every runtime service must wait for its own migrator: without this it can start against a
# schema the deployment has not migrated yet
unguarded = []
for name, spec in sorted(services.items()):
    side = GUARD.get((spec.get("build") or {}).get("dockerfile", ""))
    if not side or name in migrators.get(side, []):
        continue
    job = migrators[side][0]
    wait = (spec.get("depends_on") or {}).get(job) or {}
    if wait.get("condition") != "service_completed_successfully":
        unguarded.append(f"{name} -> {job}")
if unguarded:
    print("FAIL: these start without waiting for their migration job: " + ", ".join(unguarded))
    raise SystemExit(1)
MIGRATE

# the release procedure must render the production stack: a bare `docker compose` there brings up the dev overlay with its mounts and fallbacks
python3 - <<'DEPLOYDOC' || fail=1
import pathlib, re

doc = pathlib.Path("DEPLOY.md").read_text(encoding="utf-8")
helper = re.compile(
    r"^dc\(\)\s*\{.*--env-file \"\$PROD_ENV_FILE\".*-f compose\.yaml.*-f compose\.prod\.yaml.*",
    re.M,
)
if not helper.search(doc):
    print("FAIL: DEPLOY.md has no dc() wrapper passing --env-file \"$PROD_ENV_FILE\" with both compose files")
    raise SystemExit(1)
bare = [ln.strip() for ln in doc.splitlines()
        if "docker compose" in ln and not ln.startswith("dc()")]
if bare:
    print("FAIL: DEPLOY.md calls docker compose directly: " + "; ".join(bare))
    raise SystemExit(1)
DEPLOYDOC

# HTTPS redirect must be on by default in production, not left to the operator to remember
grep -Eq "DJANGO_SSL_REDIRECT:[[:space:]]*[\"']?(1|true|True)[\"']?" <<<"$rendered" || {
  echo "FAIL: DJANGO_SSL_REDIRECT not enabled in the production render"; fail=1; }

# every Django process must start under its production guard. keyed off the image a service is
# built from rather than a service count, so a new one cannot satisfy the check by merely existing
RENDERED_JSON="$rendered_json" python3 - <<'GUARD' || fail=1
import json, os

GUARD = {"backend/Dockerfile": "DJANGO_PRODUCTION",
         "services/order_operations/Dockerfile": "OPERATIONS_PRODUCTION"}
missing = []
checked = set()
for name, spec in sorted(json.loads(os.environ["RENDERED_JSON"])["services"].items()):
    guard = GUARD.get((spec.get("build") or {}).get("dockerfile", ""))
    if not guard:
        continue
    checked.add(guard)
    if guard not in (spec.get("environment") or {}):
        missing.append(name + " (" + guard + ")")
if missing:
    print("FAIL: production guard missing on: " + ", ".join(missing))
    raise SystemExit(1)
unmatched = sorted(set(GUARD.values()) - checked)
if unmatched:
    print("FAIL: no service matched the guard for: " + ", ".join(unmatched))
    raise SystemExit(1)
GUARD
grep -Eq "OPERATIONS_ALLOWED_HOSTS:[[:space:]]*'?\*'?[[:space:]]*$" <<<"$rendered" && { echo "FAIL: wildcard ALLOWED_HOSTS"; fail=1; }

# each mandatory variable being unset must make `config` fail (fail-closed, no silent default)
for var in "${MANDATORY[@]}"; do
  if env -u "$var" docker compose "${PROD[@]}" config >/dev/null 2>&1; then
    echo "FAIL: missing $var did not error"; fail=1
  fi
done

[ "$fail" -eq 0 ] && echo "prod config OK"
exit "$fail"
