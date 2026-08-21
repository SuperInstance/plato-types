# plato-types

Core types for the PLATO tile protocol. Zero dependencies, pure Python.

Every service, agent, and tool in the Cocapn fleet imports from this package. It defines the shared vocabulary — tile lifecycles, causal clocks, content addressing, training configurations — that makes PLATO work.

## What's Here

| Type | Purpose |
|------|---------|
| `TileLifecycle` | Enum: `ACTIVE` → `SUPERSEDED` → `RETRACTED` |
| `TileType` | Enum: `DATASET`, `CHECKPOINT`, `ADAPTER`, `METRICS`, `EVALUATION`, `PREDICTION` |
| `LamportClock` | Causal ordering across distributed agents |
| `TrainingTile` | Training artifact with full provenance chain |
| `AdapterConfig` | LoRA-style adapter hyperparameters |
| `TrainingConfig` | Training loop configuration |
| `TrainingMetrics` | Loss, accuracy, memory, timing |
| `LifecycleEvent` | Provenance record for state transitions |
| `content_hash()` | SHA-256 content addressing (truncated to 16 hex chars) |

## Install

```bash
pip install plato-types
```

Requires Python 3.9+. No external dependencies.

## Usage

### Tile lifecycle

```python
from plato_types import TileLifecycle, TrainingTile, content_hash, TileType

tile = TrainingTile(
    tile_id="t1",
    room="my-room",
    tile_type=TileType.ADAPTER,
    state=TileLifecycle.ACTIVE,
    lamport=1,
    name="my-adapter",
    description="Fine-tuned adapter for code generation",
    content_hash=content_hash(b"model weights here"),
)

assert tile.is_active()

# Supersede with a new tile
tile2 = TrainingTile(
    tile_id="t2", room="my-room", tile_type=TileType.ADAPTER,
    state=TileLifecycle.ACTIVE, lamport=2,
    name="my-adapter-v2", description="Improved adapter",
    content_hash=content_hash(b"updated weights"),
)
tile.supersede(tile2, reason="better validation loss")
assert tile.state == TileLifecycle.SUPERSEDED
assert tile2.parent_tile == "t1"

# Retract a bad tile
tile2.retract(reason="data contamination")
assert tile2.state == TileLifecycle.RETRACTED

# Inspect lifecycle history
for event in tile.history():
    print(f"{event['from']} → {event['to']}: {event['reason']}")
```

### Lamport clock

```python
from plato_types import LamportClock

clock = LamportClock()
t1 = clock.tick()  # 1
t2 = clock.tick()  # 2

# Merge with a remote clock (e.g., from another agent)
clock.merge(5)  # max(2, 5) + 1 = 6
assert clock.now() == 6
```

### Content addressing

```python
from plato_types import content_hash

h = content_hash(b"some data")
assert len(h) == 16  # truncated SHA-256 hex
assert h == content_hash(b"some data")  # deterministic
```

### Serialization

```python
# Serialize to dict (JSON-safe)
d = tile.to_dict()

# Deserialize back
restored = TrainingTile.from_dict(d)
assert restored.tile_id == tile.tile_id
```

### Training configurations

```python
from plato_types import AdapterConfig, TrainingConfig, TrainingMetrics

adapter = AdapterConfig(rank=16, alpha=32, target_modules=["W_query", "W_value", "W_output"])
training = TrainingConfig(learning_rate=1e-4, epochs=5, batch_size=16)
metrics = TrainingMetrics(train_loss=0.42, val_loss=0.38, epochs_completed=5)
```

## API Reference

### `TileLifecycle`

```python
class TileLifecycle(Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
```

### `TileType`

```python
class TileType(Enum):
    DATASET = "dataset"
    CHECKPOINT = "checkpoint"
    ADAPTER = "adapter"
    METRICS = "metrics"
    EVALUATION = "evaluation"
    PREDICTION = "prediction"
```

### `LamportClock`

| Method | Returns | Description |
|--------|---------|-------------|
| `tick()` | `int` | Increment and return new time |
| `merge(remote)` | `int` | Merge with remote clock: `max(local, remote) + 1` |
| `now()` | `int` | Current time without incrementing |

### `TrainingTile`

| Method | Description |
|--------|-------------|
| `transition(new_state, reason, lamport)` | Record a lifecycle transition |
| `supersede(successor, reason)` | Mark as superseded, link successor |
| `retract(reason)` | Mark as retracted |
| `is_active()` | `True` if state is `ACTIVE` |
| `history()` | List of `{from, to, reason, lamport}` dicts |
| `summary()` | Human-readable one-liner |
| `to_dict()` | Serialize to JSON-safe dict |
| `from_dict(d)` | Deserialize from dict |

### `content_hash(data: bytes) -> str`

Returns first 16 hex characters of SHA-256 hash.

## Project Structure

```
plato_types/
├── __init__.py       # Public API, version
├── types.py          # All types and functions
└── tests/
    └── test_types.py # Full test suite
```

## Used By

- `fleet-health-monitor` — PLATO server, conductor, tile scorer
- `constraint-inference` — PLATO bridge, lifecycle tiles
- `agent-field` — room coordination
- `plato-training` — micro model training rooms
- `plato-sdk` — PLATO server client
- `folding-order` — anomaly detection

## License

MIT
