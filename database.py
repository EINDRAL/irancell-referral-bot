import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

DB_PATH = Path(__file__).resolve().parent / "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sent_numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Defaults
    defaults = {
        "delay_seconds": "120",  # default 2 minutes
        "token": "",
        "is_running": "0",
        "prefixes": "930,933,935,936,937,938,939,901,902,903,905"
    }
    
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_delay() -> int:
    try:
        val = int(get_setting("delay_seconds", "120"))
        return max(75, val)  # Guard: never lower than 75 seconds
    except (ValueError, TypeError):
        return 120

def set_delay(seconds: int) -> int:
    val = max(75, int(seconds))  # Guard: clamp to 75 seconds minimum
    set_setting("delay_seconds", str(val))
    return val

def record_sent(phone: str, status: str = "success") -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO sent_numbers (phone, status) VALUES (?, ?)", (phone, status))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def is_phone_sent(phone: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM sent_numbers WHERE phone = ?", (phone,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def get_stats() -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sent_numbers")
    total_sent = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM sent_numbers WHERE date(created_at, '+3.5 hours') = date('now', '+3.5 hours')")
    today_sent = cur.fetchone()[0]
    
    cur.execute("SELECT phone, datetime(created_at, '+3.5 hours') FROM sent_numbers ORDER BY id DESC LIMIT 5")
    recent = cur.fetchall()
    
    conn.close()
    return {
        "total_sent": total_sent,
        "today_sent": today_sent,
        "recent": recent
    }

DEFAULT_PREFIXES = ["900", "901", "902", "903", "904", "905", "930", "933", "935", "936", "937", "938", "939", "941"]

def get_prefixes() -> List[str]:
    return list(DEFAULT_PREFIXES)

def get_all_sent_numbers() -> List[Tuple[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT phone, datetime(created_at, '+3.5 hours') FROM sent_numbers ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows
