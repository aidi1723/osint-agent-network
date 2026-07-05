from __future__ import annotations


ROLE_TIERS = {
    "enterprise_intel_agent": "reader",
    "social_intel_agent": "reader",
    "contact_discovery_agent": "reader",
    "supply_chain_agent": "reader",
    "purchase_intent_agent": "reader",
    "news_intel_agent": "reader",
    "search_planning_agent": "reader",
    "cross_verification_agent": "verifier",
    "analysis_judgement_agent": "reporter",
}

ALLOWED_METHODS = {
    "reader": {
        "get_investigation",
        "add_entity",
        "add_evidence",
        "add_evidence_record",
        "add_relationship",
    },
    "verifier": {
        "get_investigation",
        "add_fact",
        "add_hypothesis",
        "score_hypotheses",
    },
    "reporter": {
        "get_investigation",
        "complete_task",
    },
}


def tier_for_role(agent_role: str) -> str:
    return ROLE_TIERS.get(agent_role, "reader")


class PermissionedRoleStore:
    def __init__(self, store, tier: str):
        if tier not in ALLOWED_METHODS:
            raise ValueError(f"unknown role tier: {tier}")
        self._store = store
        self._tier = tier

    @property
    def tier(self) -> str:
        return self._tier

    def __getattr__(self, name: str):
        if name not in ALLOWED_METHODS[self._tier]:
            raise PermissionError(f"{self._tier} role cannot call {name}")
        return getattr(self._store, name)
