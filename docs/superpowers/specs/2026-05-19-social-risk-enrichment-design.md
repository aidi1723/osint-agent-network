# Social Risk Enrichment Design

Date: 2026-05-19
Project: OSINT Agent Network

## Purpose

Add an enhanced public social-media enrichment module for risk investigation and anomalous customer review.

The module supports human review by collecting public, attributable evidence, extracting explainable risk signals, and producing an overall risk score plus category scores. Scores are used for prioritization and review guidance only. They must not automatically reject, block, or restrict a customer.

## Scope

First version:

- Input types: `username` and `email`.
- Platform priority: international public platforms, including GitHub, X/Twitter, LinkedIn, Facebook, Instagram, YouTube, Reddit, and platforms covered by existing enumeration tools.
- Tool additions: `maigret`, `socialscan`, `profile_parser`, `social_identity_resolver`, `risk_signal_extractor`, and `risk_score_engine`.
- Output: total score, category scores, top risk signals, public profile summary, and supporting evidence.

Out of scope for the first version:

- Private or authenticated scraping.
- Deep post crawling or full timeline collection.
- Face recognition, face matching, or age estimation from photos.
- Inferring home address or precise residence.
- Automatic account blocking, rejection, or limitation.
- China-platform-specific adapters.

## Safety And Evidence Rules

- Store only public, operator-authorized evidence.
- Every risk signal must reference a source tool and a public evidence item such as a profile URL, public field, or saved artifact.
- Use cautious language in generated summaries: `claimed`, `declared`, `likely`, `possible`, and `needs review`.
- Age is only stored as `age_claim` when publicly self-declared.
- Location is stored as `declared_location` or `likely_activity_region`, never as a confirmed home address.
- Photos are stored as public image URLs or evidence references. No face recognition is performed.
- Interests are context for review. Interest tags do not directly increase risk by themselves.

## Architecture

The module extends the existing tool registry, adapter, planner, evidence, and verification patterns.

```text
username + email
  -> normalize
  -> Sherlock / Maigret for username enumeration
  -> socialscan / GHunt for email and account existence signals
  -> derive candidate usernames from email local-part
  -> profile_parser for public profile metadata
  -> social_identity_resolver for candidate identity groups
  -> risk_signal_extractor for explainable risk signals
  -> risk_score_engine for total and category scores
  -> evidence-backed review output
```

The tools do not call each other directly. They exchange information through normalized entities, evidence, relationships, and planned follow-up jobs.

## Tool Responsibilities

### Maigret

- Accepts: `username`.
- Produces: `social_profile`, `profile_url`, `platform_account`, `bio_snippet`, `profile_image_url`, `declared_location`, `external_link`.
- Role: broad username search and public profile metadata collection.
- Default state: enabled after healthcheck passes.

### socialscan

- Accepts: `email`, `username`.
- Produces: `platform_account`, `social_profile`, `negative_result`.
- Role: lightweight account existence and availability checks.
- Default state: enabled after healthcheck passes.

### profile_parser

- Accepts: `profile_url`.
- Produces: `bio_snippet`, `profile_image_url`, `declared_location`, `external_link`, `interest_tag`, `age_claim`.
- Role: parse public profile pages and normalize common profile metadata.
- Rule: parse public pages only and preserve source URL evidence.

### social_identity_resolver

- Accepts: `social_profile`, `profile_url`, `username`, `email`.
- Produces: relationships such as `profile_same_identity_candidate`.
- Role: group profiles that may belong to the same customer identity.
- Signals: shared username, shared external link, matching display name, matching bio phrase, matching email-derived username, repeated avatar URL.

### risk_signal_extractor

- Accepts: normalized entities, evidence, relationships, customer-declared context when available.
- Produces: `risk_signal` entities and evidence.
- Role: identify explainable review signals without making final decisions.

### risk_score_engine

- Accepts: risk signals and evidence strength.
- Produces: `risk_category_score` entities and final report fields.
- Role: calculate total score, category scores, review requirement, and top signals.

## New Entity Types

- `social_profile`: normalized account/profile object.
- `platform_account`: platform-specific account handle or ID.
- `profile_image_url`: public avatar or profile image URL.
- `bio_snippet`: public profile bio or description excerpt.
- `declared_location`: public self-declared location.
- `likely_activity_region`: coarse region inferred from public profile metadata such as repeated public geotags or timezone.
- `interest_tag`: public interest or topic tag extracted from bio or public metadata.
- `age_claim`: public self-declared age-like claim.
- `external_link`: public profile link to another profile, website, or company page.
- `risk_signal`: explainable signal requiring review.
- `risk_category_score`: category score with supporting evidence.

## New Relationship Types

- `username_has_social_profile`.
- `email_linked_to_social_profile`.
- `profile_links_to_profile`.
- `profile_same_identity_candidate`.
- `profile_declares_location`.
- `profile_mentions_interest`.
- `profile_has_risk_signal`.
- `risk_signal_supported_by_evidence`.

## Risk Categories

Scores use `0-100`, where higher means higher review risk.

### identity_consistency

Measures whether discovered profiles appear to support or contradict the claimed identity.

Risk increases when:

