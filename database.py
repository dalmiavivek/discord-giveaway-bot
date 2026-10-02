import sqlite3
import time
from typing import Optional, List, Dict, Any

DB_PATH = "giveaways.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER UNIQUE,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winners_count INTEGER NOT NULL DEFAULT 1,
                end_time REAL NOT NULL,
                host_id INTEGER NOT NULL,
                required_role_id INTEGER,
                min_messages INTEGER NOT NULL DEFAULT 0,
                min_vc_seconds INTEGER NOT NULL DEFAULT 0,
                ended INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                entered_at REAL NOT NULL,
                PRIMARY KEY (giveaway_id, user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways (id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                vc_seconds INTEGER NOT NULL DEFAULT 0,
                vc_joined_at REAL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT NOT NULL DEFAULT '!'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                support_role_id INTEGER,
                log_channel_id INTEGER,
                ticket_counter INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                ticket_number INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at REAL NOT NULL,
                closed_at REAL,
                closed_by INTEGER
            )
        """)
        conn.commit()

def create_giveaway(
    channel_id: int,
    guild_id: int,
    prize: str,
    winners_count: int,
    end_time: float,
    host_id: int,
    required_role_id: Optional[int] = None,
    min_messages: int = 0,
    min_vc_seconds: int = 0
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO giveaways (
                channel_id, guild_id, prize, winners_count,
                end_time, host_id, required_role_id,
                min_messages, min_vc_seconds, ended
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            channel_id, guild_id, prize, winners_count,
            end_time, host_id, required_role_id,
            min_messages, min_vc_seconds
        ))
        conn.commit()
        return cursor.lastrowid

def set_giveaway_message_id(giveaway_id: int, message_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE giveaways SET message_id = ? WHERE id = ?", (message_id, giveaway_id))
        conn.commit()

def get_giveaway(giveaway_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,)).fetchone()
        return dict(row) if row else None

def get_giveaway_by_message_id(message_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (message_id,)).fetchone()
        return dict(row) if row else None

def get_active_giveaways() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM giveaways WHERE ended = 0").fetchall()
        return [dict(r) for r in rows]

def get_expired_giveaways() -> List[Dict[str, Any]]:
    now = time.time()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM giveaways WHERE ended = 0 AND end_time <= ?", (now,)).fetchall()
        return [dict(r) for r in rows]

def mark_giveaway_ended(giveaway_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,))
        conn.commit()

def add_entry(giveaway_id: int, user_id: int) -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO giveaway_entries (giveaway_id, user_id, entered_at) VALUES (?, ?, ?)",
                (giveaway_id, user_id, time.time())
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def remove_entry(giveaway_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
            (giveaway_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def get_entries(giveaway_id: int) -> List[int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
            (giveaway_id,)
        ).fetchall()
        return [r["user_id"] for r in rows]

def get_entry_count(giveaway_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM giveaway_entries WHERE giveaway_id = ?",
            (giveaway_id,)
        ).fetchone()
        return row["count"] if row else 0

def is_user_entered(giveaway_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
            (giveaway_id, user_id)
        ).fetchone()
        return row is not None

# --- User Activity Tracking ---

def increment_message_count(guild_id: int, user_id: int):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO user_activity (guild_id, user_id, message_count, vc_seconds, vc_joined_at)
            VALUES (?, ?, 1, 0, NULL)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
            message_count = user_activity.message_count + 1
        """, (guild_id, user_id))
        conn.commit()

def start_vc_session(guild_id: int, user_id: int):
    now = time.time()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO user_activity (guild_id, user_id, message_count, vc_seconds, vc_joined_at)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
            vc_joined_at = ?
        """, (guild_id, user_id, now, now))
        conn.commit()

def end_vc_session(guild_id: int, user_id: int):
    now = time.time()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT vc_joined_at, vc_seconds FROM user_activity WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ).fetchone()
        
        if row and row["vc_joined_at"]:
            duration = max(0, int(now - row["vc_joined_at"]))
            conn.execute("""
                UPDATE user_activity
                SET vc_seconds = vc_seconds + ?, vc_joined_at = NULL
                WHERE guild_id = ? AND user_id = ?
            """, (duration, guild_id, user_id))
            conn.commit()

def get_user_activity(guild_id: int, user_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT message_count, vc_seconds, vc_joined_at FROM user_activity WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ).fetchone()
        
        if not row:
            return {"message_count": 0, "vc_seconds": 0}
        
        total_vc = row["vc_seconds"]
        # If currently in VC, calculate real-time voice seconds
        if row["vc_joined_at"]:
            total_vc += max(0, int(time.time() - row["vc_joined_at"]))
            
        return {
            "message_count": row["message_count"],
            "vc_seconds": total_vc
        }

# --- Guild Settings & Prefix ---

def get_guild_prefix(guild_id: Optional[int]) -> str:
    if not guild_id:
        return "!"
    with get_connection() as conn:
        row = conn.execute("SELECT prefix FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        return row["prefix"] if row and row["prefix"] else "!"

def set_guild_prefix(guild_id: int, prefix: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO guild_settings (guild_id, prefix)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = ?
        """, (guild_id, prefix, prefix))
        conn.commit()

# --- Ticket System ---

def get_ticket_settings(guild_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM ticket_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        if row:
            return dict(row)
        return {
            "guild_id": guild_id,
            "category_id": None,
            "support_role_id": None,
            "log_channel_id": None,
            "ticket_counter": 0
        }

def set_ticket_settings(
    guild_id: int,
    category_id: Optional[int] = None,
    support_role_id: Optional[int] = None,
    log_channel_id: Optional[int] = None
):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO ticket_settings (guild_id, category_id, support_role_id, log_channel_id, ticket_counter)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(guild_id) DO UPDATE SET
                category_id = COALESCE(?, category_id),
                support_role_id = COALESCE(?, support_role_id),
                log_channel_id = COALESCE(?, log_channel_id)
        """, (guild_id, category_id, support_role_id, log_channel_id, category_id, support_role_id, log_channel_id))
        conn.commit()

def increment_ticket_counter(guild_id: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ticket_settings (guild_id, ticket_counter)
            VALUES (?, 1)
            ON CONFLICT(guild_id) DO UPDATE SET ticket_counter = ticket_counter + 1
        """, (guild_id,))
        row = cursor.execute("SELECT ticket_counter FROM ticket_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        conn.commit()
        return row["ticket_counter"] if row else 1

def create_ticket(guild_id: int, channel_id: int, user_id: int, ticket_number: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (guild_id, channel_id, user_id, ticket_number, status, created_at)
            VALUES (?, ?, ?, ?, 'open', ?)
        """, (guild_id, channel_id, user_id, ticket_number, time.time()))
        conn.commit()
        return cursor.lastrowid

def get_ticket_by_channel(channel_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)).fetchone()
        return dict(row) if row else None

def get_user_open_ticket(guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            (guild_id, user_id)
        ).fetchone()
        return dict(row) if row else None

def close_ticket(channel_id: int, closed_by: int):
    with get_connection() as conn:
        conn.execute("""
            UPDATE tickets
            SET status = 'closed', closed_at = ?, closed_by = ?
            WHERE channel_id = ?
        """, (time.time(), closed_by, channel_id))
        conn.commit()

