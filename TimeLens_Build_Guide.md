# TimeLens Build Guide

Build instructions for the project "Modeling Time-Dependent Business Processes and Analyzing Temporal Constraints".
Proposed solution name: **TimeLens**.

This file is written for Claude Code. Put it in the root of an empty repository. Rename it to `CLAUDE.md` if you want Claude Code to load it automatically, or tell Claude Code: "Read TimeLens_Build_Guide.md and do Phase 0."

---

## 0. Instructions for Claude Code

Read this whole file before you write code. Then obey these rules:

1. Build the project **phase by phase** (Section 12). Do not start a phase before the tests of the previous phase pass.
2. After each phase, run `ruff check .`, `mypy src`, and `pytest -q`. All must pass. Report the result to the user in 2 to 4 lines.
3. Do not invent data. If an activity name, a file, or a number is not in this guide or in the data, stop and ask the user.
4. All costs in this project are **assumptions**. Keep them only in config files. Label them as assumptions in every report.
5. Tests must not use the network. Tests must be deterministic (fixed random seeds).
6. Store all time values as **integer minutes**. Never store time as float in the model layer. (NumPy arrays may use `float64` with `inf`, because integers up to 2^53 are exact in `float64`.)
7. When this guide says "MUST", it is a requirement. When it says "SHOULD", it is a strong default. When it says "OPTIONAL", do it only if time allows or the user asks.
8. If a requirement in this guide seems wrong, do not silently change it. Tell the user what you found and propose a fix.
9. Do not commit to git unless the user asks.

---

## 1. Project summary

### 1.1 Problem

Business processes have time rules: task durations, minimum and maximum gaps between tasks, and deadlines. Some durations are not under the control of the organization. For example, the customer decides how long a document upload takes. BPMN can draw the tasks but cannot check if all time rules can always hold together.

**Problem statement.** Given a BPMN process model with controllable and uncontrollable (contingent) task durations, time gaps, and deadlines, decide at **design time** whether every case can always finish within its rules (**dynamic controllability**). If not, find the conflicting rules, explain them in business terms, and compute the cheapest repair.

### 1.2 The TimeLens pipeline

```
 Event log (BPI 2017)          BPMN model + time rules (JSON)
        |                                 |
        v                                 |
 [1] CALIBRATE  ---- duration ranges ---->|
                                          v
                                    [2] MAP: BPMN -> STNU
                                          |
                                          v
                                    [3] CHECK: consistency, SC, DC
                                          |
                     +--------------------+--------------------+
                     | DC                                      | NOT DC
                     v                                         v
              schedule, slack,                        [4] REPAIR: conflict ->
              critical path                               linear cut -> LP ->
                     |                                        cheapest levers
                     v                                         |
              [5] DECIDE + ALERT <-----------------------------+
              risk vs cost frontier, run-time alert thresholds,
              replay on real cases (precision, recall, lead time)
```

Steps 1, 4 and 5 are the new contribution. Steps 2 and 3 follow published methods.

### 1.3 What is new (keep this claim honest)

Each building block exists in the literature. The contribution is the combination:

- contingent duration ranges learned from a real event log, with a coverage level alpha as a risk knob;
- repair of a BPMN model at minimum business cost, with conflict-directed linear cuts (this idea follows CDRU by Yu, Fang and Williams, ICAPS 2014; credit it);
- a risk vs cost frontier for the manager;
- run-time alert thresholds derived from the design-time network, validated by replay on a real event log.

---

## 2. Glossary

| Term | Meaning |
| --- | --- |
| Timepoint | A moment in time: the start or end of a task, or an event. |
| Z | The reference timepoint. Time 0 of a case. It is the start event. |
| Requirement constraint | `l <= Y - X <= u`. The scheduler must satisfy it. |
| Contingent link | `(A, x, y, C)`: C happens between x and y after A. Nature picks the value. A is the activation, C is the contingent end. |
| Executable timepoint | A timepoint the scheduler decides. Every timepoint except contingent ends. |
| STN | Simple Temporal Network. Only requirement constraints. |
| STNU | STN with Uncertainty. Requirement constraints plus contingent links. |
| Distance graph | Edge `X -> Y` with weight `w` means `Y - X <= w`. |
| Consistent | Some choice of all durations satisfies all constraints (weak check). |
| Strong controllability (SC) | One fixed schedule of executable timepoints works for all contingent durations. |
| Dynamic controllability (DC) | A reactive strategy works for all contingent durations. A decision may use only what has already happened. |
| AllMax projection | Every contingent duration set to its maximum. |
| Lever | A business action that changes one time bound, with a cost. |
| alpha | Coverage level for calibration. alpha = 0.95 means the range covers 95% of observed durations. |

Relation that MUST hold: SC implies DC, and DC implies consistent.

---

## 3. Tech stack

| Purpose | Tool | Minimum version |
| --- | --- | --- |
| Language | Python | 3.11 |
| Arrays | numpy | 1.26 |
| LP solver | scipy (`scipy.optimize.linprog`, method `"highs"`) | 1.11 |
| Tables | pandas | 2.1 |
| Event log reading | pm4py | 2.7 |
| Config and schema validation | pydantic | 2.5 |
| YAML | pyyaml | 6.0 |
| Safe XML parsing | defusedxml | 0.7 |
| CLI | typer | 0.12 |
| Plots | matplotlib | 3.8 |
| Parquet cache | pyarrow | 14 |
| Tests | pytest, hypothesis | 8.0, 6.100 |
| Lint and types | ruff, mypy | current |
| OPTIONAL baseline | UPPAAL `verifyta` (free academic licence, installed by the user) | any |
| OPTIONAL oracle | CSTNU Tool by R. Posenato, University of Verona (Java). Find it from the TimeAwareBPMN wiki: https://gitlab.com/univr.di/TimeAwareBPMN/-/wikis/home | any |
| OPTIONAL modeling | bpmn.io web modeler, `bpmn-auto-layout` (npm) for diagram layout | any |

Use a `src/` layout and `pyproject.toml` with a `timelens` console script.

---

## 4. Repository layout

