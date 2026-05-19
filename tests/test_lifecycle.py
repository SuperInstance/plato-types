"""Tests for enhanced tile lifecycle system."""

import pytest
import time as _time
from plato_types.tile_lifecycle import (
    DeprecationNotice, LineageNode, LineageTracker,
    ConflictEntry, ConflictResolver,
)
from plato_types.types import TileLifecycle


class TestDeprecationNotice:
    def test_defaults(self):
        dn = DeprecationNotice(tile_id="t1")
        assert dn.grace_seconds == 3600.0
        assert dn.reason == ""
        assert dn.superseded_by == ""

    def test_expires_at(self):
        dn = DeprecationNotice(tile_id="t1", created_at=1000.0, grace_seconds=60.0)
        assert dn.expires_at == 1060.0

    def test_is_expired_false(self):
        dn = DeprecationNotice(tile_id="t1", created_at=_time.time(), grace_seconds=3600.0)
        assert not dn.is_expired()

    def test_is_expired_true(self):
        dn = DeprecationNotice(tile_id="t1", created_at=1000.0, grace_seconds=1.0)
        assert dn.is_expired(now=2000.0)

    def test_is_active(self):
        dn = DeprecationNotice(tile_id="t1", created_at=_time.time(), grace_seconds=3600.0)
        assert dn.is_active()

    def test_remaining_seconds(self):
        dn = DeprecationNotice(tile_id="t1", created_at=1000.0, grace_seconds=100.0)
        assert dn.remaining_seconds(now=1050.0) == 50.0
        assert dn.remaining_seconds(now=2000.0) == 0.0

    def test_roundtrip(self):
        dn = DeprecationNotice(
            tile_id="t1", reason="deprecated model",
            grace_seconds=120.0, superseded_by="t2"
        )
        d = dn.to_dict()
        dn2 = DeprecationNotice.from_dict(d)
        assert dn2.tile_id == "t1"
        assert dn2.reason == "deprecated model"
        assert dn2.grace_seconds == 120.0
        assert dn2.superseded_by == "t2"


class TestLineageTracker:
    def test_register_and_lineage(self):
        lt = LineageTracker()
        lt.register("v1")
        lineage = lt.lineage("v1")
        assert len(lineage) == 1
        assert lineage[0].tile_id == "v1"

    def test_supersede_chain(self):
        lt = LineageTracker()
        lt.register("v1")
        lt.record_supersede("v1", "v2", "better accuracy")
        lt.record_supersede("v2", "v3", "faster inference")

        lineage = lt.lineage("v3")
        assert [n.tile_id for n in lineage] == ["v1", "v2", "v3"]

    def test_root(self):
        lt = LineageTracker()
        lt.register("v1")
        lt.record_supersede("v1", "v2")
        lt.record_supersede("v2", "v3")
        assert lt.root("v3") == "v1"
        assert lt.root("v2") == "v1"
        assert lt.root("v1") == "v1"

    def test_latest(self):
        lt = LineageTracker()
        lt.register("v1")
        lt.record_supersede("v1", "v2")
        lt.record_supersede("v2", "v3")
        assert lt.latest("v1") == "v3"
        assert lt.latest("v2") == "v3"
        assert lt.latest("v3") == "v3"

    def test_chain_length(self):
        lt = LineageTracker()
        lt.register("v1")
        lt.record_supersede("v1", "v2")
        lt.record_supersede("v2", "v3")
        assert lt.chain_length("v3") == 3
        assert lt.chain_length("v1") == 3

    def test_is_ancestor(self):
        lt = LineageTracker()
        lt.register("v1")
        lt.record_supersede("v1", "v2")
        lt.record_supersede("v2", "v3")
        assert lt.is_ancestor("v1", "v3")
        assert lt.is_ancestor("v2", "v3")
        assert not lt.is_ancestor("v3", "v1")

    def test_successors(self):
        lt = LineageTracker()
        lt.register("v1")
        lt.record_supersede("v1", "v2")
        assert lt.successors("v1") == ["v2"]
        assert lt.successors("v2") == []

    def test_all_roots(self):
        lt = LineageTracker()
        lt.register("a1")
        lt.record_supersede("a1", "a2")
        lt.register("b1")
        roots = lt.all_roots()
        assert "a1" in roots
        assert "b1" in roots
        assert "a2" not in roots

    def test_auto_register_on_supersede(self):
        lt = LineageTracker()
        lt.record_supersede("v1", "v2", "auto-registered")
        assert lt.chain_length("v2") == 2
        assert lt.root("v2") == "v1"

    def test_superseded_state(self):
        lt = LineageTracker()
        lt.register("v1", TileLifecycle.ACTIVE)
        lt.record_supersede("v1", "v2")
        assert lt._nodes["v1"].state == TileLifecycle.SUPERSEDED
        assert lt._nodes["v2"].state == TileLifecycle.ACTIVE


