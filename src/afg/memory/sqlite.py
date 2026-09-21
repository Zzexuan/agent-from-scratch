import sqlite3
import time

from afg.context.messages import Message
from afg.memory.base import BaseMemory
from afg.observability.logging import get_logger


class SQLiteMemory(BaseMemory):
    def __init__(self, db_path, session_id="default"):
        self._db_path = db_path
        self._session_id = session_id
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS memories ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id TEXT NOT NULL, "
            "role TEXT NOT NULL, "
            "content TEXT NOT NULL, "
            "created_at REAL NOT NULL)"
        )
        self._conn.commit()

    def save(self, messages):
        now = time.time()
        rows = []
        for message in messages:
            if message.role == "tool":
                continue
            if not message.content:
                continue
            rows.append((self._session_id, message.role, message.content, now))
        self._conn.executemany(
            "INSERT INTO memories (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        logger = get_logger("memory")
        logger.info("memory.save", session_id=self._session_id, count=len(rows))

    def load_context(self, query=None, k=5):
        cursor = self._conn.execute(
            "SELECT role, content FROM memories WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (self._session_id, k),
        )
        rows = cursor.fetchall()
        rows.reverse()
        messages = []
        for row in rows:
            messages.append(Message(role=row[0], content=row[1]))
        logger = get_logger("memory")
        logger.info("memory.load", session_id=self._session_id, count=len(messages))
        return messages