- Profiles linked to the same username show unrelated names, avatars, companies, or bios.
- A profile links to unrelated identities.
- Multiple identity groups compete for the same input.

Risk decreases when:

- Multiple independent public profiles share consistent handles, names, links, or bios.

### contact_reputation

Measures whether the email and username have plausible public footprint.

Risk increases when:

- Email and username have almost no public footprint for a claimed mature customer.
- One contact identifier maps to many unrelated public identities.
- Negative account-existence results contradict claimed platform presence.

### location_consistency

Measures whether public declared locations and activity regions conflict with customer-declared context.

Risk increases when:

- Public declared location strongly conflicts with customer-provided region.
- Repeated public location signals point to a different region.

Rule: location signals are coarse and review-oriented. Do not infer exact residence.

### business_content_risk

Measures public business/content risk.

Risk increases when:

- Public bio, website, or links contain configured high-risk business keywords.
- Profiles point to suspicious landing pages or conflicting business categories.

Rule: keyword hits must be evidence, not final conclusions.

### evidence_uncertainty

Measures how much uncertainty remains.

Risk increases when:

- Findings come from a single weak source.
- Artifacts are missing or parsing confidence is low.
- There are too few independent sources for the requested review.

## Risk Levels

- `low`: 0-24.
- `medium`: 25-49.
- `high`: 50-74.
- `critical`: 75-100.

Recommended review behavior:

- `low`: normal review queue.
- `medium`: reviewer should inspect top signals.
- `high`: reviewer required before relying on the account.
- `critical`: senior review recommended.

## Output Shape

```json
{
  "overall_risk_score": 72,
  "overall_risk_level": "high",
  "category_scores": {
    "identity_consistency": 65,
    "contact_reputation": 70,
    "location_consistency": 55,
    "business_content_risk": 80,
    "evidence_uncertainty": 60
  },
  "review_required": true,
  "top_risk_signals": [
    {
      "kind": "business_risk_keyword",
      "severity": "high",
      "summary": "Public profile links to a site containing configured high-risk business terms.",
      "evidence_ids": []
    }
  ],
  "public_profile_summary": {
    "profiles": [],
    "declared_locations": [],
    "likely_activity_regions": [],
    "profile_image_urls": [],
    "bio_snippets": [],
    "interest_tags": [],
    "age_claims": []
  },
  "supporting_evidence": []
}
```

## Planning Rules

Initial jobs:

- For `username`: run `sherlock` and `maigret`.
- For `email`: run `socialscan` and `ghunt` when applicable.
- For `email`: derive local-part as a candidate username and run username tools.

Follow-up jobs:

- `profile_url` queues `profile_parser`.
- Parsed `external_link` pointing to a supported public platform queues `profile_parser`.
- New `username` candidates can queue username enumeration if budgets allow.

Budget rules:

- Respect investigation `max_depth`, `max_jobs`, and `max_entities`.
- Deduplicate by `(tool_name, target_type, target_value)`.
- Disable deep expansion for quick strategy.
- Keep profile parsing shallow in the first version.

## Validation

### Unit Tests

- Maigret parser maps sample JSON to `social_profile`, `profile_url`, and public metadata.
- socialscan parser maps positive and negative results.
- profile_parser maps simple public HTML fixtures.
- identity resolver groups profiles with shared handles and external links.
- risk signal extractor emits signals with evidence references.
- risk score engine produces deterministic total and category scores.

### Integration Tests

- Creating an email investigation queues socialscan, GHunt, and derived username jobs.
- A username investigation queues Sherlock and Maigret.
- Parsed profile URLs queue profile_parser follow-up jobs.
- Risk report contains total score, category scores, top signals, and evidence links.

### Healthchecks

- `maigret`: command available and version command succeeds.
- `socialscan`: command available and version/help command succeeds.
- `ghunt`: command available and credential check state recorded.
- `profile_parser`: HTTP fetch disabled in tests; parser fixture test must pass.

## Implementation Phases

### Phase 1: Schema And Registry

- Add new tool definitions.
- Add entity and relationship constants or validation.
- Add risk report data structures.
- Add tests for registry and planning.

### Phase 2: Tool Adapters

- Add `MaigretAdapter`.
- Add `SocialScanAdapter`.
- Add `ProfileParserAdapter` with fixture-driven parser tests.
- Keep network calls isolated and mockable.

### Phase 3: Enrichment Planner

- Extend initial and follow-up planning for username, email, and profile URL.
- Add budget enforcement and deduplication tests.

### Phase 4: Risk Engine

- Add `social_identity_resolver`.
- Add `risk_signal_extractor`.
- Add `risk_score_engine`.
- Store category scores and risk signals as evidence-backed outputs.

### Phase 5: API And UI

- Add risk summary to investigation detail.
- Add review-focused UI sections for total score, category scores, top signals, and evidence.
- Keep final actions manual.

## First-Version Defaults

- High-risk keyword lists are server-side configuration in the first version. UI editing can be added after review workflows stabilize.
- `profile_parser` parses saved artifacts first. Direct public-page fetching can be enabled per adapter, but tests must use fixtures and must not require live network access.
- Category score weights are fixed in code for the first version. Store the calculated component values so future operator-tunable weights can be introduced without changing evidence records.
