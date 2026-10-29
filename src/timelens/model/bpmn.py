"""BPMN 2.0 XML parser. Reads flow nodes and sequence flows, ignores the diagram part."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree.ElementTree import Element, ParseError

import defusedxml.ElementTree as ET

from timelens.errors import ModelError

NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"

NodeKind = Literal["start", "end", "event", "task", "and", "xor"]

_KINDS: dict[str, NodeKind] = {
    "startEvent": "start",
    "endEvent": "end",
    "intermediateCatchEvent": "event",
    "intermediateThrowEvent": "event",
    "parallelGateway": "and",
    "exclusiveGateway": "xor",
    **{t: "task" for t in (
        "task", "userTask", "serviceTask", "manualTask", "scriptTask",
        "sendTask", "receiveTask", "businessRuleTask",
    )},
}
# Children of <process> that carry no control flow.
_IGNORED = {
    "laneSet", "documentation", "extensionElements", "textAnnotation", "association",
    "dataObject", "dataObjectReference", "dataStoreReference", "group", "property",
    "ioSpecification",
}


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    name: str


@dataclass(frozen=True)
class Flow:
    id: str
    src: str
    dst: str


@dataclass(frozen=True)
class BpmnModel:
    process_id: str
    nodes: dict[str, Node]
    flows: dict[str, Flow]


def _parse_process(proc: Element) -> BpmnModel:
    nodes: dict[str, Node] = {}
    flows: dict[str, Flow] = {}
    for el in proc:
        tag = el.tag.removeprefix(NS)
        el_id = el.get("id")
        if tag in _IGNORED:
            continue
        if el_id is None:
            raise ModelError(f"<{tag}> has no id")
        if el_id in nodes or el_id in flows:
            raise ModelError(f"duplicate element id {el_id}")
        if tag == "sequenceFlow":
            src, dst = el.get("sourceRef"), el.get("targetRef")
            if not src or not dst:
                raise ModelError(f"sequence flow {el_id} needs sourceRef and targetRef")
            flows[el_id] = Flow(el_id, src, dst)
        elif tag in _KINDS:
            nodes[el_id] = Node(el_id, _KINDS[tag], (el.get("name") or el_id).strip())
        else:
            raise ModelError(f"unsupported BPMN element <{tag}> (id {el_id})")
    for f in flows.values():
        for end in (f.src, f.dst):
            if end not in nodes:
                raise ModelError(f"sequence flow {f.id} refers to unknown node {end}")
    return BpmnModel(proc.get("id") or "process", nodes, flows)


def parse_bpmn(source: str | Path) -> BpmnModel:
    """Return the single process in a BPMN file (path) or XML string. Raises ModelError. O(size)."""
    try:
        if isinstance(source, Path) or not source.lstrip().startswith("<"):
            root = ET.parse(str(source)).getroot()
        else:
            root = ET.fromstring(source)
    except (ParseError, OSError) as e:
        raise ModelError(f"cannot read BPMN: {e}") from e
    if root is None:
        raise ModelError("empty BPMN document")
    procs = root.findall(f"{NS}process")
    if len(procs) != 1:
        raise ModelError(f"expected exactly one <process>, found {len(procs)}")
    return _parse_process(procs[0])
