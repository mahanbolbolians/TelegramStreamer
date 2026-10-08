import unittest
import os
import sys
import subprocess
import asyncio
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crypto_patch
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web
from server import create_app
import database
import compressor

class DummyBot:
    username = "TestCompressorBot"
    first_name = "Test Compressor"

class TestCompressionAndServer(AioHTTPTestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.sample_in = os.path.join(cls.test_dir, "sample_1080p.mp4")
        cls.sample_out = os.path.join(cls.test_dir, "sample_720p.mp4")

        # Generate a synthetic 3-second 1080p test video using ffmpeg
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=1920x1080:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
            "-c:v", "libx264", "-t", "3", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            cls.sample_in
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to generate synthetic test video: {res.stderr.decode()}")

    @classmethod
    def tearDownClass(cls):
        import shutil
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    async def get_application(self):
        await database.init_db()
        return create_app(client=None, bot_me=DummyBot(), port=8080)

    async def test_1_database_operations(self):
        await database.save_compressed(
            comp_id="test_comp_001",
            original_link_id="orig_123",
            file_path=self.sample_in,
            file_name="sample_1080p.mp4",
            file_size=os.path.getsize(self.sample_in),
            mime_type="video/mp4"
        )
        rec = await database.get_compressed("test_comp_001")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["id"], "test_comp_001")
        self.assertEqual(rec["original_link_id"], "orig_123")

        by_orig = await database.get_compressed_by_original("orig_123")
        self.assertIsNotNone(by_orig)
        self.assertEqual(by_orig["id"], "test_comp_001")

        await database.delete_compressed("test_comp_001")
        self.assertIsNone(await database.get_compressed("test_comp_001"))
        print("[+] Verified compressed_media database CRUD operations")

    async def test_2_ffmpeg_compression_execution(self):
        progress_calls = []
        async def on_progress(pct, out_time_s, speed):
            progress_calls.append((pct, speed))

        success = await compressor.run_fast_compression(
            input_path=self.sample_in,
            output_path=self.sample_out,
            duration_seconds=3.0,
            progress_callback=on_progress
        )
        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.sample_out))
        self.assertGreater(os.path.getsize(self.sample_out), 0)
        print(f"[+] Verified fast compression: output size = {os.path.getsize(self.sample_out)} bytes")

    async def test_3_compressed_download_and_range_requests(self):
        # Save compressed sample to DB
        comp_id = "test_serve_720"
        file_size = os.path.getsize(self.sample_in)
        await database.save_compressed(
            comp_id=comp_id,
            original_link_id="orig_456",
            file_path=self.sample_in,
            file_name="sample_720p.mp4",
            file_size=file_size,
            mime_type="video/mp4"
        )

        # 1. Full GET request
        resp = await self.client.request("GET", f"/dl/c/{comp_id}/sample_720p.mp4")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Accept-Ranges"), "bytes")
        self.assertEqual(resp.headers.get("Content-Length"), str(file_size))
        body = await resp.read()
        self.assertEqual(len(body), file_size)

        # 2. HTTP 206 Range request (ADM multi-threading test)
        headers = {"Range": "bytes=0-99"}
        resp_range = await self.client.request("GET", f"/dl/c/{comp_id}/sample_720p.mp4", headers=headers)
        self.assertEqual(resp_range.status, 206)
        self.assertEqual(resp_range.headers.get("Content-Range"), f"bytes 0-99/{file_size}")
        self.assertEqual(resp_range.headers.get("Content-Length"), "100")
        range_body = await resp_range.read()
        self.assertEqual(len(range_body), 100)
        self.assertEqual(range_body, body[0:100])

        # 3. 404 for non-existent compressed ID
        resp_404 = await self.client.request("GET", "/dl/c/non_existent_id/fake.mp4")
        self.assertEqual(resp_404.status, 404)
        print("[+] Verified /dl/c HTTP 200 & HTTP 206 Partial Content Range streaming")

if __name__ == "__main__":
    unittest.main()
