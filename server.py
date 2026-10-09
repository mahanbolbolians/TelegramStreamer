import os
import re
import urllib.parse
import logging
import secrets
import asyncio
from aiohttp import web
import database
from streamer import stream_file_chunks
from network_utils import format_size, get_lan_ip, get_media_info

logger = logging.getLogger("server")

RANGE_REGEX = re.compile(r"^bytes=(\d*)-(\d*)$")
TG_LINK_PRIVATE = re.compile(r"(?:https?://)?t\.me/c/(\d+)/(\d+)")
TG_LINK_PUBLIC = re.compile(r"(?:https?://)?t\.me/([a-zA-Z0-9_]+)/(\d+)")
STREAMER_ID_REGEX = re.compile(r"(?:/dl/(?:c/)?|^)([a-zA-Z0-9_-]{5,32})(?:/.*)?$")

INDEX_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")


active_compressions = {}

def make_safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    return cleaned.strip() or "telegram_file.bin"

def get_base_url(request: web.Request) -> str:
    from config import config
    custom_domain = config.get("custom_domain", "").strip()
    if custom_domain:
        return custom_domain.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    if host and "0.0.0.0" not in host:
        return f"{proto}://{host}"
    lan_ip = get_lan_ip()
    port = request.app["port"]
    return f"http://{lan_ip}:{port}"

async def handle_status(request: web.Request) -> web.Response:
    from config import config
    from compressor import is_ffmpeg_available
    bot_me = request.app.get("bot_me")
    bot_name = getattr(bot_me, "username", "GxDataCenterBot")
    bot_display = getattr(bot_me, "first_name", "GxDataCenter")
    custom_domain = config.get("custom_domain", "").strip()
    return web.json_response({
        "status": "online",
        "bot": f"@{bot_name}",
        "bot_display": bot_display,
        "lan_ip": get_lan_ip(),
        "port": request.app["port"],
        "custom_domain": custom_domain,
        "ffmpeg_available": is_ffmpeg_available()
    })

async def handle_index(request: web.Request) -> web.Response:
    bot_me = request.app.get("bot_me")
    bot_name = getattr(bot_me, "username", "GxDataCenterBot")
    bot_display = getattr(bot_me, "first_name", "GxDataCenter")

    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            html = f.read()
        html = html.replace("GxDataCenter ADM Streamer", f"{bot_display} ADM Streamer")
        return web.Response(text=html, content_type="text/html")

    return web.Response(
        text=f"<!DOCTYPE html><html><head><title>{bot_display} — ADM Streamer</title></head><body><h1>{bot_display} ADM Streamer</h1><p>Online</p></body></html>",
        content_type="text/html"
    )

async def handle_recent(request: web.Request) -> web.Response:
    recent = await database.get_recent_media(10)
    base_url = get_base_url(request)
    items = []
    for r in recent:
        safe_name = make_safe_filename(r["file_name"] or "file.bin")
        encoded_name = urllib.parse.quote(safe_name)
        dl_url = f"{base_url}/dl/{r['id']}/{encoded_name}"
        mime_type = r.get("mime_type") or "application/octet-stream"
        adm_intent = f"intent:{dl_url}#Intent;action=android.intent.action.VIEW;type={mime_type};package=com.dv.adm;end"
        items.append({
            "link_id": r["id"],
            "file_name": r["file_name"],
            "file_size": r["file_size"],
            "readable_size": format_size(r["file_size"]),
            "mime_type": mime_type,
            "dl_url": dl_url,
            "adm_intent": adm_intent,
            "created_at": r.get("created_at")
        })
    return web.json_response({"success": True, "items": items})