```
timelens/
  pyproject.toml
  README.md
  CLAUDE.md                      (this guide, optional rename)
  .gitignore                     (data/, results/, .venv/, __pycache__/)
  config/
    levers_loan.yaml
    levers_bpi2017.yaml
    mapping_bpi2017.yaml
  examples/
    loan_minimal/  loan_minimal.bpmn  loan_minimal.rules.json
    loan_full/     loan_full.bpmn     loan_full.rules.json
    bpi2017/       loan_bpi.bpmn      loan_bpi.rules.template.json
  data/                          (not in git; BPI 2017 log goes here)
  results/                       (not in git; all outputs)
  src/timelens/
    __init__.py
    units.py                     time parsing and formatting
    model/
      rules.py                   pydantic schema for the rules JSON
      bpmn.py                    BPMN XML parser
      process.py                 ProcessGraph, validation, XOR scenarios
    stnu/
      network.py                 STNU data structure and parameters
      build.py                   ProcessGraph + rules -> STNU
      stn.py                     Floyd-Warshall, Bellman-Ford, cycle extraction
      sc.py                      strong controllability
      dc.py                      vectorized DC check (main engine, optional provenance)
      dc_reference.py            slow pairwise DC check for tests
      dc_morris14.py             OPTIONAL O(n^3) DC check
    analysis/
      schedule.py                EST, LST, slack, critical path
      conflict.py                conflict extraction and business text
      repair.py                  LP repair loop
      frontier.py                risk vs cost frontier
      alerts.py                  latest safe times, monitor, replay
    mining/
      log.py                     load, cache, split the event log
      calibrate.py               duration ranges from the log
    bench/
      generate.py                random structured process generator
      run.py                     timing benchmark
    baseline/
      uppaal.py                  OPTIONAL UPPAAL export and run
    report/
      text.py                    console and markdown reports
      plots.py                   PNG plots
    cli.py                       typer commands
  tests/
    test_units.py  test_rules.py  test_bpmn.py  test_process.py
    test_stn.py  test_sc.py  test_dc_known.py  test_dc_properties.py
    test_schedule.py  test_conflict.py  test_repair.py
    test_calibrate.py  test_alerts.py  test_frontier.py  test_cli.py
```

---

## 5. Input formats

### 5.1 Time values

Accept strings `"<number><unit>"` with unit `m` (minute), `h` (hour), `d` (day = 1440 m), `w` (week = 7 d). Also accept a plain integer (minutes) and `"0"`. Regex: `^\s*(\d+(?:\.\d+)?)\s*([mhdw]?)\s*$`. Convert to integer minutes. If the result is not an integer number of minutes, raise `ValueError`. Elapsed calendar time only. Working calendars are out of scope.

`units.py` MUST also give `format_minutes(m: int) -> str` that prints `"1 d 4 h 30 m"` style text (omit zero parts, `"0 m"` for zero, a `-` sign for negative values).

### 5.2 BPMN file

Standard BPMN 2.0 XML. Namespace `http://www.omg.org/spec/BPMN/20100524/MODEL`. Parse with `defusedxml.ElementTree`. Ignore the diagram interchange part (`bpmndi`).

Supported elements:

| BPMN element | Treatment |
| --- | --- |
| `startEvent` | Exactly one per process. Becomes Z. |
| `endEvent` | Exactly one per process. One timepoint. |
| `intermediateCatchEvent`, `intermediateThrowEvent` | One timepoint. |
| `task`, `userTask`, `serviceTask`, `manualTask`, `scriptTask`, `sendTask`, `receiveTask`, `businessRuleTask` | Two timepoints: start and end. |
| `parallelGateway` | One timepoint. Split if it has more than one outgoing flow, join if more than one incoming flow. |
| `exclusiveGateway` | One timepoint. Split or join as above. |
| `sequenceFlow` | Precedence with default gap `[0, inf)`. |

Reject with a clear error: any other flow node type, loops (the flow graph MUST be acyclic), more than one start or end event, a gateway that is both split and join, and elements not reachable from the start or not able to reach the end. Use the `name` attribute as the business label. If no name, use the id.

### 5.3 Time rules file (`*.rules.json`)

The BPMN file stays standard. Time rules live in a side file, keyed by BPMN element id.

```json
{
  "process_id": "loan_minimal",
  "xor_outcome_known_at": "start",
  "tasks": {
    "Task_Upload":   {"kind": "contingent",   "owner": "customer", "min": "1d", "max": "5d"},
    "Task_KYC":      {"kind": "contingent",   "owner": "staff",    "min": "1d", "max": "2d"},
    "Task_Approval": {"kind": "controllable", "owner": "staff",    "min": "1d", "max": "1d"}
  },
  "constraints": [
    {
      "id": "C_deadline",
      "type": "deadline",
      "label": "Decision within 7 days of application",
      "from": {"element": "StartEvent_1", "point": "start"},
      "to":   {"element": "EndEvent_1",   "point": "end"},
      "max": "7d"
    }
  ],
  "flow_gaps": [
    {"flow": "Flow_3", "min": "0", "max": "4h"}
  ]
}
```

Schema rules (enforce in `model/rules.py` with pydantic):

- `kind` is `"contingent"` or `"controllable"`. `0 <= min <= max`. A contingent task MUST have `min < max` or `min == max` (equal means fixed; treat a fixed contingent as controllable with a warning).
- Every task in the BPMN MUST have an entry. A task with no entry is an error, not a silent default.
- `point` is `"start"` or `"end"`. For events and gateways both points are the same timepoint.
- Constraint `type` is `"deadline"` (only `max`, measured from `from` to `to`) or `"lag"` (`min`, `max`, or both). A missing `max` means no upper bound. A missing `min` means no lower bound.
- `flow_gaps` overrides the default gap `[0, inf)` of a sequence flow. `min` MUST be `>= 0`.
- `xor_outcome_known_at` is `"start"` (the outcome is fixed by case data at the start, for example the loan amount) or `"split"` (the outcome is revealed when the split happens). Default `"split"`.
- Constraint ids and element ids MUST be unique and MUST exist.

**Modeling rule (important).** A task done by people normally has an uncertain duration. Model it as `contingent`. Use `controllable` only when the organization truly fixes the duration. Reason: if a duration is controllable, the scheduler can always pick its minimum, so its maximum never causes a conflict. In the loan example, KYC MUST be contingent, or the example is not a conflict.

### 5.4 Parameters

Every number in the rules file is a **parameter** with a stable id:

| Source | Parameter ids |
| --- | --- |
| Task duration | `<task_id>.min`, `<task_id>.max` |
| Constraint | `<constraint_id>.min`, `<constraint_id>.max` |
| Flow gap | `<flow_id>.min`, `<flow_id>.max` |
| Constant zero (default gaps, gateway joins) | `const.zero` |

