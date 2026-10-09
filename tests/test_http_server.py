import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crypto_patch
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web
from server import create_app
import database

class DummyBot:
    username = "GxDataCenterBot"
    first_name = "GxDataCenter"

class TestHttpServer(AioHTTPTestCase):
    async def get_application(self):
        await database.init_db()
        return create_app(client=None, bot_me=DummyBot(), port=8080)

    async def test_index_page(self):
        resp = await self.client.request("GET", "/")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("GxDataCenter", text)
        self.assertIn("ADM", text)
        print("[+] Verified Dashboard HTML response (200 OK)")

    async def test_status_json(self):
        resp = await self.client.request("GET", "/status")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["bot"], "@GxDataCenterBot")
        self.assertEqual(data["port"], 8080)
        print("[+] Verified /status JSON endpoint")

    async def test_dl_not_found(self):
        resp = await self.client.request("GET", "/dl/nonexistent_123/file.mp4")
        self.assertEqual(resp.status, 404)
        print("[+] Verified /dl 404 response for non-existent file")

    async def test_api_status(self):
        resp = await self.client.request("GET", "/api/status")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["bot"], "@GxDataCenterBot")
        self.assertIn("ffmpeg_available", data)
        print("[+] Verified /api/status endpoint")

    async def test_api_recent(self):
        resp = await self.client.request("GET", "/api/recent")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["items"], list)
        print("[+] Verified /api/recent endpoint")

    async def test_api_resolve_existing_id(self):
        # Insert dummy record into database
        await database.save_media("testlink01", 12345, 678, "file_id_abc", "sample_test.mp4", 1048576, "video/mp4")
        resp = await self.client.request("POST", "/api/resolve", json={"url": "testlink01"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["link_id"], "testlink01")
        self.assertEqual(data["file_name"], "sample_test.mp4")
        self.assertIn("/dl/testlink01/", data["dl_url"])
        self.assertIn("intent:", data["adm_intent"])
        print("[+] Verified /api/resolve for existing link_id")

    async def test_api_resolve_invalid_url(self):
        resp = await self.client.request("POST", "/api/resolve", json={"url": "https://example.com/not/a/telegram/link"})
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertFalse(data["success"])
        print("[+] Verified /api/resolve rejection for invalid link syntax")


if __name__ == "__main__":
    unittest.main()

