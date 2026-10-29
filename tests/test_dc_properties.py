import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import make_stnu
from timelens.stnu.dc import dc_check
from timelens.stnu.dc_reference import dc_check_reference
from timelens.stnu.network import weighted
from timelens.stnu.sc import strong_controllability
from timelens.stnu.stn import distance_matrix, floyd_warshall, is_consistent, negative_diagonal

PROFILE = settings(max_examples=500, deadline=None, derandomize=True)


@st.composite
def stnus(draw):
    n = draw(st.integers(3, 8))
    tps = ["Z"] + [f"T{i}" for i in range(1, n)]
    k = draw(st.integers(0, min(2, (n - 1) // 2)))
    others = draw(st.permutations(tps[1:]))
    ends = list(others[:k])
    execs = [t for t in tps if t not in ends]
    links = []
    for c in ends:
        a = draw(st.sampled_from(execs))
        x = draw(st.integers(0, 20))
        y = draw(st.integers(x, 20))
        links.append((a, x, y, c))
    pairs = st.tuples(st.sampled_from(tps), st.sampled_from(tps), st.integers(-20, 20))
    req = [(s, d, w) for s, d, w in draw(st.lists(pairs, max_size=12)) if s != d]
    return make_stnu(tps, req, links)


def projection_consistent(stnu, durations) -> bool:
    """Fix every contingent duration and check the plain STN."""
    idx = stnu.index
    triples = weighted(stnu, stnu.edges)
    for lk, d in zip(stnu.links, durations, strict=True):
        a, c = idx[lk.activation], idx[lk.contingent]
        triples += [(a, c, d), (c, a, -d)]
    D = floyd_warshall(distance_matrix(len(stnu.timepoints), triples))
    return negative_diagonal(D) is None


def bounds(stnu):
    return [(lk.lower.value(stnu.params), lk.upper.value(stnu.params)) for lk in stnu.links]


@PROFILE
@given(stnus())
def test_engines_agree_and_verdicts_are_ordered(stnu):
    res = dc_check(stnu, provenance=True, debug=True)  # debug asserts D == C @ p every round
    assert res.dc == dc_check_reference(stnu)
    assert res.dc == dc_check(stnu, provenance=False).dc
    consistent = projection_consistent(stnu, []) if not stnu.links else None
    if strong_controllability(stnu).controllable:
        assert res.dc
    if res.dc:
        assert is_consistent(stnu)
    if not is_consistent(stnu):
        assert not res.dc
    if consistent is not None:
        assert consistent == res.dc  # no links: DC is plain STN consistency
    if not res.dc:
        assert res.conflict is not None and res.conflict.value(stnu.params) < 0


@PROFILE
@given(stnus(), st.integers(0, 2**32 - 1))
def test_dc_implies_projections_are_consistent(stnu, seed):
    if not dc_check(stnu).dc:
        return
    b = bounds(stnu)
    rng = np.random.default_rng(seed)
    projections = [[x for x, _ in b], [y for _, y in b]]
    projections += [[int(rng.integers(x, y + 1)) for x, y in b] for _ in range(5)]
    for durations in projections:
        assert projection_consistent(stnu, durations)


@PROFILE
@given(stnus(), st.integers(1, 5))
def test_monotonicity(stnu, step):
    dc = dc_check(stnu).dc
    if stnu.links:
        lo, up = bounds(stnu)[0]
        wider = {"l0.max": up + step} if lo == 0 else {"l0.min": max(0, lo - step)}
        if not dc:
            assert not dc_check(stnu.with_values(wider)).dc
    if "e0" in stnu.params and dc:
        looser = stnu.with_values({"e0": stnu.params["e0"].value + step})
        assert dc_check(looser).dc
