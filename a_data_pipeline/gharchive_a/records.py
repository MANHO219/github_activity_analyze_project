"""One authoritative validation rule set for Python and Spark ingestion.

The full raw event remains in the immutable archive. A canonical hash includes
payload too, so conflicting IDs are not hidden by selecting only common fields.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone

MAX_ID = 2**63 - 1


def positive_id(value):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        number = int(value)
    else:
        return None
    return number if 0 < number <= MAX_ID else None


def nonempty_text(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return value


def source_hour(name):
    return datetime.strptime(name.removesuffix(".json.gz"), "%Y-%m-%d-%H").replace(tzinfo=timezone.utc)


def reject_constant(value):
    raise ValueError(f"Non-JSON constant: {value}")


def normalize_line(raw, filename, line_number):
    """Returns an explicit status; no rejected or blank line silently disappears."""
    record = {"status": "blank", "reason": None, "source_file": filename,
              "source_line": line_number, "raw_line": None, "canonical_sha256": None,
              "optional_field_issues": [], "time_outside_file_hour": False}
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except UnicodeDecodeError:
        record.update(status="parse_error", reason="invalid_utf8", raw_line=raw.decode("utf-8", errors="replace"), raw_hex=raw.hex())
        return record
    if not text.strip():
        return record
    record["raw_line"] = text.rstrip("\r\n")
    try:
        event = json.loads(text, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError, RecursionError) as error:
        record.update(status="parse_error", reason="invalid_json", parse_detail=str(error))
        return record
    if not isinstance(event, dict):
        record.update(status="invalid", reason="json_root_not_object")
        return record
    event_id = positive_id(event.get("id"))
    event_type = nonempty_text(event.get("type"))
    repo = event.get("repo") if isinstance(event.get("repo"), dict) else {}
    repo_id = positive_id(repo.get("id"))
    if event_id is None:
        record.update(status="invalid", reason="invalid_event_id")
        return record
    if event_type is None:
        record.update(status="invalid", reason="invalid_event_type")
        return record
    if repo_id is None:
        record.update(status="invalid", reason="invalid_repo_id")
        return record
    try:
        created = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("Time must contain an explicit UTC offset")
        created = created.astimezone(timezone.utc)
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError):
        record.update(status="invalid", reason="invalid_event_time")
        return record
    actor = event.get("actor") if isinstance(event.get("actor"), dict) else {}
    values = {"repo_name": nonempty_text(repo.get("name")),
              "actor_id": positive_id(actor.get("id")),
              "actor_login": nonempty_text(actor.get("login"))}
    flags = [f"missing_or_invalid_{key}" for key, value in values.items() if value is None]
    hour = source_hour(filename)
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    record.update(status="valid", reason=None, event_id=str(event_id), event_type=event_type,
                  event_time=created.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                  event_date=created.date().isoformat(), repo_id=repo_id, **values,
                  source_hour=hour.isoformat().replace("+00:00", "Z"),
                  time_outside_file_hour=created.replace(minute=0, second=0, microsecond=0) != hour,
                  optional_field_issues=flags,
                  canonical_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    return record


def iter_records(path):
    """Streams bytes to detect invalid UTF-8 and lets truncated gzip fail the stage."""
    from pathlib import Path
    path = Path(path)
    with gzip.open(path, "rb") as handle:
        for number, raw in enumerate(handle, 1):
            yield normalize_line(raw, path.name, number)
