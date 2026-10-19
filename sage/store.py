"""Session-scoped storage. No model or UI dependencies."""
import json
from pathlib import Path
import sqlite3
import uuid
from contextlib import contextmanager


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, settings TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT);
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, session TEXT, name TEXT, text TEXT);
                CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, session TEXT, title TEXT, content TEXT);
                CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, session TEXT, kind TEXT, title TEXT, payload BLOB, metadata TEXT);
            """)
            columns = {r[1] for r in db.execute("PRAGMA table_info(messages)")}
            if "metadata" not in columns:
                db.execute("ALTER TABLE messages ADD COLUMN metadata TEXT DEFAULT '{}'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def session(self, session_id=None):
        with self.connect() as db:
            if session_id and db.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
                return session_id
            session_id = uuid.uuid4().hex
            db.execute("INSERT INTO sessions VALUES (?, '{}')", (session_id,))
        return session_id

    def settings(self, session):
        with self.connect() as db:
            return json.loads(db.execute("SELECT settings FROM sessions WHERE id=?", (session,)).fetchone()[0])

    def save_settings(self, session, settings):
        with self.connect() as db:
            db.execute("UPDATE sessions SET settings=? WHERE id=?", (json.dumps(settings), session))

    def history(self, session, limit=40, rich=False):
        with self.connect() as db:
            rows = db.execute("SELECT role,content,metadata FROM messages WHERE session=? ORDER BY id DESC LIMIT ?", (session, limit)).fetchall()
        return [{"role": r, "content": c, **({"metadata": json.loads(m or '{}')} if rich else {})} for r, c, m in reversed(rows)]

    def append(self, session, role, content, metadata=None):
        with self.connect() as db:
            db.execute("INSERT INTO messages(session,role,content,metadata) VALUES (?,?,?,?)", (session, role, content, json.dumps(metadata or {}, ensure_ascii=False)))

    def clear_history(self, session):
        with self.connect() as db:
            db.execute("DELETE FROM messages WHERE session=?", (session,))

    def add_document(self, session, name, text):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Document name must contain 1–200 characters")
        if not isinstance(text, str) or not text.strip() or len(text) > 300_000:
            raise ValueError("Document must contain 1–300,000 text characters")
        doc_id = uuid.uuid4().hex[:12]
        with self.connect() as db:
            if db.execute("SELECT COUNT(*) FROM documents WHERE session=?", (session,)).fetchone()[0] >= 50:
                raise ValueError("Workspace limit is 50 documents; remove one before uploading")
            db.execute("INSERT INTO documents VALUES (?,?,?,?)", (doc_id, session, name, text))
        return doc_id

    def documents(self, session):
        with self.connect() as db:
            rows = db.execute("SELECT id,name,text FROM documents WHERE session=? ORDER BY rowid", (session,)).fetchall()
        return [{"id": i, "name": n, "text": t} for i, n, t in rows]

    def remove_document(self, session, doc_id):
        with self.connect() as db:
            db.execute("DELETE FROM documents WHERE id=? AND session=?", (doc_id, session))

    def save_draft(self, session, title, content):
        draft_id = uuid.uuid4().hex[:12]
        with self.connect() as db:
            db.execute("INSERT INTO drafts VALUES (?,?,?,?)", (draft_id, session, title, content))
        return {"id": draft_id, "title": title}

    def drafts(self, session):
        with self.connect() as db:
            rows = db.execute("SELECT id,title,content FROM drafts WHERE session=? ORDER BY rowid DESC", (session,)).fetchall()
        return [{"id": i, "title": t, "content": c} for i, t, c in rows]

    def save_asset(self, session, kind, title, payload, metadata):
        if kind not in {"chart", "image"} or len(payload) > 10_000_000:
            raise ValueError("Unsupported asset or size exceeds 10 MB")
        asset_id = uuid.uuid4().hex
        with self.connect() as db:
            if db.execute("SELECT COUNT(*) FROM assets WHERE session=?", (session,)).fetchone()[0] >= 100:
                raise ValueError("Workspace limit is 100 generated assets")
            db.execute("INSERT INTO assets VALUES (?,?,?,?,?,?)", (asset_id, session, kind, title[:200], payload, json.dumps(metadata, ensure_ascii=False)))
        return {"id": asset_id, "kind": kind, "title": title[:200], **metadata}

    def asset(self, session, asset_id):
        with self.connect() as db:
            row = db.execute("SELECT kind,title,payload,metadata FROM assets WHERE session=? AND id=?", (session, asset_id)).fetchone()
        return {"id": asset_id, "kind": row[0], "title": row[1], "payload": row[2], **json.loads(row[3])} if row else None

    def assets(self, session):
        with self.connect() as db:
            rows = db.execute("SELECT id,kind,title,metadata FROM assets WHERE session=? ORDER BY rowid DESC LIMIT 40", (session,)).fetchall()
        return [{"id": i, "kind": k, "title": t, **json.loads(m)} for i, k, t, m in rows]
