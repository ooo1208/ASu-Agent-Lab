"""SQLite authentication for the explicitly local demonstration app."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalUser:
    user_id: str
    username: str
    display_name: str


class LocalState:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL, updated REAL NOT NULL, messages TEXT NOT NULL DEFAULT '[]', pending TEXT);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _hash(password: str, salt: str | None = None):
        if not 8 <= len(password) <= 128:
            raise ValueError("密码长度须为 8–128 位")
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 300000).hex()
        return salt + ":" + digest

    def register(self, username: str, password: str, display_name: str | None):
        normalized = username.strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff]{3,32}", normalized):
            raise ValueError("用户名须为 3–32 位文字、数字或下划线")
        name = (display_name or username).strip()
        if not 1 <= len(name) <= 50:
            raise ValueError("显示名称须为 1–50 位")
        user = LocalUser(uuid.uuid4().hex, normalized, name)
        with self.connect() as db:
            try:
                db.execute("INSERT INTO users VALUES(?,?,?,?)", (user.user_id, user.username, user.display_name, self._hash(password)))
            except sqlite3.IntegrityError as exc:
                raise ValueError("用户名已存在") from exc
        return user

    def login(self, username: str, password: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        if row and hmac.compare_digest(self._hash(password, row["password_hash"].split(":")[0]), row["password_hash"]):
            return LocalUser(row["id"], row["username"], row["display_name"])
        return None

    def issue(self, user: LocalUser):
        token = secrets.token_urlsafe(40)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user.user_id, time.time() + 43200))
        return token

    def authenticate(self, token: str):
        with self.connect() as db:
            row = db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?", (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return LocalUser(row["id"], row["username"], row["display_name"]) if row else None

    def claim_thread(self, user_id: str, thread_id: str, title: str = "新会话"):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT user_id FROM threads WHERE id=?", (thread_id,)).fetchone()
            if existing and existing[0] != user_id:
                raise PermissionError("会话不存在")
            db.execute("INSERT OR IGNORE INTO threads(id,user_id,title,updated) VALUES(?,?,?,?)", (thread_id, user_id, title[:60], time.time()))

    def thread(self, user_id: str, thread_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM threads WHERE id=? AND user_id=?", (thread_id, user_id)).fetchone()
        if not row:
            raise PermissionError("会话不存在")
        return dict(row)

    def append(self, user_id: str, thread_id: str, role: str, content: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT messages FROM threads WHERE id=? AND user_id=?", (thread_id, user_id)).fetchone()
            if not row:
                raise PermissionError("会话不存在")
            messages = json.loads(row[0])
            messages.append({"id": uuid.uuid4().hex, "role": role, "content": content})
            db.execute("UPDATE threads SET messages=?,updated=? WHERE id=? AND user_id=?", (json.dumps(messages[-200:], ensure_ascii=False), time.time(), thread_id, user_id))

    def set_pending(self, user_id, thread_id, payload):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT pending FROM threads WHERE id=? AND user_id=?", (thread_id, user_id)).fetchone()
            if not row:
                raise PermissionError("会话不存在")
            previous = json.loads(row[0]) if row[0] else None
            if payload.get("status") == "awaiting_approval" and previous and previous.get("status") in {"awaiting_approval", "executing", "outcome_unknown"}:
                raise ValueError("当前操作尚未结束；请先处理审批或核对 ERP 状态")
            db.execute("UPDATE threads SET pending=? WHERE id=? AND user_id=?", (json.dumps(payload, ensure_ascii=False), thread_id, user_id))

    def take_pending(self, user_id, thread_id, approved: bool):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT pending FROM threads WHERE id=? AND user_id=?", (thread_id, user_id)).fetchone()
            if not row:
                raise PermissionError("会话不存在")
            pending = json.loads(row[0]) if row[0] else None
            if not pending or pending.get("status") != "awaiting_approval":
                raise ValueError("没有待审批操作；重复审批不会再次写入")
            pending["status"] = "executing" if approved else "rejected"
            db.execute("UPDATE threads SET pending=? WHERE id=? AND user_id=?", (json.dumps(pending), thread_id, user_id))
        return pending
