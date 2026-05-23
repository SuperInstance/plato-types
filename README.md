# plato-types

Core types for the PLATO tile protocol. Pure Python, zero dependencies. Everything in the PLATO ecosystem uses these types.

## Install

```bash
pip install plato-types
```

## Quick Start

```python
from plato_types import TileLifecycle, LamportClock, TrainingTile, content_hash

# Tile lifecycle: Active → Superseded → Retracted
tile = TrainingTile(
    tile_id="t1",
    room="my-room",
    lifecycle=TileLifecycle.ACTIVE,
)
assert tile.is_active()

# Lamport clock — causal ordering across distributed rooms
clock = LamportClock()
t1 = clock.tick()  # 1
t2 = clock.tick()  # 2

# Content addressing (SHA-256)
h = content_hash(b"my weights data")
assert len(h) == 64  # hex-encoded SHA-256
```

## Key Concepts

### Tile Lifecycle

Every tile goes through three states:

- **Active** — the tile is current and in use
- **Superseded** — a newer tile has replaced this one (it's still valid, just not latest)
- **Retracted** — the tile was withdrawn (treated as if it never existed)

This is a log-structured model. You never mutate a tile — you supersede it. This gives you a full provenance chain.

### Lamport Clocks

Distributed systems need ordering without a central clock. Lamport clocks solve this:

- Each room maintains a counter
- When sending a tile, increment and attach the counter
- When receiving, merge: `clock = max(local, received) + 1`

The result: a partial order that preserves causality. You can always tell if tile A "happened before" tile B.

### Content Hashing

Every tile is content-addressed with SHA-256. Two tiles with the same content produce the same hash. This enables deduplication, integrity checking, and content-based routing.

### Procedure Tiles

Procedure tiles encode executable procedures (not just data). They carry a sequence of steps that can be replayed or verified:

```python
from plato_types import ProcedureTile

proc = ProcedureTile(
    tile_id="proc-001",
    room="training",
    steps=[
        {"action": "train", "config": {"lr": 0.001}},
        {"action": "evaluate", "metrics": ["accuracy"]},
    ],
)
```

## What's Provided

| Type | Purpose |
|------|---------|
| `TrainingTile` | Training artifact with full provenance |
| `ProcedureTile` | Executable procedure (sequence of steps) |
| `TileLifecycle` | Active / Superseded / Retracted enum |
| `LamportClock` | Distributed causal ordering |
| `content_hash()` | SHA-256 content addressing |
| `AdapterConfig` | LoRA adapter configuration |
| `TrainingConfig` | Training run configuration |
| `TrainingMetrics` | Training result metrics |

## Used By

- `plato-core` — re-exports these types for the mesh ecosystem
- `plato-training` — training rooms and micro models
- `plato-mcp` — MCP tool interface
- `plato-sdk` — PLATO server client
- `fleet-memory` — distributed memory with lifecycle
- `dodecet-encoder` — agent lifecycle encoding

## Related Repos

- **plato-core** — mesh registry (depends on this package)
- **plato-training** — training pipeline that produces tiles
- **plato-mcp** — exposes tiles via MCP
