"""Small STNU builders for tests. All values in minutes."""

from timelens.model.process import load_model
from timelens.stnu.build import build_stnu
from timelens.stnu.network import STNU, ZERO, ContingentLink, Edge, LinForm, Param


def make_stnu(timepoints, req, links=()):
    """req: (src, dst, w) meaning dst - src <= w; links: (A, x, y, C). One param per number."""
    params = {"const.zero": Param("const.zero", 0, "zero")}
    edges, lks = [], []
    for k, (s, d, w) in enumerate(req):
        params[f"e{k}"] = Param(f"e{k}", w, f"edge {k}")
        edges.append(Edge(s, d, LinForm.of(f"e{k}")))
    for k, (a, x, y, c) in enumerate(links):
        params[f"l{k}.min"] = Param(f"l{k}.min", x, f"link {k} min")
        params[f"l{k}.max"] = Param(f"l{k}.max", y, f"link {k} max")
        lks.append(ContingentLink(a, c, LinForm.of(f"l{k}.min"), LinForm.of(f"l{k}.max")))
    edges += [Edge(t, "Z", ZERO) for t in timepoints[1:]]
    return STNU(list(timepoints), edges, lks, params, {t: t for t in timepoints})


def example_stnu(paths, values=None) -> STNU:
    process, rules = load_model(*paths)
    return build_stnu(process, rules, values=values)
