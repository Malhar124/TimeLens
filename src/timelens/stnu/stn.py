"""STN tools: distance matrices, Floyd-Warshall (with optional provenance), Bellman-Ford."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import numpy.typing as npt

from timelens.stnu.network import STNU, ContingentLink, Edge, LinForm, weighted

Matrix = npt.NDArray[np.float64]
Coefs = npt.NDArray[np.int32]

PROVENANCE_MAX_N = 200


def distance_matrix(n: int, triples: Iterable[tuple[int, int, float]]) -> Matrix:
    """Return a dense (n, n) matrix: inf if no edge, 0 on the diagonal, min weight kept. O(n^2)."""
    D = np.full((n, n), np.inf)
    np.fill_diagonal(D, 0.0)
    for i, j, w in triples:
        if w < D[i, j]:
            D[i, j] = w
    return D


def distance_matrix_prov(
    stnu: STNU, edges: Iterable[Edge]
) -> tuple[Matrix, Coefs]:
    """Return (D, C) for `edges`: C[i, j] is the coefficient vector of D[i, j]. O(n^2 P)."""
    idx, pidx, n = stnu.index, stnu.param_index, len(stnu.timepoints)
    D = np.full((n, n), np.inf)
    np.fill_diagonal(D, 0.0)
    C = np.zeros((n, n, len(pidx)), dtype=np.int32)
    for e in edges:
        i, j, w = idx[e.src], idx[e.dst], e.weight.value(stnu.params)
        if w < D[i, j]:
            D[i, j] = w
            C[i, j] = e.weight.vector(pidx)
    return D, C


def floyd_warshall(D: Matrix) -> Matrix:
    """Return the all-pairs shortest path closure of D. O(n^3), vectorized per pivot.

    Stops early on a negative cycle; the caller checks the diagonal.
    """
    D = D.copy()
    for k in range(D.shape[0]):
        np.minimum(D, D[:, k, None] + D[None, k, :], out=D)
        # Stop at the first negative diagonal entry (any i, not only k), so its cycle stays simple.
        if (np.diagonal(D) < 0).any():
            break
    return D


def floyd_warshall_prov(D: Matrix, C: Coefs) -> tuple[Matrix, Coefs]:
    """Floyd-Warshall that keeps D[i, j] == C[i, j] @ p. O(n^3 P) worst case."""
    D, C = D.copy(), C.copy()
    for k in range(D.shape[0]):
        cand = D[:, k, None] + D[None, k, :]
        better = cand < D
        if better.any():
            i, j = np.nonzero(better)
            newC = C[i, k, :] + C[k, j, :]  # advanced indexing copies before the write
            D[i, j] = cand[i, j]
            C[i, j, :] = newC
            if (np.diagonal(D) < 0).any():
                break
    return D, C


def negative_diagonal(D: Matrix) -> int | None:
    """Return the first index with a negative diagonal entry, or None."""
    neg = np.flatnonzero(np.diagonal(D) < 0)
    return int(neg[0]) if neg.size else None


def check_invariant(D: Matrix, C: Coefs, p: npt.NDArray[np.int64]) -> None:
    """Assert D[i, j] == C[i, j, :] @ p for every finite entry."""
    finite = np.isfinite(D)
    assert np.array_equal(D[finite], (C[finite] @ p).astype(np.float64)), "provenance invariant"


def bellman_ford_cycle(
    n: int, edges: list[tuple[int, int, float]], source: int | None = None
) -> list[int] | None:
    """Return one negative cycle as a node list, or None. O(n * edges).

    `source=None` means a virtual source linked to every node, so any negative cycle is found.
    """
    dist = np.zeros(n) if source is None else np.full(n, np.inf)
    if source is not None:
        dist[source] = 0.0
    pred = [-1] * n
    last = -1
    for _ in range(n):
        last = -1
        for u, v, w in edges:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                pred[v] = u
                last = v
        if last == -1:
            return None
    v = last
    for _ in range(n):  # walk back n steps to land inside the cycle
        v = pred[v]
    cycle, u = [v], pred[v]
    while u != v:
        cycle.append(u)
        u = pred[u]
    return cycle[::-1]


def requirement_edges(links: Iterable[ContingentLink]) -> list[Edge]:
    """Return x <= C - A <= y as two ordinary edges per link."""
    out: list[Edge] = []
    for lk in links:
        out.append(Edge(lk.activation, lk.contingent, lk.upper))
        out.append(Edge(lk.contingent, lk.activation, -lk.lower))
    return out


def allmax_edges(links: Iterable[ContingentLink]) -> list[Edge]:
    """Return C - A == y (every contingent duration at its maximum) as two edges per link."""
    out: list[Edge] = []
    for lk in links:
        out.append(Edge(lk.activation, lk.contingent, lk.upper))
        out.append(Edge(lk.contingent, lk.activation, -lk.upper))
    return out


def is_consistent(stnu: STNU) -> bool:
    """Weak consistency: some choice of contingent durations satisfies every constraint. O(n^3)."""
    edges = stnu.edges + requirement_edges(stnu.links)
    D = floyd_warshall(distance_matrix(len(stnu.timepoints), weighted(stnu, edges)))
    return negative_diagonal(D) is None


def cycle_form(C: Coefs, i: int, param_ids: list[str]) -> LinForm:
    """Return the linear form stored at C[i, i]."""
    return LinForm({param_ids[k]: int(c) for k, c in enumerate(C[i, i]) if c})
