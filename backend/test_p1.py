"""P1 regressions through the real HTTP app and an isolated database.

Run: python -m unittest -v test_p1.py (no network / provider credentials).
"""
import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

os.environ["STT_PROVIDER"] = "mistral"
os.environ["STT_FALLBACK_LOCAL"] = "0"
os.environ["INVITE_REQUIRED"] = "0"

from fastapi.testclient import TestClient
import main
import scoring
import ege_scoring
import storage


class P1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        storage._drop_connection()
        self.previous_db = storage._SQLITE_PATH
        self.previous_pg = storage._IS_PG
        storage._IS_PG = False
        storage._SQLITE_PATH = str(Path(self.temp.name) / "test.db")
        storage.ensure_schema()
        main._storage_ok = True
        self.patches = [patch.object(main, "_track_usage"),
                        patch.object(main, "_rate_ok", return_value=True),
                        patch.object(main, "_remember"),
                        patch.object(main, "_collect_corpus_bg"),
                        patch.object(main, "_collect_pron_bg")]
        for p in self.patches:
            p.start()
        # No lifespan: startup must not call Mistral or the real MAX bot.
        self.client = TestClient(main.app)
        self.user = self.signup()
        self.headers = {"Authorization": "Bearer " + self.user["session_token"]}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):
            p.stop()
        storage._drop_connection()
        storage._SQLITE_PATH = self.previous_db
        storage._IS_PG = self.previous_pg
        self.temp.cleanup()

    def signup(self, name="CarefulTestStudent", **extra):
        res = self.client.post("/auth/register", json={
            "nickname": name, "password": "test-only-password", "exam": "ege", **extra})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.headers["cache-control"], "no-store")
        return res.json()

    def test_health_detects_database_loss_after_startup(self):
        with patch.dict(os.environ, {"LLM_API_KEY": "test-config-only"}), \
             patch.dict(main._READY_CACHE, {"at": 0, "database": True}), \
             patch.object(storage, "_exec", side_effect=RuntimeError("database unavailable")):
            res = self.client.get("/health")
        self.assertEqual(res.status_code, 503)
        self.assertFalse(res.json()["ok"])
        self.assertFalse(res.json()["readiness"]["database"])

    def test_conversation_stream_failure_is_not_http_success(self):
        with patch.object(main, "transcribe_auto", side_effect=main.SttFailed("test failure")), \
             patch.object(main, "_load_memory", new=AsyncMock(return_value={})), \
             patch.object(main, "_track_usage") as track:
            res = self.client.post("/talk_stream", headers=self.headers,
                                   files={"audio": ("test.mp3", b"synthetic audio", "audio/mpeg")})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.text)["user"], "")
        self.assertIn({"conversation_failed": 1}, [c.kwargs for c in track.call_args_list])
        self.assertNotIn({"http_ok": 1}, [c.kwargs for c in track.call_args_list])

    def test_conversation_overlaps_voice_and_generation_without_reordering(self):
        from types import SimpleNamespace

        head = "The park sounds peaceful on a rainy day."
        tail = "What do you usually do there?"
        first_started = asyncio.Event()
        tail_started = asyncio.Event()

        def chunk(text):
            return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])

        class ModelStream:
            closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                self.closed = True

            async def __aiter__(self):
                yield chunk(head)
                await asyncio.wait_for(first_started.wait(), timeout=2)
                yield chunk(" " + tail)

        async def voice(sentence, _persona):
            if sentence == head:
                first_started.set()
                await asyncio.wait_for(tail_started.wait(), timeout=2)
            else:
                self.assertEqual(sentence, tail)
                tail_started.set()
            return b"synthetic speech"

        stream = ModelStream()
        create = AsyncMock(return_value=stream)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(main, "transcribe_auto", new=AsyncMock(return_value="I like the park")), \
             patch.object(main, "async_llm_client", return_value=client), \
             patch.object(main, "synthesize", side_effect=voice), \
             patch.object(main, "_note_reply_bg"):
            res = self.client.post("/talk_stream", headers=self.headers,
                                   files={"audio": ("test.mp3", b"synthetic audio", "audio/mpeg")})

        events = [json.loads(line) for line in res.text.splitlines()]
        self.assertEqual(events[1], {"preview": head})
        self.assertEqual([e["text"] for e in events if e.get("audio_b64")], [head, tail])
        self.assertEqual(events[-1]["reply"], head + " " + tail)
        self.assertTrue(events[-1]["done"])
        self.assertTrue(stream.closed)
        create.assert_awaited_once()

    def test_exam_deadline_finishes_the_stream_without_a_grade(self):
        async def timeout_response():
            async def slow_judge():
                await asyncio.Event().wait()

            return [json.loads(chunk) async for chunk in
                    main._json_with_heartbeat(slow_judge(), timeout=0.01) if chunk.strip()]

        with patch.object(main, "_track_usage") as track:
            rows = asyncio.run(timeout_response())
        self.assertEqual(len(rows), 1)
        self.assertIn("Балл не выставлен", rows[0]["detail"])
        track.assert_called_once_with(analysis_failed=1)

    def test_registration_defaults_to_no_consent(self):
        settings = json.loads(storage.get_settings(self.user["id"]))
        self.assertIs(settings["corpus_consent"], False)
        self.assertFalse(storage.corpus_consent(settings))

    def test_registration_persists_explicit_consent(self):
        user = self.signup("ExplicitConsentStudent", corpus_consent=True)
        self.assertTrue(storage.corpus_consent(json.loads(storage.get_settings(user["id"]))))

    def test_registration_rejects_truthy_strings(self):
        res = self.client.post("/auth/register", json={
            "nickname": "WrongConsentStudent", "password": "test-only-password",
            "corpus_consent": "false"})
        self.assertEqual(res.status_code, 422)
        self.assertIsNone(storage.get_account("WrongConsentStudent"))

    def test_registration_rolls_back_if_consent_write_fails(self):
        storage._exec("CREATE TRIGGER fail_settings BEFORE INSERT ON settings "
                      "BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END")
        res = self.client.post("/auth/register", json={
            "nickname": "AtomicConsentStudent", "password": "test-only-password"})
        self.assertEqual(res.status_code, 503)
        self.assertIsNone(storage.get_account("AtomicConsentStudent"))

    def test_account_id_is_not_a_credential(self):
        for headers in ({"X-Device": self.user["id"]},
                        {"Authorization": "Bearer " + self.user["id"]}):
            self.assertEqual(self.client.get("/me/settings", headers=headers).status_code, 401)

    def test_session_tokens_are_hashed_in_database(self):
        digest = storage._exec("SELECT token_hash FROM auth_sessions").fetchone()[0]
        self.assertEqual(len(digest), 64)
        self.assertNotEqual(digest, self.user["session_token"])
        self.assertNotEqual(self.user["session_token"], self.user["id"])

    def test_client_cannot_select_another_account(self):
        other = self.signup("AnotherTestStudent", corpus_consent=True)
        res = self.client.get("/me/settings", headers={**self.headers, "X-Device": other["id"]})
        self.assertIs(res.json()["settings"]["corpus_consent"], False)

    def test_logout_revokes_only_its_session(self):
        second = self.client.post("/auth/login", json={
            "nickname": self.user["nickname"], "password": "test-only-password"}).json()
        res = self.client.post("/auth/logout", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/me/settings", headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get("/me/settings", headers={
            "Authorization": "Bearer " + second["session_token"]}).status_code, 200)

    def test_password_reset_revokes_every_session(self):
        second = storage.issue_session(self.user["id"])
        storage.reset_password(self.user["nickname"], main._hash_pw("a-new-test-password"))
        for token in [self.user["session_token"], second["session_token"]]:
            self.assertIsNone(storage.session_account(token))
        fresh = self.client.post("/auth/login", json={
            "nickname": self.user["nickname"], "password": "a-new-test-password"})
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(fresh.json()["id"], self.user["id"])

    def test_password_reset_cannot_race_session_issuance(self):
        old_hash = storage.get_account(self.user["nickname"])[2]
        storage.reset_password(self.user["nickname"], "new-hash")
        with self.assertRaises(ValueError):
            storage.issue_session(self.user["id"], old_hash)

    def test_expired_session_is_rejected(self):
        expired = storage.issue_session(self.user["id"], lifetime=-1)
        self.assertEqual(self.client.get("/me/settings", headers={
            "Authorization": "Bearer " + expired["session_token"]}).status_code, 401)

    def test_database_outage_fails_closed(self):
        with patch.object(main, "_storage_ok", False):
            self.assertEqual(self.client.get("/me/settings", headers=self.headers).status_code, 503)
            self.assertEqual(self.client.get("/me/settings", headers={"X-Device": "unknown"}).status_code, 401)
            self.assertEqual(self.client.post("/auth/logout", headers=self.headers).status_code, 503)
        with patch.object(storage, "session_account", side_effect=OSError("database down")):
            self.assertEqual(self.client.get("/me/settings", headers=self.headers).status_code, 503)

    def test_every_private_route_rejects_the_legacy_id(self):
        for path in ["/me/settings", "/me/stats", "/me/analytics", "/me/favorites",
                     "/progress", "/pron/weakest"]:
            self.assertEqual(self.client.get(path, headers={"X-Device": self.user["id"]}).status_code, 401, path)
        for path in ["/speak", "/talk_review", "/task_dispute", "/me/nickname"]:
            self.assertEqual(self.client.post(path, json={}, headers={"X-Device": self.user["id"]}).status_code, 401, path)
        for path in ["/talk", "/talk_stream", "/monologue", "/task_feedback"]:
            res = self.client.post(path, files={"audio": ("test.mp3", b"audio", "audio/mpeg")},
                                   data={"kind": "reading"}, headers={"X-Device": self.user["id"]})
            self.assertEqual(res.status_code, 401, path)

    def test_legacy_consent_is_not_reused(self):
        storage.save_settings(self.user["id"], json.dumps({"corpus_consent": True}))
        self.assertIs(self.client.get("/me/settings", headers=self.headers).json()["settings"]["corpus_consent"], False)
        self.assertIsNone(storage.corpus_add(self.user["id"], "reading", "v", b"audio", "audio/mp3", 1, "text", "text", 1, 1, {}))

    def test_consent_withdrawal_survives_delayed_preferences(self):
        for patch_body in [{"corpus_consent": True}, {"corpus_consent": False}, {"volume": 0.5}]:
            res = self.client.post("/me/settings", json=patch_body, headers=self.headers)
            self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["settings"]["volume"], 0.5)
        self.assertIs(res.json()["settings"]["corpus_consent"], False)
        self.assertIsNone(storage.corpus_add(self.user["id"], "reading", "v", b"audio", "audio/mp3", 1, "text", "text", 1, 1, {}))

    def test_corpus_insert_checks_consent_again(self):
        storage.update_settings(self.user["id"], {"corpus_consent": True})
        self.assertTrue(storage.corpus_consent(json.loads(storage.get_settings(self.user["id"]))))
        storage.update_settings(self.user["id"], {"corpus_consent": False})
        self.assertIsNone(storage.corpus_add(self.user["id"], "reading", "v", b"audio", "audio/mp3", 1, "text", "text", 1, 1, {}))

    def test_reading_does_not_call_llm_or_use_history(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads((root / "docs/test-data/task_feedback_payloads.json").read_text())["reading"]["payload"]
        reference = payload["referenceText"]
        transcripts = [reference.replace("forms", "form").replace("today’s", "today"), reference.replace("forms", "form"), reference]
        with patch.object(main, "transcribe_for_task", new=AsyncMock(side_effect=transcripts)), \
             patch.object(main.audio_check, "inspect", return_value={}), \
             patch.object(main.audio_check, "silence_reason", return_value=None), \
             patch.object(main.audio_check, "recognition_failed", return_value=False), \
             patch.object(main, "llm_client", side_effect=AssertionError("LLM must not grade reading")), \
             patch.object(main, "_load_memory", side_effect=AssertionError("history must not affect grading")):
            results = [asyncio.run(main._task_feedback_work("reading", json.dumps(payload), b"audio",
                       self.user["id"], "audit", 60, filename="test.mp3")) for _ in transcripts]
        self.assertEqual([r["feedback"]["score"] for r in results], [1, 1, 1])
        self.assertTrue(all(r["feedback"]["misread_words"] == 0 for r in results))

    def test_reading_cannot_be_changed_by_model_claims(self):
        ref = "The children visit teachers and watch movies in the evening."
        ctx = {"diff": ege_scoring.reading_diff(ref, ref), "reference": ref}
        a = scoring._score_feedback("reading", {}, ctx)
        b = scoring._score_feedback("reading", {"summary": "Everything is wrong", "misread": [
            {"expected": "children visit teachers", "heard": "wrong words", "real": True}]}, ctx)
        self.assertEqual(a, b)

    def test_grading_stt_outage_does_not_change_model(self):
        with patch.object(main, "STT_TASK_MODE", "chat"), \
             patch.object(main, "STT_TASK_MODEL", "precise-test-model"), \
             patch.object(main, "transcribe_chat", new=AsyncMock(side_effect=OSError("upstream down"))), \
             patch.object(main, "transcribe_auto", new=AsyncMock()) as fallback:
            with self.assertRaises(main.SttFailed) as error:
                asyncio.run(main.transcribe_for_task(b"audio", "test.mp3"))
            self.assertIn("Балл не выставлен", error.exception.user_message)
            fallback.assert_not_called()

    def test_grading_uses_fixed_available_transcription_route(self):
        with patch.object(main, "STT_TASK_MODE", "transcription"), \
             patch.object(main, "STT_TASK_MODEL", "legacy-unavailable-model"), \
             patch.object(main, "transcribe_remote", new=AsyncMock(return_value="spoken text")) as remote, \
             patch.object(main, "transcribe_chat", new=AsyncMock()) as chat, \
             patch.object(main, "transcribe_auto", new=AsyncMock()) as fallback:
            self.assertEqual(asyncio.run(main.transcribe_for_task(b"audio")), "spoken text")
            remote.assert_awaited_once_with(b"audio", temperature=0.0, timeout=40.0)
            chat.assert_not_called()
            remote.side_effect = OSError("transcription unavailable")
            with self.assertRaises(main.SttFailed):
                asyncio.run(main.transcribe_for_task(b"audio"))
            fallback.assert_not_called()
            chat.assert_not_called()

    def test_monologue_passes_run_concurrently_with_fixed_seeds(self):
        import threading
        from types import SimpleNamespace
        barrier = threading.Barrier(2, timeout=2)
        seeds = []
        def create(**kw):
            seeds.append(kw["extra_body"]["random_seed"])
            barrier.wait()
            content = json.dumps({"aspects": [{"n": n} for n in range(1, 5)]})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(main, "MONO_CONSENSUS", True), patch.object(main, "_track_llm"):
            observations, _ = asyncio.run(main._grading_observations(client, "prompt", "speech", "monologue"))
        self.assertEqual(sorted(seeds), [20261102, 20261103])
        self.assertEqual(len(observations["aspects"]), 4)

    def test_incomplete_monologue_consensus_does_not_return_partial_grade(self):
        from types import SimpleNamespace
        def create(**kw):
            if kw["extra_body"]["random_seed"] == 20261103:
                raise OSError("second pass unavailable")
            content = json.dumps({"aspects": [{"n": n} for n in range(1, 5)]})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(main, "MONO_CONSENSUS", True), patch.object(main, "_track_llm"):
            with self.assertRaises(OSError):
                asyncio.run(main._grading_observations(client, "prompt", "speech", "monologue"))

    def test_invalid_monologue_structure_is_not_scored(self):
        from types import SimpleNamespace
        for aspects in ([], [{"n": n} for n in (1, 2, 3)], [{"n": n} for n in (1, 1, 3, 4)]):
            with self.subTest(aspects=aspects):
                response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                    content=json.dumps({"aspects": aspects})))])
                client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
                with patch.object(main, "MONO_CONSENSUS", False), patch.object(main, "_track_llm"):
                    with self.assertRaises(main.HTTPException):
                        asyncio.run(main._grading_observations(client, "prompt", "speech", "monologue"))

    def test_grading_generation_is_seeded_and_does_not_switch_models(self):
        from unittest.mock import Mock
        inner = Mock()
        inner.create.side_effect = OSError("upstream down")
        with patch.object(main, "_llm_use_fallback", return_value=True):
            with self.assertRaises(OSError):
                main._Completions(inner).create(model="chosen-model", temperature=0,
                                               response_format={"type": "json_object"})
        self.assertEqual(inner.create.call_count, 1)
        self.assertEqual(inner.create.call_args.kwargs["model"], "chosen-model")
        self.assertEqual(inner.create.call_args.kwargs["extra_body"]["random_seed"], 20261102)

    def test_real_omissions_still_fail_reading(self):
        ref = "The children visit teachers every morning and watch movies in the evening."
        diff = ege_scoring.reading_diff(ref, "The children visit teachers every morning")
        self.assertEqual(scoring.reading_feedback(diff)["score"], 0)

    def test_unchanged_correction_is_not_an_error(self):
        errors = [{"quote": "a woman is sitting", "correction": "a woman is sitting", "cat": "gram"}]
        self.assertEqual(scoring._errors_from(errors), [])
        self.assertEqual(ege_scoring.drop_unsupported(errors, "a woman is sitting"), [])

    def test_max_login_returns_separate_revocable_sessions(self):
        with patch.dict(os.environ, {"MAX_BOT_TOKEN": "synthetic-test-token"}), \
             patch.object(main.max_auth, "verify", return_value={"valid": True, "user": {"id": 12345}}), \
             patch.object(main, "_note_miniapp_ready"):
            users = [self.client.post("/auth/max", json={"init_data": "test-data"}).json() for _ in range(2)]
        self.assertEqual(users[0]["id"], users[1]["id"])
        self.assertNotEqual(users[0]["session_token"], users[1]["session_token"])
        self.assertFalse(storage.corpus_consent(json.loads(storage.get_settings(users[0]["id"]))))

    def test_schema_upgrade_keeps_existing_accounts_and_progress(self):
        storage._exec("INSERT INTO results(id,student_id,kind,score,max_score,created_at) VALUES(?,?,?,?,?,?)",
                      ("prior-result", self.user["id"], "reading", 1, 1, storage._now()))
        storage.ensure_schema()
        storage.ensure_schema()
        self.assertEqual(storage.get_account(self.user["nickname"])[0], self.user["id"])
        self.assertEqual(storage._exec("SELECT score FROM results WHERE id='prior-result'").fetchone()[0], 1)

    def test_restore_does_not_resurrect_a_revoked_session(self):
        backup = storage.dump_all()
        storage.reset_password(self.user["nickname"], "new-pass-hash")
        storage.restore_all({"accounts": backup["accounts"]}, replace=True)
        self.assertIsNone(storage.session_account(self.user["session_token"]))

    def test_health_and_readiness_report_missing_dependencies(self):
        with patch.object(main, "_storage_ok", False), patch.dict(os.environ, {"LLM_API_KEY": ""}):
            for path in ("/health", "/ready"):
                res = self.client.get(path)
                self.assertEqual(res.status_code, 503)
                self.assertFalse(res.json()["ok"])
            self.assertEqual(self.client.get("/ping").status_code, 200)
        with patch.dict(os.environ, {"LLM_API_KEY": "synthetic-test-key"}), \
             patch.dict(main._READY_CACHE, {"at": 0.0, "database": False}):
            res = self.client.get("/ready")
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["database"])
            self.assertEqual(res.json()["provider_inference"], "not_probed")

    def test_streamed_failure_counts_as_analysis_failure(self):
        async def failing():
            raise main.HTTPException(502, "synthetic upstream failure")
        async def consume():
            return "".join([chunk async for chunk in main._json_with_heartbeat(failing())])
        with patch.object(main, "_track_usage") as usage:
            result = json.loads(asyncio.run(consume()))
        self.assertIn("detail", result)
        usage.assert_called_once_with(analysis_failed=1)


if __name__ == "__main__":
    unittest.main()