class TestConflictResolver:
    def test_last_writer_wins(self):
        cr = ConflictResolver(strategy="last-writer-wins")
        entries = [
            ConflictEntry(tile_id="t1", agent_id="a", timestamp=100.0),
            ConflictEntry(tile_id="t2", agent_id="b", timestamp=200.0),
        ]
        winner = cr.resolve(entries)
        assert winner.tile_id == "t2"

    def test_priority_wins(self):
        cr = ConflictResolver(strategy="priority-wins")
        entries = [
            ConflictEntry(tile_id="t1", agent_id="a", priority=5),
            ConflictEntry(tile_id="t2", agent_id="b", priority=10),
        ]
        winner = cr.resolve(entries)
        assert winner.tile_id == "t2"

    def test_agent_wins(self):
        cr = ConflictResolver(strategy="agent-wins", favored_agent="oracle")
        entries = [
            ConflictEntry(tile_id="t1", agent_id="forgemaster", timestamp=100.0),
            ConflictEntry(tile_id="t2", agent_id="oracle", timestamp=50.0),
        ]
        winner = cr.resolve(entries)
        assert winner.agent_id == "oracle"

    def test_agent_wins_fallback(self):
        cr = ConflictResolver(strategy="agent-wins", favored_agent="missing")
        entries = [
            ConflictEntry(tile_id="t1", agent_id="a", timestamp=100.0),
            ConflictEntry(tile_id="t2", agent_id="b", timestamp=200.0),
        ]
        winner = cr.resolve(entries)
        assert winner.tile_id == "t2"  # falls back to last-writer-wins

    def test_clock_wins(self):
        cr = ConflictResolver(strategy="clock-wins")
        entries = [
            ConflictEntry(tile_id="t1", agent_id="a", clock={"a": 1, "b": 1}),
            ConflictEntry(tile_id="t2", agent_id="b", clock={"a": 3, "b": 3}),
        ]
        winner = cr.resolve(entries)
        assert winner.tile_id == "t2"

    def test_single_entry(self):
        cr = ConflictResolver()
        entries = [ConflictEntry(tile_id="only", agent_id="a")]
        assert cr.resolve(entries).tile_id == "only"

    def test_empty_raises(self):
        cr = ConflictResolver()
        with pytest.raises(ValueError):
            cr.resolve([])

    def test_resolve_all(self):
        cr = ConflictResolver(strategy="last-writer-wins")
        conflicts = {
            "room1": [
                ConflictEntry(tile_id="r1a", agent_id="a", timestamp=100.0),
                ConflictEntry(tile_id="r1b", agent_id="b", timestamp=200.0),
            ],
            "room2": [
                ConflictEntry(tile_id="r2a", agent_id="a", timestamp=300.0),
                ConflictEntry(tile_id="r2b", agent_id="b", timestamp=200.0),
            ],
        }
        results = cr.resolve_all(conflicts)
        assert results["room1"].tile_id == "r1b"
        assert results["room2"].tile_id == "r2a"

    def test_unknown_strategy_raises(self):
        cr = ConflictResolver(strategy="bogus")
        entries = [ConflictEntry(tile_id="t1", agent_id="a"),
                   ConflictEntry(tile_id="t2", agent_id="b")]
        with pytest.raises(ValueError, match="Unknown conflict resolution strategy"):
            cr.resolve(entries)
