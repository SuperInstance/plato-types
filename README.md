# plato-types

Core types for the PLATO tile protocol. Used across the fleet.

## What's Here

- **TileLifecycle**: Active → Superseded → Retracted
- **LamportClock**: Causal ordering across distributed agents
- **TrainingTile**: Training artifact with full provenance chain
- **content_hash**: SHA-256 content addressing for tiles
- **AdapterConfig / TrainingConfig**: ML training configuration types

## Install

```bash
pip install plato-types
```

## Usage

```python
from plato_types import TileLifecycle, LamportClock, TrainingTile, content_hash

# Lifecycle
tile = TrainingTile(tile_id="t1", room="my-room", lifecycle=TileLifecycle.ACTIVE)
assert tile.is_active()

# Lamport clock for causal ordering
clock = LamportClock()
t1 = clock.tick()  # 1
t2 = clock.tick()  # 2

# Content addressing
h = content_hash(b"my data")
assert len(h) == 64  # SHA-256 hex
```

## Zero Dependencies

Pure Python. No external packages required. This is the foundation — everything else builds on it.

## Used By

- `plato-training` — micro model training rooms
- `plato-sdk` — PLATO server client
- `fleet-memory` — distributed memory with lifecycle
- `folding-order` — anomaly detection
- `flux-lucid` — intent alignment
- `dodecet-encoder` — agent lifecycle
