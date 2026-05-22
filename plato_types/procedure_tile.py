"""
ProcedureTile — Tiles that ARE executable procedures.

Inspired by medical protocols and military SOPs: a tile encodes
the accumulated intelligence of many executions into a repeatable
procedure that any competent model can follow.

Types:
  - ProcedureTile: a tile that IS a procedure
  - ProcedureStep: one step in a procedure
  - DecisionBranch: conditional branching within a step
  - ProcedureExecutor: executes a ProcedureTile
  - ProcedureRefiner: refines procedures based on outcomes
  - ProcedureLibrary: indexed collection of procedures
"""

from __future__ import annotations
import json
import hashlib
import time
import copy
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Tuple

from .types import content_hash


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

class ProcedureStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class StepOutcome(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    BRANCHED = "branched"
    ROLLED_BACK = "rolled_back"


@dataclass
class DecisionBranch:
    """Conditional branch: if condition evaluates truthy, jump to target step."""
    condition: str  # expression or key to check in context
    target_step: int  # 0-based index to jump to


@dataclass
class ProcedureStep:
    """One step in a procedure."""
    description: str
    code: str  # source code (Python) or a callable label
    decision_tree: List[DecisionBranch] = field(default_factory=list)
    rollback: str = ""  # rollback code/description if this step fails
    timeout_seconds: float = 0.0  # 0 = no timeout

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "code": self.code,
            "decision_tree": [
                {"condition": b.condition, "target_step": b.target_step}
                for b in self.decision_tree
            ],
            "rollback": self.rollback,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ProcedureStep:
        branches = [
            DecisionBranch(condition=b["condition"], target_step=b["target_step"])
            for b in d.get("decision_tree", [])
        ]
        return cls(
            description=d["description"],
            code=d["code"],
            decision_tree=branches,
            rollback=d.get("rollback", ""),
            timeout_seconds=d.get("timeout_seconds", 0.0),
        )


@dataclass
class Provenance:
    """Who wrote this procedure, when, based on what evidence."""
    author: str
    created_at: float = 0.0  # unix timestamp
    based_on: List[str] = field(default_factory=list)  # tile hashes or refs
    notes: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "author": self.author,
            "created_at": self.created_at,
            "based_on": self.based_on,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Provenance:
        return cls(
            author=d["author"],
            created_at=d.get("created_at", 0.0),
            based_on=d.get("based_on", []),
            notes=d.get("notes", ""),
        )


@dataclass
class Contingency:
    """A failure mode and its recovery procedure."""
    failure_mode: str
    detection: str  # how to detect this failure
    recovery: str  # what to do

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_mode": self.failure_mode,
            "detection": self.detection,
            "recovery": self.recovery,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Contingency:
        return cls(
            failure_mode=d["failure_mode"],
            detection=d["detection"],
            recovery=d["recovery"],
        )


@dataclass
class SemanticVersion:
    """Simple semantic version."""
    major: int = 1
    minor: int = 0
    patch: int = 0

    def bump_patch(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor, self.patch + 1)

    def bump_minor(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_major(self) -> SemanticVersion:
        return SemanticVersion(self.major + 1, 0, 0)

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def to_dict(self) -> Dict[str, Any]:
        return {"major": self.major, "minor": self.minor, "patch": self.patch}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> SemanticVersion:
        return cls(
            major=d.get("major", 1),
            minor=d.get("minor", 0),
            patch=d.get("patch", 0),
        )


# ---------------------------------------------------------------------------
# ProcedureTile — the main tile type
# ---------------------------------------------------------------------------

@dataclass
class ProcedureTile:
    """A tile that IS a procedure: executable intelligence for smaller models."""
    name: str
    domain: str
    pre_conditions: List[str]
    steps: List[ProcedureStep]
    post_conditions: List[str]
    contingencies: List[Contingency] = field(default_factory=list)
    provenance: Optional[Provenance] = None
    version: SemanticVersion = field(default_factory=SemanticVersion)
    parent_hash: Optional[str] = None  # hash of tile this was refined from

    def content_hash(self) -> str:
        """Deterministic SHA-256 of the tile's canonical form."""
        payload = json.dumps(self.to_dict(sort_keys=True), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self, sort_keys: bool = False) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "domain": self.domain,
            "pre_conditions": self.pre_conditions,
            "steps": [s.to_dict() for s in self.steps],
            "post_conditions": self.post_conditions,
            "contingencies": [c.to_dict() for c in self.contingencies],
            "version": self.version.to_dict(),
            "parent_hash": self.parent_hash,
        }
        if self.provenance:
            d["provenance"] = self.provenance.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ProcedureTile:
        return cls(
            name=d["name"],
            domain=d["domain"],
            pre_conditions=d.get("pre_conditions", []),
            steps=[ProcedureStep.from_dict(s) for s in d.get("steps", [])],
            post_conditions=d.get("post_conditions", []),
            contingencies=[Contingency.from_dict(c) for c in d.get("contingencies", [])],
            provenance=Provenance.from_dict(d["provenance"]) if "provenance" in d else None,
            version=SemanticVersion.from_dict(d["version"]) if "version" in d else SemanticVersion(),
            parent_hash=d.get("parent_hash"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> ProcedureTile:
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# Execution result tracking
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """Outcome of a single step execution."""
    step_index: int
    outcome: StepOutcome
    message: str = ""
    duration_seconds: float = 0.0
    branched_to: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "step_index": self.step_index,
            "outcome": self.outcome.value,
            "message": self.message,
            "duration_seconds": self.duration_seconds,
        }
        if self.branched_to is not None:
            d["branched_to"] = self.branched_to
        return d


@dataclass
class ExecutionResult:
    """Full result of executing a ProcedureTile."""
    tile_name: str
    tile_hash: str
    status: ProcedureStatus
    step_results: List[StepResult] = field(default_factory=list)
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str = ""

    @property
    def elapsed_seconds(self) -> float:
        if self.finished_at is not None and self.started_at is not None:
            return self.finished_at - self.started_at
        return 0.0

    @property
    def success(self) -> bool:
        return self.status == ProcedureStatus.COMPLETED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tile_name": self.tile_name,
            "tile_hash": self.tile_hash,
            "status": self.status.value,
            "step_results": [sr.to_dict() for sr in self.step_results],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# ProcedureExecutor — runs a tile's steps
# ---------------------------------------------------------------------------

class ProcedureExecutor:
    """Executes a ProcedureTile against a context dict.

    Steps are executed in order. Each step's ``code`` is interpreted:
      - If the context contains a callable under the key ``_executors[step.code]``,
        that callable is invoked with (context).
      - Otherwise, ``code`` is exec'd in a sandboxed namespace with ``context``
        available as ``ctx``.
    """

    def __init__(self, callable_registry: Optional[Dict[str, Callable]] = None):
        self._registry: Dict[str, Callable] = callable_registry or {}

    def register(self, name: str, fn: Callable) -> None:
        self._registry[name] = fn

    # -- pre/post condition checking --

    @staticmethod
    def _check_conditions(conditions: List[str], context: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Evaluate conditions as Python expressions with context as 'ctx'."""
        failures: List[str] = []
        eval_ns = {"__builtins__": {}, "ctx": context}
        for cond in conditions:
            try:
                if not eval(cond, eval_ns, context):
                    failures.append(cond)
            except Exception as exc:
                failures.append(f"{cond} (error: {exc})")
        return (len(failures) == 0, failures)

    # -- single step execution --

    def _execute_step(self, step: ProcedureStep, context: Dict[str, Any]) -> StepResult:
        t0 = time.time()
        try:
            # Look up in registry first
            if step.code in self._registry:
                self._registry[step.code](context)
            else:
                # Execute code string in sandboxed namespace
                local_ns: Dict[str, Any] = {"ctx": context}
                exec(step.code, {"__builtins__": {}}, local_ns)
                # Propagate any ctx mutations back
                if "ctx" in local_ns and isinstance(local_ns["ctx"], dict):
                    context.update(local_ns["ctx"])

            # Check decision tree
            branch_ns = {"__builtins__": {}, "ctx": context}
            for branch in step.decision_tree:
                try:
                    if eval(branch.condition, branch_ns, context):
                        elapsed = time.time() - t0
                        return StepResult(
                            step_index=0,  # caller fills in
                            outcome=StepOutcome.BRANCHED,
                            message=f"Branch '{branch.condition}' → step {branch.target_step}",
                            duration_seconds=elapsed,
                            branched_to=branch.target_step,
                        )
                except Exception:
                    continue

            elapsed = time.time() - t0
            return StepResult(
                step_index=0,
                outcome=StepOutcome.SUCCESS,
                duration_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.time() - t0
            return StepResult(
                step_index=0,
                outcome=StepOutcome.FAILURE,
                message=str(exc),
                duration_seconds=elapsed,
            )

    # -- rollback a step --

    def _rollback_step(self, step: ProcedureStep, context: Dict[str, Any]) -> None:
        if not step.rollback:
            return
        if step.rollback in self._registry:
            self._registry[step.rollback](context)
        else:
            local_ns: Dict[str, Any] = {"ctx": context}
            try:
                exec(step.rollback, {"__builtins__": {}}, local_ns)
                if "ctx" in local_ns and isinstance(local_ns["ctx"], dict):
                    context.update(local_ns["ctx"])
            except Exception:
                pass  # best-effort rollback

    # -- main execute --

    def execute(self, tile: ProcedureTile, context: Dict[str, Any]) -> ExecutionResult:
        """Execute a ProcedureTile, returns ExecutionResult."""
        result = ExecutionResult(
            tile_name=tile.name,
            tile_hash=tile.content_hash(),
            status=ProcedureStatus.PENDING,
            started_at=time.time(),
        )

        # Pre-conditions
        ok, failures = self._check_conditions(tile.pre_conditions, context)
        if not ok:
            result.status = ProcedureStatus.FAILED
            result.error = f"Pre-conditions failed: {failures}"
            result.finished_at = time.time()
            return result

        result.status = ProcedureStatus.RUNNING
        executed_steps: List[int] = []  # stack for rollback

        # Execute steps with possible branching
        step_idx = 0
        max_steps = len(tile.steps) * 3  # safety: prevent infinite branch loops
        visited: set = set()

        while step_idx < len(tile.steps):
            if step_idx in visited and max_steps <= 0:
                result.status = ProcedureStatus.FAILED
                result.error = f"Branch loop detected at step {step_idx}"
                break
            visited.add(step_idx)
            max_steps -= 1

            step = tile.steps[step_idx]
            sr = self._execute_step(step, context)
            sr.step_index = step_idx
            result.step_results.append(sr)

            if sr.outcome == StepOutcome.FAILURE:
                # Rollback executed steps in reverse
                result.status = ProcedureStatus.ROLLED_BACK
                result.error = f"Step {step_idx} failed: {sr.message}"
                for prev_idx in reversed(executed_steps):
                    self._rollback_step(tile.steps[prev_idx], context)
                    result.step_results.append(StepResult(
                        step_index=prev_idx,
                        outcome=StepOutcome.ROLLED_BACK,
                        message="rolled back",
                    ))
                break
            elif sr.outcome == StepOutcome.BRANCHED and sr.branched_to is not None:
                executed_steps.append(step_idx)
                step_idx = sr.branched_to
                continue
            else:
                executed_steps.append(step_idx)
                step_idx += 1
        else:
            # All steps completed — check post-conditions
            if result.status != ProcedureStatus.ROLLED_BACK:
                ok, failures = self._check_conditions(tile.post_conditions, context)
                if not ok:
                    result.status = ProcedureStatus.FAILED
                    result.error = f"Post-conditions failed: {failures}"
                    for prev_idx in reversed(executed_steps):
                        self._rollback_step(tile.steps[prev_idx], context)
                else:
                    result.status = ProcedureStatus.COMPLETED

        result.finished_at = time.time()
        return result


# ---------------------------------------------------------------------------
# ProcedureRefiner — refines procedures from execution outcomes
# ---------------------------------------------------------------------------

@dataclass
class RefinementSuggestion:
    """A suggested change to a procedure."""
    step_index: Optional[int]  # None = global change
    field: str  # e.g. "code", "pre_conditions", "rollback"
    current: str
    suggested: str
    reason: str
    priority: str = "low"  # low, medium, high


class ProcedureRefiner:
    """Analyzes execution outcomes and produces refined tile versions."""

    @staticmethod
    def analyze(tile: ProcedureTile, results: List[ExecutionResult]) -> List[RefinementSuggestion]:
        """Analyze a batch of results and produce suggestions."""
        suggestions: List[RefinementSuggestion] = []
        if not results:
            return suggestions

        # Track per-step failure rates
        step_failures: Dict[int, int] = {}
        step_total: Dict[int, int] = {}
        for r in results:
            for sr in r.step_results:
                step_total[sr.step_index] = step_total.get(sr.step_index, 0) + 1
                if sr.outcome == StepOutcome.FAILURE:
                    step_failures[sr.step_index] = step_failures.get(sr.step_index, 0) + 1

        # Suggest rollback improvements for failing steps
        for idx, count in step_failures.items():
            if count > 0 and idx < len(tile.steps):
                step = tile.steps[idx]
                rate = count / step_total[idx]
                if rate > 0.3:
                    priority = "high" if rate > 0.7 else "medium"
                    suggestions.append(RefinementSuggestion(
                        step_index=idx,
                        field="rollback",
                        current=step.rollback or "(none)",
                        suggested=f"Add rollback for step {idx}",
                        reason=f"Step fails {rate:.0%} of the time ({count}/{step_total[idx]})",
                        priority=priority,
                    ))

        # Check for pre-condition failures
        pre_cond_fails = sum(1 for r in results if "Pre-conditions" in r.error)
        if pre_cond_fails > 0:
            rate = pre_cond_fails / len(results)
            suggestions.append(RefinementSuggestion(
                step_index=None,
                field="pre_conditions",
                current=str(tile.pre_conditions),
                suggested="Strengthen or relax pre-conditions",
                reason=f"Pre-conditions failed {rate:.0%} of the time",
                priority="high" if rate > 0.5 else "medium",
            ))

        # Check for post-condition failures
        post_cond_fails = sum(1 for r in results if "Post-conditions" in r.error)
        if post_cond_fails > 0:
            rate = post_cond_fails / len(results)
            suggestions.append(RefinementSuggestion(
                step_index=None,
                field="post_conditions",
                current=str(tile.post_conditions),
                suggested="Review post-conditions for correctness",
                reason=f"Post-conditions failed {rate:.0%} of the time",
                priority="high" if rate > 0.5 else "medium",
            ))

        return suggestions

    @staticmethod
    def refine(
        tile: ProcedureTile,
        results: List[ExecutionResult],
        author: str = "refiner",
        bump: str = "patch",  # patch, minor, major
        extra_steps: Optional[List[ProcedureStep]] = None,
        extra_pre_conditions: Optional[List[str]] = None,
        extra_post_conditions: Optional[List[str]] = None,
    ) -> ProcedureTile:
        """Create a refined version of the tile based on execution outcomes."""
        new = copy.deepcopy(tile)
        new.parent_hash = tile.content_hash()

        # Version bump
        if bump == "major":
            new.version = new.version.bump_major()
        elif bump == "minor":
            new.version = new.version.bump_minor()
        else:
            new.version = new.version.bump_patch()

        # Apply additions
        if extra_steps:
            new.steps.extend(extra_steps)
        if extra_pre_conditions:
            new.pre_conditions = list(set(new.pre_conditions + extra_pre_conditions))
        if extra_post_conditions:
            new.post_conditions = list(set(new.post_conditions + extra_post_conditions))

        # Update provenance
        new.provenance = Provenance(
            author=author,
            based_on=[tile.content_hash()],
            notes=f"Refined from {tile.name} {tile.version} based on {len(results)} executions",
        )

        return new


# ---------------------------------------------------------------------------
# ProcedureLibrary — indexed collection of procedures
# ---------------------------------------------------------------------------

@dataclass
class ProcedureStats:
    """Usage statistics for a procedure."""
    times_executed: int = 0
    times_succeeded: int = 0
    times_failed: int = 0
    total_duration: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.times_succeeded / self.times_executed if self.times_executed else 0.0

    @property
    def avg_duration(self) -> float:
        return self.total_duration / self.times_executed if self.times_executed else 0.0

    def record(self, result: ExecutionResult) -> None:
        self.times_executed += 1
        if result.success:
            self.times_succeeded += 1
        else:
            self.times_failed += 1
        self.total_duration += result.elapsed_seconds


class ProcedureLibrary:
    """Collection of procedures indexed by domain with usage tracking."""

    def __init__(self):
        self._tiles: Dict[str, ProcedureTile] = {}  # hash -> tile
        self._domain_index: Dict[str, List[str]] = {}  # domain -> [hashes]
        self._name_index: Dict[str, str] = {}  # name -> hash
        self._stats: Dict[str, ProcedureStats] = {}  # hash -> stats

    def register(self, tile: ProcedureTile) -> str:
        """Register a tile. Returns its content hash."""
        h = tile.content_hash()
        self._tiles[h] = tile
        self._name_index[tile.name] = h
        self._domain_index.setdefault(tile.domain, []).append(h)
        self._stats.setdefault(h, ProcedureStats())
        return h

    def get(self, name: str) -> Optional[ProcedureTile]:
        """Get a tile by name."""
        h = self._name_index.get(name)
        if h:
            return self._tiles.get(h)
        return self._tiles.get(name)  # try as hash

    def find_by_domain(self, domain: str) -> List[ProcedureTile]:
        """Find all procedures in a domain."""
        hashes = self._domain_index.get(domain, [])
        return [self._tiles[h] for h in hashes if h in self._tiles]

    def find_by_capability(self, query: str) -> List[ProcedureTile]:
        """Search by keyword match in name, domain, step descriptions, pre/post conditions."""
        query_lower = query.lower()
        matches: List[ProcedureTile] = []
        for tile in self._tiles.values():
            searchable = " ".join([
                tile.name, tile.domain,
                *[s.description for s in tile.steps],
                *tile.pre_conditions,
                *tile.post_conditions,
            ]).lower()
            if query_lower in searchable:
                matches.append(tile)
        return matches

    def record_result(self, result: ExecutionResult) -> None:
        """Record an execution result for stats tracking."""
        h = result.tile_hash
        if h not in self._stats:
            self._stats[h] = ProcedureStats()
        self._stats[h].record(result)

    def stats(self, name: str) -> Optional[ProcedureStats]:
        """Get usage stats for a procedure by name."""
        h = self._name_index.get(name, name)
        return self._stats.get(h)

    def list_domains(self) -> List[str]:
        """List all registered domains."""
        return list(self._domain_index.keys())

    def all_procedures(self) -> List[ProcedureTile]:
        """Return all registered procedures."""
        return list(self._tiles.values())

    def latest_version(self, name: str) -> Optional[ProcedureTile]:
        """Get the latest version of a named procedure (highest version)."""
        tiles = [t for t in self._tiles.values() if t.name == name]
        if not tiles:
            return None
        return max(tiles, key=lambda t: t.version)
