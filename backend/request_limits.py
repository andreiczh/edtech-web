"""Bound uploads before multipart parsing, including chunked requests."""
import asyncio
import time

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse

VOICE_PATHS = {"/talk", "/talk_stream", "/monologue", "/task_feedback"}


class UploadLimits:
    def __init__(self, app, authenticate=None, max_bytes=26 * 1024 * 1024,
                 max_active=4, upload_seconds=60):
        self.app = app
        self.authenticate = authenticate
        self.max_bytes = max_bytes
        self.max_active = max_active
        self.upload_seconds = upload_seconds
        self.active = 0

    async def __call__(self, scope, receive, send):
        path = scope.get("path")
        if scope["type"] != "http" or scope.get("method") != "POST" or path not in VOICE_PATHS | {"/max/probe/audio"}:
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        limit = min(self.max_bytes, 2304 * 1024) if path == "/max/probe/audio" else self.max_bytes

        async def reject(status, message):
            await JSONResponse({"detail": message}, status_code=status)(scope, receive, send)

        try:
            if int(headers.get("content-length", "0")) > limit:
                return await reject(413, "Запись слишком большая — сократи её и попробуй снова.")
        except ValueError:
            return await reject(400, "Некорректный размер запроса.")
        if self.active >= self.max_active:
            return await reject(429, "Сейчас обрабатывается много записей — попробуй чуть позже.")
        self.active += 1
        try:
            if self.authenticate and path in VOICE_PATHS:
                try:
                    await self.authenticate(scope, headers)
                except HTTPException as error:
                    return await reject(error.status_code, error.detail)
            total = 0
            deadline = time.monotonic() + self.upload_seconds
            status = 0
            sent = False
            complete = False

            async def bounded_receive():
                nonlocal total, status, complete
                if complete:
                    return await receive()
                try:
                    message = await asyncio.wait_for(receive(), max(0.001, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    status = 408
                    raise MultiPartException("upload timed out")
                if message["type"] == "http.request":
                    total += len(message.get("body", b""))
                    if total > limit:
                        status = 413
                        # Starlette closes every temporary multipart file on this exception.
                        raise MultiPartException("upload too large")
                    complete = not message.get("more_body", False)
                return message

            async def bounded_send(message):
                nonlocal sent
                if status:
                    if not sent:
                        sent = True
                        await reject(status, "Запись слишком большая." if status == 413 else "Не удалось загрузить запись за минуту — попробуй снова.")
                    return
                await send(message)

            try:
                await self.app(scope, bounded_receive, bounded_send)
            except MultiPartException:
                if not sent:
                    await reject(status or 413, "Загрузка записи не завершена.")
        finally:
            self.active -= 1
