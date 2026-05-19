"""
Enhanced Lamport clock system for PLATO distributed agents.

Provides:
  - VectorClock: per-agent logical clocks for causal ordering
  - CausalOrder: determines happens-before relationships
  - ConcurrentDetector: finds tiles with no causal relation
  - ClockSync: lightweight clock synchronization across agents
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class VectorClock:
    """Vector clock with per-agent counters.

    Each agent maintains its own counter. Ticks increment the local counter.
    Merge takes the element-wise max with another clock.
    """

    agent_id: str
    counters: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.agent_id not in self.counters:
            self.counters[self.agent_id] = 0

    def tick(self) -> Dict[str, int]:
        """Increment local counter and return the new state."""
        self.counters[self.agent_id] = self.counters.get(self.agent_id, 0) + 1
        return dict(self.counters)

    def merge(self, other: Dict[str, int]) -> Dict[str, int]:
        """Merge with another vector clock (element-wise max), then tick local."""
        all_keys = set(self.counters.keys()) | set(other.keys())
        for key in all_keys:
            self.counters[key] = max(self.counters.get(key, 0), other.get(key, 0))
        # Tick local after merge
        self.counters[self.agent_id] = self.counters.get(self.agent_id, 0) + 1
        return dict(self.counters)

    def now(self) -> Dict[str, int]:
        """Return current clock state as a copy."""
        return dict(self.counters)

    def __le__(self, other: Dict[str, int]) -> bool:
        """True if every counter in self <= corresponding counter in other."""
        all_keys = set(self.counters.keys()) | set(other.keys())
        return all(self.counters.get(k, 0) <= other.get(k, 0) for k in all_keys)

    def __lt__(self, other: Dict[str, int]) -> bool:
        """True if self <= other and at least one counter is strictly less."""
        return self <= other and self.counters != other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, dict):
            return NotImplemented
        all_keys = set(self.counters.keys()) | set(other.keys())
        return all(self.counters.get(k, 0) == other.get(k, 0) for k in all_keys)

    def to_dict(self) -> Dict[str, int]:
        return dict(self.counters)

    @classmethod
    def from_dict(cls, d: Dict[str, int], agent_id: str) -> "VectorClock":
        vc = cls(agent_id=agent_id, counters=dict(d))
        return vc


class CausalOrder:
    """Determines causal (happens-before) relationships between vector clocks.

    A happened-before B iff A < B (every element <= and at least one <).
    Concurrent means neither A <= B nor B <= A.
    """

    @staticmethod
    def happens_before(a: Dict[str, int], b: Dict[str, int]) -> bool:
        """Return True if event a happened before event b."""
        all_keys = set(a.keys()) | set(b.keys())
        le = all(a.get(k, 0) <= b.get(k, 0) for k in all_keys)
        if not le:
            return False
        # At least one strictly less
        return any(a.get(k, 0) < b.get(k, 0) for k in all_keys)

    @staticmethod
    def is_concurrent(a: Dict[str, int], b: Dict[str, int]) -> bool:
        """Return True if a and b are concurrent (no causal relation).

        Equal clocks are NOT concurrent — they represent the same event.
        """
        if CausalOrder.are_equal(a, b):
            return False
        return not CausalOrder.happens_before(a, b) and not CausalOrder.happens_before(b, a)

    @staticmethod
    def are_equal(a: Dict[str, int], b: Dict[str, int]) -> bool:
        all_keys = set(a.keys()) | set(b.keys())
        return all(a.get(k, 0) == b.get(k, 0) for k in all_keys)


class ConcurrentDetector:
    """Finds tiles/events that happened concurrently (no causal relation).

    Given a list of (id, vector_clock) pairs, groups them into
    concurrent clusters — sets of events with no causal ordering between them.
    """

    @staticmethod
    def find_concurrent_pairs(
        events: List[Tuple[str, Dict[str, int]]]
    ) -> List[Tuple[str, str]]:
        """Return all pairs of event IDs that are concurrent."""
        pairs = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                id_a, clock_a = events[i]
                id_b, clock_b = events[j]
                if CausalOrder.is_concurrent(clock_a, clock_b):
                    pairs.append((id_a, id_b))
        return pairs

    @staticmethod
    def find_concurrent_groups(
        events: List[Tuple[str, Dict[str, int]]]
    ) -> List[Set[str]]:
        """Group events into maximal concurrent clusters.

        Two events are in the same group if they are transitively concurrent
        (connected via concurrent pairs).
        """
        if not events:
            return []

        # Build adjacency for concurrent events
        concurrent_pairs = ConcurrentDetector.find_concurrent_pairs(events)
        adj: Dict[str, Set[str]] = {eid: set() for eid, _ in events}
        for a, b in concurrent_pairs:
            adj[a].add(b)
            adj[b].add(a)

        # BFS to find connected components
        visited: Set[str] = set()
        groups: List[Set[str]] = []
        for eid, _ in events:
            if eid not in visited:
                group: Set[str] = set()
                queue = [eid]
                while queue:
                    node = queue.pop(0)
                    if node in visited:
                        continue
                    visited.add(node)
                    group.add(node)
                    for neighbor in adj[node]:
                        if neighbor not in visited:
                            queue.append(neighbor)
                if len(group) > 1:
                    groups.append(group)
        return groups

    @staticmethod
    def causal_chain(
        events: List[Tuple[str, Dict[str, int]]]
    ) -> List[str]:
        """Return event IDs sorted in causal order (topological by happens-before).

        Breaks ties deterministically by ID string order."""
        # Simple topological sort using happens-before
        event_dict = {eid: clock for eid, clock in events}
        ids = list(event_dict.keys())

        # Build DAG: edge from a -> b if a happens_before b
        edges: Dict[str, Set[str]] = {eid: set() for eid in ids}
        in_degree: Dict[str, int] = {eid: 0 for eid in ids}
        for i, id_a in enumerate(ids):
            for id_b in ids:
                if id_a != id_b and CausalOrder.happens_before(event_dict[id_a], event_dict[id_b]):
                    edges[id_a].add(id_b)
                    in_degree[id_b] += 1

        # Kahn's algorithm
        queue = sorted([eid for eid in ids if in_degree[eid] == 0])
        result = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in sorted(edges[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()
        return result


@dataclass
class ClockEntry:
    """A snapshot of a remote agent's clock with metadata."""
    agent_id: str
    counters: Dict[str, int]
    wall_time: float = field(default_factory=time.time)


