"""Failure Recovery Engines for External Services."""

import os
import json
import asyncio
import logging
from collections import deque
from typing import Callable, Any

log = logging.getLogger("Recovery")

class PersistentTelegramQueue:
    def __init__(self, queue_path="project_alpha/data/telegram_queue.jsonl"):
        self.queue_path = queue_path
        os.makedirs(os.path.dirname(self.queue_path), exist_ok=True)
        self.queue = deque()
        self._load()
        
    def _load(self):
        if not os.path.exists(self.queue_path): return
        try:
            with open(self.queue_path, "r") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        # Remove photo from kwargs for json serialization safety, or just store message and retries.
                        # For Phase 6, we'll store basic fields. Photos might be lost on hard reboot, but text survives.
                        self.queue.append((item["message"], item["retries"], item.get("kwargs", {})))
        except Exception as e:
            log.error(f"Failed to load persistent telegram queue: {e}")
            
    def _save(self):
        temp_path = f"{self.queue_path}.tmp"
        try:
            with open(temp_path, "w") as f:
                for msg, retries, kwargs in self.queue:
                    # Strip out non-serializable bytes (e.g. photo)
                    safe_kwargs = {k: v for k, v in kwargs.items() if not isinstance(v, bytes)}
                    f.write(json.dumps({"message": msg, "retries": retries, "kwargs": safe_kwargs}) + "\n")
            os.replace(temp_path, self.queue_path)
        except Exception as e:
            log.error(f"Failed to save persistent telegram queue: {e}")

    def append(self, item):
        self.queue.append(item)
        self._save()
        
    def popleft(self):
        item = self.queue.popleft()
        self._save()
        return item
        
    def __len__(self):
        return len(self.queue)
        
    def __iter__(self):
        return iter(self.queue)

class TelegramRecoveryEngine:
    def __init__(self, send_callback: Callable[[str], Any], max_retries: int = 5):
        self.send_callback = send_callback
        self.failed_queue = PersistentTelegramQueue()
        self.max_retries = max_retries
        self.is_running = False
        
    async def start(self):
        """Starts the background retry loop for failed messages."""
        if self.is_running: return
        self.is_running = True
        asyncio.create_task(self._retry_loop())
        
    async def queue_alert(self, message: str, retries: int = 0, **kwargs):
        """Attempts to send an alert. Queues on failure."""
        try:
            success = await self.send_callback(message, **kwargs)
            if not success:
                raise Exception("Telegram API returned failure status")
        except Exception as e:
            log.error(f"Telegram alert failed: {e}. Queuing for recovery.")
            if retries < self.max_retries:
                # Prevent exact duplicates back-to-back
                if not any(msg == message for msg, _, _ in self.failed_queue):
                    self.failed_queue.append((message, retries + 1, kwargs))
            else:
                log.critical(f"DROPPED ALERT: Max retries exceeded for message.")

    async def _retry_loop(self):
        """Background loop flushing the failed alert queue sequentially."""
        while self.is_running:
            if self.failed_queue:
                msg, retries, kwargs = self.failed_queue.popleft()
                log.info(f"Retrying failed Telegram alert (Attempt {retries})...")
                await self.queue_alert(msg, retries, **kwargs)
                # Stagger retries to avoid rate limits
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(10)


class BrokerRecoveryEngine:
    def __init__(self, reconnect_callback: Callable, validate_callback: Callable):
        self.reconnect_callback = reconnect_callback
        self.validate_callback = validate_callback
        self.is_connected = True
        self.disconnect_count = 0
        self.is_monitoring = False
        
    async def start_monitoring(self):
        if self.is_monitoring: return
        self.is_monitoring = True
        asyncio.create_task(self._monitor_connection())
        
    async def _monitor_connection(self):
        """Continuously checks data freshness and socket health."""
        while self.is_monitoring:
            try:
                self.is_connected = await self.validate_callback()
                if not self.is_connected:
                    await self._handle_disconnect()
                else:
                    self.disconnect_count = 0
            except Exception as e:
                log.error(f"Broker connection monitoring error: {e}")
                await self._handle_disconnect()
                
            await asyncio.sleep(15) # Check every 15s
            
    async def _handle_disconnect(self):
        """Broker Disconnect Recovery with Exponential Backoff."""
        self.disconnect_count += 1
        log.critical(f"BROKER DISCONNECTED. Attempting recovery (Count: {self.disconnect_count})...")
        
        # Exponential backoff: 2, 4, 8, 16... max 60 seconds
        backoff = min(60, 2 ** self.disconnect_count)
        log.info(f"Backing off for {backoff} seconds before retry.")
        await asyncio.sleep(backoff)
        
        try:
            success = await self.reconnect_callback()
            if success:
                self.is_connected = True
                self.disconnect_count = 0
                log.info("Broker reconnected successfully.")
        except Exception as e:
            log.error(f"Reconnection failed: {e}")
