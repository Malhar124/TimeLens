# TimeLens

Design-time analysis of time rules in BPMN processes.

TimeLens reads a BPMN 2.0 model and a side file of time rules: task durations, gaps between tasks, lags and deadlines. Some durations are **contingent**: the organization does not control them (for example, how long a customer takes to upload documents). TimeLens decides if every case can always meet its rules (**dynamic controllability**, DC). If not, it explains the conflict in business words and computes the cheapest repair with business levers.

```
 Event log (BPI 2017)          BPMN model + time rules (JSON)
        |                                 |
 [1] CALIBRATE  ---- duration ranges ---->|
                                    [2] MAP: BPMN -> STNU
                                    [3] CHECK: consistency, SC, DC
                     +--------------------+--------------------+
                     | DC                                      | NOT DC
              schedule, slack,                        [4] REPAIR: conflict ->
              critical path                               linear cut -> LP
                     +---------> [5] DECIDE + ALERT <----------+
              risk vs cost frontier, run-time alerts, replay on past cases
```

Steps 2 and 3 follow published methods (Vidal and Fargier 1999; Morris and Muscettola 2005). The contribution is the combination: duration ranges learned from a real log with a coverage level alpha as a risk knob, repair at minimum business cost with conflict-directed linear cuts (after CDRU by Yu, Fang and Williams, ICAPS 2014), a risk vs cost frontier, and run-time alert thresholds validated by replay.

## Install

Python 3.11 or later.

```bash
uv venv -p 3.12 .venv
uv pip install -p .venv -e ".[dev]"
source .venv/bin/activate
timelens --help
```

With plain pip: `python -m venv .venv && .venv/bin/pip install -e ".[dev]"`.

Verification commands:

```bash
ruff check .
mypy src          # strict for timelens.stnu and timelens.analysis
pytest -q         # no network, fixed seeds
```

## Inputs

- **BPMN file.** Standard BPMN 2.0 XML with one process. Supported: one start event, one end event, intermediate events, tasks (all task types), parallel and exclusive gateways, sequence flows. The diagram part is ignored. Loops, other element types, and gateways that both split and join are rejected.
- **Rules file** (`*.rules.json`). Time rules keyed by BPMN element id. See `examples/loan_minimal/loan_minimal.rules.json`. Time values are `"90m"`, `"4h"`, `"2d"`, `"1w"` or plain integer minutes. Every task needs an entry.
- **Levers file** (`config/levers_*.yaml`). Business actions that change one time bound, with a cost per day and a maximum change.
- **Mapping file** (`config/mapping_bpi2017.yaml`). Maps log events to model timepoints.

Model a task done by people as `contingent`. Use `controllable` only when the organization truly fixes the duration.

## Commands

Exit codes: `0` success and DC, `1` success and NOT DC (or no repair), `2` input error, `3` internal error.

| Command | What it does |
| --- | --- |
| `timelens check MODEL.bpmn RULES.json [--json OUT] [--force-schedule]` | Consistency, strong and dynamic controllability. Worst-case schedule, slack and critical path if DC. Conflict text if not. |
| `timelens repair MODEL.bpmn RULES.json LEVERS.yaml [--json OUT] [--rules-out OUT]` | Cheapest lever changes that make the model DC. `--rules-out` writes the repaired rules. |
| `timelens discover-log LOG` | Every activity with its lifecycle values and counts. Run it before you write a mapping. |
| `timelens calibrate LOG MAPPING.yaml TEMPLATE.json --alpha 0.95 --out RULES.json [--deadline-days N]` | Duration ranges from the first 70 % of cases. Joint coverage on the last 30 %. |
| `timelens frontier MODEL.bpmn LOG MAPPING.yaml TEMPLATE.json LEVERS.yaml [--deadline-days N]` | Risk vs cost for alpha 0.80 to 0.99. Writes `results/frontier.csv` and `results/frontier.png`. |
| `timelens alerts-eval MODEL.bpmn RULES.json LOG MAPPING.yaml` | Replays the test cases with run-time alerts and a static baseline. Writes `results/alerts_eval.json` and `.md`. Pass repaired (DC) rules. |
| `timelens bench [--sizes 10,25,50] [--models 20] [--seed 7]` | Timing benchmark on random structured processes. Writes `results/bench.csv` and `results/bench.png`. |

