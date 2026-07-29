import sqlite3
from pathlib import Path
import time

DB_PATH = Path(__file__).resolve().parent / "history.db"

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id TEXT PRIMARY KEY,
            url TEXT,
            title TEXT,
            status TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def insert_download(task_id: str, url: str, title: str = "Initializing..."):
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO downloads (id, url, title, status) VALUES (?, ?, ?, ?)",
            (task_id, url, title, "queued")
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def update_status(task_id: str, status: str):
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE downloads SET status = ? WHERE id = ?",
            (status, task_id)
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def update_title(task_id: str, title: str):
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE downloads SET title = ? WHERE id = ?",
            (title, task_id)
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def get_all_history():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    history = []
    try:
        cursor.execute("SELECT id, url, title, status, timestamp FROM downloads ORDER BY timestamp DESC")
        for row in cursor.fetchall():
            history.append({
                "id": row["id"],
                "url": row["url"],
                "title": row["title"],
                "status": row["status"],
                "timestamp": row["timestamp"]
            })
    except Exception:
        pass
    finally:
        conn.close()
    return history

# Automatically initialize database on module import
init_db()
