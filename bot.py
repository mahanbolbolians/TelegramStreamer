import time
import os
import sys
import secrets
import logging
import asyncio
import urllib.parse
from datetime import datetime

# Configure UTF-8 encoding for Windows consoles with non-UTF8 code pages (e.g. cp1256)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load C-crypto patch and Network routing patch before Hydrogram
import crypto_patch
from net_patch import apply_net_patch
apply_net_patch()

from hydrogram import Client, filters
from hydrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

from config import config
import database
from compressor import run_fast_compression, purge_old_cache, TEMP_INPUT_DIR, COMPRESSED_DIR, is_ffmpeg_available
from network_utils import get_lan_ip, format_size
from server import create_app, make_safe_filename

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s"
)
logger = logging.getLogger("bot")

def get_media_info(message: Message):
    for kind in ("document", "video", "audio", "voice", "animation", "photo"):
        media = getattr(message, kind, None)
        if media is not None:
            if kind == "photo":
                media = media[-1] if isinstance(media, list) else media
                file_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                mime_type = "image/jpeg"
                duration = 0
            else:
                file_name = getattr(media, "file_name", None) or f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"
                mime_type = getattr(media, "mime_type", "application/octet-stream")
                duration = getattr(media, "duration", 0)

            file_size = getattr(media, "file_size", 0)
            file_id = getattr(media, "file_id", "")
            return kind, file_id, file_name, file_size, mime_type, duration
    return None, None, None, None, None, 0

def is_authorized(user_id: int) -> bool:
    allowed = config.get("allowed_users") or []
    if not allowed:
        return True
    return user_id in allowed

