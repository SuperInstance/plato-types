"""
plato-types — Core types for the PLATO tile protocol.

Used across the fleet by every agent and service.

Types:
  - TileLifecycle: Active / Superseded / Retracted
  - LamportClock: Scalar causal ordering (legacy)
  - VectorClock: Per-agent vector clocks
  - CausalOrder: Happens-before relationships
  - ConcurrentDetector: Find concurrent events
  - ClockSync: Distributed clock synchronization
  - DeprecationNotice: Grace-period tile deprecation
  - LineageTracker: Tile evolution chains
  - ConflictResolver: Concurrent write resolution
  - TrainingTile: Training artifact with provenance
  - content_hash: SHA-256 content addressing
"""

from .types import (
    TileType, TileLifecycle,
    LamportClock, TrainingTile, TrainingMetrics,
    AdapterConfig, TrainingConfig,
    LifecycleEvent,
    content_hash,
)

from .lamport import (
    VectorClock,
    CausalOrder,
    ConcurrentDetector,
    ClockSync,
    ClockEntry,
)

from .tile_lifecycle import (
    DeprecationNotice,
    LineageNode,
    LineageTracker,
    ConflictEntry,
    ConflictResolver,
)

__version__ = "1.1.0"
