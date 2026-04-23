# Phase 1 Metric Formula Contract Revision Proposal

Ngay lap: 2026-04-23

Pham vi: de xuat sua contract cho `relative_to_baseline` trong final dedicated
controls sau chuoi notebook 36-40. Day la tai lieu planning/proposal. No khong
doi code runtime, khong doi config threshold, khong sua logits/metrics, khong
rerun controls, khong phan loai lai artifact da fail, va khong mo claim Phase 1.

## 1. Trang thai dau vao

Nguon dau vao nguoi dung da cung cap tu Colab closeout:

| Stage | Run | Ket qua chinh |
|---|---|---|
| Metric contract audit | `phase1_final_controls_metric_contract_audit/20260423T145402567040Z` | `relative_formula_locked=False`, `formula_ambiguity_detected=True`, runtime formula id `raw_ba_ratio`, control formula-dependent: `nuisance_shared_control` |
| Formula revision plan | `phase1_final_controls_metric_formula_revision_plan/20260423T150122168051Z` | `revision_required=True`, `manual_decision_required=True`, `selected_formula=None`, code/rerun/threshold change not allowed |
| Formula decision | `phase1_final_controls_metric_formula_decision/20260423T151113767836Z` | decision `unresolved`, selected formula `None`, code/config revision not required by runner, controls rerun not allowed |
| Post-formula governance | `phase1_final_post_formula_decision_governance_update/20260423T151640450262Z` | metric formula claim-evaluable `False`, next step `do_not_rerun_controls_until_metric_formula_contract_is_resolved`, claims opened `False` |
| Remediation plan | `phase1_final_metric_formula_contract_remediation_plan/20260423T152340014269Z` | selected formula `None`, code change allowed now `False`, controls rerun allowed now `False`, next step `draft_metric_formula_contract_revision_proposal` |

Current claim boundary:

- `nuisance_shared_control` remains failed/blocking.
- `spatial_control` remains failed/blocking.
- `metric_formula_contract_unresolved` remains blocking.
- No decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 comparator claim is opened.

## 2. Source review

| Source | Observation | Integrity implication |
|---|---|---|
| `configs/phase1/final_metric_formula_contract_remediation_plan.json` | Allows only docs/config-schema/unit-test/future-rerun planning; explicitly forbids selecting formula inside the plan, changing runtime formula, changing thresholds, editing metrics/logits, rerunning controls, or opening claims. | This proposal may define a future patch, but must not apply it. |
| `configs/phase1/final_controls_metric_contract_audit.json` | Candidate formulas are `raw_ba_ratio` and `gain_over_chance_ratio`; audit is claim-closed and forbids selecting a formula post hoc to improve results. | Formula selection must be justified by contract/runtime consistency, not by pass/fail effect. |
| `configs/phase1/final_controls_metric_formula_revision_plan.json` | Allowed outcomes include locking `raw_ba_ratio`, locking `gain_over_chance_ratio` with a scoped patch, or declaring unresolved. | A later reviewed decision may choose one outcome, but current artifacts stay fail-closed. |
| `configs/phase1/final_controls_metric_formula_decision.json` | Required before rerun: reviewed formula decision, code/config patch if needed, unit tests, full unittest, notebook/governance docs, explicit manual rerun acknowledgement. | Controls cannot be rerun directly after this proposal. |
| `configs/phase1/final_dedicated_controls.json` | Threshold sources are locked to Gate 2, but there is no explicit formula field for `relative_to_baseline`. | Missing formula field is the contract gap to fix. |
| `src/phase1/final_dedicated_controls.py` | `_relative(value, baseline)` returns `value / baseline`; nuisance and spatial controls write `relative_to_baseline` from that helper. | Existing runtime semantics match `raw_ba_ratio`. |

## 3. Candidate formula analysis

### `raw_ba_ratio`

Definition:

```text
control_balanced_accuracy / baseline_balanced_accuracy
```

Observed runtime status:

- This is the formula currently implemented by `_relative(...)`.
- It is the formula id detected by the metric-contract audit as current runtime behavior.
- Locking it prospectively would document the runtime that actually generated current artifacts.

Integrity risk:

- It must not be used to declare current artifacts valid. The formula was not locked
  before observing failures, so current controls remain fail-closed.

### `gain_over_chance_ratio`

Definition:

```text
abs(control_balanced_accuracy - 0.5) / abs(baseline_balanced_accuracy - 0.5)
```

Observed runtime status:

- This is a candidate formula only.
- It does not match the current `_relative(...)` runtime implementation.
- Adopting it would require a scoped code/config/docs patch and tests before any rerun.

