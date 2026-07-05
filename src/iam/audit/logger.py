import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

class AuditLogger:
    def __init__(self, log_path: str = "audit_log.jsonl"):
        self.log_path = Path(log_path)
        
    def log_change(self, model_id: str, change_type: str, details: Dict[str, Any]):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "model_id": model_id,
            "change_type": change_type,
            "details": details
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    def log_override(self, model_id: str, assumption: str, original_value: Any, new_value: Any, reason: str):
        self.log_change(model_id, "assumption_override", {
            "assumption": assumption,
            "original_value": original_value,
            "new_value": new_value,
            "reason": reason
        })
