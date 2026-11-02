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


if __name__ == "__main__":
    unittest.main()
