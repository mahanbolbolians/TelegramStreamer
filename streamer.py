import math
import logging
from typing import AsyncGenerator
from hydrogram.errors import FileReferenceExpired

logger = logging.getLogger("streamer")

CHUNK_SIZE = 1024 * 1024  # 1 MiB per Telegram MTProto chunk

async def stream_file_chunks(
    client,
    chat_id: int,
    message_id: int,
    file_id: str,
    file_size: int,
    start_byte: int,
    end_byte: int
) -> AsyncGenerator[bytes, None]:
    """
    Streams byte-precise slices of a Telegram file chunk by chunk.
    Directly compatible with HTTP Range requests and ADM multi-threading.
    Zero disk space used.
    """
    if file_size <= 0:
        return

    # Boundary clamping
    start_byte = max(0, start_byte)
    end_byte = min(file_size - 1, end_byte)
    if start_byte > end_byte:
        return

    first_chunk = start_byte // CHUNK_SIZE
    last_chunk = end_byte // CHUNK_SIZE
    num_chunks = (last_chunk - first_chunk) + 1

    skip_start = start_byte % CHUNK_SIZE
    bytes_remaining = end_byte - start_byte + 1

    logger.debug(
        f"Streaming bytes {start_byte}-{end_byte} ({bytes_remaining} bytes) "
        f"from chunks {first_chunk} to {last_chunk} ({num_chunks} chunks)"
    )

    async def get_stream_source():
        try:
            msg = await client.get_messages(chat_id, message_id)
            if msg:
                return msg
        except Exception as e:
            logger.warning(f"Could not fetch message {message_id} from chat {chat_id}: {e}")
        return file_id

    source = await get_stream_source()
    chunk_index = 0

    try:
        async for chunk in client.stream_media(source, offset=first_chunk, limit=num_chunks):
            if not chunk:
                continue

            # First chunk might have an offset within the 1MB block
            if chunk_index == 0 and skip_start > 0:
                chunk = chunk[skip_start:]

            # Clamp chunk length if we need fewer bytes than chunk contains
            if len(chunk) > bytes_remaining:
                chunk = chunk[:bytes_remaining]

            if chunk:
                yield chunk
                bytes_remaining -= len(chunk)

            chunk_index += 1
            if bytes_remaining <= 0:
                break

    except FileReferenceExpired:
        logger.info("File reference expired during stream, re-fetching message...")
        source = await client.get_messages(chat_id, message_id)
        # Continue streaming remaining bytes
        if bytes_remaining > 0:
            new_start = end_byte - bytes_remaining + 1
            new_first_chunk = new_start // CHUNK_SIZE
            new_last_chunk = end_byte // CHUNK_SIZE
            new_num_chunks = (new_last_chunk - new_first_chunk) + 1
            new_skip = new_start % CHUNK_SIZE

            c_idx = 0
            async for chunk in client.stream_media(source, offset=new_first_chunk, limit=new_num_chunks):
                if not chunk:
                    continue
                if c_idx == 0 and new_skip > 0:
                    chunk = chunk[new_skip:]
                if len(chunk) > bytes_remaining:
                    chunk = chunk[:bytes_remaining]
                if chunk:
                    yield chunk
                    bytes_remaining -= len(chunk)
                c_idx += 1
                if bytes_remaining <= 0:
                    break
