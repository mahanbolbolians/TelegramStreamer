import aiosqlite
import os
from typing import Optional, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamer.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS media_links (
                id TEXT PRIMARY KEY,
                chat_id INTEGER,
                message_id INTEGER,
                file_id TEXT,
                file_name TEXT,
                file_size INTEGER,
                mime_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def save_media(link_id: str, chat_id: int, message_id: int, file_id: str,
                     file_name: str, file_size: int, mime_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO media_links 
            (id, chat_id, message_id, file_id, file_name, file_size, mime_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (link_id, chat_id, message_id, file_id, file_name, file_size, mime_type))
        await db.commit()

async def get_media(link_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM media_links WHERE id = ?", (link_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
