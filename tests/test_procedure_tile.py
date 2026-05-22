"""Tests for ProcedureTile, ProcedureExecutor, ProcedureRefiner, ProcedureLibrary."""

import pytest
import json
import time
from plato_types.procedure_tile import (
    ProcedureTile,
    ProcedureStep,
    DecisionBranch,
    Provenance,
    Contingency,
    SemanticVersion,
    ProcedureExecutor,
    ExecutionResult,
    StepOutcome,
    ProcedureStatus,
    ProcedureRefiner,
    RefinementSuggestion,
    ProcedureLibrary,
    ProcedureStats,
)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def make_simple_tile(name="add_numbers", domain="math"):
    """A tile that adds two numbers stored in context."""
    return ProcedureTile(
        name=name,
        domain=domain,
        pre_conditions=["'x' in ctx", "'y' in ctx"],
        steps=[
            ProcedureStep(
                description="Add x and y, store in result",
                code="ctx['result'] = ctx['x'] + ctx['y']",
            ),
        ],
        post_conditions=["ctx.get('result') is not None"],
        provenance=Provenance(author="test"),
    )


def make_branching_tile():
    """A tile with decision-tree branching."""
    return ProcedureTile(
        name="classify_number",
        domain="math",
        pre_conditions=["'value' in ctx"],
        steps=[
            ProcedureStep(
                description="Check if positive",
                code="ctx['positive'] = ctx['value'] > 0",
                decision_tree=[
                    DecisionBranch(condition="ctx['value'] < 0", target_step=2),
                ],
            ),
            ProcedureStep(
                description="Mark as positive result",
                code="ctx['classification'] = 'positive'",
                decision_tree=[
                    DecisionBranch(condition="True", target_step=3),  # skip to end
                ],
            ),
            ProcedureStep(
                description="Mark as negative result",
                code="ctx['classification'] = 'negative'",
            ),
        ],
        post_conditions=["'classification' in ctx"],
        provenance=Provenance(author="test"),
    )


def make_rollback_tile():
    """A tile with a failing step and rollback."""
    return ProcedureTile(
        name="multi_step_with_failure",
        domain="test",
        pre_conditions=[],
        steps=[
            ProcedureStep(
                description="Step 1: set a",
                code="ctx['a'] = 1",
                rollback="ctx.pop('a', None)",
            ),
            ProcedureStep(
                description="Step 2: set b then fail",
                code="raise ValueError('intentional')",
                rollback="ctx.pop('b', None)",
            ),
            ProcedureStep(
                description="Step 3: set c (should not reach)",
                code="ctx['c'] = 3",
            ),
        ],
        post_conditions=[],
    )


# ===========================================================================
# SemanticVersion
# ===========================================================================

class TestSemanticVersion:

    def test_default(self):
        v = SemanticVersion()
        assert str(v) == "v1.0.0"

    def test_bump_patch(self):
        v = SemanticVersion(1, 2, 3)
        assert str(v.bump_patch()) == "v1.2.4"

    def test_bump_minor(self):
        v = SemanticVersion(1, 2, 3)
        assert str(v.bump_minor()) == "v1.3.0"

    def test_bump_major(self):
        v = SemanticVersion(1, 2, 3)
        assert str(v.bump_major()) == "v2.0.0"

    def test_equality(self):
        assert SemanticVersion(1, 0, 0) == SemanticVersion(1, 0, 0)

    def test_ordering(self):
        assert SemanticVersion(1, 0, 0) < SemanticVersion(2, 0, 0)
        assert SemanticVersion(1, 0, 0) < SemanticVersion(1, 1, 0)
        assert SemanticVersion(1, 0, 0) < SemanticVersion(1, 0, 1)

    def test_roundtrip_dict(self):
        v = SemanticVersion(2, 3, 4)
        assert SemanticVersion.from_dict(v.to_dict()) == v


# ===========================================================================
# ProcedureStep serialization
# ===========================================================================

