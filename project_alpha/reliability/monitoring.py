"""Health Monitoring, Heartbeat, and Operational Alerting Engine."""

import logging
import asyncio
from typing import Any, Callable

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

log = logging.getLogger("Monitoring")

class OperationalAlerting:
    def __init__(self, alert_callback: Callable[[str], Any]):
        self.alert_callback = alert_callback
        
    async def trigger_critical(self, title: str, details: str):
        """Dispatches emergency alerts directly to Telegram ops channels."""
        msg = f"🚨 CRITICAL ALERT: {title}\n\n{details}\n\nSystem requires immediate attention."
        log.critical(msg)
        try:
            await self.alert_callback(msg)
        except Exception as e:
            log.error(f"Failed to transmit critical alert: {e}")

class HealthMonitoringEngine:
    def __init__(self, strategy_instance, alert_engine: OperationalAlerting, broker_recovery):
        self.strategy = strategy_instance
        self.alert_engine = alert_engine
        self.broker = broker_recovery
        self.is_monitoring = False
        
    async def start(self):
        if self.is_monitoring: return
        self.is_monitoring = True
        asyncio.create_task(self._run_heartbeat())
        asyncio.create_task(self._run_health_checks())
        
    async def _run_health_checks(self):
        """Continuous internal state monitoring."""
        while self.is_monitoring:
            await asyncio.sleep(60) # Check every minute
            if HAS_PSUTIL:
                mem = psutil.virtual_memory().percent
            
                # RAM Protection
                if mem > 90:
                    await self.alert_engine.trigger_critical(
                        "High Memory Usage", 
                        f"Virtual Memory at {mem}%. Potential memory leak in live data frames."
                    )
            
            # Risk Limits Protection Check
            if hasattr(self.strategy, 'paper_trading'):
                if self.strategy.paper_trading.risk_engine.trading_halted:
                    await self.alert_engine.trigger_critical(
                        "Risk Halt Triggered",
                        "The Trading Engine has halted execution due to Drawdown/Loss limits."
                    )
            
    async def _run_heartbeat(self):
        """Periodic status message (Heartbeat). Proof of life."""
        while self.is_monitoring:
            await asyncio.sleep(3600) # Hourly heartbeat
            
            mem = psutil.virtual_memory().percent
            open_sigs = len(self.strategy.signal_store.get_all_active())
            
            pos_str = "0"
            val_str = "N/A"
            if hasattr(self.strategy, 'paper_trading'):
                open_pos = len(self.strategy.paper_trading.portfolio.open_positions)
                val = self.strategy.paper_trading.portfolio.current_capital
                pos_str = str(open_pos)
                val_str = f"₹{val:,.2f}"
                
            broker_status = "🟢 Connected" if self.broker.is_connected else "🔴 DISCONNECTED"
            
            msg = (
                f"💓 SYSTEM HEARTBEAT\n"
                f"Status: OK\n"
                f"Memory: {mem}%\n"
                f"Broker: {broker_status}\n"
                f"Active Signals: {open_sigs}\n"
                f"Open Positions: {pos_str}\n"
                f"Portfolio Value: {val_str}"
            )
            log.info("Heartbeat generated.")
            try:
                await self.alert_engine.alert_callback(msg)
            except Exception:
                pass
