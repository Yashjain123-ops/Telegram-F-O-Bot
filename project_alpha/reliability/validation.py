"""Deployment Validation Engine."""

import os
import logging
from typing import Any

log = logging.getLogger("DeploymentValidator")

class DeploymentValidator:
    def __init__(self, strategy_instance: Any):
        self.strategy = strategy_instance
        self.checks_passed = 0
        self.checks_failed = 0
        
    def _report(self, check_name: str, passed: bool, details: str = ""):
        if passed:
            self.checks_passed += 1
            log.info(f"✅ {check_name}: PASS {details}")
        else:
            self.checks_failed += 1
            log.error(f"❌ {check_name}: FAIL - {details}")

    def verify_all(self):
        log.info("--- Starting Deployment Validation ---")
        
        # 1. Verify Persistence Engine
        try:
            db_path = self.strategy.persistence.db_path
            backup_dir = self.strategy.persistence.backup_dir
            
            has_db = os.path.exists(db_path)
            has_backup_dir = os.path.exists(backup_dir)
            has_versioning = hasattr(self.strategy.persistence, 'CURRENT_VERSION')
            
            passed = has_backup_dir and has_versioning
            self._report("Persistence Engine", passed, f"(DB exists: {has_db}, Versioned: {has_versioning})")
        except Exception as e:
            self._report("Persistence Engine", False, str(e))
            
        # 2. Verify Recovery Engine
        try:
            tr = self.strategy.telegram_recovery
            has_persistent_queue = hasattr(tr.failed_queue, '_save')
            
            br = self.strategy.broker_recovery
            has_reconnect = hasattr(br, '_handle_disconnect')
            
            self._report("Recovery Engine", has_persistent_queue and has_reconnect, "(Telegram Queue + Broker Reconnect)")
        except Exception as e:
            self._report("Recovery Engine", False, str(e))

        # 3. Verify Alert Queue Persistence
        try:
            q_path = self.strategy.telegram_recovery.failed_queue.queue_path
            q_exists = os.path.exists(os.path.dirname(q_path))
            self._report("Persistent Alert Queue", q_exists, f"(Queue path: {q_path})")
        except Exception as e:
            self._report("Persistent Alert Queue", False, str(e))
            
        # 4. Verify Monitoring & Heartbeat
        try:
            hm = self.strategy.health_monitor
            has_heartbeat = hasattr(hm, '_run_heartbeat')
            has_checks = hasattr(hm, '_run_health_checks')
            
            self._report("Monitoring & Heartbeat", has_heartbeat and has_checks, "(Memory & Risk tracking bound)")
        except Exception as e:
            self._report("Monitoring & Heartbeat", False, str(e))

        log.info(f"--- Validation Complete: {self.checks_passed} Passed, {self.checks_failed} Failed ---")
        return self.checks_failed == 0
