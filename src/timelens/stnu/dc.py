"""Dynamic controllability, main engine (Morris and Muscettola, AAAI 2005), vectorized.

Ordinary edges live in a dense matrix D (O in the paper). Every upper-case edge with label M
points to A_M, so the upper-case edges of link m are one vector U[m] (U[m][v] = weight of
v -> A_m, label M).
Provenance mode keeps an integer coefficient vector for every entry, so a negative cycle can be
written as a linear form over the parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from timelens.stnu.network import STNU, LinForm, weighted
from timelens.stnu.stn import (
    PROVENANCE_MAX_N,
    Coefs,
    Matrix,
    check_invariant,
    cycle_form,
    distance_matrix,
    distance_matrix_prov,
    floyd_warshall,
    floyd_warshall_prov,
    negative_diagonal,
    requirement_edges,
)


@dataclass
class DCResult:
    dc: bool
    rounds: int
    ordinary: Matrix  # O in the paper
    upper: Matrix  # U in the paper, shape (K, n)
    conflict: LinForm | None  # negative cycle form (provenance mode only)
    where: str  # "ordinary" or "allmax" when not DC


def max_rounds(k: int) -> int:
    return 10 * (k + 1) ** 2 + 50


def _fw(D: Matrix, C: Coefs | None) -> tuple[Matrix, Coefs | None]:
    return floyd_warshall_prov(D, C) if C is not None else (floyd_warshall(D), None)


def dc_check(stnu: STNU, provenance: bool | None = None, debug: bool = False) -> DCResult:
    """Return whether `stnu` is dynamically controllable.

    D(rounds * (n^3 + K n^2 + K^2)); provenance multiplies the matrix work by P (parameters).
    Provenance defaults to on for n <= 200. `debug` asserts the provenance invariant each round.
    """
    n, K = len(stnu.timepoints), len(stnu.links)
    prov = n <= PROVENANCE_MAX_N if provenance is None else provenance
    idx, pidx, pids = stnu.index, stnu.param_index, list(stnu.params)
    pval = stnu.param_values()
    act = [idx[lk.activation] for lk in stnu.links]
    end = [idx[lk.contingent] for lk in stnu.links]
    x = [lk.lower.value(stnu.params) for lk in stnu.links]
    xv = [lk.lower.vector(pidx) for lk in stnu.links]
    ordinary = stnu.edges + requirement_edges(stnu.links)

    DP: Coefs | None
    if prov:
        D, DP = distance_matrix_prov(stnu, ordinary)
    else:
        D, DP = distance_matrix(n, weighted(stnu, ordinary)), None
    U = np.full((K, n), np.inf)
    UP: npt.NDArray[np.int32] | None = np.zeros((K, n, len(pids)), dtype=np.int32) if prov else None
    for m, lk in enumerate(stnu.links):
        U[m, end[m]] = -lk.upper.value(stnu.params)
        if UP is not None:
            UP[m, end[m]] = -lk.upper.vector(pidx)

    def fail(where: str, i: int, C: Coefs | None, rounds: int) -> DCResult:
        form = cycle_form(C, i, pids) if C is not None else None
        return DCResult(False, rounds, D, U, form, where)

    for rnd in range(1, max_rounds(K) + 1):
        D, DP = _fw(D, DP)
        if (i := negative_diagonal(D)) is not None:
            return fail("ordinary", i, DP, rnd)

        # AllMax check: upper-case edges as ordinary, lower-case edges ignored.
        M, MP = D.copy(), (DP.copy() if DP is not None else None)
        for m in range(K):
            better = U[m] < M[:, act[m]]
            M[better, act[m]] = U[m][better]
            if MP is not None and UP is not None:
                MP[better, act[m]] = UP[m][better]
        M, MP = _fw(M, MP)
        if (i := negative_diagonal(M)) is not None:
            return fail("allmax", i, MP, rnd)

        changed = False
        rows = np.arange(n)
        for m in range(K):  # upper-case: V -w-> B, B -M:z-> A_M  =>  V -M:w+z-> A_M
            S = D + U[m][None, :]
            b = S.argmin(axis=1)
            new = S[rows, b]
            v = np.flatnonzero(new < U[m])
            if v.size:
                if UP is not None and DP is not None:
                    UP[m, v] = DP[v, b[v]] + UP[m, b[v]]
                U[m, v] = new[v]
                changed = True
        for L in range(K):  # lower-case: A_L -c:x-> C_L, C_L -w-> V, w < 0  =>  A_L -x+w-> V
            row = D[end[L]]
            cand = x[L] + row
            v = np.flatnonzero((row < 0) & (cand < D[act[L]]))
            if v.size:
                if DP is not None:
                    DP[act[L], v] = xv[L] + DP[end[L], v]
                D[act[L], v] = cand[v]
                changed = True
        for L in range(K):  # cross-case: A_L -c:x-> C_L, C_L -M:z-> A_M, z < 0, M != L
            for m in range(K):
                z = U[m, end[L]]
                if m != L and z < 0 and x[L] + z < U[m, act[L]]:
                    if UP is not None:
                        UP[m, act[L]] = xv[L] + UP[m, end[L]]
                    U[m, act[L]] = x[L] + z
                    changed = True
        for m in range(K):  # label removal: B -M:z-> A_M with z >= -x_M  =>  B -z-> A_M
            v = np.flatnonzero((U[m] >= -x[m]) & (U[m] < D[:, act[m]]))
            if v.size:
                if DP is not None and UP is not None:
                    DP[v, act[m]] = UP[m, v]
                D[v, act[m]] = U[m, v]
                changed = True

        if debug and DP is not None and UP is not None:
            check_invariant(D, DP, pval)
            for m in range(K):
                check_invariant(U[m][None, :], UP[m][None, :], pval)
        if not changed:
            return DCResult(True, rnd, D, U, None, "")
    raise RuntimeError("DC check did not converge")  # weights only decrease: this is a bug
