"""
Enhanced logging and metrics collection for dry run validation.
Provides rotating logs, JSON metrics, and system health snapshots.
"""

import json
import logging
import os
import time
import psutil
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path


def setup_logging(cfg):
    """Set up enhanced logging with rotation and metrics collection."""
    os.makedirs("logs", exist_ok=True)
    prefix = cfg["logging"]["file_prefix"]
    rotate_bytes = cfg["logging"]["rotate_mb"] * 1024 * 1024
    backups = cfg["logging"]["backups"]

    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = RotatingFileHandler(
        f"{prefix}.log", maxBytes=rotate_bytes, backupCount=backups
    )
    file_handler.setFormatter(fmt)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, cfg["logging"]["level"]))
    logger.addHandler(file_handler)

    # Console remains simple
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    # Metrics file (JSON Lines)
    metrics_path = cfg["logging"]["json_metrics_file"]
    return MetricsLogger(metrics_path)


class MetricsLogger:
    """JSON Lines metrics logger for system performance tracking."""
    
    def __init__(self, path):
        self.path = path
        self.proc = psutil.Process(os.getpid())
        
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def write(self, **kv):
        """Write a metrics entry to JSON Lines file."""
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **kv
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def snapshot_system(self, extra=None):
        """Take a system health snapshot with CPU, memory, and custom metrics."""
        try:
            mem = self.proc.memory_info()
            cpu = psutil.cpu_percent(interval=None)
            self.write(
                type="health_snapshot",
                cpu_pct=cpu,
                rss_mb=round(mem.rss / (1024*1024), 2),
                extra=extra or {}
            )
        except Exception as e:
            # Don't let metrics collection break the main system
            logging.warning(f"[METRICS] Failed to take system snapshot: {e}")

    def log_incident(self, event_type, severity, symbol=None, context=None, action=None, ttr_seconds=0, notes=None):
        """Log an incident to both metrics and CSV incident log."""
        # Write to metrics
        self.write(
            type="incident",
            event_type=event_type,
            severity=severity,
            symbol=symbol,
            context=context,
            action=action,
            ttr_seconds=ttr_seconds,
            notes=notes
        )
        
        # Write to incident CSV
        try:
            incident_file = "monitoring/incident_log.csv"
            os.makedirs("monitoring", exist_ok=True)
            
            with open(incident_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now(timezone.utc).isoformat()
                f.write(f"{timestamp},{event_type},{severity},{symbol or ''},"
                       f'"{context or ''}","{action or ''}",{ttr_seconds},"{notes or ''}"\n')
        except Exception as e:
            logging.warning(f"[METRICS] Failed to log incident to CSV: {e}")

    def log_performance(self, operation, duration_ms, success=True, **extra):
        """Log performance metrics for operations."""
        self.write(
            type="performance",
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            **extra
        )
