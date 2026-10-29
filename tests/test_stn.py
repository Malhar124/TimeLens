import numpy as np

from tests.helpers import example_stnu
from timelens.stnu.network import weighted
from timelens.stnu.stn import (
    bellman_ford_cycle,
    check_invariant,
    distance_matrix,
    distance_matrix_prov,
    floyd_warshall,
    floyd_warshall_prov,
    is_consistent,
    negative_diagonal,
    requirement_edges,
)


def test_floyd_warshall_agrees_with_bellman_ford_on_random_graphs():
    rng = np.random.default_rng(7)
    found_cycles = 0
    for _ in range(500):
        n = int(rng.integers(2, 9))
        m = int(rng.integers(1, n * n))
        edges = [(int(rng.integers(n)), int(rng.integers(n)), int(rng.integers(-10, 20)))
                 for _ in range(m)]
        edges = [(u, v, w) for u, v, w in edges if u != v]
        fw_neg = negative_diagonal(floyd_warshall(distance_matrix(n, edges))) is not None
        cycle = bellman_ford_cycle(n, edges)
        assert fw_neg == (cycle is not None)
        if cycle:
            found_cycles += 1
            ring = cycle + cycle[:1]
            best = {(u, v): min(w for a, b, w in edges if (a, b) == (u, v))
                    for u, v in zip(ring, ring[1:], strict=False)}
            assert sum(best.values()) < 0
    assert found_cycles > 50  # both outcomes are exercised


def test_provenance_invariant_holds(minimal_paths, full_paths):
    for paths in (minimal_paths, full_paths):
        stnu = example_stnu(paths)
        D, C = distance_matrix_prov(stnu, stnu.edges + requirement_edges(stnu.links))
        D, C = floyd_warshall_prov(D, C)
        check_invariant(D, C, stnu.param_values())
        assert np.array_equal(D, floyd_warshall(distance_matrix(
            len(stnu.timepoints), weighted(stnu, stnu.edges + requirement_edges(stnu.links)))))


def test_examples_are_consistent(minimal_paths, full_paths):
    assert is_consistent(example_stnu(minimal_paths))
    assert is_consistent(example_stnu(full_paths))


def test_minimal_is_inconsistent_with_a_two_day_deadline(minimal_paths):
    assert not is_consistent(example_stnu(minimal_paths, {"C_deadline.max": 2880}))
