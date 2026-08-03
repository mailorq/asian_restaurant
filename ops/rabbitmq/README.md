# RabbitMQ provisioning

Storefront and operations are isolated by **vhost + user**, with minimal permissions:

| vhost | user | configure / write / read |
|---|---|---|
| `storefront` | `storefront_app` | `.*` / `.*` / `.*` |
| `operations` | `operations_consumer` | `^operations\.` (own namespace only) |
| `storefront` | `operations_bridge` | `^operations\.bridge\.` / `^operations\.bridge\.` / `^(orders\|operations\.bridge\.)` |
| `operations` | `operations_bridge` | `^operations\.events$` / `^operations\.events$` / `^$` |

The bridge is the only cross-vhost actor; it reads `orders` on the storefront vhost
and writes only `operations.events` on the operations vhost.

## Dev

`definitions.dev.json` is a **development-only** template with placeholder passwords.
Compose mounts it and `rabbitmq.conf` loads it at boot (`load_definitions`). Do not
put real credentials in it and do not use it outside dev.

## Staging / production

Do **not** ship `definitions.dev.json`. `compose.prod.yaml` overrides the broker so the
dev template and `load_definitions` are not mounted (`volumes: !override`), boots a
baseline admin from `RABBITMQ_ADMIN_USER/PASSWORD`, and you converge the rest from
secrets with `provision.sh` — idempotent, reads passwords from the environment, safe on
an existing volume (never deletes vhosts, users, queues or messages), and it also
**revokes** any stale grants in vhosts a user must not touch:

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d rabbitmq
docker compose -f compose.yaml -f compose.prod.yaml exec -T \
  -e RABBITMQ_ADMIN_USER -e RABBITMQ_ADMIN_PASSWORD \
  -e STOREFRONT_MQ_PASSWORD -e OPERATIONS_MQ_PASSWORD -e BRIDGE_MQ_PASSWORD \
  rabbitmq bash -s < ops/rabbitmq/provision.sh
```

## Updating an existing broker without data loss

`provision.sh` converges users and permissions in place. To rotate a password on a
running broker with an existing volume:

1. set the new value in your secret store and re-run `provision.sh` (or
   `rabbitmqctl change_password <user> <new>`);
2. update the matching AMQP URL and restart the dependent services so they reconnect
   (e.g. `docker compose up -d --force-recreate operations-consumer operations-bridge`).

Never `docker compose down -v` or delete the `rabbitmqdata` volume to apply credential
changes — that destroys durable queues and unacked messages. Adding a new vhost/user is
likewise just another `provision.sh` run.
