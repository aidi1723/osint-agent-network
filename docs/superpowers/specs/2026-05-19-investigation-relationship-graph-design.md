# Investigation Relationship Graph Design

## Goal

Add a first-version relationship graph to each investigation so analysts can see how seed identifiers, social profiles, public metadata, evidence, and risk signals connect.

## Scope

- Show an investigation-centered graph in the existing data board.
- Derive graph data from existing investigation detail fields: `seed_type`, `seed_value`, `entities`, `relationships`, `evidence`, and `risk_report`.
- Keep every node backed by public evidence already stored by the system.
- Treat age, photos, regions, interests, and activity areas as public profile claims or evidence signals, not verified real-world facts.
- Do not add private scraping, face recognition, exact residence inference, or automatic customer blocking.

## Reference Tools

- Maigret remains the primary upstream source for social profile dossiers and metadata.
- Social Analyzer is a useful reference for graph UI and similarity scoring, but should not be a required runtime dependency in this version.
- Blackbird can be considered later for cross-checking and report-style output.
- CrossLinked belongs in a later company/person/org graph lane.
- Osintgram should remain manual, authorized, and isolated instead of entering the default automation chain.

## Data Model

The API includes a derived `graph` object on investigation details:

- `nodes`: `id`, `label`, `type`, `value`, `source_tool`, `confidence`, `risk_level`, `evidence_count`, `metadata`.
- `edges`: `id`, `from`, `to`, `label`, `type`, `confidence`, `source`.
- `summary`: counts for total nodes, total edges, risk nodes, and evidence nodes.

Node types:

- `seed`: the initial investigation target.
- `entity`: normalized entities such as username, email, profile URL, location, image URL, bio snippet, interest tag, and age claim.
- `evidence`: evidence rows attached to an entity.
- `risk_signal`: review signals from the social risk report.

Edges:

- Existing relationships become graph edges when both endpoint values can be resolved.
- The seed links to direct seed-value entity matches.
- Evidence nodes link to their matching entity.
- Risk signals link to referenced evidence values or to the seed if no reference is resolvable.

## UI

The graph appears as a compact `关系图谱` panel in the selected investigation data board. It follows `DESIGN.md`: dense operations console, restrained colors, 8px radius, monospace for identifiers, no hero layout.

The first version uses an SVG layout without adding a graph library:

- Seed node fixed in the center-left.
- Entity, evidence, and risk nodes arranged in lanes.
- Edges are straight or lightly curved SVG paths with labels.
- Node color follows type: blue for seed/profile identity, slate for contact/entity, cyan for location/interest metadata, gray for evidence, amber/red for risk signals.
- Edge opacity and node border strength reflect confidence.

Interactions:

- Hover a node or edge to emphasize it.
- Click a node to show a compact side detail panel with label, type, source, confidence, evidence count, and related metadata.
- Empty state explains that graph data appears after entities, relationships, or evidence are written back.

## Error Handling

- If graph derivation receives unknown entity types, show them as generic entity nodes.
- If an edge endpoint cannot be resolved, omit only that edge.
- If risk report values do not match a node, attach the risk signal to the seed.
- The graph must not fail the whole investigation detail response.

## Testing

- Backend unit tests cover graph derivation from memory and SQLite stores.
- Tests assert seed/entity/evidence/risk nodes, relationship edges, evidence edges, and risk fallback edges.
- Frontend verification uses `npm run build`; browser visual QA checks desktop and narrow layouts.
