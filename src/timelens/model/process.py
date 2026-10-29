"""ProcessGraph: structural validation and XOR scenario enumeration."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from timelens.errors import ModelError
from timelens.model.bpmn import BpmnModel, Flow, Node, parse_bpmn
from timelens.model.rules import Rules, load_rules

SCENARIO_CAP = 256


@dataclass(frozen=True)
class Scenario:
    name: str
    nodes: frozenset[str]
    flows: frozenset[str]


class ProcessGraph:
    """A validated, acyclic process with one start and one end event."""

    def __init__(self, model: BpmnModel) -> None:
        self.process_id = model.process_id
        self.nodes: dict[str, Node] = model.nodes
        self.flows: dict[str, Flow] = model.flows
        self.out_flows: dict[str, list[str]] = {n: [] for n in self.nodes}
        self.in_flows: dict[str, list[str]] = {n: [] for n in self.nodes}
        for f in self.flows.values():
            self.out_flows[f.src].append(f.id)
            self.in_flows[f.dst].append(f.id)
        self._validate()
        self.topo = self._topo_order()
        self._check_reachability()

    @property
    def start(self) -> str:
        return next(n.id for n in self.nodes.values() if n.kind == "start")

    @property
    def end(self) -> str:
        return next(n.id for n in self.nodes.values() if n.kind == "end")

    @property
    def tasks(self) -> list[str]:
        return [n for n in self.topo if self.nodes[n].kind == "task"]

    def _validate(self) -> None:
        for kind in ("start", "end"):
            found = [n.id for n in self.nodes.values() if n.kind == kind]
            if len(found) != 1:
                raise ModelError(f"expected exactly one {kind} event, found {found or 'none'}")
        for n in self.nodes.values():
            n_in, n_out = len(self.in_flows[n.id]), len(self.out_flows[n.id])
            if n.kind in ("and", "xor"):
                if n_in > 1 and n_out > 1:
                    raise ModelError(f"gateway {n.id} is both a split and a join")
            elif n.kind == "start" and (n_in, n_out) != (0, 1):
                raise ModelError(f"start event {n.id} needs no incoming and one outgoing flow")
            elif n.kind == "end" and (n_in, n_out) != (1, 0):
                raise ModelError(f"end event {n.id} needs one incoming and no outgoing flow")
            elif n.kind in ("task", "event") and (n_in, n_out) != (1, 1):
                # shortcut: implicit splits/joins on tasks are rejected; use explicit gateways.
                raise ModelError(f"{n.id} needs exactly one incoming and one outgoing flow "
                                 f"(use a gateway to split or join)")

    def _topo_order(self) -> list[str]:
        indeg = {n: len(fs) for n, fs in self.in_flows.items()}
        queue = deque(n for n, d in indeg.items() if d == 0)
        order: list[str] = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for f in self.out_flows[n]:
                dst = self.flows[f].dst
                indeg[dst] -= 1
                if indeg[dst] == 0:
                    queue.append(dst)
        if len(order) != len(self.nodes):
            cyclic = sorted(n for n, d in indeg.items() if d > 0)
            raise ModelError(f"the flow graph has a loop through {', '.join(cyclic)}")
        return order

    def _check_reachability(self) -> None:
        def reach(start: str, forward: bool) -> set[str]:
            seen, stack = {start}, [start]
            while stack:
                n = stack.pop()
                for f in (self.out_flows if forward else self.in_flows)[n]:
                    m = self.flows[f].dst if forward else self.flows[f].src
                    if m not in seen:
                        seen.add(m)
                        stack.append(m)
            return seen

        every = set(self.nodes)
        bad = (every - reach(self.start, True)) | (every - reach(self.end, False))
        if bad:
            raise ModelError(f"elements not on a path from start to end: {', '.join(sorted(bad))}")

    def union(self) -> Scenario:
        """Every node and flow active: XOR branches all taken, XOR joins act as AND joins."""
        return Scenario("union", frozenset(self.nodes), frozenset(self.flows))

    def has_xor(self) -> bool:
        return any(n.kind == "xor" and len(self.out_flows[n.id]) > 1 for n in self.nodes.values())

    def scenarios(self, cap: int = SCENARIO_CAP) -> list[Scenario] | None:
        """Return every XOR scenario, or None if there are more than `cap`.

        Raises ModelError if some XOR choice activates an AND join partially or an XOR join
        more than once. O(cap * nodes) states.
        """
        # state: (active flows, active nodes, choices made)
        states: list[tuple[frozenset[str], frozenset[str], tuple[str, ...]]] = [
            (frozenset(), frozenset(), ())
        ]
        for n in self.topo:
            node, outs = self.nodes[n], self.out_flows[n]
            new_states = []
            for flows, nodes, choices in states:
                ins = [f for f in self.in_flows[n] if f in flows]
                if n != self.start and not ins:
                    new_states.append((flows, nodes, choices))
                    continue
                if node.kind == "and" and len(ins) != len(self.in_flows[n]):
                    raise ModelError(f"AND join {n} can be reached by only some branches "
                                     f"(XOR choices: {', '.join(choices)})")
                if node.kind == "xor" and len(self.in_flows[n]) > 1 and len(ins) != 1:
                    raise ModelError(f"XOR join {n} can be reached by more than one branch")
                if node.kind == "xor" and len(outs) > 1:
                    for f in outs:
                        label = f"{node.name}={self.nodes[self.flows[f].dst].name}"
                        new_states.append((flows | {f}, nodes | {n}, (*choices, label)))
                else:
                    new_states.append((flows | set(outs), nodes | {n}, choices))
            if len(new_states) > cap:
                return None
            states = new_states
        return [
            Scenario(", ".join(choices) or "default", nodes, flows)
            for flows, nodes, choices in states
        ]


def load_process(path: str | Path) -> ProcessGraph:
    """Return the validated process in the BPMN file at `path`. Raises ModelError."""
    return ProcessGraph(parse_bpmn(Path(path)))


def load_model(bpmn_path: str | Path, rules_path: str | Path) -> tuple[ProcessGraph, Rules]:
    """Return the process and its rules, checked against each other. Raises Model/RulesError."""
    process, rules = load_process(bpmn_path), load_rules(rules_path)
    rules.check_against(set(process.tasks), set(process.nodes), set(process.flows))
    return process, rules
