# Runbook — operations migration 0008 (command plane)

Migration `operations.0008_operationcommand_command_plane` makes `OperationCommand.actor_id` and
`OperationCommand.idempotency_key` **required** and adds a unique constraint
`(actor_id, command_type, target, idempotency_key)`.

The migration runs a preflight that **refuses to apply** if the `OperationCommand` table already
holds any rows, because those rows predate the command plane and have no valid `actor_id` /
`idempotency_key`. It deliberately does **not** backfill placeholder values (`actor_id=0`,
`idempotency_key=""`), which would be semantically wrong and could collide on the new unique
constraint.

## If the migration stops with the preflight RuntimeError

On a fresh or empty deployment this never triggers. If it does, do **not** assume the rows are
disposable. Inspect them and confirm they are pre-command-plane **scaffold** records with no
business value before deleting anything; if they carry meaning, archive them and migrate the data
by hand rather than dropping it.

1. Inspect what is there:
   ```sql
   SELECT id, command_id, command_type, target, status, created_at FROM operations_operationcommand;
   ```
2. Decide, based on that inspection:
   - **only if** the rows are confirmed scaffold with no business value → delete them (step 3);
   - **otherwise** → archive (`pg_dump -t operations_operationcommand …`) and perform a manual,
     data-preserving migration that supplies real `actor_id` / `idempotency_key`. Do not delete.
3. Delete the confirmed-disposable rows:
   ```sql
   DELETE FROM operations_operationcommand;
   ```
4. Re-run `python manage.py migrate operations`. With the table empty, the required fields are
   added without any placeholder default and the unique constraint is created cleanly.

Only take these steps against the **operations** service database. This migration never touches
the storefront database.
