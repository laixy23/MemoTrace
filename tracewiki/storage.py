from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import (
    InteractionLog,
    KnowledgeCard,
    PreferenceCandidate,
    SourceRecord,
    SourceSpan,
    StagingItem,
    SystemLog,
    VectorRecord,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  filename TEXT NOT NULL,
  modality TEXT NOT NULL,
  mime_type TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
  card_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  category TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_path TEXT NOT NULL,
  content TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interaction_logs (
  log_id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  answer_summary TEXT NOT NULL,
  answer_type TEXT NOT NULL,
  user_feedback TEXT NOT NULL,
  user_action TEXT NOT NULL,
  accepted INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preference_candidates (
  candidate_id TEXT PRIMARY KEY,
  field TEXT NOT NULL,
  old_value TEXT NOT NULL,
  new_value TEXT NOT NULL,
  evidence TEXT NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_spans (
  span_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  source_path TEXT NOT NULL,
  locator TEXT NOT NULL,
  text TEXT NOT NULL,
  span_type TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_logs (
  log_id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vector_index (
  item_id TEXT PRIMARY KEY,
  item_type TEXT NOT NULL,
  text TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging_items (
  staging_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  summary TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class KnowledgeStore:
    def __init__(self, sqlite_path: Path, wiki_dir: Path) -> None:
        self.sqlite_path = sqlite_path
        self.wiki_dir = wiki_dir
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(SCHEMA)

    def upsert_source(self, source: SourceRecord) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO sources
                (source_id, path, filename, modality, mime_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source.source_id,
                    source.path,
                    source.filename,
                    source.modality,
                    source.mime_type,
                    source.created_at,
                ),
            )

    def upsert_card(self, card: KnowledgeCard) -> Path:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO cards
                (card_id, title, summary, tags_json, category, source_id, source_path,
                 content, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.card_id,
                    card.title,
                    card.summary,
                    json.dumps(card.tags, ensure_ascii=False),
                    card.category,
                    card.source_id,
                    card.source_path,
                    card.content,
                    json.dumps(card.evidence, ensure_ascii=False),
                    card.created_at,
                ),
            )
        card_path = self.wiki_dir / card.filename
        card_path.write_text(card.content, encoding="utf-8")
        return card_path

    def list_cards(self) -> list[KnowledgeCard]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT card_id, title, summary, tags_json, category, source_id,
                       source_path, content, evidence_json, created_at
                FROM cards
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            KnowledgeCard(
                card_id=row[0],
                title=row[1],
                summary=row[2],
                tags=json.loads(row[3]),
                category=row[4],
                source_id=row[5],
                source_path=row[6],
                content=row[7],
                evidence=json.loads(row[8]),
                created_at=row[9],
            )
            for row in rows
        ]

    def list_sources(self) -> list[SourceRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT source_id, path, filename, modality, mime_type, created_at
                FROM sources
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            SourceRecord(
                source_id=row[0],
                path=row[1],
                filename=row[2],
                modality=row[3],
                mime_type=row[4] or "",
                created_at=row[5],
            )
            for row in rows
        ]

    def add_interaction(self, log: InteractionLog) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO interaction_logs
                (log_id, question, answer_summary, answer_type, user_feedback,
                 user_action, accepted, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.log_id,
                    log.question,
                    log.answer_summary,
                    log.answer_type,
                    log.user_feedback,
                    log.user_action,
                    1 if log.accepted else 0,
                    log.created_at,
                ),
            )

    def list_interactions(self, limit: int = 50) -> list[InteractionLog]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT log_id, question, answer_summary, answer_type, user_feedback,
                       user_action, accepted, created_at
                FROM interaction_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            InteractionLog(
                log_id=row[0],
                question=row[1],
                answer_summary=row[2],
                answer_type=row[3],
                user_feedback=row[4],
                user_action=row[5],
                accepted=bool(row[6]),
                created_at=row[7],
            )
            for row in rows
        ]

    def add_preference_candidate(self, candidate: PreferenceCandidate) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO preference_candidates
                (candidate_id, field, old_value, new_value, evidence, confidence, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.candidate_id,
                    candidate.field,
                    candidate.old_value,
                    candidate.new_value,
                    candidate.evidence,
                    candidate.confidence,
                    candidate.status,
                    candidate.created_at,
                ),
            )

    def list_preference_candidates(self, status: str | None = None) -> list[PreferenceCandidate]:
        query = """
            SELECT candidate_id, field, old_value, new_value, evidence,
                   confidence, status, created_at
            FROM preference_candidates
        """
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at DESC"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [
            PreferenceCandidate(
                candidate_id=row[0],
                field=row[1],
                old_value=row[2],
                new_value=row[3],
                evidence=row[4],
                confidence=float(row[5]),
                status=row[6],
                created_at=row[7],
            )
            for row in rows
        ]

    def update_candidate_status(self, candidate_id: str, status: str) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE preference_candidates SET status = ? WHERE candidate_id = ?",
                (status, candidate_id),
            )

    def replace_spans_for_card(self, card_id: str, spans: list[SourceSpan]) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM source_spans WHERE card_id = ?", (card_id,))
            con.executemany(
                """
                INSERT INTO source_spans
                (span_id, source_id, card_id, source_path, locator, text, span_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        span.span_id,
                        span.source_id,
                        span.card_id,
                        span.source_path,
                        span.locator,
                        span.text,
                        span.span_type,
                        span.created_at,
                    )
                    for span in spans
                ],
            )

    def list_spans(self, limit: int = 500) -> list[SourceSpan]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT span_id, source_id, card_id, source_path, locator, text, span_type, created_at
                FROM source_spans
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            SourceSpan(
                span_id=row[0],
                source_id=row[1],
                card_id=row[2],
                source_path=row[3],
                locator=row[4],
                text=row[5],
                span_type=row[6],
                created_at=row[7],
            )
            for row in rows
        ]

    def add_system_log(self, log: SystemLog) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO system_logs
                (log_id, action_type, summary, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    log.log_id,
                    log.action_type,
                    log.summary,
                    json.dumps(log.payload, ensure_ascii=False),
                    log.created_at,
                ),
            )

    def list_system_logs(self, limit: int = 80) -> list[SystemLog]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT log_id, action_type, summary, payload_json, created_at
                FROM system_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            SystemLog(
                log_id=row[0],
                action_type=row[1],
                summary=row[2],
                payload=json.loads(row[3]),
                created_at=row[4],
            )
            for row in rows
        ]

    def upsert_vectors(self, records: list[VectorRecord]) -> None:
        with self._connect() as con:
            con.executemany(
                """
                INSERT OR REPLACE INTO vector_index
                (item_id, item_type, text, vector_json, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.item_id,
                        record.item_type,
                        record.text,
                        json.dumps(record.vector),
                        json.dumps(record.metadata, ensure_ascii=False),
                        record.updated_at,
                    )
                    for record in records
                ],
            )

    def list_vectors(self, limit: int = 5000) -> list[VectorRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT item_id, item_type, text, vector_json, metadata_json, updated_at
                FROM vector_index
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            VectorRecord(
                item_id=row[0],
                item_type=row[1],
                text=row[2],
                vector=json.loads(row[3]),
                metadata=json.loads(row[4]),
                updated_at=row[5],
            )
            for row in rows
        ]

    def add_staging_item(self, item: StagingItem) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO staging_items
                (staging_id, title, url, summary, content, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.staging_id,
                    item.title,
                    item.url,
                    item.summary,
                    item.content,
                    item.status,
                    item.created_at,
                ),
            )

    def list_staging_items(self, status: str | None = None) -> list[StagingItem]:
        query = """
            SELECT staging_id, title, url, summary, content, status, created_at
            FROM staging_items
        """
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at DESC"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [
            StagingItem(
                staging_id=row[0],
                title=row[1],
                url=row[2],
                summary=row[3],
                content=row[4],
                status=row[5],
                created_at=row[6],
            )
            for row in rows
        ]

    def update_staging_status(self, staging_id: str, status: str) -> None:
        with self._connect() as con:
            con.execute("UPDATE staging_items SET status = ? WHERE staging_id = ?", (status, staging_id))