Integrity risk:

- Because the ambiguity was discovered after observing the failed controls, choosing
  this formula now would be high-risk unless there is an independent pre-result source
  proving it was the intended contract.
- It is especially risky because `nuisance_shared_control` is formula-dependent.

## 4. Proposal

Recommended future contract direction:

```text
proposal_status: draft_not_active
proposed_formula_id: raw_ba_ratio
proposed_definition: control_balanced_accuracy / baseline_balanced_accuracy
applies_to:
  - nuisance_shared_control.relative_to_baseline
  - spatial_control.relative_to_baseline
default_baseline_comparator: A2
thresholds_changed: false
current_artifacts_reclassified: false
claims_opened: false
```

Rationale:

1. The current runtime already computes `relative_to_baseline` as
   `control_balanced_accuracy / baseline_balanced_accuracy`.
2. A prospective `raw_ba_ratio` contract is a documentation/config clarification,
   not a result-saving reinterpretation.
3. It preserves the current failed-control state instead of converting observed
   failures into passes.
4. It avoids choosing `gain_over_chance_ratio` after seeing that at least one control
   is formula-dependent.
5. It keeps the scientific record honest: the previous run had an ambiguous contract,
   so its failed status remains recorded and claim-closed.

This proposal does not make `raw_ba_ratio` active. It only recommends that a later,
reviewed code/config/docs patch should explicitly lock it if the project team accepts
the rationale.

## 5. Future patch scope

If this proposal is accepted, the next patch should be narrow and reviewable:

| Area | Proposed change | Not allowed in that patch |
|---|---|---|
| Dedicated controls config | Add explicit `relative_metric_formula_id: raw_ba_ratio` and definition text for nuisance/spatial relative ceilings. | Do not change threshold values. |
| Final controls config | Mirror or reference the same formula contract for final controls reporting. | Do not alter required controls. |
| Runtime output | Add `relative_metric_formula_id` and formula definition to generated nuisance/spatial control threshold payloads. | Do not change `_relative(...)` math if `raw_ba_ratio` is accepted. |
| Unit tests | Assert that configured formula id matches runtime computation and output metadata. | Do not assert pass/fail improvement. |
| Docs/notebooks | Add text that current artifacts are not reclassified and any future rerun needs manual acknowledgement. | Do not open claims. |

The metric-contract audit must treat the config field as prospective unless the
dedicated-control artifacts under audit also carry formula metadata. In other
words, adding `relative_metric_contract` to config is not enough to clear the
old ambiguity for already generated controls. A future dedicated-control rerun
must write `threshold.relative_metric_formula_id` before a metric-contract audit
can mark the audited artifacts as formula-locked.

Likely files:

- `configs/phase1/final_dedicated_controls.json`
- `configs/phase1/final_controls.json`
- `src/phase1/final_dedicated_controls.py`
- `tests/unit/test_phase1_final_dedicated_controls.py` or a new focused unit test
- `docs/` runbook/update note

## 6. Future rerun dependency plan

No rerun is allowed from this proposal. After a reviewed contract patch lands and
tests pass, a separate manual-gated rerun plan should specify:

1. Rerun `phase1_final_dedicated_controls` using the locked formula metadata.
2. Rerun controls remediation/governance artifacts that depend on dedicated controls.
3. Rerun metric-contract audit to confirm formula lock is no longer ambiguous.
4. Rerun formula decision/governance closeout only if the new contract state requires it.
5. Keep all claims closed until the full final package, including controls,
   calibration, influence, reporting, A2d status, and governance, passes.

## 7. Integrity checklist

This proposal satisfies the current fail-closed boundary because it:

- does not choose a formula for existing artifacts;
- does not change `selected_formula=None` in the recorded formula-decision artifact;
- does not edit threshold values;
- does not edit logits or metrics;
- does not drop subjects;
- does not rerun controls;
- does not reclassify `nuisance_shared_control` or `spatial_control`;
- does not open Phase 1 claims;
- explicitly preserves `metric_formula_contract_unresolved` until a reviewed patch
  and follow-up governance artifact resolve it.

## 8. Recommended next action

Prepare a small reviewed patch that only makes the formula contract explicit and
testable. The patch should be labelled as prospective contract clarification and
must include tests proving that:

- `relative_metric_formula_id == raw_ba_ratio`;
- `relative_to_baseline == control_balanced_accuracy / baseline_balanced_accuracy`;
- nuisance/spatial threshold values are unchanged;
- controls remain claim-closed after the patch;
- no current failed control is reclassified without a fresh, manual-gated rerun.