Every edge weight in the STNU MUST be a linear form `sum(coef * param)`, with integer coefficients. This is needed for conflict explanation and repair.

### 5.5 Levers file (`levers_*.yaml`)

```yaml
currency: INR
assumption_note: "All costs are illustrative assumptions, not real bank data."
granularity: 1h            # round repairs to this step
levers:
  - id: add_kyc_staff
    label: "Add one KYC officer"
    param: Task_KYC.max
    direction: decrease
    cost_per_day: 20000
    max_change: 1d
  - id: nudge_customer
    label: "Send reminders to the customer"
    param: Task_Upload.max
    direction: decrease
    cost_per_day: 30000
    max_change: 2d
  - id: extend_deadline
    label: "Extend the decision deadline (SLA penalty)"
    param: C_deadline.max
    direction: increase
    cost_per_day: 50000
    max_change: 3d
```

Rules: `direction` is `increase` or `decrease`. `max_change >= 0`. A decrease of a `*.max` parameter MUST NOT go below the matching `*.min`. An increase of a `*.min` MUST NOT go above the matching `*.max`. Parameters with no lever are fixed during repair.

---

## 6. Mapping BPMN to an STNU (`stnu/build.py`)

### 6.1 Timepoints

- Start event: one timepoint `Z`.
- End event, intermediate events, gateways: one timepoint `<id>`.
- Task: `<id>:s` and `<id>:e`.

### 6.2 Edges

Write constraints as distance-graph edges. `X -> Y` weight `w` means `Y - X <= w`.

| Source | Edges |
| --- | --- |
| Controllable task `[l, u]` | `T:s -> T:e` weight `u`; `T:e -> T:s` weight `-l` |
| Contingent task `[x, y]` | contingent link `(T:s, x, y, T:e)` |
| Sequence flow `P -> S` with gap `[g1, g2]` | `S_in -> P_out` weight `-g1`; if `g2` finite, `P_out -> S_in` weight `g2`. `P_out` is the end point of P, `S_in` is the start point of S. |
| Lag `[l, u]` from X to Y | `X -> Y` weight `u` (if given); `Y -> X` weight `-l` (if given) |
| Deadline `max D` from X to Y | `X -> Y` weight `D` |

Every timepoint `X` other than `Z` also gets `X -> Z` weight `0` (nothing happens before the case starts).

### 6.3 Gateways and XOR scenarios

- AND split and AND join: normal precedence edges as in 6.2. The join gets one edge from each incoming branch.
- XOR split: in a **scenario**, exactly one outgoing branch is active.
- A scenario is valid if every active AND join has all incoming flows active and every active XOR join has exactly one incoming flow active. Reject the model if some choice of XOR outcomes gives an invalid scenario.
- Constraints that touch an inactive element are dropped in that scenario.
- Cap the number of scenarios at 256. Above the cap, skip the exact per-scenario check and use only the union check (below).

**Verdict with XOR (`xor_outcome_known_at`):**

- `"start"`: the process is DC if and only if every scenario STNU is DC. This is exact.
- `"split"`: per-scenario DC is **necessary** but not sufficient, because the scheduler must act the same way before the split in all scenarios. Also build the **union network**: all XOR branches active at once, each XOR join treated as an AND join, all constraints kept. Union DC is **sufficient**. Report:
  - `DC` if the union is DC;
  - `NOT_DC` if some scenario is not DC;
  - `UNKNOWN_XOR` otherwise. In this case, if the CSTNU Tool oracle is configured, call it; else report `UNKNOWN_XOR` with the explanation above.

Write a short proof comment in `build.py` for both claims. (Necessary: a strategy for the process restricted to one scenario is a strategy for that scenario. Sufficient: every scenario constraint is also in the union, and a scenario join constraint is weaker than the union join constraint, so a union strategy satisfies each scenario.)

### 6.4 Data structure (`stnu/network.py`)

```python
@dataclass(frozen=True)
class Param:
    id: str
    value: int              # minutes
    label: str              # business text, e.g. "KYC check: maximum duration"

@dataclass(frozen=True)
class LinForm:
    coefs: Mapping[str, int]    # param id -> integer coefficient
    def value(self, params: Mapping[str, Param]) -> int: ...

@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    weight: LinForm

@dataclass(frozen=True)
class ContingentLink:
    activation: str
    contingent: str
    lower: LinForm          # x
    upper: LinForm          # y

@dataclass
class STNU:
    timepoints: list[str]           # index 0 MUST be "Z"
    edges: list[Edge]
    links: list[ContingentLink]
    params: dict[str, Param]
    origin: dict[str, str]          # timepoint -> BPMN element id
```

Validation in the constructor: each contingent end has exactly one contingent link; the activation of a link is executable (it is not a contingent end of another link); no timepoint is both; parameter values satisfy `0 <= lower <= upper` for each link.

---

## 7. Algorithms

### 7.1 STN tools (`stnu/stn.py`)

Use a dense `float64` matrix `D` of shape `(n, n)`, `inf` where no edge, `0` on the diagonal. Keep the minimum weight if two edges join the same pair.

```python
def floyd_warshall(D: np.ndarray) -> np.ndarray:
    D = D.copy()
    for k in range(D.shape[0]):
        np.minimum(D, D[:, k, None] + D[None, k, :], out=D)
        if D[k, k] < 0:
            break                      # negative cycle found; caller checks the diagonal
    return D
```

- Consistent if and only if no diagonal value is negative.
- Also give `bellman_ford_cycle(n, edges, source) -> list[int] | None` that returns one negative cycle as a node list (use predecessor tracking; walk back `n` steps to enter the cycle, then collect it). Use it only for display.
- Unit tests MUST compare Floyd-Warshall verdicts with Bellman-Ford verdicts on random graphs.

**Provenance mode.** Keep a coefficient tensor `C` of shape `(n, n, P)` (`int32`) next to `D`, where `P` is the number of parameters. Invariant: `D[i, j] == C[i, j, :] @ p` for every finite `D[i, j]`. In the Floyd-Warshall loop, compute all right-hand sides before any write:

```python
cand = D[:, k, None] + D[None, k, :]
better = cand < D
if better.any():
    i, j = np.nonzero(better)
    newC = C[i, k, :] + C[k, j, :]     # advanced indexing returns copies
    D[i, j] = cand[i, j]
    C[i, j, :] = newC
```

