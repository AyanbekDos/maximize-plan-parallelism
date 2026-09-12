"""Deterministic regression scenarios; no task tools or external services."""
from __future__ import annotations
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "checker_under_test", Path(__file__).with_name("check_orchestration.py")
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def plan(mode="execute", slots=2):
    result = checker.example_plan()
    result.update(schema_version=2, mode=mode, transport="threads")
    result["policy"]["worker_slots"] = slots
    result["policy"]["required_final_roles"] = ["integration"] if mode == "execute" else []
    result["nodes"] = [node for node in result["nodes"] if node["id"] != "F"]
    for node in result["nodes"]:
        node["interfaces_produced"] = []
        node["interfaces_consumed"] = []
        if node["id"] in {"A", "B"}:
            node["prerequisites"] = []
            node["prerequisite_reasons"] = {}
            node["read_only_inputs"] = []
    if mode != "execute":
        result["nodes"] = result["nodes"][:2]
    return result


def event(seq, node, old, new, attempt=1, ref=None, actor=None):
    value = {
        "seq": seq, "node_id": node, "from": old, "to": new,
        "attempt": attempt, "evidence": f"Recorded {node} {new}",
    }
    if ref is not None:
        value["agent_ref"] = ref
    if actor is not None:
        value["actor"] = actor
    return value


def through_done():
    return [
        event(1, "A", "planned", "claimed", ref="a"),
        event(2, "A", "claimed", "running", ref="a"),
        event(3, "A", "running", "worker_done", ref="a"),
    ]


