import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class BatchJobStatus:
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"

class BatchQueueService:
    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.is_running = False

    def create_batch_job(self, batch_id: str, file_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        job_state = {
            "batch_id": batch_id,
            "status": BatchJobStatus.QUEUED,
            "total": len(file_list),
            "completed": 0,
            "processing": 0,
            "queued": len(file_list),
            "failed": 0,
            "files": file_list,
            "errors": [],
            "created_at": datetime.utcnow().isoformat()
        }
        self.jobs[batch_id] = job_state
        return job_state

    def get_batch_status(self, batch_id: str) -> Optional[Dict[str, Any]]:
        return self.jobs.get(batch_id)

    def retry_failed(self, batch_id: str) -> Optional[Dict[str, Any]]:
        job = self.jobs.get(batch_id)
        if not job:
            return None
        
        failed_files = [f for f in job["files"] if f.get("status") == "FAILED"]
        for f in failed_files:
            f["status"] = "QUEUED"
            f.pop("error", None)

        job["queued"] += len(failed_files)
        job["failed"] -= len(failed_files)
        job["status"] = BatchJobStatus.PROCESSING
        return job
