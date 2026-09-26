"""ChatGPT export ingestion. Parsing stays behind this adapter."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from serah.clock import utc_now
from serah.ids import new_id, stable_id
from serah.models import Conversation, ImportWarning, Message


def _iso(timestamp: float | int | None) -> str | None:
    if timestamp is None:
        return None
    try:
        moment = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return moment.replace(microsecond=0).isoformat()


def _parts_text(content: object) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not isinstance(content, dict):
        return "", ["message content was not an object"]
    parts = content.get("parts")
    chunks: list[str] = []
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, str):
                if part.strip():
                    chunks.append(part)
            elif isinstance(part, dict):
                warnings.append("skipped a non-text content part")
            else:
                warnings.append("skipped an unknown content part")
    elif isinstance(content.get("text"), str) and content["text"].strip():
        chunks.append(content["text"])
    elif content.get("content_type") not in {None, "text", "multimodal_text", "user_editable_context"}:
        warnings.append(f"unsupported content type {content.get('content_type')}")
    return "\n".join(chunks).strip(), warnings


def _current_branch(mapping: dict, current_node: str | None) -> set[str]:
    found: set[str] = set()
    node = current_node
    seen: set[str] = set()
    while isinstance(node, str) and node and node not in seen and node in mapping:
        seen.add(node)
        found.add(node)
        parent = mapping[node].get("parent") if isinstance(mapping[node], dict) else None
        node = parent if isinstance(parent, str) else None
    return found


def _load_documents(path: Path) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    if path.is_dir():
        files = sorted(
            item
            for item in path.iterdir()
            if item.suffix == ".json" and "conversation" in item.name.lower()
        )
        documents: list[dict] = []
        for item in files:
            documents.extend(_documents_from_json(json.loads(item.read_text(encoding="utf-8")), warnings))
        if not files:
            warnings.append("directory contained no conversation json files")
        return documents, warnings
    if path.suffix.lower() == ".zip":
        documents = []
        with zipfile.ZipFile(path) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".json") and "conversation" in Path(name).name.lower()
            ]
            if not names:
                warnings.append("zip contained no conversation json files")
            for name in names:
                documents.extend(
                    _documents_from_json(json.loads(archive.read(name).decode("utf-8")), warnings)
                )
        return documents, warnings
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _documents_from_json(payload, warnings), warnings


def _documents_from_json(payload: object, warnings: list[str]) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("mapping"), dict):
        return [payload]
    if isinstance(payload, dict):
        for key in ("conversations", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    warnings.append("json payload was not a conversation or a list of conversations")
    return []


def import_chatgpt(session: Session, path: Path) -> dict:
    documents, file_warnings = _load_documents(path)
    return import_conversations(session, documents, file_warnings)


def import_conversations(session: Session, documents: list[dict], extra_warnings: list[str] | None = None) -> dict:
    batch_id = new_id()
    now = utc_now()
    stats = {
        "batch_id": batch_id,
        "conversations": 0,
        "messages": 0,
        "skipped_conversations": 0,
        "skipped_messages": 0,
        "warnings": 0,
    }
    for warning in extra_warnings or []:
        _warn(session, batch_id, "", warning, now)
        stats["warnings"] += 1
    for document in documents:
        _import_one(session, document, batch_id, now, stats)
    session.flush()
    return stats


def _warn(session: Session, batch_id: str, ref: str, warning: str, now: str) -> None:
    session.add(
        ImportWarning(
            id=new_id(),
            batch_id=batch_id,
            external_ref=ref[:200],
            warning=warning,
            created_at=now,
        )
    )


def _import_one(session: Session, document: dict, batch_id: str, now: str, stats: dict) -> None:
    external_id = str(document.get("conversation_id") or document.get("id") or "")
    mapping = document.get("mapping")
    if not external_id or not isinstance(mapping, dict):
        _warn(session, batch_id, external_id, "conversation missing id or mapping", now)
        stats["warnings"] += 1
        return
    conversation_id = stable_id("chatgpt", "conversation", external_id)
    existing = session.scalar(
        select(Conversation).where(
            Conversation.source_type == "chatgpt",
            Conversation.external_id == external_id,
        )
    )
    if existing is not None:
        stats["skipped_conversations"] += 1
        return
    created = _iso(document.get("create_time"))
    title = document.get("title") if isinstance(document.get("title"), str) else ""
    session.add(
        Conversation(
            id=conversation_id,
            source_type="chatgpt",
            external_id=external_id,
            title=title,
            created_at=created,
            imported_at=now,
            source_metadata={"update_time": document.get("update_time")},
        )
    )
    stats["conversations"] += 1
    current_ids = _current_branch(
        mapping, document.get("current_node") if isinstance(document.get("current_node"), str) else None
    )
    if not current_ids:
        _warn(session, batch_id, external_id, "current branch could not be resolved; no node marked current", now)
        stats["warnings"] += 1
    ordinal = 0
    # Stable order: timestamp, then node id.
    nodes = []
    for node_id, node in mapping.items():
        if not isinstance(node, dict):
            _warn(session, batch_id, str(node_id), "mapping node was not an object", now)
            stats["warnings"] += 1
            continue
        nodes.append((str(node_id), node))
    def sort_key(item: tuple[str, dict]) -> tuple:
        message = item[1].get("message") if isinstance(item[1].get("message"), dict) else {}
        stamp = message.get("create_time")
        try:
            stamp_value = float(stamp)
        except (TypeError, ValueError):
            stamp_value = 0.0
        return (stamp_value, item[0])

    for node_id, node in sorted(nodes, key=sort_key):
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author") if isinstance(message.get("author"), dict) else {}
        role = str(author.get("role") or "unknown")
        external_message_id = message.get("id")
        derived = False
        if not isinstance(external_message_id, str) or not external_message_id:
            fingerprint = hashlib.sha256(json.dumps(message.get("content"), default=str).encode()).hexdigest()[:16]
            external_message_id = f"derived-{node_id}-{fingerprint}"
            derived = True
            _warn(session, batch_id, node_id, "message missing id; derived a stable id", now)
            stats["warnings"] += 1
        text, part_warnings = _parts_text(message.get("content"))
        for part_warning in part_warnings:
            _warn(session, batch_id, external_message_id, part_warning, now)
            stats["warnings"] += 1
        if not text and part_warnings:
            stats["skipped_messages"] += 1
            continue
        timestamp = _iso(message.get("create_time"))
        if timestamp is None:
            timestamp = created
            _warn(session, batch_id, external_message_id, "message missing timestamp; used conversation time", now)
            stats["warnings"] += 1
            if timestamp is None:
                stats["skipped_messages"] += 1
                continue
        already = session.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.external_id == external_message_id,
            )
        )
        if already is not None:
            stats["skipped_messages"] += 1
            continue
        parent = node.get("parent") if isinstance(node.get("parent"), str) else None
        session.add(
            Message(
                id=stable_id("chatgpt", "message", external_id, external_message_id),
                conversation_id=conversation_id,
                external_id=external_message_id,
                role=role,
                text=text,
                timestamp=timestamp,
                ordinal=ordinal,
                on_current_branch=node_id in current_ids,
                parent_external_id=parent,
                source_metadata={"derived_id": derived, "node_id": node_id},
            )
        )
        ordinal += 1
        stats["messages"] += 1
