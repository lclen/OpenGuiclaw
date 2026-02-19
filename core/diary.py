"""
Diary Manager: Stores AI's daily personal diary entries.

Unlike `memory.jsonl` (factual core memory), diary entries are
first-person emotional/experiential writing by the AI.

Storage: data/diary/YYYY-MM-DD.md
Each file is one day's diary. The content is free-form Markdown.
"""

from pathlib import Path
from typing import Optional, List
import time


class DiaryManager:
    """
    Manages daily diary files for the AI.
    
    - Each day gets a single Markdown file: data/diary/YYYY-MM-DD.md
    - The content is the AI's own reflection on the day: emotional, 
      free-form, first-person prose - not a task log.
    """

    def __init__(self, data_dir: str = "data"):
        self.diary_dir = Path(data_dir) / "diary"
        self.diary_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, date_str: str) -> Path:
        return self.diary_dir / f"{date_str}.md"

    def write(self, date_str: str, content: str) -> Path:
        """Write (or overwrite) the diary for a given date."""
        path = self._get_path(date_str)
        wrapped = f"# 日记 — {date_str}\n\n{content}\n"
        path.write_text(wrapped, encoding="utf-8")
        return path

    def read(self, date_str: str) -> Optional[str]:
        """Read the diary for a specific date. Returns None if not found."""
        path = self._get_path(date_str)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def has_diary(self, date_str: str) -> bool:
        return self._get_path(date_str).exists()

    def list_dates(self) -> List[str]:
        """Return all dates that have diary entries, sorted ascending."""
        return sorted(p.stem for p in self.diary_dir.glob("*.md"))

    def search(self, query: str, top_k: int = 3) -> List[dict]:
        """
        Simple keyword search across all diary entries.
        Returns [{date, snippet}] sorted by date descending.
        Falls back to case-insensitive substring match.
        """
        q = query.lower()
        results = []

        for date_str in sorted(self.list_dates(), reverse=True):
            content = self.read(date_str) or ""
            if q in content.lower():
                # Extract a short context around the match
                idx = content.lower().find(q)
                start = max(0, idx - 60)
                end = min(len(content), idx + 200)
                snippet = "..." + content[start:end].replace("\n", " ") + "..."
                results.append({"date": date_str, "snippet": snippet})
                if len(results) >= top_k:
                    break

        return results
