"""
plato-types — Core types for the PLATO tile protocol.

Used across the fleet by every agent and service.

Types:
  - TileLifecycle: Active / Superseded / Retracted
  - LamportClock: Causal ordering across agents
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

__version__ = "1.0.0"
