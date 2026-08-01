#!/usr/bin/env bash
# Idempotent RabbitMQ provisioning for storefront/operations isolation.
# Passwords come from the environment (a secret store), never from a committed file.
# Safe to re-run and to run against an existing volume: it never deletes vhosts,
# users, queues or messages — it only converges users/permissions to the target.
#
# Required env:
#   RABBITMQ_ADMIN_USER RABBITMQ_ADMIN_PASSWORD
#   STOREFRONT_MQ_PASSWORD OPERATIONS_MQ_PASSWORD BRIDGE_MQ_PASSWORD
#
# Run inside the broker container, e.g.:
#   docker compose exec -T \
#     -e RABBITMQ_ADMIN_USER -e RABBITMQ_ADMIN_PASSWORD \
#     -e STOREFRONT_MQ_PASSWORD -e OPERATIONS_MQ_PASSWORD -e BRIDGE_MQ_PASSWORD \
#     rabbitmq bash -s < ops/rabbitmq/provision.sh
set -euo pipefail

: "${RABBITMQ_ADMIN_USER:?set RABBITMQ_ADMIN_USER}"
: "${RABBITMQ_ADMIN_PASSWORD:?set RABBITMQ_ADMIN_PASSWORD}"
: "${STOREFRONT_MQ_PASSWORD:?set STOREFRONT_MQ_PASSWORD}"
: "${OPERATIONS_MQ_PASSWORD:?set OPERATIONS_MQ_PASSWORD}"
: "${BRIDGE_MQ_PASSWORD:?set BRIDGE_MQ_PASSWORD}"

ensure_vhost() { rabbitmqctl add_vhost "$1" 2>/dev/null || true; }
ensure_user() { rabbitmqctl add_user "$1" "$2" 2>/dev/null || rabbitmqctl change_password "$1" "$2"; }

ensure_vhost /
ensure_vhost storefront
ensure_vhost operations

ensure_user "$RABBITMQ_ADMIN_USER" "$RABBITMQ_ADMIN_PASSWORD"
rabbitmqctl set_user_tags "$RABBITMQ_ADMIN_USER" administrator
ensure_user storefront_app "$STOREFRONT_MQ_PASSWORD"
ensure_user operations_consumer "$OPERATIONS_MQ_PASSWORD"
ensure_user operations_bridge "$BRIDGE_MQ_PASSWORD"

for v in / storefront operations; do
  rabbitmqctl set_permissions -p "$v" "$RABBITMQ_ADMIN_USER" '.*' '.*' '.*'
done

rabbitmqctl set_permissions -p storefront storefront_app '.*' '.*' '.*'
rabbitmqctl set_permissions -p operations operations_consumer '^operations\.' '^operations\.' '^operations\.'
rabbitmqctl set_permissions -p storefront operations_bridge \
  '^operations\.bridge\.' '^operations\.bridge\.' '^(orders|operations\.bridge\.)'
rabbitmqctl set_permissions -p operations operations_bridge \
  '^operations\.events$' '^operations\.events$' '^$'

echo "rabbitmq provisioning complete"