Add a debug assertion helper `check_invariant(D, C, p)` and call it in tests. Provenance mode is for networks with `n <= 200` timepoints. Above that, run without provenance.

### 7.2 Consistency (weak) check

Treat every contingent link `(A, x, y, C)` as a requirement `x <= C - A <= y`. Run Floyd-Warshall. Report `consistent: true/false`.

### 7.3 Strong controllability (`stnu/sc.py`)

Method of Vidal and Fargier (1999). Write each contingent end as `C = A + d`, with `d` in `[x, y]`. For every requirement edge `X -> Y` weight `w` (that is, `Y - X <= w`):

- Replace X by its activation if X is a contingent end, and Y likewise.
- The constraint must hold for all durations, so the new weight is `w - y_Y + x_X`, where `y_Y` is the upper bound of Y's link (0 if Y is executable) and `x_X` is the lower bound of X's link (0 if X is executable).
- Add the edge between the two executable timepoints. If both become the same timepoint, the new weight MUST be `>= 0`, else SC fails.

Drop the contingent links. SC holds if and only if the resulting STN over executable timepoints is consistent. The linear forms MUST be built the same way, so conflicts can also be explained for SC.

### 7.4 Dynamic controllability, main engine (`stnu/dc.py`)

Reference: P. Morris and N. Muscettola, "Temporal Dynamic Controllability Revisited", AAAI 2005. Labeled distance graph with these edge kinds:

- **Ordinary** edge `X -> Y` weight `w`.
- **Lower-case** edge for link `L = (A, x, y, C)`: `A -> C` value `x`, label `c`.
- **Upper-case** edge for link `L`: `C -> A` value `-y`, label `C`.
- Each link also adds ordinary edges `A -> C` weight `y` and `C -> A` weight `-x`.

Reduction rules (L, M are contingent links; `A_L`, `C_L`, `x_L` belong to L):

| Rule | Input | Output | Condition |
| --- | --- | --- | --- |
| No-case | `X -w1-> Y`, `Y -w2-> V` ordinary | ordinary `X -> V` weight `w1 + w2` | none |
| Upper-case | ordinary `V -w-> B`, upper-case `B -M:z-> A_M` | upper-case `V -M:w+z-> A_M` | none |
| Lower-case | lower-case `A_L -c:x_L-> C_L`, ordinary `C_L -w-> V` | ordinary `A_L -> V` weight `x_L + w` | `w < 0` |
| Cross-case | lower-case `A_L -c:x_L-> C_L`, upper-case `C_L -M:z-> A_M` | upper-case `A_L -M:x_L+z-> A_M` | `z < 0` and `M != L` |
| Label removal | upper-case `B -M:z-> A_M` | ordinary `B -> A_M` weight `z` | `z >= -x_M` |

Every upper-case edge with label M points to `A_M`. So store upper-case edges as one vector per link: `U[m]` of shape `(n,)`, where `U[m][v]` is the weight of `v -> A_M` with label M (`inf` if none). Start with `U[m][C_M] = -y_M`.

**Algorithm (vectorized):**

```
input: ordinary matrix O (n x n), vectors U[m], links (A_m, x_m, y_m, C_m)
for round in 1..MAX_ROUNDS:
    O = floyd_warshall(O)                         # no-case closure
    if any diag(O) < 0: return NOT_DC (cycle in O)
    # AllMax check: upper-case edges as ordinary, lower-case ignored
    M = O.copy(); for each m: M[:, A_m] = min(M[:, A_m], U[m])
    M = floyd_warshall(M)
    if any diag(M) < 0: return NOT_DC (cycle in M)
    changed = False
    for each m:                                   # upper-case rule
        new = min over B of (O[:, B] + U[m][B])   # (O + U[m][None, :]).min(axis=1)
        changed |= update U[m] = min(U[m], new)
    for each link L:                              # lower-case rule
        row = O[C_L, :]; mask = row < 0
        changed |= update O[A_L, mask] = min(O[A_L, mask], x_L + row[mask])
    for each link L, each m != L:                 # cross-case rule
        z = U[m][C_L]
        if z < 0: changed |= update U[m][A_L] = min(U[m][A_L], x_L + z)
    for each m:                                   # label removal
        mask = U[m] >= -x_m
        changed |= update O[mask, A_m] = min(O[mask, A_m], U[m][mask])
    if not changed: return DC
raise RuntimeError("DC check did not converge")  # this means a bug
```

- `MAX_ROUNDS = 10 * (K + 1) ** 2 + 50`, where K is the number of links. All weights are integers and only decrease. While the AllMax graph is consistent they are bounded below, so the loop ends.
- Count a change only on a strict decrease.
- Return a result object: `verdict`, `rounds`, the final `O`, `U`, and, in provenance mode, the linear form of the negative cycle (`C[i, i, :]` for the first negative diagonal entry `i`).
- **Provenance mode**: keep a coefficient tensor for `O`, and a coefficient matrix for each `U[m]`. Every rule adds the coefficient vectors of its inputs. For link edges, `x_L` and `y_L` are linear forms of the link parameters. Assert the invariant after each round in tests.

### 7.5 Dynamic controllability, reference engine (`stnu/dc_reference.py`)

Pure Python with dicts. Apply the same five rules pairwise over explicit edge sets until no change, with the same AllMax check each round. Slow, but easy to read. Use it only in tests, for networks with up to 12 timepoints. The two engines MUST give the same verdict on every test network.

### 7.6 OPTIONAL: Morris 2014 O(n^3) engine (`stnu/dc_morris14.py`)

Reference: P. Morris, "Dynamic Controllability and Dispatchability Relationships", CPAIOR 2014, LNCS 8451. The sketch below is from memory of the paper. **Verify it against the paper before you trust it.** It is acceptable only if it agrees with `dc.py` on 10,000 random networks (Section 10.3).

