import json
import hashlib
import time
import os
import threading
from typing import Any, Dict, Optional
from datetime import datetime

class ImmutableAuditLog:
    """
    Immutable audit logging infrastructure for SEC/GDPR compliance.
    Ensures that every logged event (e.g., model changes, scoring operations)
    is recorded with a cryptographic hash chain to prevent tampering.
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, log_file: str = "audit_log.jsonl"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ImmutableAuditLog, cls).__new__(cls)
                cls._instance._init(log_file)
        return cls._instance

    def _init(self, log_file: str):
        self.log_file = log_file
        self.last_hash = self._get_last_hash()

    def _get_last_hash(self) -> str:
        """Retrieve the hash of the last log entry to maintain the chain."""
        if not os.path.exists(self.log_file):
            return hashlib.sha256(b"genesis").hexdigest()
        
        try:
            with open(self.log_file, "rb") as f:
                try:
                    f.seek(-2, os.SEEK_END)
                    while f.read(1) != b'\n':
                        f.seek(-2, os.SEEK_CUR)
                except OSError:
                    f.seek(0)
                last_line = f.readline().decode()
                if last_line:
                    last_entry = json.loads(last_line)
                    return last_entry.get("hash", hashlib.sha256(b"genesis").hexdigest())
        except Exception:
            pass
            
        return hashlib.sha256(b"genesis").hexdigest()

    def log_event(self, action: str, user: str, details: Dict[str, Any]) -> str:
        """
        Log an event immutably. 
        """
        with self._lock:
            event = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "action": action,
                "user": user,
                "details": details,
                "previous_hash": self.last_hash
            }
            
            event_str = json.dumps(event, sort_keys=True)
            current_hash = hashlib.sha256(event_str.encode()).hexdigest()
            
            # The final entry that gets written
            log_entry = {
                "payload": event,
                "hash": current_hash
            }
            
            # Write securely in append-only mode
            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
                
            self.last_hash = current_hash
            return current_hash

    @classmethod
    def verify_chain(cls, log_file: str) -> bool:
        """Verify the integrity of the audit log chain."""
        if not os.path.exists(log_file):
            return True
            
        expected_prev_hash = hashlib.sha256(b"genesis").hexdigest()
        
        with open(log_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                payload = entry["payload"]
                record_hash = entry["hash"]
                
                if payload["previous_hash"] != expected_prev_hash:
                    return False
                    
                payload_str = json.dumps(payload, sort_keys=True)
                computed_hash = hashlib.sha256(payload_str.encode()).hexdigest()
                
                if computed_hash != record_hash:
                    return False
                    
                expected_prev_hash = record_hash
                
        return True

# Global instances/helpers
def log_model_change(model_name: str, version: str, user: str, changes: Dict[str, Any]):
    audit_logger = ImmutableAuditLog()
    audit_logger.log_event(
        action="MODEL_CHANGE",
        user=user,
        details={
            "model_name": model_name,
            "version": version,
            "changes": changes
        }
    )

def log_scoring_operation(model_name: str, target: str, score: float, user: str, metadata: Optional[Dict[str, Any]] = None):
    audit_logger = ImmutableAuditLog()
    audit_logger.log_event(
        action="SCORING_OPERATION",
        user=user,
        details={
            "model_name": model_name,
            "target": target,
            "score": score,
            "metadata": metadata or {}
        }
    )