class CheckerRegression(unittest.TestCase):
    def check(self, data, events=None, complete=False):
        report = checker.Report()
        context = checker.validate_plan(data, report)
        if context and not report.errors:
            if events is not None:
                checker.validate_events(events, context, report, complete)
            else:
                checker.ready_frontier(
                    context, {node: "planned" for node in context["nodes"]}, report
                )
        return report

    def good(self, data, events=None, complete=False):
        report = self.check(data, events, complete)
        self.assertFalse(report.errors, report.errors)
        return report

    def bad(self, data, needle, events=None, complete=False):
        report = self.check(data, events, complete)
        self.assertTrue(any(needle in error for error in report.errors), report.errors)

    def test_legacy_example_and_complete_ledger(self):
        self.good(checker.example_plan(), checker.complete_events(), True)

    def test_minimal_plan_without_dummy_gates(self):
        data = plan("plan")
        minimal = {
            "id", "title", "outcome", "owned_paths", "deliverables",
            "targeted_verification", "acceptance_criteria",
        }
        for node in data["nodes"]:
            for key in list(node):
                if key not in minimal:
                    del node[key]
        self.assertEqual(self.good(data).ready_nodes, ["A", "B"])

    def test_prepare_without_execution_gates(self):
        self.good(plan("prepare"))

    def test_invalid_mode_or_transport(self):
        for key, value in (("mode", "deploy"), ("transport", "unknown")):
            data = plan()
            data[key] = value
            self.bad(data, key)

    def test_independent_execute_does_not_require_freeze(self):
        self.good(plan())

    def test_single_slot_released_at_worker_done(self):
        self.good(plan(slots=1), through_done() + [
            event(4, "B", "planned", "claimed", ref="b"),
        ])

    def test_verified_result_frees_unrelated_slot(self):
        self.good(plan(slots=1), through_done() + [
            event(4, "A", "worker_done", "verified", actor="root"),
            event(5, "B", "planned", "claimed", ref="b"),
        ])

    def test_pending_review_keeps_only_relevant_lock(self):
        data = plan(slots=1)
        data["nodes"][1]["owned_paths"] = ["src/a/other.ts"]
        data["shared_hot_paths"] = [{"path": "src/a/**", "reason": "same output area"}]
        self.good(data)
        self.bad(data, "conflicting lock", through_done() + [
            event(4, "B", "planned", "claimed", ref="b"),
        ])

    def test_frontier_is_live_not_wave_barrier(self):
        self.assertEqual(self.good(plan(slots=1), through_done()).ready_nodes, ["B"])

    def test_root_and_worker_co_dispatch(self):
        data = plan()
        data["nodes"][0]["root_only"] = True
        report = self.good(data, [
            event(1, "A", "planned", "claimed", ref="root"),
            event(2, "B", "planned", "claimed", ref="b"),
        ])
        self.assertEqual(report.waves[0]["nodes"], ["A", "B"])

    def test_one_root_capacity(self):
        data = plan()
        for node in data["nodes"][:2]:
            node["root_only"] = True
        self.bad(data, "root capacity", [
            event(1, "A", "planned", "claimed", ref="root"),
            event(2, "B", "planned", "claimed", ref="root"),
        ])

    def test_explicit_global_exclusivity(self):
        data = plan()
        data["nodes"][0]["exclusive_run"] = True
        self.bad(data, "exclusive_run", [
            event(1, "A", "planned", "claimed", ref="a"),
            event(2, "B", "planned", "claimed", ref="b"),
        ])

    def test_active_workers_count_toward_capacity(self):
        self.bad(plan(slots=1), "capacity", [
            event(1, "A", "planned", "claimed", ref="a"),
            event(2, "B", "planned", "claimed", ref="b"),
        ])

    def test_segment_aware_paths(self):
        self.assertFalse(checker.patterns_overlap("src/a/**", "src/ab/**"))
        self.assertTrue(checker.patterns_overlap("src/a/**", "src/a/file.ts"))
        self.assertTrue(checker.patterns_overlap("**", "any/file.ts"))

    def test_complex_glob_is_explicitly_unsupported(self):
        data = plan()
        data["nodes"][0]["owned_paths"] = ["src/a*/x.ts"]
        data["nodes"][1]["owned_paths"] = ["src/ab*/y.ts"]
        self.bad(data, "unsupported glob")

    def test_path_escape_and_forbidden_ownership(self):
        for invalid in ("../private", "C:/elsewhere/file", "src/../escape"):
            data = plan()
            data["nodes"][0]["owned_paths"] = [invalid]
            self.assertTrue(self.check(data).errors)
        data = plan()
        data["nodes"][0]["forbidden_paths"] = ["src/a/**"]
        self.bad(data, "forbidden")

    def test_unknown_and_uncovered_criteria(self):
        data = plan()
        data["nodes"][0]["acceptance_criteria"] = ["missing"]
        self.bad(data, "unknown acceptance")
        data = plan()
        data["acceptance_criteria"].append({"id": "AC2", "text": "another result"})
        self.bad(data, "not covered")

    def test_undefined_resource(self):
        data = plan()
        data["nodes"][0]["exclusive_resources"] = ["missing"]
        self.bad(data, "not defined")
        data["nodes"][1]["exclusive_resources"] = ["missing"]
        self.bad(data, "not defined")

    def test_unordered_write_read(self):
        data = plan()
        data["nodes"][1]["read_only_inputs"] = ["src/a/file.ts"]
        self.bad(data, "write/read")

    def test_interface_requires_producer(self):
        data = plan()
        data["nodes"][0]["interfaces_consumed"] = ["missing"]
        self.bad(data, "no producer")

    def test_producer_kind_and_unique_producer(self):
        data = plan()
        data["nodes"][0]["interfaces_produced"] = ["shared"]
        self.bad(data, "only interface_freeze")
        for node in data["nodes"][:2]:
            node["kind"] = "interface_freeze"
            node["interfaces_produced"] = ["shared"]
        self.bad(data, "multiple producers")

    def test_root_final_gate_is_required_for_execution(self):
        data = plan()
        data["nodes"].pop()
        self.bad(data, "final gate")
        data = plan()
        data["nodes"][-1]["root_only"] = False
        self.bad(data, "root_only")
        data = plan()
        data["nodes"][-1]["kind"] = "implementation"
        self.bad(data, "must agree")

    def test_required_final_roles_follow_policy(self):
        data = plan()
        data["nodes"][-1]["gate_roles"] = ["integration"]
        self.good(data)
        data["policy"]["required_final_roles"].append("e2e")
        self.bad(data, "missing roles")

    def test_stale_attempt_or_wrong_agent(self):
        entries = through_done()
        entries[-1]["attempt"] = 2
        self.bad(plan(), "stale", entries)
        entries = through_done()
        entries[-1]["agent_ref"] = "different"
        self.bad(plan(), "matching agent_ref", entries)

    def test_retry_requires_next_attempt(self):
        entries = through_done()[:2] + [
            event(3, "A", "running", "failed", actor="root"),
            event(4, "A", "failed", "claimed", attempt=2, ref="new-a"),
            event(5, "A", "claimed", "running", attempt=2, ref="new-a"),
        ]
        self.good(plan(), entries)
        entries[-1]["attempt"] = 1
        self.bad(plan(), "stale", entries)

    def test_root_acceptance_actor(self):
        self.bad(plan(), "actor=root", through_done() + [
            event(4, "A", "worker_done", "verified", actor="a"),
        ])

    def test_trimmed_identity_cannot_be_reused_while_active(self):
        self.bad(plan(), "already active", [
            event(1, "A", "planned", "claimed", ref="a"),
            event(2, "B", "planned", "claimed", ref=" a "),
        ])

    def test_complete_v2_run_and_incomplete_gate(self):
        entries = []
        for node in ("A", "B", "G"):
            ref = "root" if node == "G" else node.lower()
            for old, new in (
                ("planned", "claimed"), ("claimed", "running"),
                ("running", "worker_done"), ("worker_done", "verified"),
                ("verified", "integrated"),
            ):
                entries.append(event(
                    len(entries) + 1, node, old, new, ref=ref,
                    actor="root" if new in {"verified", "integrated"} else None,
                ))
        self.good(plan(slots=1), entries, True)
        self.bad(plan(), "incomplete", entries[:-1], True)

    def test_real_dependency_waits_for_integration(self):
        data = plan()
        data["nodes"][1]["prerequisites"] = ["A"]
        data["nodes"][1]["prerequisite_reasons"] = {"A": "B consumes A"}
        self.bad(data, "not integrated", through_done() + [
            event(4, "B", "planned", "claimed", ref="b"),
        ])

    def test_cycle_self_dependency_unknown_node(self):
        for prerequisite in ("A", "G", "missing"):
            data = plan()
            data["nodes"][0]["prerequisites"] = [prerequisite]
            data["nodes"][0]["prerequisite_reasons"] = {prerequisite: "needed input"}
            self.assertTrue(self.check(data).errors)

    def test_malformed_data_is_error_not_exception(self):
        for data in (None, [], {}, {"schema_version": 2, "nodes": [None]}):
            self.assertTrue(self.check(data).errors)
        for entry in (None, [], {"node_id": [], "seq": 1}, {"node_id": "A", "to": []}):
            self.assertTrue(self.check(plan(), [entry]).errors)

    def test_missing_ownership_is_not_silent(self):
        data = plan()
        del data["nodes"][0]["owned_paths"]
        self.bad(data, "missing owned_paths")

    def test_contiguous_sequence(self):
        entries = through_done()
        entries[1]["seq"] = 100
        self.bad(plan(), "contiguous", entries)

    def test_jsonl_bom_and_invalid_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "events.jsonl"
            file.write_text(json.dumps(through_done()[0]) + "\n", encoding="utf-8-sig")
            report = checker.Report()
            self.assertEqual(len(checker.load_events(file, report)), 1)
            self.assertFalse(report.errors)
            file.write_text("{invalid}\n[]\n", encoding="utf-8")
            report = checker.Report()
            checker.load_events(file, report)
            self.assertEqual(len(report.errors), 2)


def build_suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(CheckerRegression)


if __name__ == "__main__":
    unittest.main()
