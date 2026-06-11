"""Persistent State Engine and Database Protection."""

import os
import pickle
import logging
from datetime import datetime
import shutil
from typing import Any, Dict

log = logging.getLogger("Persistence")

class StatePersistenceEngine:
    def __init__(self, db_path="project_alpha/data/state.pkl", backup_dir="project_alpha/data/backups/"):
        self.db_path = db_path
        self.backup_dir = backup_dir
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        self.CURRENT_VERSION = "1.0.0"

    def _migrate_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Migration hooks for future schema compatibility."""
        version = state.get("version", "0.0.0")
        
        if version == "0.0.0":
            log.info("Migrating unversioned state to 1.0.0")
            state["version"] = "1.0.0"
            
        # Example future hook:
        # if version == "1.0.0":
        #    state = migrate_v1_to_v2(state)
            
        return state

    def _validate_schema(self, state: Dict[str, Any]) -> bool:
        """Schema Integrity Validation."""
        if not isinstance(state, dict):
            return False
        if "version" not in state:
            return False
        if "data" not in state:
            return False
        return True
        
    def save_state(self, state_dict: Dict[str, Any]):
        """Snapshot system state safely with corruption protection & versioning.
        Justification for Pickle: Project Alpha uses complex deeply nested objects 
        (e.g. defaultdict, datetime, dataclasses) in PaperTrading/VirtualPortfolio.
        Pickle is retained to preserve Python references, but wrapped in a version schema.
        """
        temp_path = f"{self.db_path}.tmp"
        
        versioned_snapshot = {
            "version": self.CURRENT_VERSION,
            "timestamp": datetime.now().isoformat(),
            "data": state_dict
        }
        
        try:
            with open(temp_path, "wb") as f:
                pickle.dump(versioned_snapshot, f)
                
            # Safe atomic replace prevents corruption if power fails during write
            os.replace(temp_path, self.db_path)
            self._create_backup()
            log.info("System state successfully persisted to disk.")
        except Exception as e:
            log.error(f"Failed to persist state: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def load_state(self) -> Dict[str, Any] | None:
        """Loads state with automatic corruption detection and fallback."""
        if not os.path.exists(self.db_path):
            log.info("No existing state database found. Booting fresh.")
            return None
            
        try:
            with open(self.db_path, "rb") as f:
                snapshot = pickle.load(f)
                
            if not self._validate_schema(snapshot):
                raise ValueError("State schema validation failed. Possible corruption.")
                
            migrated_snapshot = self._migrate_state(snapshot)
            log.info(f"State successfully loaded. Version: {migrated_snapshot['version']}")
            return migrated_snapshot["data"]
            
        except Exception as e:
            log.error(f"State corruption or load failure detected in primary db: {e}")
            return self._recover_from_backup()

    def _create_backup(self):
        """Database Protection Backup Strategy."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"state_{timestamp}.pkl")
        shutil.copy2(self.db_path, backup_path)
        
        # Pruning: Keep only last 10 backups
        backups = sorted([f for f in os.listdir(self.backup_dir) if f.startswith("state_")])
        while len(backups) > 10:
            os.remove(os.path.join(self.backup_dir, backups.pop(0)))

    def _recover_from_backup(self) -> Dict[str, Any] | None:
        """Sequential backup traversal if primary DB is corrupt."""
        backups = sorted([f for f in os.listdir(self.backup_dir) if f.startswith("state_")], reverse=True)
        for b in backups:
            try:
                b_path = os.path.join(self.backup_dir, b)
                with open(b_path, "rb") as f:
                    snapshot = pickle.load(f)
                    
                if not self._validate_schema(snapshot):
                    raise ValueError("Backup schema invalid.")
                    
                migrated_snapshot = self._migrate_state(snapshot)
                log.warning(f"Successfully recovered from backup instance: {b}")
                
                # Restore the corrupt primary DB from this backup
                shutil.copy2(b_path, self.db_path)
                return migrated_snapshot["data"]
            except Exception:
                log.error(f"Backup {b} is also corrupted or incompatible. Moving to next.")
                continue
                
        log.critical("FATAL: All backups corrupted or missing. Manual intervention or fresh start required.")
        return None
