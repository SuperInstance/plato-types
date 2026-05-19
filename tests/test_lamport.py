"""Tests for enhanced Lamport clock system."""

import pytest
from plato_types.lamport import VectorClock, CausalOrder, ConcurrentDetector, ClockSync


class TestVectorClock:
    def test_tick_increments_local(self):
        vc = VectorClock(agent_id="a")
        assert vc.now() == {"a": 0}
        vc.tick()
        assert vc.now() == {"a": 1}
        vc.tick()
        assert vc.now() == {"a": 2}

    def test_merge_takes_max(self):
        vc = VectorClock(agent_id="a")
        vc.tick()
        vc.tick()
        # Merge with a clock where b=3, a=1
        result = vc.merge({"a": 1, "b": 3})
        assert result["a"] == 3  # max(2, 1) + 1 = 3
        assert result["b"] == 3

    def test_merge_adds_new_agents(self):
        vc = VectorClock(agent_id="a", counters={"a": 2})
        result = vc.merge({"b": 5})
        assert result["a"] == 3  # max(2, 0) + 1
        assert result["b"] == 5

    def test_le_comparison(self):
        vc = VectorClock(agent_id="a", counters={"a": 1, "b": 1})
        assert vc <= {"a": 2, "b": 2}
        assert vc <= {"a": 1, "b": 1}
        assert not (vc <= {"a": 0, "b": 2})

    def test_lt_comparison(self):
        vc = VectorClock(agent_id="a", counters={"a": 1, "b": 1})
        assert vc < {"a": 2, "b": 2}
        assert not (vc < {"a": 1, "b": 1})

    def test_eq_comparison(self):
        vc = VectorClock(agent_id="a", counters={"a": 1, "b": 2})
        assert vc == {"a": 1, "b": 2}
        assert not (vc == {"a": 1, "b": 3})

    def test_to_dict_from_dict_roundtrip(self):
        vc = VectorClock(agent_id="a")
        vc.tick()
        vc.merge({"b": 3})
        d = vc.to_dict()
        vc2 = VectorClock.from_dict(d, agent_id="a")
        assert vc2.now() == vc.now()

    def test_default_counter_is_zero(self):
        vc = VectorClock(agent_id="agent1")
        assert vc.now()["agent1"] == 0


class TestCausalOrder:
    def test_happens_before_clear(self):
        a = {"x": 1}
        b = {"x": 2}
        assert CausalOrder.happens_before(a, b)
        assert not CausalOrder.happens_before(b, a)

    def test_happens_before_multi_agent(self):
        a = {"agent1": 2, "agent2": 1}
        b = {"agent1": 2, "agent2": 3}
        assert CausalOrder.happens_before(a, b)

    def test_not_happens_before_incomparable(self):
        a = {"agent1": 2, "agent2": 1}
        b = {"agent1": 1, "agent2": 2}
        assert not CausalOrder.happens_before(a, b)
        assert not CausalOrder.happens_before(b, a)

    def test_concurrent(self):
        a = {"agent1": 2, "agent2": 1}
        b = {"agent1": 1, "agent2": 2}
        assert CausalOrder.is_concurrent(a, b)

    def test_not_concurrent_ordered(self):
        a = {"x": 1}
        b = {"x": 2}
        assert not CausalOrder.is_concurrent(a, b)

    def test_equal_clocks_not_concurrent(self):
        a = {"x": 1, "y": 1}
        assert not CausalOrder.is_concurrent(a, a)

    def test_are_equal(self):
        a = {"x": 1, "y": 2}
        b = {"x": 1, "y": 2}
        assert CausalOrder.are_equal(a, b)

    def test_missing_keys_treated_as_zero(self):
        a = {"agent1": 1}
        b = {"agent1": 1, "agent2": 0}
        assert CausalOrder.are_equal(a, b)


class TestConcurrentDetector:
    def test_find_concurrent_pairs(self):
        events = [
            ("e1", {"a": 2, "b": 1}),
            ("e2", {"a": 1, "b": 2}),
            ("e3", {"a": 3, "b": 3}),
        ]
        pairs = ConcurrentDetector.find_concurrent_pairs(events)
        # e1 and e2 are concurrent; e3 dominates both
        assert ("e1", "e2") in pairs
        assert len(pairs) == 1

    def test_no_concurrent_events(self):
        events = [
            ("e1", {"a": 1}),
            ("e2", {"a": 2}),
            ("e3", {"a": 3}),
        ]
        pairs = ConcurrentDetector.find_concurrent_pairs(events)
        assert pairs == []

    def test_find_concurrent_groups(self):
        events = [
            ("e1", {"a": 2, "b": 1}),
            ("e2", {"a": 1, "b": 2}),
            ("e3", {"a": 3, "b": 3}),
        ]
        groups = ConcurrentDetector.find_concurrent_groups(events)
        assert len(groups) == 1
        assert groups[0] == {"e1", "e2"}

    def test_empty_events(self):
        assert ConcurrentDetector.find_concurrent_pairs([]) == []
        assert ConcurrentDetector.find_concurrent_groups([]) == []

    def test_causal_chain(self):
        events = [
            ("late", {"a": 3}),
            ("early", {"a": 1}),
            ("mid", {"a": 2}),
        ]
        chain = ConcurrentDetector.causal_chain(events)
        assert chain == ["early", "mid", "late"]

    def test_causal_chain_with_concurrent(self):
        events = [
            ("e1", {"a": 2, "b": 1}),
            ("e2", {"a": 1, "b": 2}),
            ("e3", {"a": 3, "b": 3}),
        ]
        chain = ConcurrentDetector.causal_chain(events)
        # e3 must come after both e1 and e2; e1 and e2 can be in either order
        assert chain[-1] == "e3"
        assert set(chain[:2]) == {"e1", "e2"}


class TestClockSync:
    def test_basic_sync(self):
        sync = ClockSync(local_agent_id="a")
        sync.tick()
        sync.tick()
        assert sync.local_clock.now()["a"] == 2

    def test_receive_merges(self):
        sync = ClockSync(local_agent_id="a")
        sync.tick()
        result = sync.receive("b", {"b": 3})
        assert result["a"] == 2  # max(1, 0) + 1
        assert result["b"] == 3

    def test_global_clock(self):
        sync = ClockSync(local_agent_id="a")
        sync.tick()  # a=1
        sync.receive("b", {"b": 3, "a": 0})  # a=2, b=3
        sync.receive("c", {"c": 5})  # a=3, b=3, c=5
        g = sync.global_clock()
        assert g["a"] == 3
        assert g["b"] == 3
        assert g["c"] == 5

    def test_known_agents(self):
        sync = ClockSync(local_agent_id="a")
        sync.receive("b", {"b": 1})
        agents = sync.known_agents()
        assert "a" in agents
        assert "b" in agents

    def test_is_up_to_date(self):
        sync = ClockSync(local_agent_id="a")
        sync.receive("b", {"b": 2})
        assert sync.is_up_to_date("b", {"b": 3})
        assert not sync.is_up_to_date("b", {"b": 1})

    def test_skew(self):
        sync = ClockSync(local_agent_id="a")
        sync.tick()
        sync.receive("b", {"b": 2})
        skew = sync.skew()
        # skew for b = our_view["b"] - their_local["b"]
        # After merge: local has a=2, b=2. Remote snapshot has b=2
        # skew["b"] = 2 - 2 = 0
        assert "b" in skew

    def test_unknown_agent_is_up_to_date(self):
        sync = ClockSync(local_agent_id="a")
        assert sync.is_up_to_date("new_agent", {"new_agent": 1})
