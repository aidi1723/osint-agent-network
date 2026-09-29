from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.core.browser_sessions import BrowserSessionStore


class BrowserSessionStoreTests(TestCase):
    def test_session_can_be_read_by_a_new_store_after_restart(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sessions.sqlite"
            first = BrowserSessionStore(path)
            first.put("session-1", csrf="csrf-1", expires=4_000_000_000)
            second = BrowserSessionStore(path)
            loaded = second.get("session-1")

        self.assertEqual(loaded, {"csrf": "csrf-1", "expires": 4_000_000_000})

    def test_expired_session_is_removed(self):
        with TemporaryDirectory() as tmpdir:
            store = BrowserSessionStore(Path(tmpdir) / "sessions.sqlite")
            store.put("session-1", csrf="csrf-1", expires=1)
            self.assertIsNone(store.get("session-1"))
            self.assertIsNone(store.get("session-1"))

    def test_clear_removes_only_the_named_session(self):
        with TemporaryDirectory() as tmpdir:
            store = BrowserSessionStore(Path(tmpdir) / "sessions.sqlite")
            store.put("keep", csrf="csrf-keep", expires=4_000_000_000)
            store.put("drop", csrf="csrf-drop", expires=4_000_000_000)
            store.delete("drop")
            self.assertIsNotNone(store.get("keep"))
            self.assertIsNone(store.get("drop"))