```
negative node = a node with an incoming negative edge (ordinary or upper-case)

determineDC():
    for each negative node n:
        if not DCbackprop(n): return NOT_DC
    return DC

DCbackprop(source):
    if source is on the current recursion stack: return False      # negative cycle
    if source is already finished: return True
    dist[*] = inf; dist[source] = 0
    for each edge e into source:  dist[start(e)] = weight(e); push start(e)
    (remember, for each node, if its best distance came from an upper-case
     initial edge, and the label of that edge)
    while queue not empty:
        u = pop min
        if dist[u] >= 0:
            add ordinary edge u -> source with weight dist[u]; continue
        if u is a negative node and not DCbackprop(u): return False
        for each edge e into u with weight(e) >= 0:
            if e is a lower-case edge whose label matches the upper-case
               initial edge that gave dist[u]: skip           # unusable
            relax start(e) with dist[u] + weight(e)
    mark source finished; return True
```

### 7.7 Schedule and slack (`analysis/schedule.py`)

Use the **AllMax projection** of the (repaired) network: every contingent duration fixed at its maximum (both edges `A -> C` weight `y` and `C -> A` weight `-y`). Run Floyd-Warshall to get `D`.

- `EST(X) = -D[X, Z]` (earliest time).
- `LST(X) = D[Z, X]` (latest time that still meets all upper bounds when all later contingent durations take their maximum).
- `slack(X) = LST(X) - EST(X)`.
- Critical path: tasks whose start slack is `0`, in topological order.

Report the schedule only when the verdict is `DC` or the user passes `--force-schedule`. Label it "worst-case schedule".

### 7.8 Conflict explanation (`analysis/conflict.py`)

When DC fails:

1. Run the DC engine in provenance mode on the failing network (or failing scenario). If `n > 200`, first shrink the network: run a **deletion filter** over the user constraints (lags, deadlines, flow gaps) with the fast engine. Remove one user constraint at a time. If the network stays NOT DC, keep it removed. Then run provenance mode on the result if it is small enough. Else report the kept user constraints only.
2. The negative cycle gives a linear form `W = sum(a_k * p_k) < 0`.
3. Split the terms. **Budget** = terms with `a_k > 0` (upper bounds such as deadlines and maximum gaps). **Demand** = terms with `a_k < 0` (contingent maxima from upper-case edges, minimum durations, minimum gaps). Ignore `const.zero`.
4. Print in business words, with `|a_k|` as a multiplier when it is not 1:

```
Not dynamically controllable.
Budget:  Decision within 7 days of application ............ 7 d
Demand:  Upload documents (customer), maximum ............. 5 d
         KYC check, maximum ............................... 2 d
         Approval, minimum ................................ 1 d
         Total demand ..................................... 8 d
Shortfall: 1 d
```

Expected for `loan_minimal`: budget `{C_deadline.max: +1}`, demand `{Task_Upload.max: -1, Task_KYC.max: -1, Task_Approval.min: -1}`, shortfall 1440 m.

### 7.9 Repair (`analysis/repair.py`)

Conflict-directed repair, after CDRU (Yu, Fang, Williams, ICAPS 2014), with business levers.

Variables: one change `delta_k` per lever, in minutes. Bounds: `[0, max_change]` for `increase`, `[-max_change, 0]` for `decrease`, also respecting the min/max rule in 5.5. Cost: `cost_per_minute_k * |delta_k|`, which is linear because the sign is fixed (`cost_per_minute = cost_per_day / 1440`).

```
cuts = []
repeat up to 100 times:
    apply current deltas to the parameters; rebuild the STNU
    run the DC check
    if DC: round deltas (below), re-check DC, return the repair
    get conflict W = sum(a_k * p_k) from provenance
       (xor mode "start": the first failing scenario; xor mode "split": the union network,
        because union DC is the sufficient condition)
    add cut: sum over levers k of a_k * delta_k >= -W
       (terms of parameters without a lever are constants already inside W)
    solve LP: minimize sum cost_k * |delta_k| subject to all cuts and bounds
             (scipy.optimize.linprog, method="highs")
    if infeasible: return NO_REPAIR with the last conflict and the levers that touch it
raise RuntimeError("repair did not converge")
```

- Always solve the LP from the **original** parameter values with **all** cuts so far.
- Rounding: round each delta away from zero to a multiple of `granularity` (default 1 minute), clip to the bounds, re-check DC. If the rounded repair fails, add the new conflict as a cut and continue the loop.
- Output: the list of lever changes (label, old value, new value, cost), total cost, currency, the assumption note, and the number of LP rounds.

Expected for `loan_minimal` with `config/levers_loan.yaml`: change `add_kyc_staff` by `-1d` (KYC max 2 d to 1 d), total cost 20,000 INR. If `add_kyc_staff` is removed: `nudge_customer` `-1d`, cost 30,000 INR. If all levers are removed: `NO_REPAIR`.

### 7.10 Calibration from the event log (`mining/log.py`, `mining/calibrate.py`)

Data: BPI Challenge 2017, a loan application process of a Dutch financial institute (applications from 2016, events until 1 February 2017). DOI: https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b. File `BPI Challenge 2017.xes.gz` (about 30 MB).

- The user downloads the file to `data/`. If the network allows, Claude Code MAY download it. If the download fails, ask the user to download it. Do not retry with other tools.
- Read with `pm4py.read_xes(path)`. If the result is not a pandas DataFrame, convert it with `pm4py.convert_to_dataframe`. Keep the columns `case:concept:name`, `concept:name`, `lifecycle:transition`, `time:timestamp`. Convert timestamps to UTC. Cache to `data/bpi2017.parquet`.
- Command `timelens discover-log` MUST print every activity with its lifecycle values and counts. **Before writing the mapping, run it and check the names.** Do not guess activity names.

Mapping file (`config/mapping_bpi2017.yaml`). The names below are expected in BPI 2017 but MUST be checked with `discover-log`:

```yaml
case_start: {activity: "A_Create Application", occurrence: first}
case_end:   {activity_any: ["A_Pending", "A_Denied", "A_Cancelled"], occurrence: first}
tasks:
  Task_Complete:          # staff completes the application
    start: {activity: "W_Complete application", lifecycle: "start", occurrence: first}
    end:   {activity: "W_Complete application", lifecycle: "complete", occurrence: last}
  Task_CustomerReturn:    # customer returns the signed offer and documents
    start: {activity: "O_Sent (mail and online)", occurrence: first}
    end:   {activity: "O_Returned", occurrence: first}
  Task_Validate:          # staff validates the application
    start: {activity: "W_Validate application", lifecycle: "start", occurrence: first}
    end:   {activity: "W_Validate application", lifecycle: "complete", occurrence: last}
```

Calibration rules:

