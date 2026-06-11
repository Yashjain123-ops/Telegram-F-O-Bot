import asyncio
import contextlib
import logging

import requests

import config

log = logging.getLogger("Notifier")


class TelegramNotifier:
    def __init__(self):
        self.queue = asyncio.Queue()
        self._worker_task = None
        self.text_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        self.photo_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())
        log.info("Telegram notification worker started.")

    async def stop(self):
        await self.queue.join()
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

    async def send(self, message: str):
        await self.queue.put({"type": "text", "content": message})

    async def send_photo(self, caption: str, image_bytes: bytes):
        await self.queue.put({"type": "photo", "caption": caption, "image": image_bytes})

    async def _worker(self):
        while True:
            item = await self.queue.get()
            try:
                if item["type"] == "text":
                    payload = {
                        "chat_id": config.TELEGRAM_CHAT_ID,
                        "text": item["content"],
                        "parse_mode": "Markdown",
                    }
                    await self._post_with_retry(self.text_url, json=payload)

                elif item["type"] == "photo":
                    payload = {
                        "chat_id": config.TELEGRAM_CHAT_ID,
                        "caption": item["caption"],
                        "parse_mode": "Markdown",
                    }
                    files = {"photo": ("chart.png", item["image"], "image/png")}
                    await self._post_with_retry(self.photo_url, data=payload, files=files)

                await asyncio.sleep(0.5)

            except Exception as exc:
                log.error(f"Failed to send Telegram message: {exc}")
                await asyncio.sleep(2)
            finally:
                self.queue.task_done()

    async def _post_with_retry(self, url: str, **kwargs):
        last_error = None
        for attempt in range(1, 4):
            try:
                response = await asyncio.to_thread(
                    requests.post,
                    url,
                    timeout=15,
                    **kwargs,
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok", False):
                    raise RuntimeError(payload)
                return payload
            except Exception as exc:
                last_error = exc
                log.warning(f"Telegram send failed (attempt {attempt}/3): {exc}")
                await asyncio.sleep(attempt)
        raise RuntimeError(f"Telegram send failed after retries: {last_error}")
