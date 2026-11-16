"""Per-file progress for SQS batch processing.

The API writes one row per uploaded file and one SQS message per row; worker
tasks update their own row, so several workers never race on one JSON array.
batch_jobs keeps its counters for the existing API responses; they are
recomputed from batch_files on every status change.

Revision ID: 0002_batch_files
Revises: 0001_initial_schema
Create Date: 2026-11-16
"""
from alembic import op

revision = "0002_batch_files"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE batch_files (
            batch_id      text NOT NULL REFERENCES batch_jobs (batch_id) ON DELETE CASCADE,
            file_index    integer NOT NULL,
            filename      text NOT NULL,
            file_type     text NOT NULL,
            staging_key   text,
            size_bytes    bigint,
            status        text NOT NULL DEFAULT 'QUEUED',
            candidate_id  text,
            error         text,
            attempts      integer NOT NULL DEFAULT 0,
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (batch_id, file_index)
        );
        CREATE INDEX ix_batch_files_status ON batch_files (status) WHERE status IN ('QUEUED', 'PROCESSING');
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS batch_files;")
