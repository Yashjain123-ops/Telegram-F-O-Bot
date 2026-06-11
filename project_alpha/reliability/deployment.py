"""Deployment Hardening: Graceful Shutdown and Exception Containment."""

import signal
import sys
import logging
from project_alpha.reliability.persistence import StatePersistenceEngine

log = logging.getLogger("Deployment")

class DeploymentManager:
    def __init__(self, strategy_instance, persistence_engine: StatePersistenceEngine):
        self.strategy = strategy_instance
        self.persistence = persistence_engine
        self.shutdown_triggered = False
        
    def _handle_shutdown(self, sig, frame):
        """Exception Containment and State Preservation hook."""
        if self.shutdown_triggered:
            return
        self.shutdown_triggered = True
        log.critical("GRACEFUL SHUTDOWN INITIATED. Preserving system state...")
        
        try:
            # Package the entire live operational state
            state_snapshot = {
                "signal_store": self.strategy.signal_store,
                "validation_engine": self.strategy.validation_engine,
            }
            
            # Conditionally save PaperTrading state
            if hasattr(self.strategy, "paper_trading"):
                state_snapshot["paper_trading"] = self.strategy.paper_trading
                
            self.persistence.save_state(state_snapshot)
            log.info("System state successfully preserved. Control returning to bot.py for teardown.")
            
        except Exception as e:
            log.critical(f"FATAL ERROR DURING SHUTDOWN PRESERVATION: {e}")