- **Split by time** before any calibration: sort cases by case start; the first 70% are the training set, the last 30% the test set. Calibrate only on training cases. Evaluate only on test cases. This avoids data leakage.
- Per task, duration = `end - start` in minutes, per case. Drop cases where the start or the end is missing or `end < start`. Report the number of dropped cases.
- Range for coverage `alpha`: `min = floor(quantile((1 - alpha) / 2))`, `max = ceil(quantile(1 - (1 - alpha) / 2))`. Use `numpy.quantile` with `method="linear"`.
- If a task has fewer than 30 samples, warn, and do not calibrate it.
- Output a rules JSON (from `loan_bpi.rules.template.json`, with calibrated `min` and `max`) and a calibration table (task, n, min, max, alpha).
- **Empirical joint coverage**: the share of **test** cases where every mapped task falls inside its range. Risk = `1 - joint coverage`. Do not use an independence formula.
- **Deadline for BPI**: the log has no official deadline. Put it in the template as `C_deadline.max`. Print the distribution of `case_end - case_start` on the training set (median, 80th, 90th percentile). Ask the user to choose a round number of days, or use the 90th percentile rounded up to whole days if the user is not available. Write the choice and its reason into every report.

### 7.11 Risk vs cost frontier (`analysis/frontier.py`)

For `alpha` in `[0.80, 0.85, 0.90, 0.95, 0.99]`:

1. Calibrate with this alpha.
2. Run the DC check. If not DC, run the repair with `config/levers_bpi2017.yaml`.
3. Record: alpha, empirical risk (test set), verdict, minimum repair cost (0 if already DC, `NaN` with a note if `NO_REPAIR`), lever changes.

Write `results/frontier.csv` and `results/frontier.png` (x: risk in %, y: cost in INR, one labeled point per alpha). Expected property: when alpha goes up, ranges get wider, so cost MUST NOT go down. If it goes down, it is a bug; report it.

### 7.12 Run-time alerts and replay (`analysis/alerts.py`)

**Latest safe time.** For a pending timepoint X, given the timepoints already observed:

1. Start from the AllMax projection of the (repaired) network.
2. For each observed timepoint Y at time `t_Y` (minutes from case start), add `Z -> Y` weight `t_Y` and `Y -> Z` weight `-t_Y`.
3. For each contingent end not yet observed whose activation is observed, keep it at its maximum.
4. Run Floyd-Warshall. `LST(X) = D[Z, X]`. If the network is inconsistent, the case is already at risk.

**Monitor rule.** Raise an alert at time `t` if some pending executable timepoint X has `LST(X) < t` and X has not happened. The alert says: "Start <task> by <time>, else the deadline is at risk."

**Replay (evaluation on the test set).**

- Use only test cases that have every mapped event. Report how many were used and how many were skipped.
- For each case, order the observed timepoints by time. After event `k` at `t_k`, with the next event at `t_(k+1)`: for each pending X, if `LST(X) < t_(k+1)` and X has not happened by `LST(X)`, the alert time is `max(LST(X), t_k)`. Take the first alert per case.
- Ground truth: the case is **late** if `case_end - case_start > deadline`.
- Metrics: precision, recall, F1, and the median **lead time** (deadline time minus alert time) for true positives.
- **Baseline to beat**: a static rule "alert if no decision by `deadline - 3 days`". Report the same metrics for it. TimeLens is useful only if it gives earlier alerts at similar precision. Report the result honestly, even if it is worse.

Write `results/alerts_eval.json` and `results/alerts_eval.md`.

### 7.13 Benchmark (`bench/generate.py`, `bench/run.py`)

Random structured processes, seeded:

- Build by recursive blocks: `SEQ`, `AND`, `XOR` (depth up to 4, 2 to 3 branches), leaves are tasks.
- Each task: contingent with probability 0.5. Durations: `min` uniform in `[30, 480]` minutes, `max = min + uniform[0, 960]`.
- Add `k` random lags between pairs `(X, Y)` with X before Y in a topological order, upper bound only.
- Deadline from Z to the end: `factor * worst-case makespan`, with `factor` uniform in `[0.8, 1.2]`, so the set has both DC and NOT DC cases.
- Sizes: 10, 25, 50, 100, 200, 300 tasks. 20 models per size.
- Measure the wall time of the consistency check, SC check, and DC check (fast engine, no provenance), and DC with provenance for `n <= 200` timepoints.
- Write `results/bench.csv` and `results/bench.png` (median time per size, log scale).

### 7.14 OPTIONAL: UPPAAL baseline (`baseline/uppaal.py`)

Base paper 3 (Dechsupa et al., Information Sciences 710, 2025) translates BPMN to UPPAAL timed-automata networks. Implement a simple export for comparison of run time:

- One template per task: `Idle -> Running -> Done`. On start, reset the local clock `x`. `Running` has the invariant `x <= max`. The edge to `Done` has the guard `x >= min`.
- Sequencing with shared integer flags. A global clock `g` for the deadline.
- Properties: `E<> End.done && g <= D` (some run meets the deadline; compare with the consistency check) and `A[] (End.done imply g <= D)` under as-soon-as-possible starts (urgent locations).
- Run `verifyta` if it is on `PATH`. If not, skip with a message.
- In the report, state clearly: plain UPPAAL does not check dynamic controllability. DC as a game would need UPPAAL TIGA. The comparison is about run time and the consistency verdict only.

---

## 8. Example models (MUST be in `examples/`)

### 8.1 `loan_minimal`

```
StartEvent_1 "Application received"
  -> Task_Upload "Upload documents"      contingent [1d, 5d], owner customer
  -> Task_KYC "KYC check"                contingent [1d, 2d], owner staff
  -> Task_Approval "Approval"            controllable [1d, 1d]
  -> EndEvent_1 "Decision sent"
Constraint C_deadline: StartEvent_1.start -> EndEvent_1.end, max 7d
```

Expected results (tests MUST check them):

| Check | Expected |
| --- | --- |
| Consistent | true (1 + 1 + 1 = 3 d <= 7 d) |
| SC | false |
| DC | NOT_DC, shortfall 1 d (5 + 2 + 1 = 8 d > 7 d) |
| Repair with `levers_loan.yaml` | `add_kyc_staff` by -1 d, cost 20,000 INR |
| After repair: DC | DC |
| After repair: `LST(Task_KYC:s)` | 5 d (7200 m) |
| After repair: `EST(Task_KYC:s)` | 5 d, slack 0, on the critical path |

