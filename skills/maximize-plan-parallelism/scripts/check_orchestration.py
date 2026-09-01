#!/usr/bin/env python3
"""Validate a root-owned implementation DAG and its append-only event ledger."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FINAL_ROLES = {"integration", "cross_review", "restart_replay", "e2e"}
LIST_FIELDS = (
    "gate_roles",
    "prerequisites",
    "subsystems",
    "owned_paths",
    "read_only_inputs",
    "forbidden_paths",
    "deliverables",
    "targeted_verification",
    "acceptance_criteria",
    "interfaces_produced",
    "interfaces_consumed",
    "exclusive_resources",
    "heavy_test_groups",
)
PATH_FIELDS = ("owned_paths", "read_only_inputs", "forbidden_paths")
ACTIVE_STATUSES = {"claimed", "running"}
EVIDENCE_STATUSES = {
    "worker_done",
    "verified",
    "integrated",
    "blocked",
    "failed",
    "orphaned",
    "superseded",
}
TRANSITIONS = {
    "planned": {"claimed", "blocked", "superseded"},
    "claimed": {"running", "blocked", "failed", "orphaned"},
    "running": {"worker_done", "blocked", "failed", "orphaned"},
    "worker_done": {"verified", "blocked", "failed"},
    "verified": {"integrated", "failed"},
    "blocked": {"claimed", "superseded"},
    "failed": {"claimed", "superseded"},
    "orphaned": {"claimed", "superseded"},
    "integrated": set(),
    "superseded": set(),
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.waves: list[dict[str, Any]] = []
        self.serialization: list[dict[str, Any]] = []
        self.node_status: dict[str, str] | None = None

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": not self.errors,
            "errors": self.errors,
            "warnings": self.warnings,
            "waves": self.waves,
            "serialization": self.serialization,
        }
        if self.node_status is not None:
            result["node_status"] = self.node_status
        return result


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_path(raw: Any, case_sensitive: bool) -> tuple[str | None, str | None]:
    if not is_nonempty_string(raw):
        return None, "must be a non-empty string"
    original = raw.strip()
    value = original.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    if value.startswith("/") or value.startswith("//") or re.match(r"^[A-Za-z]:/", value):
        return None, "must be repo-relative"
    if value.endswith("/"):
        return None, "must use dir/** for directory ownership"
    parts = value.split("/")
    if not value or any(part in {"", ".", ".."} for part in parts):
        return None, "contains an empty, dot, or parent segment"
    normalized = value if case_sensitive else value.casefold()
    return normalized, None


def contains_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def static_prefix(pattern: str) -> str:
    indexes = [pattern.find(char) for char in "*?[" if char in pattern]
    if not indexes:
        return pattern
    return pattern[: min(indexes)]


def patterns_overlap(left: str, right: str) -> bool:
    left_glob = contains_glob(left)
    right_glob = contains_glob(right)
    if not left_glob and not right_glob:
        return left == right
    if left_glob and not right_glob:
        return fnmatch.fnmatchcase(right, left)
    if right_glob and not left_glob:
        return fnmatch.fnmatchcase(left, right)
    if left == right:
        return True
    left_prefix = static_prefix(left)
    right_prefix = static_prefix(right)
    if not left_prefix or not right_prefix:
        return True
    return left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix)


def first_overlap(left: list[str], right: list[str]) -> tuple[str, str] | None:
    for left_pattern in left:
        for right_pattern in right:
            if patterns_overlap(left_pattern, right_pattern):
                return left_pattern, right_pattern
    return None


def valid_string_list(node_id: str, field: str, value: Any, report: Report) -> list[str]:
    if not isinstance(value, list):
        report.error(f"node {node_id}: {field} must be a list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not is_nonempty_string(item):
            report.error(f"node {node_id}: {field}[{index}] must be a non-empty string")
            continue
        result.append(item.strip())
    if len(result) != len(set(result)):
        report.error(f"node {node_id}: {field} contains duplicates")
    return result


def topological_order(nodes: dict[str, dict[str, Any]], report: Report) -> list[str]:
    indegree = {node_id: 0 for node_id in nodes}
    dependents = {node_id: [] for node_id in nodes}
    for node_id, node in nodes.items():
        for prerequisite in node["prerequisites"]:
            if prerequisite in nodes and prerequisite != node_id:
                indegree[node_id] += 1
                dependents[prerequisite].append(node_id)
    ready = sorted(node_id for node_id, count in indegree.items() if count == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for dependent in sorted(dependents[current]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort()
    if len(order) != len(nodes):
        cyclic = sorted(node_id for node_id, count in indegree.items() if count > 0)
        report.error(f"DAG contains a cycle involving: {', '.join(cyclic)}")
    return order


def ancestor_map(order: list[str], nodes: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    ancestors = {node_id: set() for node_id in nodes}
    for node_id in order:
        for prerequisite in nodes[node_id]["prerequisites"]:
            if prerequisite in nodes:
                ancestors[node_id].add(prerequisite)
                ancestors[node_id].update(ancestors[prerequisite])
    return ancestors


def declared_hot_reason(
    left_pattern: str, right_pattern: str, hot_paths: list[dict[str, str]]
) -> str | None:
    for item in hot_paths:
        hot_pattern = item["path"]
        if patterns_overlap(hot_pattern, left_pattern) and patterns_overlap(hot_pattern, right_pattern):
            return item["reason"]
    return None


def scheduling_conflict(left: dict[str, Any], right: dict[str, Any]) -> str | None:
    overlap = first_overlap(left["owned_paths_norm"], right["owned_paths_norm"])
    if overlap:
        return f"write path overlap {overlap[0]} <> {overlap[1]}"
    resources = sorted(set(left["exclusive_resources"]) & set(right["exclusive_resources"]))
    if resources:
        return f"exclusive resource {resources[0]}"
    heavy = sorted(set(left["heavy_test_groups"]) & set(right["heavy_test_groups"]))
    if heavy:
        return f"heavy test group {heavy[0]}"
    return None


def runtime_conflict(left: dict[str, Any], right: dict[str, Any]) -> str | None:
    conflict = scheduling_conflict(left, right)
    if conflict:
        return conflict
    overlap = first_overlap(left["owned_paths_norm"], right["read_only_inputs_norm"])
    if overlap:
        return f"write/read path overlap {overlap[0]} <> {overlap[1]}"
    overlap = first_overlap(right["owned_paths_norm"], left["read_only_inputs_norm"])
    if overlap:
        return f"read/write path overlap {overlap[1]} <> {overlap[0]}"
    return None


def derive_waves(
    nodes: dict[str, dict[str, Any]], worker_slots: int, report: Report
) -> list[dict[str, Any]]:
    dependents = {node_id: [] for node_id in nodes}
    for node_id, node in nodes.items():
        for prerequisite in node["prerequisites"]:
            if prerequisite in nodes:
                dependents[prerequisite].append(node_id)
    critical_cache: dict[str, int] = {}

    def critical_length(node_id: str) -> int:
        if node_id not in critical_cache:
            children = dependents[node_id]
            critical_cache[node_id] = 1 + max(
                (critical_length(child) for child in children), default=0
            )
        return critical_cache[node_id]

    remaining = set(nodes)
    completed: set[str] = set()
    waves: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(
            node_id
            for node_id in remaining
            if set(nodes[node_id]["prerequisites"]).issubset(completed)
        )
        if not ready:
            return waves
        root_ready = sorted(
            (node_id for node_id in ready if nodes[node_id]["root_only"]),
            key=lambda node_id: (-critical_length(node_id), node_id),
        )
        worker_ready = sorted(
            (node_id for node_id in ready if not nodes[node_id]["root_only"]),
            key=lambda node_id: (-critical_length(node_id), node_id),
        )
        selected: list[str] = []
        choose_root = bool(root_ready) and (
            not worker_ready or critical_length(root_ready[0]) >= critical_length(worker_ready[0])
        )
        if choose_root:
            selected = [root_ready[0]]
            waiting = [node_id for node_id in ready if node_id not in selected]
            if waiting:
                report.serialization.append(
                    {
                        "type": "root_gate_scheduling",
                        "wave": len(waves) + 1,
                        "waiting": waiting,
                        "reason": (
                            f"The sole root takes ready critical-path gate {root_ready[0]} "
                            f"(remaining path length {critical_length(root_ready[0])}) before "
                            "co-dispatching workers"
                        ),
                    }
                )
        elif worker_ready:
            for node_id in worker_ready:
                if len(selected) >= worker_slots:
                    continue
                if any(scheduling_conflict(nodes[node_id], nodes[other]) for other in selected):
                    continue
                selected.append(node_id)
            waiting_for_capacity = [node_id for node_id in worker_ready if node_id not in selected]
            for waiting_node in waiting_for_capacity:
                conflicts = [
                    (selected_node, scheduling_conflict(nodes[waiting_node], nodes[selected_node]))
                    for selected_node in selected
                ]
                conflicts = [(node_id, reason) for node_id, reason in conflicts if reason]
                if conflicts:
                    blocker, reason = conflicts[0]
                    report.serialization.append(
                        {
                            "type": "wave_lock",
                            "wave": len(waves) + 1,
                            "nodes": [blocker, waiting_node],
                            "reason": f"{reason} prevents co-dispatch in this wave",
                        }
                    )
                else:
                    report.serialization.append(
                        {
                            "type": "capacity",
                            "wave": len(waves) + 1,
                            "waiting": [waiting_node],
                            "reason": f"worker capacity {worker_slots} is already filled",
                        }
                    )
            if root_ready:
                report.serialization.append(
                    {
                        "type": "critical_path_scheduling",
                        "wave": len(waves) + 1,
                        "waiting": root_ready,
                        "reason": (
                            f"Ready worker critical path {critical_length(worker_ready[0])} is longer "
                            f"than ready root gate critical path {critical_length(root_ready[0])}"
                        ),
                    }
                )
        waves.append(
            {
                "wave": len(waves) + 1,
                "nodes": selected,
                "mode": "root_gate" if nodes[selected[0]]["root_only"] else "workers",
            }
        )
        completed.update(selected)
        remaining.difference_update(selected)
    return waves


def validate_plan(plan: Any, report: Report) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        report.error("plan root must be a JSON object")
        return None
    if plan.get("schema_version") != 1:
        report.error("schema_version must be 1")
    for field in ("run_id", "goal"):
        if not is_nonempty_string(plan.get(field)):
            report.error(f"{field} must be a non-empty string")
    repo = plan.get("repo")
    if not isinstance(repo, dict):
        report.error("repo must be an object with root and baseline")
    else:
        for field in ("root", "baseline"):
            if not is_nonempty_string(repo.get(field)):
                report.error(f"repo.{field} must be a non-empty string")

    criteria_raw = plan.get("acceptance_criteria")
    criteria: dict[str, str] = {}
    if not isinstance(criteria_raw, list) or not criteria_raw:
        report.error("acceptance_criteria must be a non-empty list")
    else:
        for index, item in enumerate(criteria_raw):
            if not isinstance(item, dict):
                report.error(f"acceptance_criteria[{index}] must be an object")
                continue
            criterion_id = item.get("id")
            text = item.get("text")
            if not is_nonempty_string(criterion_id) or not is_nonempty_string(text):
                report.error(f"acceptance_criteria[{index}] requires non-empty id and text")
                continue
            if criterion_id in criteria:
                report.error(f"duplicate acceptance criterion id: {criterion_id}")
            criteria[criterion_id] = text.strip()

    policy = plan.get("policy")
    if not isinstance(policy, dict):
        report.error("policy must be an object")
        policy = {}
    worker_slots = policy.get("worker_slots", 1)
    max_paths = policy.get("max_owned_paths_per_node", 6)
    max_subsystems = policy.get("max_subsystems_per_worker_node", 1)
    case_sensitive = policy.get("case_sensitive_paths", True)
    for name, value in (
        ("worker_slots", worker_slots),
        ("max_owned_paths_per_node", max_paths),
        ("max_subsystems_per_worker_node", max_subsystems),
    ):
        if type(value) is not int or value < 1:
            report.error(f"policy.{name} must be an integer >= 1")
    if not isinstance(case_sensitive, bool):
        report.error("policy.case_sensitive_paths must be boolean")
        case_sensitive = True
    worker_slots = worker_slots if type(worker_slots) is int and worker_slots >= 1 else 1
    max_paths = max_paths if type(max_paths) is int and max_paths >= 1 else 6
    max_subsystems = max_subsystems if type(max_subsystems) is int and max_subsystems >= 1 else 1

    hot_paths_raw = plan.get("shared_hot_paths")
    hot_paths: list[dict[str, str]] = []
    if not isinstance(hot_paths_raw, list):
        report.error("shared_hot_paths must be a list")
    else:
        for index, item in enumerate(hot_paths_raw):
            if not isinstance(item, dict):
                report.error(f"shared_hot_paths[{index}] must be an object")
                continue
            normalized, path_error = normalize_path(item.get("path"), case_sensitive)
            reason = item.get("reason")
            if path_error:
                report.error(f"shared_hot_paths[{index}].path {path_error}")
            if not is_nonempty_string(reason) or len(reason.strip()) < 20:
                report.error(f"shared_hot_paths[{index}].reason must be concrete (20+ characters)")
            if normalized and is_nonempty_string(reason):
                hot_paths.append({"path": normalized, "reason": reason.strip()})

    resource_locks = plan.get("resource_locks")
    if not isinstance(resource_locks, dict):
        report.error("resource_locks must be an object")
        resource_locks = {}
    else:
        for resource, reason in resource_locks.items():
            if not is_nonempty_string(resource) or not is_nonempty_string(reason) or len(reason.strip()) < 20:
                report.error(f"resource_locks.{resource} requires a concrete 20+ character reason")

    nodes_raw = plan.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        report.error("nodes must be a non-empty list")
        return None
    nodes: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(nodes_raw):
        if not isinstance(raw, dict):
            report.error(f"nodes[{index}] must be an object")
            continue
        node_id = raw.get("id")
        if not is_nonempty_string(node_id) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", node_id):
            report.error(f"nodes[{index}].id must match [A-Za-z0-9][A-Za-z0-9_.-]*")
            continue
        if node_id in nodes:
            report.error(f"duplicate node id: {node_id}")
            continue
        node = dict(raw)
        for field in ("title", "outcome", "kind"):
            if not is_nonempty_string(node.get(field)):
                report.error(f"node {node_id}: {field} must be a non-empty string")
        for field in ("root_only", "final_gate"):
            if not isinstance(node.get(field), bool):
                report.error(f"node {node_id}: {field} must be boolean")
                node[field] = False
        for field in LIST_FIELDS:
            node[field] = valid_string_list(node_id, field, node.get(field), report)
        reasons = node.get("prerequisite_reasons")
        if not isinstance(reasons, dict):
            report.error(f"node {node_id}: prerequisite_reasons must be an object")
            reasons = {}
        node["prerequisite_reasons"] = reasons
        split_exception = node.get("split_exception")
        if split_exception is not None and not is_nonempty_string(split_exception):
            report.error(f"node {node_id}: split_exception must be null or a non-empty string")
        if is_nonempty_string(split_exception) and not node["root_only"]:
            report.error(f"node {node_id}: only a root_only node may use split_exception")
        for field in ("deliverables", "targeted_verification", "acceptance_criteria", "subsystems"):
            if not node[field]:
                report.error(f"node {node_id}: {field} must not be empty")
        if len(node["owned_paths"]) > max_paths and not (
            node["root_only"] and is_nonempty_string(split_exception)
        ):
            report.error(
                f"node {node_id}: owns {len(node['owned_paths'])} paths, over limit {max_paths}; re-split it"
            )
        if len(node["subsystems"]) > max_subsystems and not (
            node["root_only"] and is_nonempty_string(split_exception)
        ):
            report.error(
                f"node {node_id}: spans {len(node['subsystems'])} subsystems, over limit "
                f"{max_subsystems}; re-split it"
            )
        if node["interfaces_produced"] and node.get("kind") != "interface_freeze":
            report.error(f"node {node_id}: only interface_freeze nodes may produce interfaces")
        unknown_roles = sorted(set(node["gate_roles"]) - REQUIRED_FINAL_ROLES)
        if unknown_roles:
            report.error(f"node {node_id}: unknown gate_roles: {', '.join(unknown_roles)}")
        if node["gate_roles"] and not node["final_gate"]:
            report.error(f"node {node_id}: gate_roles require final_gate=true")
        if node["final_gate"] and not node["gate_roles"]:
            report.error(f"node {node_id}: final_gate requires at least one gate role")
        for resource in node["exclusive_resources"]:
            if resource not in resource_locks:
                report.error(f"node {node_id}: exclusive resource {resource!r} is not defined")
        for field in PATH_FIELDS:
            normalized_paths: list[str] = []
            for path_index, raw_path in enumerate(node[field]):
                normalized, path_error = normalize_path(raw_path, case_sensitive)
                if path_error:
                    report.error(f"node {node_id}: {field}[{path_index}] {path_error}")
                elif normalized:
                    normalized_paths.append(normalized)
            node[f"{field}_norm"] = normalized_paths
        for path_index, left_path in enumerate(node["owned_paths_norm"]):
            for right_path in node["owned_paths_norm"][path_index + 1 :]:
                if patterns_overlap(left_path, right_path):
                    report.error(
                        f"node {node_id}: redundant/overlapping owned paths {left_path!r} and {right_path!r}"
                    )
        overlap = first_overlap(node["owned_paths_norm"], node["read_only_inputs_norm"])
        if overlap:
            report.error(
                f"node {node_id}: path cannot be both owned and read-only: {overlap[0]} <> {overlap[1]}"
            )
        overlap = first_overlap(node["owned_paths_norm"], node["forbidden_paths_norm"])
        if overlap:
            report.error(
                f"node {node_id}: owned path overlaps forbidden path: {overlap[0]} <> {overlap[1]}"
            )
        nodes[node_id] = node

    for node_id, node in nodes.items():
        prerequisites = node["prerequisites"]
        reason_keys = set(node["prerequisite_reasons"])
        for prerequisite in prerequisites:
            if prerequisite == node_id:
                report.error(f"node {node_id}: self-dependency is not allowed")
            elif prerequisite not in nodes:
                report.error(f"node {node_id}: unknown prerequisite {prerequisite}")
            reason = node["prerequisite_reasons"].get(prerequisite)
            if not is_nonempty_string(reason) or len(reason.strip()) < 20:
                report.error(
                    f"node {node_id}: prerequisite {prerequisite} needs a concrete 20+ character reason"
                )
            elif prerequisite in nodes:
                report.serialization.append(
                    {
                        "type": "semantic_dependency",
                        "nodes": [prerequisite, node_id],
                        "reason": reason.strip(),
                    }
                )
        extra_reasons = sorted(reason_keys - set(prerequisites))
        if extra_reasons:
            report.error(f"node {node_id}: reasons without prerequisites: {', '.join(extra_reasons)}")
        for criterion_id in node["acceptance_criteria"]:
            if criterion_id not in criteria:
                report.error(f"node {node_id}: unknown acceptance criterion {criterion_id}")

    uncovered = sorted(
        criterion_id
        for criterion_id in criteria
        if not any(criterion_id in node["acceptance_criteria"] for node in nodes.values())
    )
    if uncovered:
        report.error(f"acceptance criteria are not covered by any node: {', '.join(uncovered)}")

    order = topological_order(nodes, report)
    ancestors = ancestor_map(order, nodes) if len(order) == len(nodes) else {node_id: set() for node_id in nodes}

    producers: dict[str, str] = {}
    for node_id, node in nodes.items():
        for interface in node["interfaces_produced"]:
            if interface in producers:
                report.error(
                    f"interface {interface!r} has multiple producers: {producers[interface]}, {node_id}"
                )
            else:
                producers[interface] = node_id
    if not any(node.get("kind") == "interface_freeze" for node in nodes.values()):
        report.error("large implementation DAG requires at least one interface_freeze node")
    for node_id, node in nodes.items():
        for interface in node["interfaces_consumed"]:
            producer = producers.get(interface)
            if producer is None:
                report.error(f"node {node_id}: consumed interface {interface!r} has no producer")
            elif producer not in ancestors[node_id]:
                report.error(
                    f"node {node_id}: interface producer {producer} for {interface!r} is not an ancestor"
                )

    final_nodes = [node_id for node_id, node in nodes.items() if node["final_gate"]]
    if not final_nodes:
        report.error("DAG requires a final gate stage")
    covered_roles = set().union(*(set(nodes[node_id]["gate_roles"]) for node_id in final_nodes)) if final_nodes else set()
    missing_roles = sorted(REQUIRED_FINAL_ROLES - covered_roles)
    if missing_roles:
        report.error(f"final gate stage is missing roles: {', '.join(missing_roles)}")
    non_final = {node_id for node_id, node in nodes.items() if not node["final_gate"]}
    for node_id in final_nodes:
        missing_ancestors = sorted(non_final - ancestors[node_id])
        if missing_ancestors:
            report.error(
                f"final gate node {node_id} can start before non-final nodes: {', '.join(missing_ancestors)}"
            )

    node_ids = sorted(nodes)
    for left_index, left_id in enumerate(node_ids):
        for right_id in node_ids[left_index + 1 :]:
            left = nodes[left_id]
            right = nodes[right_id]
            ordered = left_id in ancestors[right_id] or right_id in ancestors[left_id]
            write_overlap = first_overlap(left["owned_paths_norm"], right["owned_paths_norm"])
            if write_overlap:
                if ordered:
                    report.serialization.append(
                        {
                            "type": "ordered_hot_path",
                            "nodes": [left_id, right_id],
                            "paths": list(write_overlap),
                            "reason": "A semantic dependency already prevents concurrent writes",
                        }
                    )
                else:
                    hot_reason = declared_hot_reason(write_overlap[0], write_overlap[1], hot_paths)
                    if hot_reason is None:
                        report.error(
                            f"nodes {left_id} and {right_id}: unordered write overlap "
                            f"{write_overlap[0]} <> {write_overlap[1]} is not declared in shared_hot_paths"
                        )
                    else:
                        report.serialization.append(
                            {
                                "type": "shared_hot_path",
                                "nodes": [left_id, right_id],
                                "paths": list(write_overlap),
                                "reason": hot_reason,
                            }
                        )
            for writer_id, writer, reader_id, reader in (
                (left_id, left, right_id, right),
                (right_id, right, left_id, left),
            ):
                read_overlap = first_overlap(
                    writer["owned_paths_norm"], reader["read_only_inputs_norm"]
                )
                if read_overlap and not ordered:
                    report.error(
                        f"nodes {writer_id} and {reader_id}: unordered write/read overlap "
                        f"{read_overlap[0]} <> {read_overlap[1]}; add the real dependency or redesign ownership"
                    )
            shared_resources = sorted(
                set(left["exclusive_resources"]) & set(right["exclusive_resources"])
            )
            if shared_resources and not ordered:
                for resource in shared_resources:
                    report.serialization.append(
                        {
                            "type": "exclusive_resource",
                            "nodes": [left_id, right_id],
                            "resource": resource,
                            "reason": resource_locks[resource],
                        }
                    )
            shared_heavy = sorted(set(left["heavy_test_groups"]) & set(right["heavy_test_groups"]))
            if shared_heavy and not ordered:
                for group in shared_heavy:
                    report.serialization.append(
                        {
                            "type": "heavy_test_group",
                            "nodes": [left_id, right_id],
                            "group": group,
                            "reason": "The expensive verification group has at most one owner per wave",
                        }
                    )

    if len(order) == len(nodes):
        report.waves = derive_waves(nodes, worker_slots, report)
    return {
        "nodes": nodes,
        "ancestors": ancestors,
        "worker_slots": worker_slots,
        "final_nodes": set(final_nodes),
        "non_final_nodes": non_final,
    }


def load_events(path: Path, report: Report) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        report.error(f"cannot read events file {path}: {exc}")
        return events
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            report.error(f"events line {line_number}: blank lines are not allowed")
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            report.error(f"events line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            report.error(f"events line {line_number}: event must be an object")
            continue
        event["_line"] = line_number
        events.append(event)
    return events


def validate_events(
    events: list[dict[str, Any]], context: dict[str, Any], report: Report, require_complete: bool
) -> None:
    nodes = context["nodes"]
    worker_slots = context["worker_slots"]
    statuses = {node_id: "planned" for node_id in nodes}
    agent_refs: dict[str, str] = {}
    for expected_seq, event in enumerate(events, start=1):
        line = event.get("_line", expected_seq)
        if event.get("seq") != expected_seq:
            report.error(
                f"events line {line}: seq must be contiguous; expected {expected_seq}, got {event.get('seq')!r}"
            )
        node_id = event.get("node_id")
        if node_id not in nodes:
            report.error(f"events line {line}: unknown node_id {node_id!r}")
            continue
        current = statuses[node_id]
        declared_from = event.get("from")
        target = event.get("to")
        if declared_from != current:
            report.error(
                f"events line {line}: node {node_id} expected from={current!r}, got {declared_from!r}"
            )
        if target not in TRANSITIONS.get(current, set()):
            report.error(f"events line {line}: invalid transition for {node_id}: {current} -> {target}")
            continue
        if target in EVIDENCE_STATUSES and not is_nonempty_string(event.get("evidence")):
            report.error(f"events line {line}: transition to {target} requires evidence")
        if target == "claimed":
            unresolved = sorted(
                other_id
                for other_id, status in statuses.items()
                if status in {"worker_done", "verified"} and other_id != node_id
            )
            if unresolved:
                report.error(
                    f"events line {line}: reconcile worker_done/verified nodes before a new claim: "
                    f"{', '.join(unresolved)}"
                )
            missing_prerequisites = sorted(
                prerequisite
                for prerequisite in nodes[node_id]["prerequisites"]
                if statuses.get(prerequisite) != "integrated"
            )
            if missing_prerequisites:
                report.error(
                    f"events line {line}: node {node_id} is not ready; prerequisites not integrated: "
                    f"{', '.join(missing_prerequisites)}"
                )
            active_ids = [other_id for other_id, status in statuses.items() if status in ACTIVE_STATUSES]
            if nodes[node_id]["root_only"]:
                if active_ids:
                    report.error(
                        f"events line {line}: root_only node {node_id} cannot start with active nodes: "
                        f"{', '.join(sorted(active_ids))}"
                    )
            else:
                if any(nodes[other_id]["root_only"] for other_id in active_ids):
                    report.error(f"events line {line}: worker node cannot start while a root_only gate is active")
                active_workers = [other_id for other_id in active_ids if not nodes[other_id]["root_only"]]
                if len(active_workers) >= worker_slots:
                    report.error(
                        f"events line {line}: worker capacity {worker_slots} exceeded by node {node_id}"
                    )
            for other_id in active_ids:
                conflict = runtime_conflict(nodes[node_id], nodes[other_id])
                if conflict:
                    report.error(
                        f"events line {line}: active nodes {node_id} and {other_id} conflict: {conflict}"
                    )
            agent_ref = event.get("agent_ref")
            if not is_nonempty_string(agent_ref):
                report.error(f"events line {line}: claimed transition requires agent_ref")
            elif nodes[node_id]["root_only"] and agent_ref.strip().casefold() != "root":
                report.error(f"events line {line}: root_only node {node_id} must use agent_ref='root'")
            elif not nodes[node_id]["root_only"] and agent_ref.strip().casefold() == "root":
                report.error(f"events line {line}: worker node {node_id} cannot use agent_ref='root'")
            elif agent_ref in (
                agent_refs.get(other_id) for other_id in active_ids if other_id != node_id
            ):
                report.error(f"events line {line}: agent_ref {agent_ref!r} is already active")
            if is_nonempty_string(agent_ref):
                agent_refs[node_id] = agent_ref.strip()
        if target == "integrated":
            missing_prerequisites = sorted(
                prerequisite
                for prerequisite in nodes[node_id]["prerequisites"]
                if statuses.get(prerequisite) != "integrated"
            )
            if missing_prerequisites:
                report.error(
                    f"events line {line}: cannot integrate {node_id}; prerequisites not integrated: "
                    f"{', '.join(missing_prerequisites)}"
                )
        statuses[node_id] = target

    report.node_status = dict(sorted(statuses.items()))
    if require_complete:
        incomplete = sorted(
            node_id for node_id, status in statuses.items() if status not in {"integrated", "superseded"}
        )
        if incomplete:
            report.error(f"run is incomplete: {', '.join(incomplete)}")
        missing_final = sorted(
            node_id for node_id in context["final_nodes"] if statuses[node_id] != "integrated"
        )
        if missing_final:
            report.error(f"final gate nodes must be integrated, not superseded: {', '.join(missing_final)}")


def example_plan() -> dict[str, Any]:
    def card(
        node_id: str,
        *,
        prerequisites: list[str],
        reasons: dict[str, str],
        subsystem: str,
        owned: list[str],
        read_only: list[str],
        produced: list[str] | None = None,
        consumed: list[str] | None = None,
        kind: str = "implementation",
        root_only: bool = False,
        final_gate: bool = False,
        gate_roles: list[str] | None = None,
        heavy: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": node_id,
            "title": f"Node {node_id}",
            "outcome": f"Observable outcome for node {node_id}",
            "kind": kind,
            "root_only": root_only,
            "final_gate": final_gate,
            "gate_roles": gate_roles or [],
            "prerequisites": prerequisites,
            "prerequisite_reasons": reasons,
            "subsystems": [subsystem],
            "owned_paths": owned,
            "read_only_inputs": read_only,
            "forbidden_paths": [],
            "deliverables": [f"Deliverable for {node_id}"],
            "targeted_verification": [f"Verify {node_id} behavior"],
            "acceptance_criteria": ["AC1"],
            "interfaces_produced": produced or [],
            "interfaces_consumed": consumed or [],
            "exclusive_resources": [],
            "heavy_test_groups": heavy or [],
            "split_exception": "Final proof must inspect one integrated state" if root_only else None,
        }

    return {
        "schema_version": 1,
        "run_id": "self-test",
        "goal": "Validate checker invariants",
        "repo": {"root": "C:/repo", "baseline": "abc123"},
        "acceptance_criteria": [{"id": "AC1", "text": "The integrated behavior is proven"}],
        "policy": {
            "worker_slots": 2,
            "max_owned_paths_per_node": 6,
            "max_subsystems_per_worker_node": 1,
            "case_sensitive_paths": False,
        },
        "shared_hot_paths": [],
        "resource_locks": {},
        "nodes": [
            card(
                "F",
                prerequisites=[],
                reasons={},
                subsystem="contract",
                owned=["src/contract.ts"],
                read_only=["docs/contract.md"],
                produced=["contract-v1"],
                kind="interface_freeze",
            ),
            card(
                "A",
                prerequisites=["F"],
                reasons={"F": "A imports the frozen contract and requires its stable type shape"},
                subsystem="a",
                owned=["src/a/**"],
                read_only=["src/contract.ts"],
                consumed=["contract-v1"],
            ),
            card(
                "B",
                prerequisites=["F"],
                reasons={"F": "B imports the frozen contract and requires its stable type shape"},
                subsystem="b",
                owned=["src/b/**"],
                read_only=["src/contract.ts"],
                consumed=["contract-v1"],
            ),
            card(
                "G",
                prerequisites=["A", "B"],
                reasons={
                    "A": "Final acceptance must exercise the integrated implementation from A",
                    "B": "Final acceptance must exercise the integrated implementation from B",
                },
                subsystem="system",
                owned=[],
                read_only=["src/**"],
                consumed=["contract-v1"],
                kind="final_gate",
                root_only=True,
                final_gate=True,
                gate_roles=sorted(REQUIRED_FINAL_ROLES),
                heavy=["full-suite"],
            ),
        ],
    }


def complete_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    def add(node: str, old: str, new: str, agent: str | None = None) -> None:
        event: dict[str, Any] = {
            "seq": len(events) + 1,
            "node_id": node,
            "from": old,
            "to": new,
            "evidence": f"Evidence for {node} {new}",
        }
        if agent is not None:
            event["agent_ref"] = agent
        events.append(event)

    for node, agent in (("F", "agent-f"),):
        add(node, "planned", "claimed", agent)
        add(node, "claimed", "running")
        add(node, "running", "worker_done")
        add(node, "worker_done", "verified")
        add(node, "verified", "integrated")
    add("A", "planned", "claimed", "agent-a")
    add("B", "planned", "claimed", "agent-b")
    for node in ("A", "B"):
        add(node, "claimed", "running")
    for node in ("A", "B"):
        add(node, "running", "worker_done")
    for node in ("A", "B"):
        add(node, "worker_done", "verified")
        add(node, "verified", "integrated")
    add("G", "planned", "claimed", "root")
    add("G", "claimed", "running")
    add("G", "running", "worker_done")
    add("G", "worker_done", "verified")
    add("G", "verified", "integrated")
    return events


def run_self_test() -> int:
    failures: list[str] = []
    valid_report = Report()
    context = validate_plan(example_plan(), valid_report)
    if valid_report.errors:
        failures.append(f"valid plan rejected: {valid_report.errors}")
    expected_waves = [["F"], ["A", "B"], ["G"]]
    actual_waves = [wave["nodes"] for wave in valid_report.waves]
    if actual_waves != expected_waves:
        failures.append(f"unexpected waves: {actual_waves}")
    if context is not None:
        validate_events(complete_events(), context, valid_report, require_complete=True)
        if valid_report.errors:
            failures.append(f"valid ledger rejected: {valid_report.errors}")

    cycle_plan = example_plan()
    cycle_plan["nodes"][0]["prerequisites"] = ["G"]
    cycle_plan["nodes"][0]["prerequisite_reasons"] = {
        "G": "The deliberately invalid self-test creates a cycle through the final gate"
    }
    cycle_report = Report()
    validate_plan(cycle_plan, cycle_report)
    if not any("cycle" in error.casefold() for error in cycle_report.errors):
        failures.append("cycle was not detected")

    overlap_plan = example_plan()
    overlap_plan["nodes"][2]["owned_paths"] = ["src/a/**"]
    overlap_report = Report()
    validate_plan(overlap_plan, overlap_report)
    if not any("unordered write overlap" in error for error in overlap_report.errors):
        failures.append("undeclared concurrent write overlap was not detected")

    if failures:
        print(json.dumps({"ok": False, "failures": failures}, indent=2))
        return 1
    print(json.dumps({"ok": True, "tests": 4}, indent=2))
    return 0


def print_human(report: Report) -> None:
    print("PASS" if not report.errors else "FAIL")
    for error in report.errors:
        print(f"ERROR: {error}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    if report.waves:
        print("WAVES:")
        for wave in report.waves:
            print(f"  {wave['wave']}: {', '.join(wave['nodes'])} ({wave['mode']})")
    if report.serialization:
        print("SEQUENTIAL CONSTRAINTS:")
        for item in report.serialization:
            nodes = ",".join(item.get("nodes", []))
            prefix = f" {nodes}" if nodes else ""
            print(f"  {item['type']}{prefix}: {item['reason']}")
    if report.node_status is not None:
        print("NODE STATUS:")
        for node_id, status in report.node_status.items():
            print(f"  {node_id}: {status}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, help="Path to dag.json")
    parser.add_argument("--events", type=Path, help="Optional events.jsonl to replay")
    parser.add_argument("--require-complete", action="store_true", help="Require all nodes integrated")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON report")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic built-in tests")
    args = parser.parse_args(argv)
    if args.self_test:
        return run_self_test()
    if args.plan is None:
        parser.error("plan is required unless --self-test is used")

    report = Report()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except OSError as exc:
        report.error(f"cannot read plan {args.plan}: {exc}")
        plan = None
    except json.JSONDecodeError as exc:
        report.error(f"invalid plan JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
        plan = None
    context = validate_plan(plan, report) if plan is not None else None
    if args.require_complete and args.events is None:
        report.error("--require-complete requires --events")
    if args.events is not None and context is not None:
        events = load_events(args.events, report)
        validate_events(events, context, report, args.require_complete)

    if args.as_json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print_human(report)
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