`LOG` is a `.xes` or `.xes.gz` file (read with pm4py and cached as parquet next to it) or a `.parquet` cache.

## Example: `loan_minimal`

Upload documents (customer, 1 to 5 days), KYC check (staff, 1 to 2 days), approval (exactly 1 day), decision within 7 days.

```
$ timelens check examples/loan_minimal/loan_minimal.bpmn examples/loan_minimal/loan_minimal.rules.json
Model: loan_minimal  (XOR outcome known at: start)
Consistent:               yes
Strongly controllable:    no
Dynamically controllable: NOT_DC

Conflict in scenario 'default':
Not dynamically controllable.
Budget:  Decision within 7 days of application ........... 7 d
Demand:  Upload documents (customer), maximum ............ 5 d
         KYC check, maximum .............................. 2 d
         Approval, minimum ............................... 1 d
         Total demand .................................... 8 d
Shortfall: 1 d
```

```
$ timelens repair examples/loan_minimal/loan_minimal.bpmn examples/loan_minimal/loan_minimal.rules.json config/levers_loan.yaml
Repair: REPAIRED  (LP rounds: 2)
  Add one KYC officer [Task_KYC.max]: 2 d -> 1 d, cost 20,000 INR
  Total cost: 20,000 INR (assumption)
After repair:
Dynamically controllable: DC
  KYC check               start             5 d           5 d           0 m
Critical path: Task_Upload -> Task_KYC -> Task_Approval
```

Without the KYC lever, the repair sends reminders to the customer (upload maximum minus 1 d, 30,000 INR). Without any lever, the result is `NO_REPAIR`.

`loan_full` adds parallel credit scoring and fraud checks and an XOR choice between auto approval and manual review (`xor_outcome_known_at: "split"`). It is NOT DC with worst-case shortfalls of 1 d 7 h (auto approval) and 2 d 6 h (manual review). The repair with the three loan levers makes it DC: KYC maximum minus 1 d and upload maximum minus 1 d 6 h, 57,500 INR.

## BPI Challenge 2017 workflow

Data: BPI Challenge 2017, loan applications of a Dutch financial institute, DOI [10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b](https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b). Put `BPI Challenge 2017.xes.gz` in `data/` (not in git).

```bash
LOG="data/BPI Challenge 2017.xes.gz"
timelens discover-log "$LOG"                       # check the activity names first
timelens calibrate "$LOG" config/mapping_bpi2017.yaml \
    examples/bpi2017/loan_bpi.rules.template.json --alpha 0.95 --out results/bpi.rules.json
timelens frontier examples/bpi2017/loan_bpi.bpmn "$LOG" config/mapping_bpi2017.yaml \
    examples/bpi2017/loan_bpi.rules.template.json config/levers_bpi2017.yaml
timelens repair examples/bpi2017/loan_bpi.bpmn results/bpi.rules.json \
    config/levers_bpi2017.yaml --rules-out results/bpi.repaired.json
timelens alerts-eval examples/bpi2017/loan_bpi.bpmn results/bpi.repaired.json \
    "$LOG" config/mapping_bpi2017.yaml
timelens bench
```

Calibration splits cases by start time: the first 70 % train, the last 30 % test. A task with fewer than 30 samples is not calibrated (warning). Range at coverage alpha: floor of the `(1 - alpha) / 2` quantile to ceil of the `1 - (1 - alpha) / 2` quantile. Risk is `1 - empirical joint coverage` on the test set (no independence formula).

## Assumptions

Every report states its assumptions in its header: date, inputs, alpha, deadline choice and the assumption note.

- **Costs.** All costs and lever limits are illustrative assumptions, not real bank data. They live only in `config/levers_*.yaml`. The BPI levers reuse the loan rates (staff 20,000, customer reminders 30,000, deadline extension 50,000 INR per day). Their `max_change` values are also assumptions.
- **BPI deadline.** The log has no official deadline. With `--deadline-days N` the user chooses it. Otherwise TimeLens uses the 90th percentile of training case durations, rounded up to whole days, and writes that reason into the rules `notes` and every report.
- **BPI mapping.** `config/mapping_bpi2017.yaml` uses the activity names of the build guide. They must be checked with `discover-log`. `calibrate` stops with an error if a mapped name or lifecycle value is not in the log. For `activity_any` lists, one present name is enough. Missing alternatives give a warning.
- **Benchmark generator.** One upper-bound lag per 10 tasks, with a bound of 1.0 to 1.5 times the worst-case gap. The deadline is 0.8 to 1.2 times the worst-case makespan.