### 8.2 `loan_full`

```
StartEvent_1 -> Task_Upload [1d,5d] contingent -> Task_KYC [1d,2d] contingent
  -> Gateway_AND_split
       -> Task_Scoring "Credit scoring" [2h,6h] contingent
       -> Task_Fraud "Fraud check" [30m,2h] contingent
  -> Gateway_AND_join
  -> Gateway_XOR_split "Risk level"
       -> Task_AutoApprove "Auto approval" [1h,1h] controllable
       -> Task_ManualReview "Manual review" [4h,1d] contingent
  -> Gateway_XOR_join
  -> Task_Approval [1d,1d] controllable
  -> EndEvent_1
Constraints:
  C_deadline: StartEvent_1.start -> EndEvent_1.end, max 7d
  C_scoring_lag: Task_KYC.end -> Task_Scoring.start, max 4h
xor_outcome_known_at: "split"
```

Expected: `NOT_DC`. The conflict MUST include `Task_Upload.max`, `Task_KYC.max` and `C_deadline.max`. Worst-case shortfall: auto-approval scenario 1 d 7 h, manual-review scenario 2 d 6 h. After repair with the three levers of `levers_loan.yaml` (total capacity 6 d), the verdict MUST be `DC`.

### 8.3 BPMN files

Write valid BPMN 2.0 XML for both examples, with a `bpmndi:BPMNDiagram` section that uses a simple left-to-right layout (x step 150, y 100 for the main line, branches at y 0 and y 200). The file MUST open in bpmn.io. The parser MUST ignore the diagram section.

---

## 9. Command line interface (`cli.py`)

| Command | Function |
| --- | --- |
| `timelens check MODEL.bpmn RULES.json [--json OUT] [--force-schedule]` | Parse, validate, build, and print consistency, SC, DC, schedule, slack, critical path, conflict text. |
| `timelens repair MODEL.bpmn RULES.json LEVERS.yaml [--json OUT]` | Run the repair loop. Print the repair and the verdict after repair. |
| `timelens discover-log LOG` | Print activities, lifecycle values, counts. |
| `timelens calibrate LOG MAPPING.yaml TEMPLATE.json --alpha 0.95 --out RULES.json` | Calibrate ranges. Print the table and the joint coverage. |
| `timelens frontier MODEL.bpmn LOG MAPPING.yaml TEMPLATE.json LEVERS.yaml` | Section 7.11. |
| `timelens alerts-eval MODEL.bpmn RULES.json LOG MAPPING.yaml` | Section 7.12. |
| `timelens bench [--sizes 10,25,50] [--seed 7]` | Section 7.13. |
| `timelens uppaal MODEL.bpmn RULES.json` | OPTIONAL, Section 7.14. |

Exit codes: `0` success and DC, `1` success and NOT DC (or NO_REPAIR), `2` input error, `3` internal error.

JSON report shape (for `check` and `repair`):

```json
{
  "model": "loan_minimal",
  "xor_mode": "start",
  "verdicts": {"consistent": true, "strongly_controllable": false, "dynamically_controllable": "NOT_DC"},
  "schedule": [
    {"element": "Task_KYC", "name": "KYC check", "point": "start",
     "est_min": 7200, "lst_min": 7200, "slack_min": 0}
  ],
  "critical_path": ["Task_Upload", "Task_KYC", "Task_Approval"],
  "conflicts": [
    {"scenario": "default", "shortfall_min": 1440,
     "terms": [{"param": "C_deadline.max", "label": "Decision within 7 days of application",
                "coefficient": 1, "value_min": 10080}],
     "text": "..."}
  ],
  "repair": {"status": "REPAIRED", "currency": "INR", "total_cost": 20000,
             "assumption_note": "...", "changes": [
               {"lever": "add_kyc_staff", "param": "Task_KYC.max",
                "old_min": 2880, "new_min": 1440, "cost": 20000}]}
}
```

---

## 10. Testing plan

### 10.1 Unit tests

- `units`: parse `"90m"`, `"1.5h"`, `"2d"`, `"1w"`, `"0"`, `45`; reject `"1.3m"` (not whole minutes), `"5x"`, `"-1d"`; `format_minutes` round trips.
- `rules`: missing task entry, unknown element id, `min > max`, duplicate ids: each gives a clear error.
- `bpmn`: both examples parse to the expected node and flow counts; a model with a loop is rejected; two start events are rejected.
- `process`: `loan_full` has 2 scenarios; an invalid XOR/AND mix is rejected.
- `stn`: Floyd-Warshall and Bellman-Ford agree on 500 random graphs (seeded); provenance invariant holds.

### 10.2 Known DC cases (`test_dc_known.py`)

All values in minutes. `A` is executable, `C` is the contingent end, `B` is executable.

| Case | Network | Expected |
| --- | --- | --- |
| K1 | link `(A, 1, 3, C)`, `0 <= A - Z` | DC |
| K2 | link `(A, 1, 5, C)`; `1 <= C - B <= 2` (B at least 1 and at most 2 before C) | NOT DC (B happens before C, so B cannot react to C; C at 1 needs B at 0 or earlier, C at 5 needs B in [3, 4]) |
| K3 | link `(A, 1, 3, C)`; `0 <= B - C <= 1` (B within 1 after C) | DC (B reacts to C) |
| K4 | `loan_minimal` | NOT DC |
| K5 | `loan_minimal` with KYC max 1 d | DC |
| K6 | same network as K2; SC check and consistency check | SC false, consistent true |

Both engines (`dc.py`, `dc_reference.py`) MUST pass all cases.

### 10.3 Property tests (`test_dc_properties.py`, hypothesis)

Generate random STNUs with 3 to 8 timepoints, 0 to 2 contingent links, integer weights in `[-20, 20]`, bounds `0 <= x <= y <= 20`. Use `@settings(max_examples=500, deadline=None)` and a fixed seed profile.

1. `dc.py` verdict == `dc_reference.py` verdict.
2. SC implies DC.
3. DC implies consistent.
4. DC implies that the AllMin, AllMax, and 5 random projections are consistent STNs.
5. Not consistent implies NOT DC.
6. Monotonicity: making a contingent interval wider never turns NOT DC into DC. Making a requirement upper bound larger never turns DC into NOT DC.
7. Provenance invariant `D == C @ p` after every round.
8. OPTIONAL: if `dc_morris14.py` exists, its verdict == `dc.py` verdict on 10,000 examples.
9. OPTIONAL: if the CSTNU Tool is configured, compare 200 examples with it. Any disagreement MUST be reported to the user with the network.

