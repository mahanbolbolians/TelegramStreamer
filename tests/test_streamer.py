import unittest
import asyncio
import os
import sys

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crypto_patch
import database
from network_utils import get_lan_ip, format_size
from server import make_safe_filename, RANGE_REGEX

class TestTelegramStreamer(unittest.TestCase):

    def test_format_size(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(500), "500.00 B")
        self.assertEqual(format_size(1024), "1.00 KB")
        self.assertEqual(format_size(1024 * 1024 * 50), "50.00 MB")
        self.assertEqual(format_size(1024 * 1024 * 1024 * 2), "2.00 GB")

    def test_safe_filename(self):
        self.assertEqual(make_safe_filename("valid_file.mp4"), "valid_file.mp4")
        self.assertEqual(make_safe_filename("invalid:/?*file.mkv"), "invalidfile.mkv")
        self.assertEqual(make_safe_filename("   "), "telegram_file.bin")

    def test_range_regex(self):
        m1 = RANGE_REGEX.match("bytes=0-1048575")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.groups(), ("0", "1048575"))

        m2 = RANGE_REGEX.match("bytes=500-")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.groups(), ("500", ""))

        m3 = RANGE_REGEX.match("bytes=-1024")
        self.assertIsNotNone(m3)
        self.assertEqual(m3.groups(), ("", "1024"))

    def test_lan_ip(self):
        ip = get_lan_ip()
        self.assertTrue(ip.startswith("192.168.") or ip.startswith("172.") or ip.startswith("10."))
        print(f"\n[+] Verified Preferred LAN IP: {ip}")

    def test_database_crud(self):
        async def run_db_test():
            await database.init_db()
            test_id = "test_media_123"
            await database.save_media(
                link_id=test_id,
                chat_id=12345678,
                message_id=999,
                file_id="tg_file_id_abc",
                file_name="Sample_Video.mp4",
                file_size=52428800,
                mime_type="video/mp4"
            )
            item = await database.get_media(test_id)
            self.assertIsNotNone(item)
            self.assertEqual(item["file_name"], "Sample_Video.mp4")
            self.assertEqual(item["file_size"], 52428800)
            self.assertEqual(item["mime_type"], "video/mp4")
            print("[+] Verified Database CRUD successfully")

        asyncio.run(run_db_test())

if __name__ == "__main__":
    unittest.main()
