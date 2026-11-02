"""Optional PostgreSQL integration test. CI uses an isolated local service."""
import json
import os
import unittest
import uuid
from urllib.parse import urlparse

import storage


@unittest.skipUnless(os.environ.get("P1_POSTGRES_DSN"), "local PostgreSQL test service not configured")
class PostgresTests(unittest.TestCase):
    def test_sessions_consent_and_upgrade(self):
        import psycopg
        from psycopg.conninfo import make_conninfo
        dsn = os.environ["P1_POSTGRES_DSN"]
        url = urlparse(dsn)
        self.assertIn(url.hostname, ("localhost", "127.0.0.1"))
        self.assertTrue(url.path.endswith("_test"))
        schema = "p1_" + uuid.uuid4().hex
        admin = psycopg.connect(dsn, autocommit=True)
        admin.execute(f'CREATE SCHEMA "{schema}"')
        old = (storage.DATABASE_URL, storage._IS_PG)
        storage._drop_connection()
        storage.DATABASE_URL = make_conninfo(dsn, options=f"-c search_path={schema}")
        storage._IS_PG = True
        storage.psycopg = psycopg
        try:
            # Existing schema has no auth_version. Upgrade must preserve its row.
            storage._exec("CREATE TABLE accounts (id TEXT PRIMARY KEY,nickname TEXT UNIQUE NOT NULL,"
                          "pass_hash TEXT NOT NULL,exam TEXT NOT NULL,created_at TEXT NOT NULL)")
            storage._exec("INSERT INTO accounts VALUES(?,?,?,?,?)", ("legacy", "LegacyTestStudent", "old-hash", "ege", storage._now()))
            storage.ensure_schema()
            self.assertEqual(storage.get_account("LegacyTestStudent")[0], "legacy")
            user = storage.create_account("PostgresTestStudent", "old-hash", "ege", True)
            self.assertTrue(storage.corpus_consent(json.loads(storage.get_settings(user))))
            token = storage.issue_session(user, "old-hash")["session_token"]
            self.assertEqual(storage.session_account(token), user)
            storage.update_settings(user, {"corpus_consent": False})
            storage.update_settings(user, {"volume": 0.4})
            self.assertFalse(storage.corpus_consent(json.loads(storage.get_settings(user))))
            self.assertIsNone(storage.corpus_add(user, "reading", "v", b"audio", "audio/mp3", 1, "text", "text", 1, 1, {}))
            storage.reset_password("PostgresTestStudent", "new-hash")
            self.assertIsNone(storage.session_account(token))
            new_token = storage.issue_session(user, "new-hash")["session_token"]
            storage.revoke_session(new_token)
            self.assertIsNone(storage.session_account(new_token))
        finally:
            storage._drop_connection()
            storage.DATABASE_URL, storage._IS_PG = old
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            admin.close()


if __name__ == "__main__":
    unittest.main()
