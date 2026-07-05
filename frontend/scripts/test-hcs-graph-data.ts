import assert from "node:assert/strict";

import { preferredDecisionLabel, preferredOrganizationLabel } from "../src/hcs-graph-data.ts";
import type { Entity } from "../src/types.ts";

const entities: Entity[] = [
  { id: "raw-company", type: "company_name_raw", value: "David Murillo", source_tool: "lead_anchor_extraction", confidence: 0.86 },
  { id: "lead-name", type: "identity", value: "David MurilloSoto", source_tool: "lead_anchor_extraction", confidence: 0.9 },
  { id: "company", type: "organization", value: "OLGLASS INTERNACIONAL S.A.S.", source_tool: "web_search", confidence: 0.86 },
  { id: "principal", type: "identity", value: "DAVID SEGUNDO MURILLO SOTO", source_tool: "dnb_public_profile", confidence: 0.82 },
];

assert.equal(
  preferredOrganizationLabel(entities, "fallback"),
  "OLGLASS INTERNACIONAL S.A.S.",
  "confirmed organization entities should outrank raw company fields in HCS graph labels",
);

assert.equal(
  preferredDecisionLabel(entities, "fallback"),
  "DAVID SEGUNDO MURILLO SOTO",
  "third-party principal identity should outrank the sparse lead display name when present",
);

console.log("hcs graph data checks passed");