def make_progress_bar(percentage: int) -> str:
    filled = max(0, min(10, percentage // 10))
    empty = 10 - filled
    return "█" * filled + "░" * empty

async def process_compression(client: Client, chat_id: int, message_id: int, original_link_id: str, status_msg: Message):
    record = await database.get_media(original_link_id)
    if not record:
        await status_msg.edit_text("❌ Original media record not found.")
        return

    orig_name = record["file_name"] or f"video_{original_link_id}.mp4"
    orig_size = record["file_size"]

    comp_id = secrets.token_hex(5)
    safe_orig_name = make_safe_filename(orig_name)
    base_name, _ = os.path.splitext(safe_orig_name)
    comp_filename = f"{base_name}_720p.mp4"

    temp_in = os.path.join(TEMP_INPUT_DIR, f"in_{comp_id}_{safe_orig_name}")
    temp_out = os.path.join(COMPRESSED_DIR, f"comp_{comp_id}.mp4")

    last_edit_time = 0.0

    async def dl_progress(current, total):
        nonlocal last_edit_time
        now = time.time()
        if now - last_edit_time >= 3.5:
            pct = min(99, int((current / total) * 100)) if total > 0 else 0
            bar = make_progress_bar(pct)
            try:
                await status_msg.edit_text(
                    f"📥 **Downloading from Telegram to Streamer...**\n"
                    f"`[{bar}] {pct}%` ({format_size(current)} / {format_size(total)})\n\n"
                    f"⚡ Direct MTProto transfer in progress..."
                )
                last_edit_time = now
            except Exception:
                pass

    try:
        source_msg = await client.get_messages(chat_id, message_id)
        if not source_msg:
            await status_msg.edit_text("❌ Could not access source message from Telegram.")
            return

        await status_msg.edit_text(
            "📥 **Downloading from Telegram to Streamer...**\n`[░░░░░░░░░░] 0%`\n⚡ Connecting..."
        )

        downloaded = await client.download_media(source_msg, file_name=temp_in, progress=dl_progress)
        if not downloaded or not os.path.exists(temp_in):
            await status_msg.edit_text("❌ Failed to download file from Telegram.")
            return

        # Extract duration if present
        _, _, _, _, _, duration = get_media_info(source_msg)

        last_edit_time = 0.0

        async def ffmpeg_progress(pct, out_time_s, speed_str):
            nonlocal last_edit_time
            now = time.time()
            if now - last_edit_time >= 3.5:
                bar = make_progress_bar(pct)
                try:
                    await status_msg.edit_text(
                        f"⚡ **Compressing to 720p HD...**\n"
                        f"`[{bar}] {pct}%`\n"
                        f"🚀 Encoder Speed: `{speed_str}`\n\n"
                        f"💡 *Applying H.264 veryfast preset (~65% reduction)*"
                    )
                    last_edit_time = now
                except Exception:
                    pass

        success = await run_fast_compression(
            input_path=temp_in,
            output_path=temp_out,
            duration_seconds=float(duration) if duration > 0 else None,
            progress_callback=ffmpeg_progress
        )

        # Immediately remove raw temp download to save ephemeral disk
        if os.path.exists(temp_in):
            try:
                os.remove(temp_in)
            except Exception:
                pass

        if not success or not os.path.exists(temp_out):
            await status_msg.edit_text(
                "❌ Compression failed or file format unsupported.\n"
                "You can still download the original file using the link above."
            )
            return

        comp_size = os.path.getsize(temp_out)
        savings = int((1 - (comp_size / orig_size)) * 100) if orig_size > comp_size else 0

        await database.save_compressed(
            comp_id=comp_id,
            original_link_id=original_link_id,
            file_path=temp_out,
            file_name=comp_filename,
            file_size=comp_size,
            mime_type="video/mp4"
        )

        lan_ip = get_lan_ip()
        custom_domain = config.get("custom_domain", "").strip()
        encoded_comp_name = urllib.parse.quote(comp_filename)
        port = int(config.get("port", 8080))

        if custom_domain:
            comp_url = f"{custom_domain.rstrip('/')}/dl/c/{comp_id}/{encoded_comp_name}"
        else:
            comp_url = f"http://{lan_ip}:{port}/dl/c/{comp_id}/{encoded_comp_name}"

        completion_text = (
            f"🎉 **Compression Complete!**\n\n"
            f"🎬 **{comp_filename}**\n"
            f"📦 **Original Size:** `{format_size(orig_size)}`\n"
            f"📉 **Compressed Size:** `{format_size(comp_size)}` (**{savings}% smaller!**)\n"
            f"⚡ **Quality:** 720p HD (H.264 / AAC)\n"
            f"🚀 **Multi-Thread (ADM):** Supported\n\n"
            f"🔗 **Direct ADM Download Link:**\n"
            f"`{comp_url}`\n\n"
            f"💡 *Tap the link to copy and paste into ADM!*"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open in Browser", url=comp_url)]
        ])

        await status_msg.edit_text(completion_text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Compression error: {e}", exc_info=True)
        if os.path.exists(temp_in):
            try:
                os.remove(temp_in)
            except Exception:
                pass
        await status_msg.edit_text(
            f"❌ Error during compression: {str(e)[:100]}\n"
            "You can still download the original file using the link above."
        )

async def main():
    await database.init_db()

    port = int(config.get("port", 8080))
    bind_ip = config.get("bind_address", "0.0.0.0")

    app = Client(
        "telegram_streamer_bot",
        api_id=config["api_id"],
        api_hash=config["api_hash"],
        bot_token=config["bot_token"],
        in_memory=True
    )

    @app.on_message(filters.command(["start", "help"]))
    async def start_handler(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else 0
        if not is_authorized(user_id):
            await message.reply_text(
                f"⛔ **Access Restricted**\n\nYour Telegram User ID is: `{user_id}`\n"
                "Add this ID to `allowed_users` in your `config.json` to enable access."
            )
            return

        lan_ip = get_lan_ip()
        await message.reply_text(
            f"👋 **Welcome to TelegramStreamer!**\n\n"
            f"⚡ **Direct ADM High-Speed Link Generator**\n\n"
            f"📡 **Streaming Server:** `http://{lan_ip}:{port}`\n"
            f"🟢 **Status:** Active & Ready\n\n"
            f"📥 **How to Use:**\n"
            f"1. Forward any video, audio, or document to this bot.\n"
            f"2. Copy the generated direct link.\n"
            f"3. Paste into **ADM (Advanced Download Manager)** on your phone.\n"
            f"4. Optionally tap **Compress to 720p HD** to reduce file size by ~65%!"
        )

    @app.on_message(filters.command("myid"))
    async def myid_handler(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else 0
        await message.reply_text(f"👤 Your Telegram User ID is: `{user_id}`")

    @app.on_message(filters.incoming & (filters.document | filters.video | filters.audio | filters.voice | filters.animation | filters.photo))
    async def media_handler(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else 0
        if not is_authorized(user_id):
            await message.reply_text(
                f"⛔ **Unauthorized**\nYour ID: `{user_id}` is not in `allowed_users`."
            )
            return

        kind, file_id, file_name, file_size, mime_type, _ = get_media_info(message)
        if not file_id:
            await message.reply_text("❌ Could not detect downloadable media in this message.")
            return

        # Generate unique short link ID
        link_id = secrets.token_hex(5)

        # Save to local database
        await database.save_media(
            link_id=link_id,
            chat_id=message.chat.id,
            message_id=message.id,
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type
        )

        lan_ip = get_lan_ip()
        custom_domain = config.get("custom_domain", "").strip()

        safe_name = make_safe_filename(file_name)
        encoded_name = urllib.parse.quote(safe_name)

        if custom_domain:
            dl_url = f"{custom_domain.rstrip('/')}/dl/{link_id}/{encoded_name}"
        else:
            dl_url = f"http://{lan_ip}:{port}/dl/{link_id}/{encoded_name}"

        readable_size = format_size(file_size)
        type_icon = {
            "video": "🎬",
            "audio": "🎵",
            "document": "📁",
            "photo": "🖼️",
            "voice": "🎙️",
            "animation": "🎞️"
        }.get(kind, "📦")

        caption = (
            f"{type_icon} **{file_name}**\n"
            f"📦 **Size:** `{readable_size}`\n"
            f"⚡ **Multi-Thread (ADM):** Supported\n\n"
            f"🔗 **Direct ADM Download Link:**\n"
            f"`{dl_url}`\n\n"
            f"💡 *Tap the link to copy, then paste into ADM for maximum speed!*"
        )

        keyboard_buttons = [
            [InlineKeyboardButton("🌐 Open in Browser", url=dl_url)]
        ]

        # Add compression option for videos or video documents
        if kind in ("video", "animation") or (kind == "document" and mime_type and mime_type.startswith("video/")):
            keyboard_buttons.append([
                InlineKeyboardButton("⚡ Compress to 720p HD (~65% smaller)", callback_data=f"comp_{link_id}")
            ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await message.reply_text(caption, reply_markup=keyboard)

    @app.on_callback_query(filters.regex(r"^comp_(\w+)"))
    async def compress_callback_handler(client: Client, query: CallbackQuery):
        user_id = query.from_user.id if query.from_user else 0
        if not is_authorized(user_id):
            await query.answer("⛔ Unauthorized", show_alert=True)
            return

        link_id = query.matches[0].group(1)
        record = await database.get_media(link_id)
        if not record:
            await query.answer("❌ Media record expired or not found.", show_alert=True)
            return

        # Check if already compressed in cache
        existing = await database.get_compressed_by_original(link_id)
        if existing and os.path.exists(existing.get("file_path", "")):
            comp_id = existing["id"]
            comp_filename = existing["file_name"]
            encoded_comp = urllib.parse.quote(comp_filename)
            lan_ip = get_lan_ip()
            custom_domain = config.get("custom_domain", "").strip()
            port = int(config.get("port", 8080))
            if custom_domain:
                comp_url = f"{custom_domain.rstrip('/')}/dl/c/{comp_id}/{encoded_comp}"
            else:
                comp_url = f"http://{lan_ip}:{port}/dl/c/{comp_id}/{encoded_comp}"

            await query.answer("⚡ Already compressed!")
            await query.message.reply_text(
                f"⚡ **Cached Compressed 720p Version:**\n\n"
                f"📁 **File:** `{comp_filename}`\n"
                f"📦 **Compressed Size:** `{format_size(existing['file_size'])}`\n"
                f"🚀 **Multi-Thread (ADM):** Supported\n\n"
                f"🔗 **Direct ADM Download Link:**\n`{comp_url}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Open in Browser", url=comp_url)]
                ])
            )
            return

        await query.answer("⚡ Starting 720p compression process...")
        status_msg = await query.message.reply_text(
            "⏳ **Initializing compression pipeline...**\n"
            "`[░░░░░░░░░░] 0%`\n"
            "⚡ Preparing to fetch media from Telegram..."
        )

        asyncio.create_task(
            process_compression(
                client=client,
                chat_id=record["chat_id"],
                message_id=record["message_id"],
                original_link_id=link_id,
                status_msg=status_msg
            )
        )

    print("\n" + "="*60)
    print("  🚀 Starting TelegramStreamer Engine...")
    print("="*60)

    await app.start()
    bot_me = await app.get_me()
    lan_ip = get_lan_ip()

    print(f"[+] Telegram Bot Connected: @{bot_me.username} ({bot_me.first_name})")
    print(f"[+] Local Wi-Fi IP: http://{lan_ip}:{port}")
    print(f"[+] Allowed Users: {config.get('allowed_users', [])}")
    print(f"[+] Ready to stream to ADM! Send/forward media to @{bot_me.username}\n")

    # Start aiohttp web server concurrently
    web_app = create_app(client=app, bot_me=bot_me, port=port)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, bind_ip, port)
    await site.start()

    logger.info(f"Streaming server running at http://{bind_ip}:{port}")

    # Periodic cleanup loop for expired compressed cache (older than 24h)
    async def cleanup_loop():
        while True:
            try:
                await asyncio.sleep(3600)
                purge_old_cache(max_age_hours=24)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in cache cleanup loop: {e}")

    cleanup_task = asyncio.create_task(cleanup_loop())

    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        print("\n[!] Shutting down TelegramStreamer...")
        cleanup_task.cancel()
        await runner.cleanup()
        await app.stop()
        print("[+] Goodbye!")

        print("[+] Goodbye!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
