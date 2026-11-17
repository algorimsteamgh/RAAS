"""Table mapping SQLite -> PostgreSQL and the canonical row form used for the
row hashes in the verification report (RAAS-MIG-05 sections 3 and 5).

Canonical form, identical on both sides:
  text   str, NUL characters removed (PostgreSQL cannot store them)
  json   parsed, NULs removed, dumped with sorted keys and no whitespace
  float  repr(float)
  int    str(int)
  ts     ISO-8601 UTC with microseconds
  NULL   None
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

TEXT, JSON, FLOAT, INT, TS = "text", "json", "float", "int", "ts"


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool = True


@dataclass(frozen=True)
class Table:
    name: str
    pk: Tuple[str, ...]
    columns: Tuple[Column, ...]
    identity: Optional[str] = None  # bigint identity column to resync
    candidate_column: Optional[str] = "candidate_id"  # for the seed-data rule
    timestamp_columns: Tuple[str, ...] = field(default=("created_at",))

    @property
    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


# Dependency order: parents before children.
TABLES: Tuple[Table, ...] = (
    Table("jobs", ("job_id",), (
        Column("job_id", TEXT, False), Column("title", TEXT, False), Column("department", TEXT),
        Column("location", TEXT), Column("employment_type", TEXT), Column("seniority", TEXT),
        Column("description", TEXT), Column("minimum_years_experience", FLOAT),
        Column("required_skills", JSON), Column("preferred_skills", JSON),
        Column("education_requirements", JSON), Column("domain_requirements", JSON),
        Column("responsibilities", JSON), Column("other_constraints", TEXT), Column("source", TEXT),
        Column("status", TEXT), Column("created_at", TS), Column("updated_at", TS),
    ), candidate_column=None, timestamp_columns=("created_at", "updated_at")),
    Table("candidates", ("candidate_id",), (
        Column("candidate_id", TEXT, False), Column("full_name", TEXT), Column("email", TEXT),
        Column("phone", TEXT), Column("location", TEXT), Column("roles", JSON), Column("skills", JSON),
        Column("years_experience", FLOAT), Column("notice_period", TEXT), Column("source", TEXT),
        Column("status", TEXT), Column("raw_json", JSON), Column("file_hash", TEXT),
        Column("filename", TEXT), Column("created_at", TS),
    )),
    # file_data is not copied into PostgreSQL: it goes to S3 (s3_key, size_bytes).
    Table("original_files", ("candidate_id",), (
        Column("candidate_id", TEXT, False), Column("filename", TEXT, False), Column("file_type", TEXT, False),
        Column("sha256_hash", TEXT, False), Column("created_at", TS),
    )),
    Table("match_results", ("id",), (
        Column("id", INT, False), Column("candidate_id", TEXT, False), Column("job_id", TEXT, False),
        Column("score", FLOAT, False), Column("recommendation", TEXT, False), Column("matched_skills", JSON),
        Column("missing_skills", JSON), Column("reasoning", TEXT), Column("score_breakdown", JSON),
        Column("created_at", TS),
    ), identity="id"),
    Table("recruiter_actions", ("id",), (
        Column("id", INT, False), Column("candidate_id", TEXT, False), Column("job_id", TEXT),
        Column("action", TEXT, False), Column("note", TEXT), Column("tag", TEXT), Column("user_id", TEXT),
        Column("created_at", TS),
    ), identity="id"),
    Table("candidate_chat_messages", ("id",), (
        Column("id", INT, False), Column("candidate_id", TEXT, False), Column("job_id", TEXT),
        Column("role", TEXT, False), Column("content", TEXT, False), Column("created_at", TS),
    ), identity="id"),
    Table("audit_logs", ("id",), (
        Column("id", INT, False), Column("event_type", TEXT, False), Column("candidate_id", TEXT),
        Column("details", TEXT), Column("timestamp", TS),
    ), identity="id", timestamp_columns=("timestamp",)),
    Table("batch_jobs", ("batch_id",), (
        Column("batch_id", TEXT, False), Column("job_id", TEXT), Column("status", TEXT), Column("total", INT),
        Column("completed", INT), Column("processing", INT), Column("queued", INT), Column("failed", INT),
        Column("file_statuses", JSON), Column("created_at", TS), Column("updated_at", TS),
    ), candidate_column=None, timestamp_columns=("created_at", "updated_at")),
)

TABLES_BY_NAME = {t.name: t for t in TABLES}


class ConversionError(ValueError):
    pass


def strip_nul(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {strip_nul(k): strip_nul(v) for k, v in value.items()}
    return value


def has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, list):
        return any(has_nul(v) for v in value)
    if isinstance(value, dict):
        return any(has_nul(k) or has_nul(v) for k, v in value.items())
    return False


def parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as err:
        raise ConversionError(f"unparseable timestamp {value!r}") from err
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_value(column: Column, value: Any) -> Any:
    """SQLite value -> the Python value written to PostgreSQL. Strict: a value
    that does not fit raises ConversionError (no silent fixes)."""
    if value is None:
        if not column.nullable:
            raise ConversionError(f"{column.name} is NULL")
        return None
    if column.kind == TEXT:
        if isinstance(value, bytes):
            raise ConversionError(f"{column.name} holds binary data")
        return strip_nul(str(value))
    if column.kind == JSON:
        if isinstance(value, (dict, list)):
            return strip_nul(value)
        try:
            return strip_nul(json.loads(value))
        except (TypeError, ValueError) as err:
            raise ConversionError(f"{column.name} is not valid JSON: {str(value)[:60]!r}") from err
    if column.kind == FLOAT:
        try:
            return float(value)
        except (TypeError, ValueError) as err:
            raise ConversionError(f"{column.name} is not a number: {value!r}") from err
    if column.kind == INT:
        if isinstance(value, float) and not value.is_integer():
            raise ConversionError(f"{column.name} is not an integer: {value!r}")
        try:
            return int(value)
        except (TypeError, ValueError) as err:
            raise ConversionError(f"{column.name} is not an integer: {value!r}") from err
    if column.kind == TS:
        return parse_timestamp(value)
    raise ConversionError(f"unknown column kind {column.kind}")


def canonical(column: Column, value: Any) -> Any:
    """Parsed (or PostgreSQL-returned) value -> canonical form for hashing."""
    if value is None:
        return None
    if column.kind == TEXT:
        return strip_nul(str(value))
    if column.kind == JSON:
        if isinstance(value, str):
            value = json.loads(value)
        return json.dumps(strip_nul(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if column.kind == FLOAT:
        return repr(float(value))
    if column.kind == INT:
        return str(int(value))
    if column.kind == TS:
        return parse_timestamp(value).astimezone(timezone.utc).isoformat(timespec="microseconds")
    return value


def row_hash(table: Table, row: Dict[str, Any]) -> str:
    values = [canonical(c, row.get(c.name)) for c in table.columns]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def pk_of(table: Table, row: Dict[str, Any]) -> str:
    return "|".join(str(row.get(k)) for k in table.pk)
