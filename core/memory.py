"""
Memory Manager: JSONL-based persistent memory with usage-layer routing.

- scene_memory.jsonl: structured long-term memories
- usage_layer: context / preference / experience
"""

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_TYPES = {"fact", "skill", "error", "preference", "rule", "experience"}
LEGACY_MEMORY_TYPES = {"general", "profile"}
VALID_MEMORY_TYPES = MEMORY_TYPES | LEGACY_MEMORY_TYPES
MEMORY_USAGE_LAYERS = {"context", "preference", "experience"}

DEFAULT_MEMORY_TYPE = "fact"
DEFAULT_USAGE_LAYER = "context"

TYPE_TO_USAGE_LAYER = {
    "fact": "context",
    "general": "context",
    "profile": "context",
    "preference": "preference",
    "rule": "preference",
    "skill": "experience",
    "error": "experience",
    "experience": "experience",
}

USAGE_LAYER_TITLES = {
    "context": "相关长期背景",
    "preference": "用户偏好与行为约束",
    "experience": "相关任务经验与避坑",
}


def normalize_memory_type(value: Optional[str]) -> str:
    normalized = (value or DEFAULT_MEMORY_TYPE).strip().lower()
    if normalized in VALID_MEMORY_TYPES:
        return normalized
    return DEFAULT_MEMORY_TYPE


