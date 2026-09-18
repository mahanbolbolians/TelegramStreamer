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

if __name__ == "__main__":
    unittest.main()
