# Decision-Maker Candidate Verification Design

## Objective

Connect official-site decision-maker candidates to cross-verification and quality-gate logic without treating them as confirmed people.

## Current Gap

`official_site_extractor` can now emit public `person`, `job_title`, and `decision_maker` candidates from official pages. However, candidate facts using the predicate `has_decision_maker_candidate` are not consistently recognized as support for the `decision_maker` field. This means source-backed candidates can remain useful entities but fail to strengthen the verified-field layer.

## Approved Approach

Extend field matching only for the `decision_maker` field:

- Treat `has_decision_maker_candidate` as a decision-maker field predicate.
- Treat `has_public_profile_candidate` as a decision-maker-adjacent field predicate.
- Keep statuses conservative. A single official source should produce `SUPPORTED`, not `CONFIRMED`.
- Do not mark these candidate facts as `ACCEPTED_FACT`.

## Non-Goals

- Do not add LinkedIn, search, or social scraping.
- Do not lower the completion score threshold.
- Do not make candidate people confirmed facts from a single official page.
- Do not infer private attributes.

## Expected Behavior

- Cross-verification matrix shows a decision-maker candidate when facts use `has_decision_maker_candidate`.
- Quality assessment no longer marks `decision_maker` missing when a `LIKELY` candidate fact exists.
- Completion still remains blocked if required evidence ledger, fact pool, cross-verification, BLUF, official website, business scope, or contact channel fields are missing.

## Verification

- Unit tests cover cross-verification matrix field matching.
- Unit tests cover quality-gate fact recognition.
- Existing official-site extraction tests continue to pass.
- Full local verification and <production-host> targeted checks must pass.