def normalize_usage_layer(value: Optional[str], memory_type: Optional[str] = None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in MEMORY_USAGE_LAYERS:
        return normalized
    return TYPE_TO_USAGE_LAYER.get(normalize_memory_type(memory_type), DEFAULT_USAGE_LAYER)


class MemoryItem:
    """A single memory record."""

    def __init__(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        type: str = DEFAULT_MEMORY_TYPE,
        source: str = "manual",
        usage_layer: Optional[str] = None,
    ):
        import uuid

        self.id = f"mem_{uuid.uuid4().hex[:12]}"
        self.content = content
        self.tags = tags or []
        self.type = normalize_memory_type(type)
        self.usage_layer = normalize_usage_layer(usage_layer, self.type)
        self.source = source
        self.timestamp = time.time()
        self.created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "type": self.type,
            "usage_layer": self.usage_layer,
            "tags": self.tags,
            "source": self.source,
            "timestamp": self.timestamp,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        item = cls(
            data["content"],
            data.get("tags", []),
            type=data.get("type", DEFAULT_MEMORY_TYPE),
            source=data.get("source", "manual"),
            usage_layer=data.get("usage_layer"),
        )
        item.id = data.get("id", item.id)
        item.timestamp = data.get("timestamp", item.timestamp)
        item.created_at = data.get("created_at", item.created_at)
        return item


class MemoryManager:
    """
    Manages long-term memory using a JSONL file.

    If `embedding_client` and `vector_store` are provided, enables
    semantic (vector) search. Falls back to keyword search otherwise.
    """

    def __init__(
        self,
        data_dir: str = "data",
        embedding_client=None,
        vector_store=None,
    ):
        import threading

        self._lock = threading.Lock()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        memory_dir = self.data_dir / "memory"
        memory_dir.mkdir(exist_ok=True)
        self.memory_file = memory_dir / "scene_memory.jsonl"

        legacy = self.data_dir / "scene_memory.jsonl"
        if legacy.exists() and not self.memory_file.exists():
            legacy.rename(self.memory_file)
            print(f"[Memory] 已迁移: {legacy} → {self.memory_file}")

        self._memories: List[MemoryItem] = []
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._load()

    def _load(self) -> None:
        """Load all memories from JSONL file and migrate usage layers if needed."""
        if not self.memory_file.exists():
            return

        migration_required = False
        try:
            with open(self.memory_file, "r", encoding="utf-8") as file_obj:
                for line in file_obj:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if "usage_layer" not in data or data.get("usage_layer") not in MEMORY_USAGE_LAYERS:
                        migration_required = True
                    self._memories.append(MemoryItem.from_dict(data))
        except Exception as error:
            print(f"[Memory] Failed to load: {error}")
            return

        if migration_required:
            self._backup_before_migration()
            self._rewrite_file()
            print("[Memory] 已完成 usage_layer 迁移")

    def _backup_before_migration(self) -> None:
        if not self.memory_file.exists():
            return
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        backup_file = self.memory_file.parent / f"{self.memory_file.stem}.usage_layer_backup_{timestamp}.jsonl"
        shutil.copy2(self.memory_file, backup_file)

    def _save_one(self, item: MemoryItem) -> None:
        with open(self.memory_file, "a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    def _filter_candidates(
        self,
        tag_filter: Optional[str] = None,
        usage_layer: Optional[str] = None,
    ) -> List[MemoryItem]:
        normalized_layer = normalize_usage_layer(usage_layer) if usage_layer else None
        return [
            memory
            for memory in self._memories
            if (not tag_filter or tag_filter in memory.tags)
            and (not normalized_layer or memory.usage_layer == normalized_layer)
        ]

    def add(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        type: str = DEFAULT_MEMORY_TYPE,
        source: str = "manual",
        usage_layer: Optional[str] = None,
    ) -> MemoryItem:
        """
        Add a new memory.

        Deduplicates within the same usage layer, allowing the same content
        to exist in different layers for different purposes.
        """
        with self._lock:
            content = content.strip()[:1200]
            normalized_type = normalize_memory_type(type)
            normalized_layer = normalize_usage_layer(usage_layer, normalized_type)
            normalized_content = " ".join(content.lower().split())

            for memory in self._memories:
                if memory.usage_layer != normalized_layer:
                    continue
                memory_normalized = " ".join(memory.content.lower().split())
                if memory_normalized == normalized_content:
                    return memory
                shorter, longer = sorted([normalized_content, memory_normalized], key=len)
                if len(longer) > 0 and len(shorter) / len(longer) > 0.8 and shorter in longer:
                    return memory

            item = MemoryItem(
                content=content,
                tags=tags,
                type=normalized_type,
                source=source,
                usage_layer=normalized_layer,
            )
            self._memories.append(item)
            self._save_one(item)

        if self._embedding_client and self._vector_store:
            try:
                vectors = self._embedding_client.embed_text(content)
                if vectors:
                    self._vector_store.add_vectors(item.id, vectors)
            except Exception as error:
                print(f"[Memory] Vector generation failed: {error}")

        return item

    def search(
        self,
        query: str,
        top_k: int = 5,
        tag_filter: Optional[str] = None,
        usage_layer: Optional[str] = None,
    ) -> List[MemoryItem]:
        """
        Retrieve relevant memories with optional usage-layer filtering.
        """
        candidates = self._filter_candidates(tag_filter=tag_filter, usage_layer=usage_layer)
        if not candidates:
            return []

        if self._embedding_client and self._vector_store:
            query_vec = self._embedding_client.embed(query)
            if query_vec:
                candidate_ids = [memory.id for memory in candidates]
                scored_ids = self._vector_store.search(query_vec, top_k=top_k, candidate_ids=candidate_ids)
                id_to_memory = {memory.id: memory for memory in candidates}
                results = [id_to_memory[memory_id] for memory_id, _ in scored_ids if memory_id in id_to_memory]
                if results:
                    return results

        return self._keyword_search(query, candidates, top_k)

    def _keyword_search(self, query: str, candidates: List[MemoryItem], top_k: int) -> List[MemoryItem]:
        query_words = set(query.lower().split())
        scored: List[tuple[float, MemoryItem]] = []

        for memory in candidates:
            content_words = set(memory.content.lower().split())
            tag_words = set(" ".join(memory.tags).lower().split())
            score = len(query_words & content_words) + 0.5 * len(query_words & tag_words)
            if score > 0:
                scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].timestamp), reverse=True)
        return [memory for _, memory in scored[:top_k]]

    def get_recent(self, n: int = 5, usage_layer: Optional[str] = None) -> List[MemoryItem]:
        memories = self._filter_candidates(usage_layer=usage_layer)
        return sorted(memories, key=lambda memory: memory.timestamp, reverse=True)[:n]

    def build_context(self, query: str, top_k: int = 5) -> str:
        return self.build_layer_context(query, "context", top_k=top_k)

    def build_layer_context(self, query: str, usage_layer: str, top_k: int = 3) -> str:
        normalized_layer = normalize_usage_layer(usage_layer)
        results = self.search(query, top_k=top_k, usage_layer=normalized_layer)
        if not results:
            return ""
        title = USAGE_LAYER_TITLES.get(normalized_layer, "相关记忆")
        lines = [f"- {memory.content}" for memory in results]
        return f"# {title}\n" + "\n".join(lines)

    def build_prompt_sections(
        self,
        query: str,
        top_k_by_layer: Optional[Dict[str, int]] = None,
    ) -> Dict[str, str]:
        top_k_map = {"preference": 2, "context": 3, "experience": 2}
        if top_k_by_layer:
            top_k_map.update(top_k_by_layer)

        sections: Dict[str, str] = {}
        for usage_layer in ("preference", "context", "experience"):
            section = self.build_layer_context(query, usage_layer, top_k=top_k_map.get(usage_layer, 3))
            if section:
                sections[usage_layer] = section
        return sections

    def list_all(self) -> List[MemoryItem]:
        return list(self._memories)

    def list_by_type(self, memory_type: str) -> List[MemoryItem]:
        normalized_type = normalize_memory_type(memory_type)
        return [memory for memory in self._memories if memory.type == normalized_type]

    def list_by_usage_layer(self, usage_layer: str) -> List[MemoryItem]:
        normalized_layer = normalize_usage_layer(usage_layer)
        return [memory for memory in self._memories if memory.usage_layer == normalized_layer]

    def delete(self, memory_id: str) -> bool:
        before = len(self._memories)
        self._memories = [memory for memory in self._memories if memory.id != memory_id]
        if len(self._memories) < before:
            self._rewrite_file()
            if self._vector_store:
                self._vector_store.remove(memory_id)
            return True
        return False

    def update(
        self,
        memory_id: str,
        new_content: Optional[str] = None,
        new_tags: Optional[List[str]] = None,
        new_type: Optional[str] = None,
        new_usage_layer: Optional[str] = None,
    ) -> bool:
        for memory in self._memories:
            if memory.id != memory_id:
                continue
            if new_content is not None:
                memory.content = new_content.strip()[:1200]
            if new_tags is not None:
                memory.tags = new_tags
            if new_type is not None:
                memory.type = normalize_memory_type(new_type)
            if new_usage_layer is not None or new_type is not None:
                memory.usage_layer = normalize_usage_layer(new_usage_layer, memory.type)

            self._rewrite_file()
            if self._embedding_client and self._vector_store:
                try:
                    self._vector_store.remove(memory_id)
                    vectors = self._embedding_client.embed_text(memory.content)
                    if vectors:
                        self._vector_store.add_vectors(memory_id, vectors)
                except Exception as error:
                    print(f"[Memory] Vector update failed: {error}")
            return True
        return False

    def clear_all(self) -> None:
        with self._lock:
            self._memories = []
            self._rewrite_file()
            if self._vector_store:
                self._vector_store.clear()

    def _rewrite_file(self) -> None:
        with open(self.memory_file, "w", encoding="utf-8") as file_obj:
            for memory in self._memories:
                file_obj.write(json.dumps(memory.to_dict(), ensure_ascii=False) + "\n")