class TestProcedureStep:

    def test_to_dict_roundtrip(self):
        step = ProcedureStep(
            description="Do the thing",
            code="ctx['done'] = True",
            decision_tree=[DecisionBranch("ctx.get('skip')", 5)],
            rollback="ctx.pop('done', None)",
        )
        d = step.to_dict()
        restored = ProcedureStep.from_dict(d)
        assert restored.description == step.description
        assert restored.code == step.code
        assert len(restored.decision_tree) == 1
        assert restored.decision_tree[0].target_step == 5
        assert restored.rollback == step.rollback


# ===========================================================================
# ProcedureTile
# ===========================================================================

class TestProcedureTile:

    def test_simple_creation(self):
        tile = make_simple_tile()
        assert tile.name == "add_numbers"
        assert tile.domain == "math"
        assert len(tile.steps) == 1

    def test_content_hash_deterministic(self):
        tile = make_simple_tile()
        h1 = tile.content_hash()
        h2 = tile.content_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_content_hash_changes_on_edit(self):
        tile = make_simple_tile()
        h1 = tile.content_hash()
        tile.steps.append(ProcedureStep(description="extra", code="pass"))
        h2 = tile.content_hash()
        assert h1 != h2

    def test_json_roundtrip(self):
        tile = make_simple_tile()
        j = tile.to_json()
        restored = ProcedureTile.from_json(j)
        assert restored.name == tile.name
        assert restored.domain == tile.domain
        assert len(restored.steps) == len(tile.steps)
        assert restored.content_hash() == tile.content_hash()

    def test_dict_roundtrip_with_contingencies(self):
        tile = ProcedureTile(
            name="deploy",
            domain="ops",
            pre_conditions=["ctx.get('ready')"],
            steps=[ProcedureStep(description="go", code="ctx['deployed'] = True")],
            post_conditions=["ctx.get('deployed')"],
            contingencies=[
                Contingency("timeout", "ctx.get('timed_out')", "retry with backoff")
            ],
            provenance=Provenance(author="forgemaster", based_on=["abc123"]),
            version=SemanticVersion(2, 1, 0),
        )
        d = tile.to_dict()
        restored = ProcedureTile.from_dict(d)
        assert restored.name == "deploy"
        assert len(restored.contingencies) == 1
        assert restored.contingencies[0].failure_mode == "timeout"
        assert restored.provenance.author == "forgemaster"
        assert str(restored.version) == "v2.1.0"

    def test_parent_hash(self):
        tile = make_simple_tile()
        assert tile.parent_hash is None
        tile.parent_hash = "abc"
        assert tile.parent_hash == "abc"


# ===========================================================================
# ProcedureExecutor
# ===========================================================================

class TestProcedureExecutor:

    def test_simple_execution(self):
        tile = make_simple_tile()
        executor = ProcedureExecutor()
        result = executor.execute(tile, {"x": 3, "y": 7})
        assert result.success
        assert result.status == ProcedureStatus.COMPLETED

    def test_simple_execution_result_correctness(self):
        tile = make_simple_tile()
        executor = ProcedureExecutor()
        ctx = {"x": 10, "y": 20}
        result = executor.execute(tile, ctx)
        assert result.success
        assert ctx["result"] == 30

    def test_pre_condition_failure(self):
        tile = make_simple_tile()
        executor = ProcedureExecutor()
        result = executor.execute(tile, {})  # missing x, y
        assert result.status == ProcedureStatus.FAILED
        assert "Pre-conditions" in result.error

    def test_post_condition_failure(self):
        tile = ProcedureTile(
            name="bad_post",
            domain="test",
            pre_conditions=[],
            steps=[ProcedureStep(description="do nothing", code="pass")],
            post_conditions=["ctx.get('must_exist') == True"],
        )
        executor = ProcedureExecutor()
        result = executor.execute(tile, {})
        assert result.status == ProcedureStatus.FAILED
        assert "Post-conditions" in result.error

    def test_step_failure_triggers_rollback(self):
        tile = make_rollback_tile()
        executor = ProcedureExecutor()
        ctx = {}
        result = executor.execute(tile, ctx)
        assert result.status == ProcedureStatus.ROLLED_BACK
        # Step 1 set 'a' then rollback should have removed it
        assert "a" not in ctx

    def test_callable_registry(self):
        tile = ProcedureTile(
            name="registry_test",
            domain="test",
            pre_conditions=[],
            steps=[
                ProcedureStep(description="use registry", code="my_func"),
            ],
            post_conditions=[],
        )
        executor = ProcedureExecutor()
        executor.register("my_func", lambda ctx: ctx.update({"called": True}))
        ctx = {}
        result = executor.execute(tile, ctx)
        assert result.success
        assert ctx.get("called") is True

    def test_branching_positive(self):
        tile = make_branching_tile()
        executor = ProcedureExecutor()
        ctx = {"value": 5}
        result = executor.execute(tile, ctx)
        assert result.success
        assert ctx["classification"] == "positive"

    def test_branching_negative(self):
        tile = make_branching_tile()
        executor = ProcedureExecutor()
        ctx = {"value": -3}
        result = executor.execute(tile, ctx)
        assert result.success
        assert ctx["classification"] == "negative"

    def test_execution_result_timing(self):
        tile = make_simple_tile()
        executor = ProcedureExecutor()
        result = executor.execute(tile, {"x": 1, "y": 2})
        assert result.started_at > 0
        assert result.finished_at >= result.started_at
        assert result.elapsed_seconds >= 0