### 10.4 Analysis tests

- `schedule`: values in 8.1 after repair.
- `conflict`: budget and demand terms in 7.8 for `loan_minimal`; the text contains "Shortfall: 1 d".
- `repair`: the three expected results in 7.9; repaired network is DC; LP cost equals the reported cost.
- `calibrate`: a synthetic DataFrame with known durations (for example 100 cases with durations 1..100 minutes) gives the exact quantiles; time split is chronological; fewer than 30 samples gives a warning.
- `alerts`: a synthetic replay with 3 cases (one on time, one late with an early alert, one late with no alert) gives the expected precision, recall, and lead time.
- `frontier`: on a synthetic log, cost is non-decreasing in alpha.
- `cli`: `check` on both examples returns exit code 1 and valid JSON; `repair` on `loan_minimal` returns exit code 0.

### 10.5 Acceptance criteria (the project is done when)

- [ ] All tests pass. `ruff` and `mypy` are clean.
- [ ] `timelens check` and `timelens repair` give the Section 8.1 table for `loan_minimal`.
- [ ] Calibration, frontier, and alerts run on the real BPI 2017 log and produce the files in `results/`.
- [ ] The benchmark runs for 10 to 300 tasks and produces `results/bench.csv` and `results/bench.png`.
- [ ] `README.md` explains install, every command, the example outputs, every assumption (costs, deadline, mapping), and the limits (Section 11).

---

## 11. Assumptions and limits (put them in the README)

- Design-time analysis plus a replay of past cases. No live integration with a workflow engine.
- Acyclic models only. No loops.
- Elapsed calendar time. No working-day calendars.
- No resource constraints (staff capacity is modeled only through the "add staff" lever cost).
- XOR with `"split"` can give `UNKNOWN_XOR` (Section 6.3).
- Provenance (explanation and repair) for networks up to about 200 timepoints. Verdicts scale higher.
- Repair changes one parameter per lever and assumes a linear cost.
- Costs, the BPI deadline, and the BPI mapping are assumptions and MUST be stated in every report.
- Calibrated ranges come from one bank and one year (2016). They may not transfer to other organizations.

---

## 12. Phases

Do each phase in order. Each phase ends with its tests passing and a 2 to 4 line status message to the user.

| Phase | Work | Done when |
| --- | --- | --- |
| 0 | `pyproject.toml`, layout (Section 4), `ruff`, `mypy`, `pytest` setup, empty CLI with `--help` | `timelens --help` works; CI commands pass |
| 1 | `units.py`, `model/rules.py`, `model/bpmn.py`, `model/process.py`, both example models (Section 8) | tests 10.1 for these modules pass |
| 2 | `stnu/network.py`, `stnu/build.py`, `stnu/stn.py`, consistency check, `analysis/schedule.py` | consistency and AllMax schedule are correct on examples |
| 3 | `stnu/sc.py` | SC false on `loan_minimal`; K6 passes |
| 4 | `stnu/dc.py`, `stnu/dc_reference.py`, XOR verdict logic | tests 10.2 and 10.3 (items 1 to 7) pass |
| 5 | `analysis/conflict.py`, `analysis/repair.py`, `config/levers_loan.yaml`, CLI `check` and `repair` | tests 10.4 for conflict, repair, schedule, cli pass |
| 6 | `mining/log.py`, `mining/calibrate.py`, CLI `discover-log` and `calibrate`. **Ask the user for the BPI file and confirm activity names and the deadline.** | calibration tests pass; real calibration table printed |
| 7 | `analysis/frontier.py`, `config/levers_bpi2017.yaml`, CLI `frontier`, plot | `results/frontier.csv` and `.png` exist; cost is non-decreasing |
| 8 | `analysis/alerts.py`, CLI `alerts-eval` | alert tests pass; `results/alerts_eval.*` exist with the static baseline |
| 9 | `bench/`, CLI `bench`; OPTIONAL `dc_morris14.py`, UPPAAL export | `results/bench.*` exist |
| 10 | `report/`, `README.md`, final run of all commands | acceptance criteria 10.5 all checked |

---

## 13. Coding standards

- Type hints everywhere. `mypy --strict` for `src/timelens/stnu` and `src/timelens/analysis`.
- Pure functions in the algorithm layer. No I/O in `stnu/` and `analysis/`.
- Raise specific exceptions (`ModelError`, `RulesError`, `LogMappingError`) with the element id in the message.
- No global random state. Pass `numpy.random.Generator` objects.
- Docstrings say what a function returns and its time complexity.
- Every report file starts with the date, the input file names, alpha, the deadline choice, and the assumption note.

---

## 14. References

Base papers:

1. M. Ocampo-Pineda, R. Posenato, F. Zerbato. "TimeAwareBPMN-js: An editor and temporal verification tool for Time-Aware BPMN processes". SoftwareX 17, 100939, 2022.
2. R. Posenato, M. Franceschetti, C. Combi, J. Eder. "Introducing Agile Controllability in Temporal Business Processes". BPMDS 2024, LNBIP 511, pp. 87-99, 2024.
3. C. Dechsupa, W. Vatanawood, A. Thongtak. "Toward automated verification of timed business process models using timed-automata networks and temporal properties". Information Sciences 710, 122088, 2025.

Algorithms and data:

4. R. Dechter, I. Meiri, J. Pearl. "Temporal Constraint Networks". Artificial Intelligence 49, 1991.
5. T. Vidal, H. Fargier. "Handling contingency in temporal constraint networks: from consistency to controllabilities". JETAI, 1999.
6. P. Morris, N. Muscettola. "Temporal Dynamic Controllability Revisited". AAAI 2005.
7. P. Morris. "Dynamic Controllability and Dispatchability Relationships". CPAIOR 2014, LNCS 8451.
8. P. Yu, C. Fang, B. Williams. "Resolving Uncontrollable Conditional Temporal Problems Using Continuous Relaxations". ICAPS 2014.
9. J. Eder, M. Franceschetti. "Time and Business Process Management: Problems, Achievements, Challenges". TIME 2020, LIPIcs 178.
10. B. van Dongen. "BPI Challenge 2017". 4TU.ResearchData, 2017. https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b
