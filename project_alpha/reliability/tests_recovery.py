"""Recovery Test Suite Framework."""

import asyncio
import logging
import os
from typing import Any

from project_alpha.reliability.persistence import StatePersistenceEngine
from project_alpha.reliability.recovery import TelegramRecoveryEngine, BrokerRecoveryEngine

log = logging.getLogger("RecoveryTests")

class RecoveryTestSuite:
    def __init__(self, strategy_instance: Any):
        self.strategy = strategy_instance
        self.tests_passed = 0
        self.tests_failed = 0
        
    def _assert(self, condition: bool, test_name: str, details: str):
        if condition:
            self.tests_passed += 1
            log.info(f"✅ {test_name}: PASS {details}")
        else:
            self.tests_failed += 1
            log.error(f"❌ {test_name}: FAIL - {details}")

    async def run_all(self):
        log.info("--- Starting Recovery Test Suite ---")
        
        await self.test_broker_recovery()
        await self.test_telegram_recovery()
        self.test_snapshot_recovery()
        self.test_state_versioning()
        
        log.info(f"--- Tests Complete: {self.tests_passed} Passed, {self.tests_failed} Failed ---")
        
    async def test_broker_recovery(self):
        """Simulate broker disconnect and trigger exponential backoff recovery."""
        br = self.strategy.broker_recovery
        original_validate = br.validate_callback
        
        # Force mock failure
        async def _mock_fail(): return False
        br.validate_callback = _mock_fail
        
        await br._handle_disconnect()
        
        self._assert(br.disconnect_count > 0, "Broker Recovery", "Disconnect counter incremented.")
        
        # Restore
        br.validate_callback = original_validate
        
    async def test_telegram_recovery(self):
        """Simulate telegram HTTP 429 rate limit to queue an alert persistently."""
        tr = self.strategy.telegram_recovery
        original_send = tr.send_callback
        
        # Force mock failure
        async def _mock_fail(msg, **kwargs): return False
        tr.send_callback = _mock_fail
        
        initial_q_size = len(tr.failed_queue)
        await tr.queue_alert("TEST_ALERT")
        
        self._assert(len(tr.failed_queue) > initial_q_size, "Telegram Recovery", "Failed message persisted to JSONL queue.")
        
        # Clean up test alert
        if len(tr.failed_queue) > 0:
            tr.failed_queue.popleft()
            
        # Restore
        tr.send_callback = original_send
        
    def test_snapshot_recovery(self):
        """Simulate full system crash and State Restore via Persistence Engine."""
        pe = self.strategy.persistence
        test_state = {"version": "0.0.0", "data": {"test_key": "test_val"}}
        
        # Save mock state
        pe.save_state(test_state["data"]) # Save state handles version embedding
        
        # Load mock state
        recovered = pe.load_state()
        
        self._assert(recovered is not None and "test_key" in recovered, "Snapshot Recovery", "State cleanly saved and reloaded.")
        
    def test_state_versioning(self):
        """Test Migration Hooks inside Persistence Engine."""
        pe = self.strategy.persistence
        mock_old_state = {"version": "0.0.0", "data": {}}
        
        migrated = pe._migrate_state(mock_old_state)
        
        self._assert(migrated["version"] == "1.0.0", "State Versioning", "Migration hook successfully upgraded v0 to v1.0.0.")