# ===========================================================================
# ProcedureRefiner
# ===========================================================================

class TestProcedureRefiner:

    def test_analyze_no_results(self):
        tile = make_simple_tile()
        suggestions = ProcedureRefiner.analyze(tile, [])
        assert suggestions == []

    def test_analyze_detects_step_failures(self):
        tile = make_rollback_tile()
        executor = ProcedureExecutor()
        results = [executor.execute(tile, {}) for _ in range(5)]
        suggestions = ProcedureRefiner.analyze(tile, results)
        # Step 1 fails every time → should suggest rollback improvement
        assert any(s.field == "rollback" for s in suggestions)

    def test_analyze_detects_pre_condition_failures(self):
        tile = make_simple_tile()
        executor = ProcedureExecutor()
        # All fail pre-conditions
        results = [executor.execute(tile, {}) for _ in range(3)]
        suggestions = ProcedureRefiner.analyze(tile, results)
        assert any(s.field == "pre_conditions" for s in suggestions)

    def test_refine_creates_new_version(self):
        tile = make_simple_tile()
        original_hash = tile.content_hash()
        original_version = str(tile.version)

        results = [ExecutionResult(
            tile_name=tile.name,
            tile_hash=tile.content_hash(),
            status=ProcedureStatus.COMPLETED,
            started_at=time.time(),
            finished_at=time.time(),
        )]

        refined = ProcedureRefiner.refine(tile, results, author="test_refiner")
        assert refined.parent_hash == original_hash
        assert str(refined.version) != original_version
        assert refined.provenance.author == "test_refiner"

    def test_refine_bump_levels(self):
        tile = make_simple_tile()
        results = [ExecutionResult(
            tile_name=tile.name,
            tile_hash=tile.content_hash(),
            status=ProcedureStatus.COMPLETED,
            started_at=0, finished_at=0,
        )]
        r_patch = ProcedureRefiner.refine(tile, results, bump="patch")
        r_minor = ProcedureRefiner.refine(tile, results, bump="minor")
        r_major = ProcedureRefiner.refine(tile, results, bump="major")
        assert str(r_patch.version) == "v1.0.1"
        assert str(r_minor.version) == "v1.1.0"
        assert str(r_major.version) == "v2.0.0"

    def test_refine_adds_steps(self):
        tile = make_simple_tile()
        results = []
        extra = [ProcedureStep(description="validate", code="assert ctx['result'] > 0")]
        refined = ProcedureRefiner.refine(tile, results, extra_steps=extra)
        assert len(refined.steps) == len(tile.steps) + 1

    def test_refine_adds_conditions(self):
        tile = make_simple_tile()
        results = []
        refined = ProcedureRefiner.refine(
            tile, results,
            extra_pre_conditions=["ctx.get('allowed')"],
            extra_post_conditions=["ctx.get('result') > 0"],
        )
        assert "ctx.get('allowed')" in refined.pre_conditions
        assert "ctx.get('result') > 0" in refined.post_conditions


# ===========================================================================
# ProcedureLibrary
# ===========================================================================

