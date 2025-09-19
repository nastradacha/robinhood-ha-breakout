"""
Lightweight persistent state manager for the position monitor.

Persists small pieces of state across restarts, e.g.:
- last_alerts
- trailing_hits_count
- stop_loss_breach_counts
- eod_summary_sent_date

Uses atomic write (temp file + rename) and creates parent directory if missing.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class MonitorState:
    path: str
    data: Dict[str, Any] = field(default_factory=dict)

    def load(self) -> Dict[str, Any]:
        try:
            if not os.path.exists(self.path):
                self.data = {}
                return self.data
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            return self.data
        except Exception:
            # Return empty state on failure
            self.data = {}
            return self.data

    def save(self, data: Dict[str, Any]) -> None:
        # Ensure directory
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        except Exception:
            pass
        # Atomic write
        tmp_path = f"{self.path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, self.path)
            self.data = data
        except Exception:
            # Best-effort cleanup of tmp file
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
