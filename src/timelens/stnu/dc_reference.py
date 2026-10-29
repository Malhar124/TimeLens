"""Dynamic controllability, slow reference engine for tests (n <= 12).

Pure Python over explicit edge sets. Applies the same five reduction rules pairwise until
nothing changes, with the same AllMax negative-cycle check every round.
"""

from __future__ import annotations

from typing import TypeVar

from timelens.stnu.dc import max_rounds
from timelens.stnu.network import STNU
from timelens.stnu.stn import bellman_ford_cycle, requirement_edges

Key = TypeVar("Key")


def _put(store: dict[Key, int], key: Key, w: int) -> bool:
    if w < store.get(key, w + 1):
        store[key] = w
        return True
    return False


def dc_check_reference(stnu: STNU) -> bool:
    """Return whether `stnu` is dynamically controllable. Roughly O(rounds * E^2)."""
    p = stnu.params
    links = [(lk.activation, lk.lower.value(p), lk.upper.value(p), lk.contingent)
             for lk in stnu.links]
    ordinary: dict[tuple[str, str], int] = {}
    upper: dict[tuple[str, int], int] = {}  # (source, link index) -> weight, target is A_m

    def put_ord(key: tuple[str, str], w: int) -> bool:
        if key[0] == key[1] and w >= 0:
            return False  # ordinary self-loops >= 0 carry no information
        return _put(ordinary, key, w)

    for e in stnu.edges + requirement_edges(stnu.links):
        put_ord((e.src, e.dst), e.weight.value(p))
    for m, (_, _, y, c) in enumerate(links):
        upper[(c, m)] = -y

    idx = stnu.index
    for _ in range(max_rounds(len(links))):
        allmax = [(idx[u], idx[v], w) for (u, v), w in ordinary.items()]
        allmax += [(idx[b], idx[links[m][0]], z) for (b, m), z in upper.items()]
        if bellman_ford_cycle(len(idx), allmax) is not None:
            return False
        new_ord: list[tuple[tuple[str, str], int]] = []
        new_up: list[tuple[tuple[str, int], int]] = []
        for (u, v), w1 in ordinary.items():
            for (v2, t), w2 in ordinary.items():  # no-case
                if v2 == v:
                    new_ord.append(((u, t), w1 + w2))
            for (b, m), z in upper.items():  # upper-case
                if b == v:
                    new_up.append(((u, m), w1 + z))
        for L, (a, x, _, c) in enumerate(links):
            for (c2, v), w in ordinary.items():  # lower-case
                if c2 == c and w < 0:
                    new_ord.append(((a, v), x + w))
            for (c2, m), z in upper.items():  # cross-case
                if c2 == c and m != L and z < 0:
                    new_up.append(((a, m), x + z))
        for (b, m), z in upper.items():  # label removal
            if z >= -links[m][1]:
                new_ord.append(((b, links[m][0]), z))
        changed = False
        for k, w in new_ord:
            changed |= put_ord(k, w)
        for k2, w in new_up:
            changed |= _put(upper, k2, w)
        if not changed:
            return True
    raise RuntimeError("reference DC check did not converge")
