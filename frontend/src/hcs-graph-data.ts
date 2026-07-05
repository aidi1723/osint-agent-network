import type { Entity } from "./types";

const organizationPriority: Record<string, number> = {
  organization: 100,
  company: 90,
  company_name_raw: 20,
};

const decisionPriority: Record<string, number> = {
  real_name: 95,
  identity: 80,
  username: 40,
  platform_account: 30,
};

const sourcePriority: Record<string, number> = {
  dnb_public_profile: 20,
  official_website: 18,
  web_search: 16,
  empresite: 14,
  larepublica_rues: 14,
  lead_anchor_extraction: 4,
};

export function preferredEntityValue(entities: Entity[] | undefined, priorities: Record<string, number>) {
  return [...(entities ?? [])]
    .filter((entity) => priorities[entity.type])
    .sort((a, b) => {
      const byType = (priorities[b.type] ?? 0) - (priorities[a.type] ?? 0);
      if (byType !== 0) {
        return byType;
      }
      const bySource = (sourcePriority[b.source_tool] ?? 0) - (sourcePriority[a.source_tool] ?? 0);
      if (bySource !== 0) {
        return bySource;
      }
      return b.confidence - a.confidence;
    })[0]?.value;
}

export function preferredOrganizationLabel(entities: Entity[] | undefined, fallback: string) {
  return preferredEntityValue(entities, organizationPriority) ?? fallback;
}

export function preferredDecisionLabel(entities: Entity[] | undefined, fallback: string) {
  return preferredEntityValue(entities, decisionPriority) ?? fallback;
}
