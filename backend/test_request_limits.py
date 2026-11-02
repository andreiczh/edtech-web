import asyncio
import unittest
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.testclient import TestClient
from request_limits import UploadLimits


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.calls = []

        @self.app.post("/talk")
        async def talk(audio: UploadFile = File(...)):
            self.calls.append(True)
            return {"bytes": len(await audio.read())}

    def test_content_length_rejected_before_handler(self):
        self.app.add_middleware(UploadLimits, max_bytes=1024)
        with TestClient(self.app) as client:
            res = client.post("/talk", files={"audio": ("x.mp3", b"a" * 2048)})
        self.assertEqual(res.status_code, 413)
        self.assertEqual(self.calls, [])

    def test_chunked_body_is_bounded_and_small_file_works(self):
        self.app.add_middleware(UploadLimits, max_bytes=1024)
        head = b'--boundary\r\nContent-Disposition: form-data; name="audio"; filename="a.mp3"\r\n\r\n'
        with TestClient(self.app) as client:
            res = client.post("/talk", content=iter([head, b"a" * 800, b"b" * 800, b'\r\n--boundary--\r\n']),
                              headers={"Content-Type": "multipart/form-data; boundary=boundary"})
            self.assertEqual(res.status_code, 413, res.text)
            self.assertEqual(self.calls, [])
            good = client.post("/talk", files={"audio": ("x.mp3", b"a" * 128)})
            self.assertEqual(good.status_code, 200)
            self.assertEqual(good.json()["bytes"], 128)

    def test_unauthorized_upload_is_not_read(self):
        async def auth(scope, headers):
            raise HTTPException(401, "login required")
        async def never_receive():
            raise AssertionError("must not read the body")
        async def never_app(*args):
            raise AssertionError("must not parse multipart")
        sent = []
        async def send(message):
            sent.append(message)
        asyncio.run(UploadLimits(never_app, authenticate=auth)(
            {"type": "http", "method": "POST", "path": "/talk", "headers": []}, never_receive, send))
        self.assertEqual(sent[0]["status"], 401)

    def test_concurrency_limit_releases_after_completion(self):
        async def scenario():
            entered, release = asyncio.Event(), asyncio.Event()
            async def inner(scope, receive, send):
                entered.set()
                await release.wait()
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b""})
            middleware = UploadLimits(inner, max_active=1)
            scope = {"type": "http", "method": "POST", "path": "/talk", "headers": []}
            async def receive():
                return {"type": "http.request", "body": b""}
            sent = []
            async def send(message):
                sent.append(message)
            first = asyncio.create_task(middleware(scope, receive, send))
            await entered.wait()
            await middleware(scope, receive, send)
            self.assertEqual(sent[0]["status"], 429)
            release.set()
            await first
            self.assertEqual(middleware.active, 0)
        asyncio.run(scenario())

    def test_slow_upload_times_out_and_releases_slot(self):
        async def scenario():
            sent = []
            async def slow_receive():
                await asyncio.sleep(1)
                return {"type":"http.request", "body":b"x", "more_body":True}
            async def send(message): sent.append(message)
            middleware = UploadLimits(self.app, upload_seconds=0.01)
            scope = {"type":"http", "http_version":"1.1", "method":"POST", "path":"/talk",
                     "query_string":b"", "headers":[(b"content-type", b"multipart/form-data; boundary=b")],
                     "scheme":"http", "server":("test",80), "client":("test",1)}
            await middleware(scope, slow_receive, send)
            self.assertEqual(sent[0]["status"],408)
            self.assertEqual(middleware.active,0)
            self.assertEqual(self.calls,[])
        asyncio.run(scenario())

    def test_disconnect_releases_slot(self):
        async def scenario():
            async def app(*args): raise asyncio.CancelledError()
            async def receive(): return {"type":"http.disconnect"}
            async def send(message): pass
            middleware=UploadLimits(app)
            with self.assertRaises(asyncio.CancelledError):
                await middleware({"type":"http", "method":"POST", "path":"/talk", "headers":[]}, receive, send)
            self.assertEqual(middleware.active,0)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
