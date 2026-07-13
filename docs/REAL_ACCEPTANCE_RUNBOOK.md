# Real Acceptance Runbook

## Purpose

`scripts/regression_smoke.py` is an offline synthetic-contract check over four
fixed fixtures. It verifies internal data and report contracts only. It cannot
establish real investigation completion, real-tool availability, or
generalization to authorized real targets.

`scripts/real_acceptance.py` is a separate, opt-in runner for controlled real
acceptance observations. Its default is validation-only and makes zero HTTP
requests.

## Cohort And Data Rules

Before making a benchmark claim, an operator must have written authorization
for real targets and review results for separate `domain`, `company`, and
`sparse_lead` cohorts. Record that authorization and the cohort rationale in
the approved operational system, not in this repository.

Do not commit sensitive target cases, credentials, target evidence, output, or
operator review notes. The checked-in
`backend/tests/fixtures/real_acceptance_manifest.example.json` is schema-only:
it uses `example.invalid`, declares `purpose: "schema_example_only"`, and is
intentionally not executable against a real target.

## Validate Without Network Access

Run the default dry run against a manifest:

```bash
backend/.venv/bin/python scripts/real_acceptance.py \
  --manifest /approved-private-path/acceptance-manifest.json
```

This validates version 1 cases and prints `executed: false`,
`network_accessed: false`, and `benchmark_established: false`. It does not need
a base URL or token, and it must not be used as a benchmark result.

The example fixture can be checked locally without network access:

```bash
backend/.venv/bin/python scripts/real_acceptance.py \
  --manifest backend/tests/fixtures/real_acceptance_manifest.example.json
```

## Explicit Authorized Execution

Only execute an approved private manifest after every case has
`real_target: true`. Set the token outside the repository and name its
environment variable explicitly:

```bash
export REAL_ACCEPTANCE_TOKEN='operator-provided-token'
backend/.venv/bin/python scripts/real_acceptance.py \
  --manifest /approved-private-path/acceptance-manifest.json \
  --execute \
  --base-url https://approved-api.example \
  --token-env REAL_ACCEPTANCE_TOKEN
```

`--execute` is required for any HTTP request. It accepts HTTPS base URLs, or
HTTP only for `localhost` or a loopback address. It sends one create request,
one run-jobs request, and a bounded sequence of detail GET polls per case. It
does not retry create or run-jobs mutations, and rejects redirect hops so the
bearer token remains scoped to the validated base URL. The schema-only example
is rejected with `--execute` because its case sets `real_target: false`.

Execution has fixed resource limits: at most `20` detail polls, a `5` second
maximum poll interval, a `30` second maximum request timeout, and a `60`
second wall-time budget per case across create, run, and polling. Values above
those limits are rejected before HTTP access. A deadline or polling sleep error
is reported as a non-success outcome. JSON responses are capped at `1 MiB`;
oversized declared or streamed responses are rejected as non-successes.

## Reading Results

- `status_counts`: final observed investigation statuses, including pending,
  blocked, failed, and unreachable outcomes without upgrading them to success.
- `completion_rate`: share of cases observed as completed without a blocking,
  failed, collection-continuation, or human-decision completion mode.
- `manual_intervention_rate`: share of cases that still require an operator
  decision or did not reach a completed outcome during bounded polling.
- `evidence_floor_rate`: share of cases whose reported evidence floor satisfies
  every `minimum_evidence` key declared in that case.
- `identity_conflict_rate`: share of cases with a conflicted company-identity
  or decision-maker cross-verification row.
- `reviewed_false_conflict_rate`: false-conflict labels divided by valid
  operator labels (`false_conflict` or `true_conflict`). It is `null` when no
  valid operator review labels exist.

`benchmark_established` is true only for an explicit execution that includes
all three real cohort seed types: `domain`, `company`, and `sparse_lead`. It
means a comparable real acceptance benchmark observation was produced; it does
not claim generalization, complete coverage, or perfect outcomes. Review the
authorization, completion modes, evidence floors, conflicts, and operator
labels before publishing or relying on the benchmark.
