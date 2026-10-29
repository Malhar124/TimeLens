"""Strong controllability (Vidal and Fargier 1999): one fixed schedule for all durations."""

from __future__ import annotations

from dataclasses import dataclass

from timelens.stnu.network import STNU, Edge, LinForm, weighted
from timelens.stnu.stn import (
    PROVENANCE_MAX_N,
    cycle_form,
    distance_matrix,
    distance_matrix_prov,
    floyd_warshall,
    floyd_warshall_prov,
    negative_diagonal,
)


@dataclass(frozen=True)
class SCResult:
    controllable: bool
    conflict: LinForm | None  # negative cycle form, if not SC and provenance was on


def executable_reduction(stnu: STNU) -> STNU:
    """Return the STN over executable timepoints that is consistent iff `stnu` is SC. O(edges).

    Edge X -> Y (Y - X <= w) with C = A + d, d in [x, y]: replace a contingent end by its
    activation; the weight becomes w - y_Y + x_X so it holds for every duration.
    """
    by_end = {lk.contingent: lk for lk in stnu.links}
    edges = []
    for e in stnu.edges:
        src, dst, w = e.src, e.dst, e.weight
        if src in by_end:
            w, src = w + by_end[src].lower, by_end[src].activation
        if dst in by_end:
            w, dst = w + -by_end[dst].upper, by_end[dst].activation
        edges.append(Edge(src, dst, w))  # a self-loop must be >= 0; FW sees it on the diagonal
    tps = [t for t in stnu.timepoints if t not in by_end]
    return STNU(tps, edges, [], stnu.params, {t: stnu.origin[t] for t in tps})


def strong_controllability(stnu: STNU, provenance: bool | None = None) -> SCResult:
    """Return whether `stnu` is strongly controllable. O(n^3), O(n^3 P) with provenance."""
    red = executable_reduction(stnu)
    n = len(red.timepoints)
    if provenance is None:
        provenance = n <= PROVENANCE_MAX_N
    if not provenance:
        D = floyd_warshall(distance_matrix(n, weighted(red, red.edges)))
        return SCResult(negative_diagonal(D) is None, None)
    D, C = floyd_warshall_prov(*distance_matrix_prov(red, red.edges))
    i = negative_diagonal(D)
    if i is None:
        return SCResult(True, None)
    return SCResult(False, cycle_form(C, i, list(red.params)))
