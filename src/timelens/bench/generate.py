"""Random structured processes (SEQ / AND / XOR blocks) with rules, for the benchmark."""

from __future__ import annotations

from typing import Any

import numpy as np

from timelens.analysis.schedule import worst_case_schedule
from timelens.model.bpmn import BpmnModel, Flow, Node, NodeKind
from timelens.model.process import ProcessGraph
from timelens.model.rules import Rules
from timelens.stnu.build import build_stnu

Block = tuple[str, list[Any]]


def _block(n: int, depth: int, rng: np.random.Generator) -> Block:
    """Return a block tree with exactly n tasks: depth <= 4, 2 to 3 branches per split."""
    if n == 1:
        return ("TASK", [])
    if depth == 0:
        return ("SEQ", [("TASK", [])] * n)
    kind = str(rng.choice(["SEQ", "AND", "XOR"]))
    k = min(n, int(rng.integers(2, 4)))
    cuts = np.sort(rng.choice(np.arange(1, n), size=k - 1, replace=False))
    sizes = np.diff(np.concatenate([[0], cuts, [n]]))
    return (kind, [_block(int(s), depth - 1, rng) for s in sizes])


def random_model(n_tasks: int, rng: np.random.Generator) -> BpmnModel:
    """Return a random acyclic BPMN model with `n_tasks` tasks."""
    nodes = {"S": Node("S", "start", "Start"), "E": Node("E", "end", "End")}
    flows: dict[str, Flow] = {}

    def link(a: str, b: str) -> None:
        fid = f"F{len(flows)}"
        flows[fid] = Flow(fid, a, b)

    def emit(block: Block, entry: str) -> str:
        kind, children = block
        if kind == "TASK":
            tid = f"T{sum(n.kind == 'task' for n in nodes.values())}"
            nodes[tid] = Node(tid, "task", tid)
            link(entry, tid)
            return tid
        if kind == "SEQ":
            for child in children:
                entry = emit(child, entry)
            return entry
        g = f"G{len(nodes)}"
        gk: NodeKind = "and" if kind == "AND" else "xor"
        nodes[f"{g}s"], nodes[f"{g}j"] = Node(f"{g}s", gk, f"{g}s"), Node(f"{g}j", gk, f"{g}j")
        link(entry, f"{g}s")
        for child in children:
            link(emit(child, f"{g}s"), f"{g}j")
        return f"{g}j"

    link(emit(_block(n_tasks, 4, rng), "S"), "E")
    return BpmnModel("bench", nodes, flows)


def random_rules(process: ProcessGraph, rng: np.random.Generator) -> Rules:
    """Return rules: 50 % contingent tasks, random lags (upper bound only), and a deadline of
    factor * worst-case makespan with factor in [0.8, 1.2], so both DC and NOT DC models occur."""
    tasks: dict[str, Any] = {}
    for t in process.tasks:
        lo = int(rng.integers(30, 481))
        hi = lo + int(rng.integers(0, 961))
        kind = "contingent" if rng.random() < 0.5 else "controllable"
        tasks[t] = {"kind": kind, "min": lo, "max": hi}
    base = Rules.model_validate({"process_id": "bench", "tasks": tasks})
    sched = worst_case_schedule(build_stnu(process, base))
    assert sched is not None  # no upper bounds yet, so the AllMax projection is consistent
    est = {r.timepoint: r.est for r in sched.rows}
    tps = [r.timepoint for r in sched.rows if r.timepoint != "Z"]
    constraints: list[dict[str, Any]] = []
    for k in range(max(1, len(process.tasks) // 10)):  # assumption: one lag per 10 tasks
        i, j = sorted(rng.choice(len(tps), size=2, replace=False))
        x, y = tps[i], tps[j]
        gap = max(60.0, est[y] - est[x])
        constraints.append({
            "id": f"L{k}", "type": "lag", "from": _ref(x), "to": _ref(y),
            "max": int(gap * rng.uniform(1.0, 1.5))})  # assumption: lags looser than worst case
    constraints.append({"id": "C_deadline", "type": "deadline", "from": {"element": "S"},
                        "to": {"element": "E"},
                        "max": int(est[process.end] * rng.uniform(0.8, 1.2))})
    return Rules.model_validate({"process_id": "bench", "xor_outcome_known_at": "split",
                                 "tasks": tasks, "constraints": constraints})


def _ref(tp: str) -> dict[str, str]:
    element, _, side = tp.partition(":")
    return {"element": element, "point": "end" if side == "e" else "start"}