## Limits

- Design-time analysis plus a replay of past cases. No live integration with a workflow engine.
- Acyclic models only. No loops.
- Elapsed calendar time. No working-day calendars.
- No resource constraints. Staff capacity appears only through the cost of an "add staff" lever.
- Tasks and intermediate events need exactly one incoming and one outgoing flow. Use gateways to split and join.
- With `xor_outcome_known_at: "split"`, per-scenario DC is necessary and union DC is sufficient. In between the verdict is `UNKNOWN_XOR`. The same rule applies to strong controllability. The CSTNU Tool oracle is not integrated.
- More than 256 XOR scenarios: only the union check runs.
- Provenance (conflict explanation and repair) is for networks up to 200 timepoints. Larger networks get verdicts and a deletion-filter list of the user constraints that keep them NOT DC, but no repair.
- Repair changes one parameter per lever and assumes a linear cost.
- The reported conflict is the most negative cycle that Floyd-Warshall closes first, not always the global worst cycle.
- The monitor watches task start timepoints. It assumes every contingent duration not yet observed takes its maximum, so it is conservative. If the repaired ranges are tighter than history, many past cases alert early.
- Calibrated ranges come from one bank and one year (2016). They may not transfer to other organizations.

## Notes on the build guide

These points differ from, or add to, `TimeLens_Build_Guide.md`:

1. Floyd-Warshall stops at the first negative diagonal entry of any node, not only the pivot. Otherwise a later pivot can double a negative cycle and its linear form.
2. The AllMax pass of the DC engine runs on the raw edge matrix, not on the closed one. The verdict is the same. The conflict found first is then the worst-case cycle, which gives the expected `loan_full` shortfalls.
3. Conflict text leaves out terms with value 0 (like `const.zero`). `loan_minimal` keeps the 4 h gap after KYC from Section 5.3, whose minimum is 0.
4. The deletion filter removes constraints, not timepoints, so the network never becomes small enough for provenance. TimeLens reports the kept constraints only.
5. `repair --rules-out` and the rules `notes` field are additions, so that `alerts-eval` can use repaired rules and reports can carry the deadline choice.
6. In the replay, a contingent link whose end is observed uses the observed time instead of its maximum.
7. Not built (OPTIONAL in the guide): the Morris 2014 O(n^3) engine, the UPPAAL export, and the CSTNU Tool oracle.

## Layout

```
config/            levers and log mapping (assumptions)
examples/          loan_minimal, loan_full, bpi2017 template
src/timelens/
  model/           BPMN parser, rules schema, process graph and XOR scenarios
  stnu/            STNU, BPMN -> STNU mapping, STN tools, SC, DC (fast and reference)
  analysis/        verdicts, schedule, conflicts, repair, frontier, alerts
  mining/          event log loading, mapping, calibration
  bench/           random process generator and timing benchmark
  report/          report text and plots
tests/             pytest and hypothesis tests
```

## References

1. M. Ocampo-Pineda, R. Posenato, F. Zerbato. TimeAwareBPMN-js. SoftwareX 17, 2022.
2. R. Posenato, M. Franceschetti, C. Combi, J. Eder. Introducing Agile Controllability in Temporal Business Processes. BPMDS 2024.
3. C. Dechsupa, W. Vatanawood, A. Thongtak. Timed-automata networks for timed business process models. Information Sciences 710, 2025.
4. R. Dechter, I. Meiri, J. Pearl. Temporal Constraint Networks. Artificial Intelligence 49, 1991.
5. T. Vidal, H. Fargier. Handling contingency in temporal constraint networks. JETAI, 1999.
6. P. Morris, N. Muscettola. Temporal Dynamic Controllability Revisited. AAAI 2005.
7. P. Yu, C. Fang, B. Williams. Resolving Uncontrollable Conditional Temporal Problems Using Continuous Relaxations. ICAPS 2014.
8. B. van Dongen. BPI Challenge 2017. 4TU.ResearchData, 2017.