class TestProcedureLibrary:

    def test_register_and_get(self):
        lib = ProcedureLibrary()
        tile = make_simple_tile()
        h = lib.register(tile)
        assert lib.get("add_numbers") is tile

    def test_get_nonexistent(self):
        lib = ProcedureLibrary()
        assert lib.get("nope") is None

    def test_find_by_domain(self):
        lib = ProcedureLibrary()
        lib.register(make_simple_tile("a", "math"))
        lib.register(make_simple_tile("b", "math"))
        lib.register(make_simple_tile("c", "ops"))
        math_tiles = lib.find_by_domain("math")
        assert len(math_tiles) == 2

    def test_find_by_capability(self):
        lib = ProcedureLibrary()
        lib.register(make_simple_tile())
        results = lib.find_by_capability("add")
        assert len(results) >= 1
        assert results[0].name == "add_numbers"

    def test_find_by_capability_step_description(self):
        lib = ProcedureLibrary()
        tile = ProcedureTile(
            name="custom",
            domain="test",
            pre_conditions=[],
            steps=[ProcedureStep(description="deploy the microservice", code="pass")],
            post_conditions=[],
        )
        lib.register(tile)
        results = lib.find_by_capability("microservice")
        assert len(results) == 1

    def test_record_result_and_stats(self):
        lib = ProcedureLibrary()
        tile = make_simple_tile()
        lib.register(tile)
        executor = ProcedureExecutor()

        for _ in range(3):
            result = executor.execute(tile, {"x": 1, "y": 2})
            lib.record_result(result)

        stats = lib.stats("add_numbers")
        assert stats is not None
        assert stats.times_executed == 3
        assert stats.times_succeeded == 3
        assert stats.success_rate == 1.0

    def test_stats_failure_rate(self):
        lib = ProcedureLibrary()
        tile = make_simple_tile()
        lib.register(tile)
        executor = ProcedureExecutor()

        # 2 succeed, 1 fail (missing y)
        for ctx in [{"x": 1, "y": 2}, {"x": 3, "y": 4}, {"x": 5}]:
            result = executor.execute(tile, ctx)
            lib.record_result(result)

        stats = lib.stats("add_numbers")
        assert stats.times_executed == 3
        assert stats.times_succeeded == 2
        assert stats.times_failed == 1

    def test_list_domains(self):
        lib = ProcedureLibrary()
        lib.register(make_simple_tile("a", "math"))
        lib.register(make_simple_tile("b", "ops"))
        domains = lib.list_domains()
        assert set(domains) == {"math", "ops"}

    def test_all_procedures(self):
        lib = ProcedureLibrary()
        lib.register(make_simple_tile("a", "math"))
        lib.register(make_simple_tile("b", "ops"))
        assert len(lib.all_procedures()) == 2

    def test_latest_version(self):
        lib = ProcedureLibrary()
        v1 = make_simple_tile()
        v1.version = SemanticVersion(1, 0, 0)
        lib.register(v1)

        v2 = make_simple_tile()
        v2.version = SemanticVersion(2, 0, 0)
        # Change something so hash is different
        v2.steps.append(ProcedureStep(description="extra", code="pass"))
        lib.register(v2)

        latest = lib.latest_version("add_numbers")
        assert latest is not None
        assert latest.version == SemanticVersion(2, 0, 0)


# ===========================================================================
# ProcedureStats
# ===========================================================================

class TestProcedureStats:

    def test_empty_stats(self):
        s = ProcedureStats()
        assert s.success_rate == 0.0
        assert s.avg_duration == 0.0

    def test_record_success(self):
        s = ProcedureStats()
        r = ExecutionResult(
            tile_name="t", tile_hash="h",
            status=ProcedureStatus.COMPLETED,
            started_at=0, finished_at=1.0,
        )
        s.record(r)
        assert s.times_executed == 1
        assert s.times_succeeded == 1
        assert s.avg_duration == 1.0

    def test_success_rate_mixed(self):
        s = ProcedureStats()
        s.record(ExecutionResult("t", "h", ProcedureStatus.COMPLETED, started_at=0, finished_at=1))
        s.record(ExecutionResult("t", "h", ProcedureStatus.FAILED, started_at=0, finished_at=1))
        assert s.success_rate == 0.5
