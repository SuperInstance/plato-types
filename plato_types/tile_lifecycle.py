"""
Enhanced tile lifecycle for PLATO protocol.

Provides:
  - DeprecationNotice: tile marked for future removal with grace period
  - LineageTracker: tracks tile evolution chains (v1 → v2 → v3)
  - ConflictResolver: resolves concurrent writes to the same room
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .types import TileLifecycle


@dataclass
class DeprecationNotice:
    """A tile marked for future removal with a grace period.

    Agents seeing this notice should stop using the tile but
    it remains valid until expires_at.
    """

    tile_id: str
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    grace_seconds: float = 3600.0  # 1 hour default
    superseded_by: str = ""  # ID of replacement tile, if any

    @property
    def expires_at(self) -> float:
        return self.created_at + self.grace_seconds

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        return now >= self.expires_at

    def is_active(self, now: Optional[float] = None) -> bool:
        """Notice is active (not yet expired) — tile is deprecated but still usable."""
        return not self.is_expired(now)

    def remaining_seconds(self, now: Optional[float] = None) -> float:
        now = now if now is not None else time.time()
        return max(0.0, self.expires_at - now)

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "reason": self.reason,
            "created_at": self.created_at,
            "grace_seconds": self.grace_seconds,
            "superseded_by": self.superseded_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DeprecationNotice":
        return cls(
            tile_id=d["tile_id"],
            reason=d.get("reason", ""),
            created_at=d.get("created_at", time.time()),
            grace_seconds=d.get("grace_seconds", 3600.0),
            superseded_by=d.get("superseded_by", ""),
        )


@dataclass
class LineageNode:
    """A node in a tile's lineage chain."""
    tile_id: str
    state: TileLifecycle = TileLifecycle.ACTIVE
    timestamp: float = field(default_factory=time.time)
    reason: str = ""


class LineageTracker:
    """Tracks tile evolution chains: v1 → v2 → v3.

    Maintains a graph of supersede relationships and can
    trace the full lineage of any tile.
    """

    def __init__(self):
        # tile_id -> list of successors (in order)
        self._successors: Dict[str, List[LineageNode]] = {}
        # tile_id -> parent tile_id
        self._parent: Dict[str, str] = {}
        # tile_id -> LineageNode metadata
        self._nodes: Dict[str, LineageNode] = {}

    def register(self, tile_id: str, state: TileLifecycle = TileLifecycle.ACTIVE,
                 reason: str = "") -> None:
        """Register a tile in the lineage graph."""
        node = LineageNode(tile_id=tile_id, state=state, reason=reason)
        self._nodes[tile_id] = node

    def record_supersede(self, old_id: str, new_id: str, reason: str = "") -> None:
        """Record that new_id supersedes old_id."""
        # Ensure both nodes exist
        if old_id not in self._nodes:
            self.register(old_id, TileLifecycle.SUPERSEDED)
        if new_id not in self._nodes:
            self.register(new_id, TileLifecycle.ACTIVE)

        # Update old node state
        self._nodes[old_id].state = TileLifecycle.SUPERSEDED

        # Record relationship
        if old_id not in self._successors:
            self._successors[old_id] = []
        self._successors[old_id].append(
            LineageNode(tile_id=new_id, state=TileLifecycle.ACTIVE, reason=reason)
        )
        self._parent[new_id] = old_id

    def lineage(self, tile_id: str) -> List[LineageNode]:
        """Return the full lineage chain from the original ancestor to the latest successor."""
        # Walk back to root
        root_id = self.root(tile_id)
        if root_id is None:
            return [self._nodes[tile_id]] if tile_id in self._nodes else []

        # Walk forward from root through successors to build chain
        chain = []
        current = root_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            if current in self._nodes:
                chain.append(self._nodes[current])
            successors = self._successors.get(current, [])
            if successors:
                current = successors[-1].tile_id  # follow latest successor
            else:
                break
        return chain

    def successors(self, tile_id: str) -> List[str]:
        """Return direct successors of a tile."""
        if tile_id in self._successors:
            return [node.tile_id for node in self._successors[tile_id]]
        return []

    def root(self, tile_id: str) -> Optional[str]:
        """Find the root (original) tile in the lineage."""
        current = tile_id
        visited = set()
        while current in self._parent and current not in visited:
            visited.add(current)
            current = self._parent[current]
        return current

    def latest(self, tile_id: str) -> str:
        """Find the latest (current) tile in the chain starting from tile_id."""
        # First go to root, then walk forward
        r = self.root(tile_id)
        if r is None:
            return tile_id
        current = r
        visited = set()
        while current in self._successors and self._successors[current] and current not in visited:
            visited.add(current)
            # Take the last successor (most recent)
            current = self._successors[current][-1].tile_id
        return current

    def chain_length(self, tile_id: str) -> int:
        """Return the number of tiles in the lineage chain."""
        return len(self.lineage(tile_id))

    def is_ancestor(self, ancestor_id: str, descendant_id: str) -> bool:
        """Check if ancestor_id is an ancestor of descendant_id."""
        # Walk from descendant back through parents
        current = descendant_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            if current == ancestor_id and current != descendant_id:
                return True
            current = self._parent.get(current)
        return False

    def all_roots(self) -> List[str]:
        """Return all root tile IDs (tiles with no parent)."""
        return [tid for tid in self._nodes if tid not in self._parent]


@dataclass
class ConflictEntry:
    """A single entry in a write conflict."""
    tile_id: str
    agent_id: str
    clock: Dict[str, int] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    priority: int = 0


class ConflictResolver:
    """Resolves concurrent writes to the same PLATO room.

    Strategies:
      - 'last-writer-wins': highest timestamp wins
      - 'clock-wins': highest vector clock wins
      - 'priority-wins': highest priority wins
      - 'agent-wins': specific agent always wins
    """

    def __init__(self, strategy: str = "last-writer-wins",
                 favored_agent: Optional[str] = None):
        self.strategy = strategy
        self.favored_agent = favored_agent

    def resolve(self, entries: List[ConflictEntry]) -> ConflictEntry:
        """Resolve conflict among entries. Return the winner."""
        if not entries:
            raise ValueError("Cannot resolve empty conflict")
        if len(entries) == 1:
            return entries[0]

        if self.strategy == "last-writer-wins":
            return max(entries, key=lambda e: e.timestamp)
        elif self.strategy == "clock-wins":
            return self._resolve_by_clock(entries)
        elif self.strategy == "priority-wins":
            return max(entries, key=lambda e: e.priority)
        elif self.strategy == "agent-wins":
            if self.favored_agent:
                favored = [e for e in entries if e.agent_id == self.favored_agent]
                if favored:
                    return favored[0]
            # Fallback to last-writer-wins
            return max(entries, key=lambda e: e.timestamp)
        else:
            raise ValueError(f"Unknown conflict resolution strategy: {self.strategy}")

    def _resolve_by_clock(self, entries: List[ConflictEntry]) -> ConflictEntry:
        """Resolve by vector clock — pick the entry with the highest total clock sum."""
        def clock_sum(entry: ConflictEntry) -> int:
            return sum(entry.clock.values()) if entry.clock else 0
        return max(entries, key=clock_sum)

    def resolve_all(self, conflicts: Dict[str, List[ConflictEntry]]) -> Dict[str, ConflictEntry]:
        """Resolve multiple room conflicts at once. Returns room_id -> winner."""
        return {room_id: self.resolve(room_entries)
                for room_id, room_entries in conflicts.items()}
