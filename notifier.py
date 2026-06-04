import asyncio
import logging
import requests
import config

log = logging.getLogger("Notifier")


class TelegramNotifier:
    def __init__(self):
        self.queue         = asyncio.Queue()
        self._worker_task  = None
        self.text_url  = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        self.photo_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())
        log.info("Telegram notification worker started.")

    async def stop(self):
        await self.queue.join()
        if self._worker_task:
            self._worker_task.cancel()

    async def send(self, message: str):
        """Queue a text message."""
        await self.queue.put({"type": "text", "content": message})

    async def send_photo(self, caption: str, image_bytes: bytes):
        """Queue a photo message with caption."""
        await self.queue.put({"type": "photo", "caption": caption, "image": image_bytes})

    async def _worker(self):
        while True:
            try:
                item = await self.queue.get()

                if item["type"] == "text":
                    payload = {
                        "chat_id":    config.TELEGRAM_CHAT_ID,
                        "text":       item["content"],
                        "parse_mode": "Markdown"
                    }
                    await asyncio.to_thread(requests.post, self.text_url, json=payload)

                elif item["type"] == "photo":
                    payload = {
                        "chat_id":    config.TELEGRAM_CHAT_ID,
                        "caption":    item["caption"],
                        "parse_mode": "Markdown"
                    }
                    files = {"photo": ("chart.png", item["image"], "image/png")}
                    await asyncio.to_thread(
                        requests.post, self.photo_url, data=payload, files=files
                    )

                await asyncio.sleep(0.5)
                self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Failed to send Telegram message: {e}")
                self.queue.task_done()
                await asyncio.sleep(2)