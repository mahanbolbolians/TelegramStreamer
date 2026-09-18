import re
import urllib.parse
import logging
from aiohttp import web
import database
from streamer import stream_file_chunks
from network_utils import format_size, get_lan_ip

logger = logging.getLogger("server")

RANGE_REGEX = re.compile(r"^bytes=(\d*)-(\d*)$")

def make_safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    return cleaned.strip() or "telegram_file.bin"

async def handle_status(request: web.Request) -> web.Response:
    bot_me = request.app.get("bot_me")
    bot_name = getattr(bot_me, "username", "UnknownBot")
    return web.json_response({
        "status": "online",
        "bot": f"@{bot_name}",
        "lan_ip": get_lan_ip(),
        "port": request.app["port"]
    })

async def handle_index(request: web.Request) -> web.Response:
    bot_me = request.app.get("bot_me")
    bot_name = getattr(bot_me, "username", "GxDataCenterBot")
    bot_display = getattr(bot_me, "first_name", "Telegram Streamer")
    lan_ip = get_lan_ip()
    port = request.app["port"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{bot_display} — ADM Streamer</title>
    <style>
        :root {{
            --bg: #0d1117;
            --card: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --heading: #f0f6fc;
            --primary: #2ea043;
            --accent: #58a6ff;
            --code-bg: #090d13;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 600px;
            width: 100%;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        }}
        .header {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(46, 160, 67, 0.15);
            color: #3fb950;
            border: 1px solid rgba(46, 160, 67, 0.4);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 12px;
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            background: #3fb950;
            border-radius: 50%;
            box-shadow: 0 0 8px #3fb950;
        }}
        h1 {{
            color: var(--heading);
            font-size: 24px;
            margin-bottom: 6px;
        }}
        p.subtitle {{
            color: #8b949e;
            font-size: 14px;
        }}
        .card {{
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 20px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 14px;
            border-bottom: 1px solid rgba(48, 54, 61, 0.5);
        }}
        .info-row:last-child {{ border-bottom: none; }}
        .label {{ color: #8b949e; }}
        .value {{ color: var(--accent); font-family: monospace; font-weight: 600; }}
        .steps {{
            margin-top: 20px;
        }}
        .steps h2 {{
            color: var(--heading);
            font-size: 16px;
            margin-bottom: 12px;
        }}
        .step-item {{
            display: flex;
            gap: 12px;
            margin-bottom: 12px;
            font-size: 14px;
            line-height: 1.5;
        }}
        .step-num {{
            background: var(--accent);
            color: #0d1117;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 12px;
            flex-shrink: 0;
            margin-top: 2px;
        }}
        a.btn {{
            display: block;
            text-align: center;
            background: var(--accent);
            color: #0d1117;
            text-decoration: none;
            padding: 12px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 15px;
            margin-top: 24px;
            transition: opacity 0.2s;
        }}
        a.btn:hover {{ opacity: 0.9; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="status-badge">
                <span class="status-dot"></span>
                Server Active & Ready
            </div>
            <h1>{bot_display}</h1>
            <p class="subtitle">High-Speed Telegram to ADM Multi-Thread Streamer</p>
        </div>

        <div class="card">
            <div class="info-row">
                <span class="label">Telegram Bot</span>
                <span class="value">@{bot_name}</span>
            </div>
            <div class="info-row">
                <span class="label">Local Wi-Fi IP</span>
                <span class="value">{lan_ip}</span>
            </div>
            <div class="info-row">
                <span class="label">Streaming Port</span>
                <span class="value">{port}</span>
            </div>
            <div class="info-row">
                <span class="label">ADM Multi-threading</span>
                <span class="value" style="color: #3fb950;">Supported (HTTP 206)</span>
            </div>
        </div>

        <div class="steps">
            <h2>🚀 How to Download with ADM:</h2>
            <div class="step-item">
                <div class="step-num">1</div>
                <div>Forward any media or file from Telegram to <strong>@{bot_name}</strong>.</div>
            </div>
            <div class="step-item">
                <div class="step-num">2</div>
                <div>The bot replies instantly with a direct streaming link.</div>
            </div>
            <div class="step-item">
                <div class="step-num">3</div>
                <div>Paste the link into <strong>ADM</strong> on your phone (supports 8–16 threads) for maximum Wi-Fi speed!</div>
            </div>
        </div>

        <a class="btn" href="https://t.me/{bot_name}" target="_blank">Open Bot in Telegram ↗</a>
    </div>
</body>
</html>
"""
    return web.Response(text=html, content_type="text/html")

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

def create_app(client, bot_me, port: int) -> web.Application:
    app = web.Application()
    app["tg_client"] = client
    app["bot_me"] = bot_me
    app["port"] = port

    app.router.add_route("*", "/", handle_index)
    app.router.add_route("*", "/status", handle_status)
    app.router.add_route("*", "/dl/{link_id}/{filename}", handle_download)
    app.router.add_route("*", "/dl/{link_id}", handle_download)

    return app
