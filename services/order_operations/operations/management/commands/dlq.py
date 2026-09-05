"""
operator handling of the operations dead-letter queue

replay goes through the exchange with the original routing key: only the projection and outcome
queues are bound to it, so the message lands back in the one it fell out of
"""

import datetime as dt
import json
import logging

import pika
from django.core.management.base import BaseCommand, CommandError

from operations import messaging

log = logging.getLogger(__name__)

QUEUE = messaging.DLQ
PREVIEW = 20
BODY_PREVIEW = 200


def _summary(properties, body: bytes) -> str:
    try:
        event_type = json.loads(body).get("event_type", "?")
    except (json.JSONDecodeError, AttributeError, TypeError):
        event_type = "unparsed"
    death = (properties.headers or {}).get("x-death") or [{}]
    return f"{event_type} | reason={death[0].get('reason', '?')} | id={properties.message_id}"


class Command(BaseCommand):
    help = "Inspects the operations dead-letter queue, replays messages, or discards them."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--list", action="store_true", help="show what is queued, consuming nothing")
        parser.add_argument("--replay", type=int, default=0, metavar="N")
        parser.add_argument("--drop", type=int, default=0, metavar="N")
        parser.add_argument("--yes", action="store_true", help="required to discard")
        parser.add_argument("--reason", default="", help="why the discarded messages are unprocessable")
        parser.add_argument("--operator", default="", help="who is taking the action")

    def handle(self, *args, **options) -> None:
        replay, drop = options["replay"], options["drop"]
        if replay and drop:
            raise CommandError("replay and drop cannot run together")
        if drop:
            if not options["yes"]:
                raise CommandError("discarding needs --yes")
            if not options["reason"].strip():
                raise CommandError("discarding needs --reason")
        if not (replay or drop):
            options["list"] = True

        connection = messaging.connect()
        channel = connection.channel()
        channel.confirm_delivery()
        try:
            if options["list"]:
                self._list(channel)
            elif replay:
                self._replay(channel, replay, options["operator"])
            else:
                self._drop(channel, drop, options["reason"], options["operator"])
        finally:
            connection.close()

    def _list(self, channel) -> None:
        """reads without consuming: everything is put back before the command returns"""
        held = []
        while len(held) < PREVIEW:
            method, properties, body = channel.basic_get(QUEUE, auto_ack=False)
            if method is None:
                break
            held.append((method, properties, body))
        self.stdout.write(f"{QUEUE}: {len(held)} message(s) read")
        for _, properties, body in held:
            self.stdout.write(f"  {_summary(properties, body)}")
            self.stdout.write(f"    {body[:BODY_PREVIEW].decode(errors='replace')}")
        for method, _, _ in held:
            channel.basic_nack(method.delivery_tag, requeue=True)

    def _replay(self, channel, count: int, operator: str) -> None:
        done = 0
        while done < count:
            method, properties, body = channel.basic_get(QUEUE, auto_ack=False)
            if method is None:
                break
            headers = {k: v for k, v in (properties.headers or {}).items()
                       if k not in ("x-retries", "x-death", "x-first-death-reason",
                                    "x-first-death-queue", "x-first-death-exchange")}
            headers["x-replayed-at"] = dt.datetime.now(dt.UTC).isoformat()
            headers["x-replayed-by"] = operator or "unattributed"
            try:
                channel.basic_publish(
                    exchange=messaging.EXCHANGE,
                    routing_key=method.routing_key,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json", delivery_mode=2,
                        message_id=properties.message_id,
                        correlation_id=properties.correlation_id,
                        headers=headers,
                    ),
                    mandatory=True,
                )
            except Exception as exc:
                # the message is only ever removed after a confirm, so it stays put on failure
                channel.basic_nack(method.delivery_tag, requeue=True)
                raise CommandError(f"replay stopped after {done}: {exc}") from exc
            channel.basic_ack(method.delivery_tag)
            done += 1
            log.info("dlq message replayed", extra={"message_id": properties.message_id,
                                                    "routing_key": method.routing_key})
        self.stdout.write(self.style.SUCCESS(f"replayed {done} message(s) to {messaging.EXCHANGE}"))

    def _drop(self, channel, count: int, reason: str, operator: str) -> None:
        done = 0
        while done < count:
            method, properties, body = channel.basic_get(QUEUE, auto_ack=False)
            if method is None:
                break
            log.warning(
                "dlq message discarded",
                extra={"message_id": properties.message_id, "routing_key": method.routing_key,
                       "operator": operator or "unattributed", "reason": reason,
                       "body": body[:BODY_PREVIEW].decode(errors="replace")},
            )
            channel.basic_ack(method.delivery_tag)
            done += 1
        self.stdout.write(self.style.SUCCESS(f"discarded {done} message(s) from {QUEUE}"))