async def handle_resolve(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON payload."}, status=400)

    raw_url = (data.get("url") or "").strip()
    if not raw_url:
        return web.json_response({"success": False, "error": "Please provide a valid Telegram message URL."}, status=400)

    base_url = get_base_url(request)

    # 1. Check if an existing link_id was passed
    id_match = STREAMER_ID_REGEX.search(raw_url)
    if id_match:
        existing_id = id_match.group(1)
        record = await database.get_media(existing_id)
        if record:
            safe_name = make_safe_filename(record["file_name"] or "file.bin")
            encoded_name = urllib.parse.quote(safe_name)
            dl_url = f"{base_url}/dl/{existing_id}/{encoded_name}"
            mime_type = record["mime_type"] or "application/octet-stream"
            adm_intent = f"intent:{dl_url}#Intent;action=android.intent.action.VIEW;type={mime_type};package=com.dv.adm;end"
            from compressor import is_ffmpeg_available
            is_video = (mime_type and mime_type.startswith("video/"))
            return web.json_response({
                "success": True,
                "link_id": existing_id,
                "file_name": record["file_name"],
                "file_size": record["file_size"],
                "readable_size": format_size(record["file_size"]),
                "mime_type": mime_type,
                "kind": "video" if is_video else "document",
                "dl_url": dl_url,
                "adm_intent": adm_intent,
                "is_video": is_video,
                "supports_compression": is_ffmpeg_available() and is_video
            })

    # 2. Parse Telegram Link Syntax
    chat_target = None
    msg_id = None

    priv_match = TG_LINK_PRIVATE.search(raw_url)
    if priv_match:
        # Private supergroup/channel: chat_id needs -100 prefix
        chat_target = int(f"-100{priv_match.group(1)}")
        msg_id = int(priv_match.group(2))
    else:
        pub_match = TG_LINK_PUBLIC.search(raw_url)
        if pub_match:
            chat_target = pub_match.group(1)
            msg_id = int(pub_match.group(2))

    if not chat_target or not msg_id:
        return web.json_response({
            "success": False,
            "error": "Unrecognized link format. Expected https://t.me/channel/123 or https://t.me/c/12345/67"
        }, status=400)

    client = request.app.get("tg_client")
    if not client:
        return web.json_response({
            "success": False,
            "error": "Telegram client session is not active on this server instance."
        }, status=503)

    try:
        source_msg = await client.get_messages(chat_target, msg_id)
    except Exception as e:
        err = str(e)
        if "CHANNEL_PRIVATE" in err or "ChatAdminRequired" in err:
            err_msg = "Cannot access private channel. Ensure the bot is added to this channel as an administrator."
        elif "USER_BANNED_IN_CHANNEL" in err:
            err_msg = "Bot is banned or restricted in this channel."
        else:
            err_msg = f"Telegram error: {err}"
        return web.json_response({"success": False, "error": err_msg}, status=400)

    if not source_msg:
        return web.json_response({
            "success": False,
            "error": "Message not found or deleted on Telegram."
        }, status=404)

    kind, file_id, file_name, file_size, mime_type, duration = get_media_info(source_msg)
    if not file_id:
        return web.json_response({
            "success": False,
            "error": "No downloadable media detected in this message. Make sure the message contains a video, audio, or document."
        }, status=400)

    link_id = secrets.token_hex(5)
    numeric_chat_id = source_msg.chat.id if hasattr(source_msg, "chat") and hasattr(source_msg.chat, "id") else 0

    await database.save_media(
        link_id=link_id,
        chat_id=numeric_chat_id,
        message_id=msg_id,
        file_id=file_id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type
    )

    safe_name = make_safe_filename(file_name)
    encoded_name = urllib.parse.quote(safe_name)
    dl_url = f"{base_url}/dl/{link_id}/{encoded_name}"
    adm_intent = f"intent:{dl_url}#Intent;action=android.intent.action.VIEW;type={mime_type};package=com.dv.adm;end"

    from compressor import is_ffmpeg_available
    is_video = kind in ("video", "animation") or (mime_type and mime_type.startswith("video/"))
    supports_compression = is_ffmpeg_available() and is_video

    return web.json_response({
        "success": True,
        "link_id": link_id,
        "file_name": file_name,
        "file_size": file_size,
        "readable_size": format_size(file_size),
        "mime_type": mime_type,
        "kind": kind,
        "duration": duration,
        "dl_url": dl_url,
        "adm_intent": adm_intent,
        "is_video": is_video,
        "supports_compression": supports_compression
    })

async def _run_compression_task(client, record, comp_id, base_url):
    from compressor import TEMP_INPUT_DIR, COMPRESSED_DIR, run_fast_compression
    orig_name = record["file_name"] or f"video_{record['id']}.mp4"
    safe_orig = make_safe_filename(orig_name)
    base_name, _ = os.path.splitext(safe_orig)
    comp_filename = f"{base_name}_720p.mp4"
    temp_in = os.path.join(TEMP_INPUT_DIR, f"in_{comp_id}_{safe_orig}")
    temp_out = os.path.join(COMPRESSED_DIR, f"comp_{comp_id}.mp4")

    try:
        source_msg = await client.get_messages(record["chat_id"], record["message_id"])

        async def dl_progress(current, total):
            pct = min(40, int((current / total) * 40)) if total > 0 else 0
            active_compressions[comp_id] = {
                "status": "downloading",
                "pct": pct,
                "speed": "MTProto transfer"
            }

        await client.download_media(source_msg, file_name=temp_in, progress=dl_progress)

        async def ffmpeg_progress(pct, out_time_s, speed_str):
            total_pct = 40 + int(pct * 0.6)
            active_compressions[comp_id] = {
                "status": "compressing",
                "pct": total_pct,
                "speed": speed_str or "encoding"
            }

        duration = record.get("duration") or 0
        success = await run_fast_compression(temp_in, temp_out, duration, ffmpeg_progress)
        if not success or not os.path.exists(temp_out):
            raise RuntimeError("FFmpeg compression process exited without producing output")

        comp_size = os.path.getsize(temp_out)
        await database.save_compressed(
            comp_id=comp_id,
            original_link_id=record["id"],
            file_path=temp_out,
            file_name=comp_filename,
            file_size=comp_size,
            mime_type="video/mp4"
        )

        encoded_name = urllib.parse.quote(comp_filename)
        comp_url = f"{base_url}/dl/c/{comp_id}/{encoded_name}"
        comp_intent = f"intent:{comp_url}#Intent;action=android.intent.action.VIEW;type=video/mp4;package=com.dv.adm;end"

        active_compressions[comp_id] = {
            "status": "completed",
            "pct": 100,
            "comp_id": comp_id,
            "comp_url": comp_url,
            "comp_intent": comp_intent,
            "readable_size": format_size(comp_size),
            "file_size": comp_size
        }
    except Exception as e:
        logger.error(f"Compression failed for {comp_id}: {e}", exc_info=True)
        active_compressions[comp_id] = {
            "status": "error",
            "error": str(e)[:120]
        }
    finally:
        if os.path.exists(temp_in):
            try:
                os.remove(temp_in)
            except Exception:
                pass

async def handle_compress(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)

    link_id = data.get("link_id")
    if not link_id:
        return web.json_response({"success": False, "error": "Missing link_id"}, status=400)

    record = await database.get_media(link_id)
    if not record:
        return web.json_response({"success": False, "error": "Media record expired or not found."}, status=404)

    base_url = get_base_url(request)
    existing = await database.get_compressed_by_original(link_id)
    if existing and os.path.exists(existing.get("file_path", "")):
        comp_id = existing["id"]
        safe_name = make_safe_filename(existing["file_name"])
        encoded_comp = urllib.parse.quote(safe_name)
        comp_url = f"{base_url}/dl/c/{comp_id}/{encoded_comp}"
        comp_intent = f"intent:{comp_url}#Intent;action=android.intent.action.VIEW;type=video/mp4;package=com.dv.adm;end"
        return web.json_response({
            "success": True,
            "status": "ready",
            "comp_id": comp_id,
            "comp_url": comp_url,
            "comp_intent": comp_intent,
            "readable_size": format_size(existing["file_size"])
        })

    client = request.app.get("tg_client")
    if not client:
        return web.json_response({"success": False, "error": "Telegram client not available."}, status=503)

    comp_id = secrets.token_hex(5)
    active_compressions[comp_id] = {
        "status": "starting",
        "pct": 0,
        "speed": "initializing"
    }

    asyncio.create_task(_run_compression_task(client, record, comp_id, base_url))

    return web.json_response({
        "success": True,
        "status": "processing",
        "comp_id": comp_id
    })

async def handle_compress_status(request: web.Request) -> web.Response:
    comp_id = request.match_info.get("comp_id")
    if not comp_id or comp_id not in active_compressions:
        comp = await database.get_compressed(comp_id)
        if comp:
            base_url = get_base_url(request)
            encoded_name = urllib.parse.quote(comp["file_name"])
            comp_url = f"{base_url}/dl/c/{comp_id}/{encoded_name}"
            comp_intent = f"intent:{comp_url}#Intent;action=android.intent.action.VIEW;type=video/mp4;package=com.dv.adm;end"
            return web.json_response({
                "status": "completed",
                "pct": 100,
                "comp_url": comp_url,
                "comp_intent": comp_intent,
                "readable_size": format_size(comp["file_size"])
            })
        return web.json_response({"status": "error", "error": "Task not found"}, status=404)

    return web.json_response(active_compressions[comp_id])

async def handle_download(request: web.Request) -> web.StreamResponse:
    link_id = request.match_info.get("link_id")
    if not link_id:
        return web.Response(status=404, text="Invalid link ID")

    record = await database.get_media(link_id)
    if not record:
        return web.Response(status=404, text="File link expired or not found")

    client = request.app["tg_client"]
    chat_id = record["chat_id"]
    message_id = record["message_id"]
    file_id = record["file_id"]
    file_size = record["file_size"]
    file_name = record["file_name"] or f"file_{link_id}.bin"
    mime_type = record["mime_type"] or "application/octet-stream"

    safe_name = make_safe_filename(file_name)
    encoded_name = urllib.parse.quote(safe_name)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime_type,
        "Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{encoded_name}',
        "Cache-Control": "public, max-age=86400",
    }

    range_header = request.headers.get("Range")
    if range_header:
        match = RANGE_REGEX.match(range_header.strip())
        if not match:
            return web.Response(
                status=416,
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        start_str, end_str = match.groups()

        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        elif end_str:
            suffix_len = int(end_str)
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            start = 0
            end = file_size - 1

        if start > end or start >= file_size:
            return web.Response(
                status=416,
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        end = min(end, file_size - 1)
        content_length = end - start + 1

        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(content_length)
        status_code = 206
    else:
        start = 0
        end = file_size - 1
        headers["Content-Length"] = str(file_size)
        status_code = 200

    # If client (like ADM) sends HEAD request to probe file size & range support:
    if request.method == "HEAD":
        return web.Response(status=status_code, headers=headers)

    response = web.StreamResponse(status=status_code, headers=headers)
    await response.prepare(request)

    logger.info(f"Streaming {file_name} bytes {start}-{end} to {request.remote}")

    try:
        async for chunk in stream_file_chunks(
            client=client,
            chat_id=chat_id,
            message_id=message_id,
            file_id=file_id,
            file_size=file_size,
            start_byte=start,
            end_byte=end
        ):
            await response.write(chunk)

        await response.write_eof()
    except (ConnectionResetError, ConnectionAbortedError, web.GracefulExit):
        # Client (ADM) disconnected or closed range connection (normal behavior)
        pass
    except Exception as e:
        logger.error(f"Error streaming {file_name}: {e}")

    return response

async def handle_compressed_download(request: web.Request) -> web.StreamResponse:
    comp_id = request.match_info.get("comp_id")
    if not comp_id:
        return web.Response(status=404, text="Invalid compressed link ID")

    record = await database.get_compressed(comp_id)
    if not record:
        return web.Response(status=404, text="Compressed file link expired or not found")

    file_path = record.get("file_path", "")
    if not os.path.exists(file_path):
        return web.Response(status=404, text="Compressed file has expired from cache.")

    file_size = os.path.getsize(file_path)
    file_name = record.get("file_name") or f"compressed_{comp_id}.mp4"
    mime_type = record.get("mime_type") or "video/mp4"

    safe_name = make_safe_filename(file_name)
    encoded_name = urllib.parse.quote(safe_name)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime_type,
        "Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{encoded_name}',
        "Cache-Control": "public, max-age=86400",
    }

    range_header = request.headers.get("Range")
    if range_header:
        match = RANGE_REGEX.match(range_header.strip())
        if not match:
            return web.Response(
                status=416,
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        start_str, end_str = match.groups()

        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        elif end_str:
            suffix_len = int(end_str)
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            start = 0
            end = file_size - 1

        if start > end or start >= file_size:
            return web.Response(
                status=416,
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        end = min(end, file_size - 1)
        content_length = end - start + 1

        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(content_length)
        status_code = 206
    else:
        start = 0
        end = file_size - 1
        content_length = file_size
        headers["Content-Length"] = str(file_size)
        status_code = 200

    if request.method == "HEAD":
        return web.Response(status=status_code, headers=headers)

    response = web.StreamResponse(status=status_code, headers=headers)
    await response.prepare(request)

    logger.info(f"Streaming compressed {file_name} bytes {start}-{end} to {request.remote}")

    try:
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = content_length
            chunk_size = 64 * 1024
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                await response.write(data)
                remaining -= len(data)

        await response.write_eof()
    except (ConnectionResetError, ConnectionAbortedError, web.GracefulExit):
        pass
    except Exception as e:
        logger.error(f"Error streaming compressed {file_name}: {e}")

    return response

def create_app(client, bot_me, port: int) -> web.Application:
    app = web.Application()
    app["tg_client"] = client
    app["bot_me"] = bot_me
    app["port"] = port

    app.router.add_route("*", "/", handle_index)
    app.router.add_route("*", "/status", handle_status)
    app.router.add_route("GET", "/api/status", handle_status)
    app.router.add_route("GET", "/api/recent", handle_recent)
    app.router.add_route("POST", "/api/resolve", handle_resolve)
    app.router.add_route("POST", "/api/compress", handle_compress)
    app.router.add_route("GET", "/api/compress/status/{comp_id}", handle_compress_status)
    app.router.add_route("*", "/dl/c/{comp_id}/{filename}", handle_compressed_download)
    app.router.add_route("*", "/dl/c/{comp_id}", handle_compressed_download)
    app.router.add_route("*", "/dl/{link_id}/{filename}", handle_download)
    app.router.add_route("*", "/dl/{link_id}", handle_download)

    return app