class ClockSync:
    """Lightweight clock synchronization for distributed PLATO agents.

    Tracks the latest known vector clock from each agent and provides
    a merged global view.
    """

    def __init__(self, local_agent_id: str):
        self.local_agent_id = local_agent_id
        self.local_clock = VectorClock(agent_id=local_agent_id)
        self.remote_snapshots: Dict[str, ClockEntry] = {}

    def tick(self) -> Dict[str, int]:
        """Local event — tick local clock."""
        return self.local_clock.tick()

    def receive(self, remote_agent_id: str, remote_clock: Dict[str, int]) -> Dict[str, int]:
        """Receive a remote clock. Merge into local and update snapshot."""
        self.remote_snapshots[remote_agent_id] = ClockEntry(
            agent_id=remote_agent_id,
            counters=dict(remote_clock),
        )
        return self.local_clock.merge(remote_clock)

    def global_clock(self) -> Dict[str, int]:
        """Return the merged global view: element-wise max across all known clocks."""
        result = dict(self.local_clock.counters)
        for entry in self.remote_snapshots.values():
            for key, val in entry.counters.items():
                result[key] = max(result.get(key, 0), val)
        return result

    def known_agents(self) -> Set[str]:
        """Return set of all known agent IDs."""
        agents = {self.local_agent_id}
        agents.update(self.remote_snapshots.keys())
        # Also include any agent IDs seen in clock counters
        for entry in self.remote_snapshots.values():
            agents.update(entry.counters.keys())
        agents.update(self.local_clock.counters.keys())
        return agents

    def is_up_to_date(self, agent_id: str, clock: Dict[str, int]) -> bool:
        """Check if the given clock from agent_id is not outdated vs our snapshot."""
        if agent_id not in self.remote_snapshots:
            return True  # Never seen this agent — it's new, not outdated
        snap = self.remote_snapshots[agent_id].counters
        # Clock is up-to-date if its local counter >= our snapshot's
        return clock.get(agent_id, 0) >= snap.get(agent_id, 0)

    def skew(self) -> Dict[str, int]:
        """Return the skew between local clock and each remote's local counter."""
        local_now = self.local_clock.now()
        result = {}
        for agent_id, entry in self.remote_snapshots.items():
            their_local = entry.counters.get(agent_id, 0)
            our_view = local_now.get(agent_id, 0)
            result[agent_id] = our_view - their_local
        return result
