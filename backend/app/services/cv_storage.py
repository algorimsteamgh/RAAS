"""Original CV file storage.

S3 in AWS (bucket CV_BUCKET, SSE-KMS with CV_BUCKET_KMS_KEY_ID, a SHA-256
checksum on every object), or a local folder for development and tests.

Object keys:
    cvs/{candidate_id}/{sha256}.{ext}        a candidate's original CV
    batch/{batch_id}/{file_index}.{ext}      a batch upload waiting for the worker
"""
import base64
import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Optional, Protocol

from backend.app.config import settings

logger = logging.getLogger(__name__)

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

_SAFE_EXT = re.compile(r"^[a-z0-9]{1,10}$")


def content_type_for(ext: str) -> str:
    return CONTENT_TYPES.get(ext.lower(), "application/octet-stream")


def _ext(ext: str) -> str:
    ext = (ext or "").lower().lstrip(".")
    return ext if _SAFE_EXT.match(ext) else "bin"


def cv_key(candidate_id: str, sha256_hex: str, ext: str) -> str:
    return f"cvs/{candidate_id}/{sha256_hex}.{_ext(ext)}"


def batch_key(batch_id: str, file_index: int, ext: str) -> str:
    return f"batch/{batch_id}/{file_index}.{_ext(ext)}"


class StoredObject(dict):
    """{"key", "version_id", "size"}"""


class CVStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str, sha256_hex: Optional[str] = None) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def checksum_sha256(self, key: str) -> Optional[str]:
        """The stored SHA-256 (hex) of the object, without downloading it."""
        ...


class S3CVStorage:
    def __init__(self, bucket: str, kms_key_id: Optional[str] = None, client=None):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.kms_key_id = kms_key_id
        self.client = client or boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=5, read_timeout=60),
        )

    def put(self, key: str, data: bytes, content_type: str, sha256_hex: Optional[str] = None) -> StoredObject:
        digest = hashlib.sha256(data).digest()
        if sha256_hex and digest.hex() != sha256_hex:
            raise ValueError(f"Checksum mismatch for {key}")
        args = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
            # Stored with the object; S3 recomputes it and rejects a corrupted upload.
            "ChecksumAlgorithm": "SHA256",
            "ChecksumSHA256": base64.b64encode(digest).decode(),
            "ServerSideEncryption": "aws:kms",
        }
        if self.kms_key_id:
            args["SSEKMSKeyId"] = self.kms_key_id
            args["BucketKeyEnabled"] = True
        resp = self.client.put_object(**args)
        return StoredObject(key=key, version_id=resp.get("VersionId"), size=len(data))

    def get(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def delete(self, key: str) -> None:
        # Versioned bucket: this adds a delete marker; earlier versions stay
        # recoverable until the lifecycle rule expires them.
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def checksum_sha256(self, key: str) -> Optional[str]:
        resp = self.client.head_object(Bucket=self.bucket, Key=key, ChecksumMode="ENABLED")
        value = resp.get("ChecksumSHA256")
        if not value or "-" in value:  # multipart composite checksums are not a file hash
            return None
        return base64.b64decode(value).hex()


class LocalCVStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"Invalid storage key: {key}")
        return path

    def put(self, key: str, data: bytes, content_type: str, sha256_hex: Optional[str] = None) -> StoredObject:
        if sha256_hex and hashlib.sha256(data).hexdigest() != sha256_hex:
            raise ValueError(f"Checksum mismatch for {key}")
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return StoredObject(key=key, version_id=None, size=len(data))

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def checksum_sha256(self, key: str) -> Optional[str]:
        path = self._path(key)
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


_storage: Optional[CVStorage] = None
_lock = threading.Lock()


def get_cv_storage() -> CVStorage:
    global _storage
    if _storage is None:
        with _lock:
            if _storage is None:
                if settings.STORAGE_BACKEND == "s3":
                    if not settings.CV_BUCKET:
                        raise RuntimeError("STORAGE_BACKEND=s3 needs CV_BUCKET")
                    _storage = S3CVStorage(settings.CV_BUCKET, settings.CV_BUCKET_KMS_KEY_ID)
                else:
                    _storage = LocalCVStorage(settings.CV_LOCAL_DIR)
                logger.info("CV storage: %s", type(_storage).__name__)
    return _storage


def set_cv_storage(storage: Optional[CVStorage]) -> None:
    """Tests and the data-load job swap the storage backend."""
    global _storage
    _storage = storage
