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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS compressed_media (
                id TEXT PRIMARY KEY,
                original_link_id TEXT,
                file_path TEXT,
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

async def save_compressed(comp_id: str, original_link_id: str, file_path: str,
                          file_name: str, file_size: int, mime_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO compressed_media 
            (id, original_link_id, file_path, file_name, file_size, mime_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (comp_id, original_link_id, file_path, file_name, file_size, mime_type))
        await db.commit()

async def get_compressed(comp_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM compressed_media WHERE id = ?", (comp_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

async def get_compressed_by_original(original_link_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM compressed_media WHERE original_link_id = ?", (original_link_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

async def delete_compressed(comp_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM compressed_media WHERE id = ?", (comp_id,))
        await db.commit()

async def get_recent_media(limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, file_name, file_size, mime_type, created_at FROM media_links ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

