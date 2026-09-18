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
from hydrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

from config import config
import database
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
            else:
                file_name = getattr(media, "file_name", None) or f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"
                mime_type = getattr(media, "mime_type", "application/octet-stream")

            file_size = getattr(media, "file_size", 0)
            file_id = getattr(media, "file_id", "")
            return kind, file_id, file_name, file_size, mime_type
    return None, None, None, None, None

def is_authorized(user_id: int) -> bool:
    allowed = config.get("allowed_users") or []
    if not allowed:
        return True
    return user_id in allowed

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
            f"4. Enjoy multi-threaded download at full Wi-Fi speed with 0 extra internet quota used!"
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

        kind, file_id, file_name, file_size, mime_type = get_media_info(message)
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

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open in Browser", url=dl_url)]
        ])

        await message.reply_text(caption, reply_markup=keyboard)

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

    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        print("\n[!] Shutting down TelegramStreamer...")
        await runner.cleanup()
        await app.stop()
        print("[+] Goodbye!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
