"""Batch worker: long-polls the SQS batch queue and processes one CV per
message. Entry point of the ECS worker service:

    python -m backend.app.worker

Each message is {"batch_id": ..., "file_index": ...}. Progress is written to
PostgreSQL (batch_files / batch_jobs), so the API's status and SSE endpoints
read it from any task. A file that fails with a retryable error is made
visible again after a short back-off; after WORKER_MAX_ATTEMPTS it is marked
FAILED. Messages that keep crashing the worker go to the dead-letter queue
(maxReceiveCount 3 on the queue).

SIGTERM (ECS stop / deploy) stops polling and lets in-flight files finish.
"""
import asyncio
import json
import logging
import signal
import sys
from typing import Any, Dict, Set

from backend.app.config import settings
from backend.app.db import database as db
from backend.app.services import batch_service

logger = logging.getLogger("raas.worker")

RETRY_BACKOFF_SECONDS = 30
SHUTDOWN_GRACE_SECONDS = 110  # ECS stopTimeout is up to 120 s


class Worker:
    def __init__(self, queue_url: str, concurrency: int, client: Any = None):
        self.queue_url = queue_url
        self.concurrency = max(1, concurrency)
        self.client = client or batch_service.sqs_client()
        self.stopping = asyncio.Event()
        self.in_flight: Set[asyncio.Task] = set()
        self.processed = 0

    def request_stop(self, *_: Any) -> None:
        if not self.stopping.is_set():
            logger.info("Stop requested; finishing %d in-flight file(s).", len(self.in_flight))
            self.stopping.set()

    async def run(self, max_messages: int = 0) -> None:
        """Poll until stopped (or until max_messages are handled, for tests)."""
        logger.info("Worker started: queue=%s concurrency=%d", self.queue_url, self.concurrency)
        while not self.stopping.is_set():
            if max_messages and self.processed >= max_messages:
                break
            free = self.concurrency - len(self.in_flight)
            if free <= 0:
                await asyncio.wait(self.in_flight, return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                resp = await asyncio.to_thread(
                    self.client.receive_message,
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=min(10, free),
                    WaitTimeSeconds=20 if not max_messages else 1,
                    AttributeNames=["ApproximateReceiveCount"],
                )
            except Exception as err:
                logger.error("SQS receive failed: %s", err)
                await asyncio.sleep(5)
                continue
            for message in resp.get("Messages", []):
                task = asyncio.create_task(self.handle(message))
                self.in_flight.add(task)
                task.add_done_callback(self.in_flight.discard)
            if max_messages and not resp.get("Messages") and not self.in_flight:
                break

        if self.in_flight:
            await asyncio.wait(self.in_flight, timeout=SHUTDOWN_GRACE_SECONDS)
        logger.info("Worker stopped after %d message(s).", self.processed)

    async def handle(self, message: Dict[str, Any]) -> None:
        receipt = message["ReceiptHandle"]
        try:
            body = json.loads(message["Body"])
            batch_id, file_index = body["batch_id"], int(body["file_index"])
        except Exception:
            logger.error("Dropping malformed message %s", message.get("MessageId"))
            await self._delete(receipt)
            return

        try:
            outcome = await batch_service.process_file(batch_id, file_index)
        except Exception as err:  # database unreachable etc.: let SQS redeliver
            logger.exception("Batch %s file %s: unexpected error: %s", batch_id, file_index, err)
            outcome = batch_service.RETRY
        finally:
            self.processed += 1

        if outcome == batch_service.DONE:
            await self._delete(receipt)
        else:
            receives = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            try:
                await asyncio.to_thread(
                    self.client.change_message_visibility,
                    QueueUrl=self.queue_url,
                    ReceiptHandle=receipt,
                    VisibilityTimeout=min(900, RETRY_BACKOFF_SECONDS * receives),
                )
            except Exception as err:
                logger.warning("Could not shorten visibility for a retry: %s", err)

    async def _delete(self, receipt: str) -> None:
        try:
            await asyncio.to_thread(self.client.delete_message, QueueUrl=self.queue_url, ReceiptHandle=receipt)
        except Exception as err:
            logger.error("SQS delete failed (message will be redelivered and skipped): %s", err)


async def main() -> int:
    if not settings.BATCH_QUEUE_URL:
        logger.error("BATCH_QUEUE_URL is not set")
        return 2
    worker = Worker(settings.BATCH_QUEUE_URL, settings.WORKER_CONCURRENCY)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.request_stop)
    try:
        await worker.run()
    finally:
        db.close_pool()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sys.exit(asyncio.run(main()))
