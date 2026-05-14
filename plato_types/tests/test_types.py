"""Tests for plato-types — core protocol types."""

import pytest
from plato_types.types import (
    TileType, TileLifecycle,
    LamportClock, TrainingTile, TrainingMetrics,
    LifecycleEvent,
    content_hash,
)


class TestTileLifecycle:
    def test_active(self):
        t = TrainingTile(
            tile_id="t1", room="test", tile_type=TileType.ADAPTER,
            state=TileLifecycle.ACTIVE, lamport=1,
            name="test", description="test tile",
            content_hash=content_hash(b"data"),
        )
        assert t.is_active()

    def test_supersede(self):
        t1 = TrainingTile(
            tile_id="t1", room="test", tile_type=TileType.ADAPTER,
            state=TileLifecycle.ACTIVE, lamport=1,
            name="test", description="test tile",
            content_hash=content_hash(b"data"),
        )
        t2 = TrainingTile(
            tile_id="t2", room="test", tile_type=TileType.ADAPTER,
            state=TileLifecycle.ACTIVE, lamport=2,
            name="test2", description="replacement",
            content_hash=content_hash(b"data2"),
        )
        t1.supersede(t2, reason="better model")
        assert t1.state == TileLifecycle.SUPERSEDED

    def test_retract(self):
        t = TrainingTile(
            tile_id="t1", room="test", tile_type=TileType.ADAPTER,
            state=TileLifecycle.ACTIVE, lamport=1,
            name="test", description="test tile",
            content_hash=content_hash(b"data"),
        )
        t.retract(reason="bad data")
        assert t.state == TileLifecycle.RETRACTED

    def test_lifecycle_events_tracked(self):
        t1 = TrainingTile(
            tile_id="t1", room="test", tile_type=TileType.ADAPTER,
            state=TileLifecycle.ACTIVE, lamport=1,
            name="test", description="test tile",
            content_hash=content_hash(b"data"),
        )
        t2 = TrainingTile(
            tile_id="t2", room="test", tile_type=TileType.ADAPTER,
            state=TileLifecycle.ACTIVE, lamport=2,
            name="test2", description="replacement",
            content_hash=content_hash(b"data2"),
        )
        t1.supersede(t2)
        assert len(t1.lifecycle_events) >= 1


class TestLamportClock:
    def test_tick_increments(self):
        c = LamportClock()
        assert c.tick() == 1
        assert c.tick() == 2

    def test_merge(self):
        c = LamportClock()
        c.tick()
        c.tick()  # time = 2
        c.merge(5)  # remote has 5
        assert c.time > 5  # should be max(2,5)+1 = 6

    def test_now(self):
        c = LamportClock()
        c.tick()
        c.tick()
        assert c.now() == 2


class TestContentHash:
    def test_deterministic(self):
        h1 = content_hash(b"hello")
        h2 = content_hash(b"hello")
        assert h1 == h2

    def test_different_data(self):
        h1 = content_hash(b"hello")
        h2 = content_hash(b"world")
        assert h1 != h2

    def test_length(self):
        h = content_hash(b"test")
        assert len(h) == 16  # truncated SHA-256
