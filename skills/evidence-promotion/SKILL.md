---
name: evidence-promotion
description: Decide when observations can become candidate, assessed, or accepted facts with evidence IDs and Admiralty Code.
---

# Evidence Promotion

Use this workflow when turning observations into facts.

## Promotion Stages

- `RAW_OBSERVATION`: extracted from a source or tool but not assessed.
- `CANDIDATE_FACT`: plausible and relevant, but weak or single-source.
- `ASSESSED_FACT`: source-backed and reviewed, but not fully accepted.
- `ACCEPTED_FACT`: confirmed or likely with evidence IDs and Admiralty Code.
- `REJECTED_FACT`: contradicted, superseded, or same-name noise.

## Rules

1. Confirmed or likely facts require evidence IDs.
2. Confirmed or likely facts require Admiralty Code.
3. Official, registry, and original-source evidence outranks aggregators and tool output.
4. Identity match must be scored separately from public-record existence.
5. Contradictions block acceptance until explained.

## Required Fields

Facts must include statement, subject, predicate, object, status, confidence, promotion stage, Admiralty Code, and evidence IDs.
