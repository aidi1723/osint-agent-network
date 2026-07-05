from dataclasses import dataclass

from app.core.intel_gateway import IntelRoute, build_intel_plan
from app.core.normalization import normalize_target
from app.core.registry import ToolRegistry


@dataclass(frozen=True)
class StrategyProfile:
    name: str
    max_depth: int
    max_jobs: int
    max_entities: int

    @classmethod
    def quick(cls):
        return cls(name="quick", max_depth=1, max_jobs=10, max_entities=100)

    @classmethod
    def standard(cls):
        return cls(name="standard", max_depth=3, max_jobs=50, max_entities=500)

    @classmethod
    def deep(cls):
        return cls(name="deep", max_depth=5, max_jobs=250, max_entities=2500)

    @classmethod
    def maximum(cls):
        return cls(name="maximum", max_depth=7, max_jobs=1000, max_entities=10000)


@dataclass(frozen=True)
class PlannedJob:
    tool_name: str
    target_type: str
    target_value: str
    depth: int
    agent_role: str = "tool_agent"
    output_contract: str = "entities,evidence,relationships"
    depends_on: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.tool_name, self.target_type, self.target_value)


def plan_initial_jobs(
    seed_type: str,
    seed_value: str,
    strategy: StrategyProfile,
    registry: ToolRegistry,
    runtime_env: dict[str, str] | None = None,
) -> list[PlannedJob]:
    plan = build_intel_plan(
        target_type=seed_type,
        target_value=seed_value,
        strategy_name=strategy.name,
        registry=registry,
        runtime_env=runtime_env,
    )
    return [_route_to_planned_job(route, depth=_route_depth(route)) for route in plan.routes]


def plan_followup_jobs(
    entity_type: str,
    entity_value: str,
    depth: int,
    strategy: StrategyProfile,
    registry: ToolRegistry,
    already_planned: set[tuple[str, str, str]],
    runtime_env: dict[str, str] | None = None,
) -> list[PlannedJob]:
    if depth >= strategy.max_depth:
        return []

    candidates: list[tuple[str, str]] = []
    normalized = normalize_target(entity_type, entity_value)

    if entity_type == "email":
        local, domain = normalized.split("@", 1)
        candidates.extend([("email", normalized), ("username", local), ("domain", domain)])
    elif entity_type == "phone":
        candidates.append(("phone", normalized))
    elif entity_type == "username":
        candidates.append(("username", normalized))
    elif entity_type == "profile_url":
        candidates.append(("profile_url", normalized))
    elif entity_type in {"domain", "subdomain"}:
        candidates.append(("domain", normalized))
    elif entity_type in {"company", "organization"}:
        candidates.append(("company", normalized))

    planned: list[PlannedJob] = []
    for target_type, target_value in candidates:
        plan = build_intel_plan(target_type, target_value, strategy.name, registry, runtime_env=runtime_env)
        for route in plan.routes:
            job = _route_to_planned_job(route, depth=depth + 1)
            if job.key not in already_planned:
                planned.append(job)
    return planned


def _route_to_planned_job(route: IntelRoute, depth: int) -> PlannedJob:
    return PlannedJob(
        tool_name=route.tool_name,
        target_type=route.target_type,
        target_value=route.target_value,
        depth=depth,
        agent_role=route.agent_role,
        output_contract=route.output_contract,
        depends_on=route.depends_on,
    )


def _route_depth(route: IntelRoute) -> int:
    if route.tool_name == "cross_verification":
        return 1
    if route.tool_name == "analysis_judgement":
        return 2
    return 0
