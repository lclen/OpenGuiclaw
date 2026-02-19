"""
Journal Manager: Daily episodic memory.

Stores summarized events in data/journals/YYYY-MM-DD.md.
"""

from pathlib import Path
import time
from typing import Optional

class JournalManager:
    def __init__(self, data_dir: str = "data"):
        self.journal_dir = Path(data_dir) / "journals"
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, date_str: str) -> Path:
        return self.journal_dir / f"{date_str}.md"

    def append(self, content: str, date_str: str = None) -> None:
        """Append content to the journal of the given date (default: today)."""
        if date_str is None:
            date_str = time.strftime("%Y-%m-%d")
        
        path = self._get_file_path(date_str)
        timestamp = time.strftime("%H:%M:%S")
        
        entry = f"\n## [{timestamp}]\n{content}\n"
        
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)

    def read_day(self, date_str: str) -> Optional[str]:
        """Read the full content of a specific day's journal."""
        path = self._get_file_path(date_str)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
