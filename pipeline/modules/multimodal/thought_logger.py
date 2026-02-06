"""
Thought Logger for Multimodal Translation.

Saves Gemini 3 Pro's thinking process during visual analysis (Phase 1.6)
to structured JSON files for editor review and QA.

Stored at: WORK/{volume_id}/cache/thoughts/{illustration_id}.json
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class VisualAnalysisLog:
    """Log entry for a single illustration's visual analysis."""
    illustration_id: str
    model: str
    thinking_level: str
    thoughts: List[str]
    iterations: int
    processing_time_seconds: float
    timestamp: str
    success: bool
    error: Optional[str] = None


class ThoughtLogger:
    """Store and retrieve thinking process logs for visual analysis."""

    def __init__(self, volume_path: Path, thoughts_dir: str = "cache/thoughts"):
        self.volume_path = volume_path
        self.thoughts_path = volume_path / thoughts_dir
        self.thoughts_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"[THOUGHT] Initialized thought logger: {self.thoughts_path}")

    def log_analysis(self, log_entry: VisualAnalysisLog) -> Path:
        """
        Save a visual analysis log entry to disk.

        Returns:
            Path to the saved log file.
        """
        log_file = self.thoughts_path / f"{log_entry.illustration_id}.json"

        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(log_entry), f, indent=2, ensure_ascii=False)

            logger.info(f"[THOUGHT] ✓ Saved analysis log: {log_file}")
            return log_file
        except Exception as e:
            logger.error(f"[THOUGHT] ✗ Failed to save log {log_file.name}: {e}")
            raise

    def get_log(self, illustration_id: str) -> Optional[VisualAnalysisLog]:
        """Load a log entry for a specific illustration."""
        log_file = self.thoughts_path / f"{illustration_id}.json"

        if not log_file.exists():
            return None

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Backward compat: remove legacy fields not in current dataclass
            data.pop("function_calls", None)
            return VisualAnalysisLog(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"[THOUGHT] Failed to load log {log_file.name}: {e}")
            return None

    def get_all_logs(self) -> List[VisualAnalysisLog]:
        """Load all thought logs for the volume."""
        logs = []
        for log_file in sorted(self.thoughts_path.glob("*.json")):
            log = self.get_log(log_file.stem)
            if log:
                logs.append(log)
        return logs

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all thought logs."""
        logs = self.get_all_logs()
        if not logs:
            return {"total": 0}

        total_time = sum(l.processing_time_seconds for l in logs)
        success_count = sum(1 for l in logs if l.success)

        return {
            "total": len(logs),
            "successful": success_count,
            "failed": len(logs) - success_count,
            "total_time_seconds": round(total_time, 1),
            "avg_time_seconds": round(total_time / len(logs), 1),
            "total_iterations": sum(l.iterations for l in logs),
        }
