import argparse
import json
import os
from pathlib import Path
from urllib import request

from app.core.intel_gateway import build_intel_plan
from app.core.registry import default_tool_registry
from app.core.social_risk import build_social_risk_report
from app.services.llm import LLMClient
from app.tools import get_adapter
from app.tools.base import run_tool_command


DEFAULT_CAPABILITIES = [
    "domain",
    "sparse_lead",
    "username",
    "email",
    "phone",
    "sherlock",
    "theharvester",
    "amass",
    "subfinder",
    "httpx",
    "katana",
    "ghunt",
    "phoneinfoga",
    "spiderfoot",
    "reconng",
    "company_news",
    "official_site_search",
    "maigret",
    "socialscan",
    "profile_parser",
    "official_site_extractor",
    "lead_anchor_extraction",
    "constrained_query_planning",
    "candidate_business_discovery",
    "rfq_category_analysis",
    "identity_match_review",
]


def post_json(base_url: str, path: str, payload: dict, token: str = "") -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def run(argv: list[str] | None = None, post_json_fn=post_json) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    token = args.token or os.getenv("AGENT_API_TOKEN", "")
    result = dispatch(args, token=token, post_json_fn=post_json_fn)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OSINT Agent Protocol CLI")
    parser.add_argument("--base-url", default=os.getenv("OSINT_AGENT_HUB_URL", "http://127.0.0.1:8088"))
    parser.add_argument("--token", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register", help="注册 Agent")
    register.add_argument("--agent-name", default="cli-agent")
    register.add_argument("--agent-type", default="cli")
    register.add_argument("--capability", action="append", default=[])

    claim = subparsers.add_parser("claim", help="认领任务")
    claim.add_argument("--agent-id", required=True)
    claim.add_argument("--capability", action="append", default=[])

    event = subparsers.add_parser("event", help="写入执行事件")
    event.add_argument("--task-id", required=True)
    event.add_argument("--agent-id", required=True)
    event.add_argument("--level", default="info")
    event.add_argument("--message", required=True)
    event.add_argument("--metadata", default="{}")

    entity = subparsers.add_parser("entity", help="写入实体")
    entity.add_argument("--task-id", required=True)
    entity.add_argument("--type", required=True)
    entity.add_argument("--value", required=True)
    entity.add_argument("--source-tool", default="agent")
    entity.add_argument("--confidence", type=float, default=0.0)

    evidence = subparsers.add_parser("evidence", help="写入证据")
    evidence.add_argument("--task-id", required=True)
    evidence.add_argument("--entity-value", required=True)
    evidence.add_argument("--kind", required=True)
    evidence.add_argument("--source-tool", default="agent")
    evidence.add_argument("--snippet", default="")

    evidence_record = subparsers.add_parser("evidence-record", help="写入 Core v2 证据账本")
    evidence_record.add_argument("--task-id", required=True)
    evidence_record.add_argument("--source-url", required=True)
    evidence_record.add_argument("--source-type", required=True)
    evidence_record.add_argument("--source-tool", default="agent")
    evidence_record.add_argument("--snippet", required=True)
    evidence_record.add_argument("--credibility", type=float, default=0.0)

    fact = subparsers.add_parser("fact", help="写入 Core v2 事实池")
    fact.add_argument("--task-id", required=True)
    fact.add_argument("--statement", required=True)
    fact.add_argument("--subject", required=True)
    fact.add_argument("--predicate", required=True)
    fact.add_argument("--object", dest="object_value", required=True)
    fact.add_argument("--status", default="CONFIRMED")
    fact.add_argument("--confidence", type=float, default=0.0)
    fact.add_argument("--admiralty-code", required=True)
    fact.add_argument("--evidence-id", action="append", default=[])

    hypothesis = subparsers.add_parser("hypothesis", help="写入 Core v2 假说池")
    hypothesis.add_argument("--task-id", required=True)
    hypothesis.add_argument("--id", dest="hypothesis_id", required=True)
    hypothesis.add_argument("--statement", required=True)
    hypothesis.add_argument("--group", default="default")

    score_hypotheses = subparsers.add_parser("score-hypotheses", help="运行 Core v2 ACH 假说评分")
    score_hypotheses.add_argument("--task-id", required=True)
    score_hypotheses.add_argument("--evidence-json", required=True)

    relationship = subparsers.add_parser("relationship", help="写入关系")
    relationship.add_argument("--task-id", required=True)
    relationship.add_argument("--from", dest="from_value", required=True)
    relationship.add_argument("--to", dest="to_value", required=True)
    relationship.add_argument("--type", dest="relationship_type", required=True)
    relationship.add_argument("--confidence", type=float, default=0.0)

    complete = subparsers.add_parser("complete", help="完成任务")
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--agent-id", required=True)
    complete.add_argument("--status", default="COMPLETED")
    complete.add_argument("--summary", default="")
    complete.add_argument("--report", default="")
    complete.add_argument("--report-file", default="")
    complete.add_argument("--confidence", type=float)

    run_tool = subparsers.add_parser("run-tool", help="运行本地工具适配器并写回标准协议")
    run_tool.add_argument(
        "--tool",
        required=True,
        choices=[
            "sherlock",
            "theharvester",
            "amass",
            "subfinder",
            "httpx",
            "katana",
            "ghunt",
            "phoneinfoga",
            "spiderfoot",
            "reconng",
            "company_news",
            "official_site_search",
            "maigret",
            "socialscan",
            "profile_parser",
            "official_site_extractor",
        ],
    )
    run_tool.add_argument("--target-type", required=True)
    run_tool.add_argument("--target", required=True)
    run_tool.add_argument("--task-id", default="")
    run_tool.add_argument("--agent-id", default="")
    run_tool.add_argument("--input-file", default="")
    run_tool.add_argument("--workdir", default="")
    run_tool.add_argument("--timeout", type=int, default=0)
    run_tool.add_argument("--dry-run", action="store_true")

    llm_check = subparsers.add_parser("llm-check", help="检查情报官中转模型 API 配置")
    llm_check.add_argument("--prompt", default="用中文回复：情报官模型中转 API 正常。")
    llm_check.add_argument("--no-call", action="store_true")

    risk_report = subparsers.add_parser("risk-report", help="根据调查详情 JSON 生成社媒风险评分")
    risk_report.add_argument("--input-file", required=True)
    risk_report.add_argument("--declared-region", default="")

    plan_tools = subparsers.add_parser("plan-tools", help="通过情报工具中枢规划应调用的底层工具")
    plan_tools.add_argument("--target-type", required=True)
    plan_tools.add_argument("--target", required=True)
    plan_tools.add_argument("--strategy", default="standard")
    plan_tools.add_argument("--env", action="append", default=[], help="覆盖运行配置，格式 KEY=VALUE")

    return parser


def dispatch(args: argparse.Namespace, token: str, post_json_fn) -> dict:
    if args.command == "register":
        capabilities = args.capability or DEFAULT_CAPABILITIES
        return post_json_fn(
            args.base_url,
            "/api/agents/register",
            {
                "agent_name": args.agent_name,
                "agent_type": args.agent_type,
                "capabilities": capabilities,
            },
            token,
        )

    if args.command == "claim":
        return post_json_fn(
            args.base_url,
            "/api/agent/tasks/claim",
            {
                "agent_id": args.agent_id,
                "capabilities": args.capability or DEFAULT_CAPABILITIES,
            },
            token,
        )

    if args.command == "event":
        return post_json_fn(
            args.base_url,
            "/api/agent/events",
            {
                "task_id": args.task_id,
                "agent_id": args.agent_id,
                "level": args.level,
                "message": args.message,
                "metadata": json.loads(args.metadata),
            },
            token,
        )

    if args.command == "entity":
        return post_json_fn(
            args.base_url,
            "/api/agent/entities",
            {
                "task_id": args.task_id,
                "entities": [
                    {
                        "type": args.type,
                        "value": args.value,
                        "source_tool": args.source_tool,
                        "confidence": args.confidence,
                    }
                ],
            },
            token,
        )

    if args.command == "evidence":
        return post_json_fn(
            args.base_url,
            "/api/agent/evidence",
            {
                "task_id": args.task_id,
                "entity_value": args.entity_value,
                "evidence_kind": args.kind,
                "source_tool": args.source_tool,
                "snippet": args.snippet,
            },
            token,
        )

    if args.command == "evidence-record":
        return post_json_fn(
            args.base_url,
            "/api/agent/evidence-records",
            {
                "task_id": args.task_id,
                "source_url": args.source_url,
                "source_type": args.source_type,
                "source_tool": args.source_tool,
                "snippet": args.snippet,
                "credibility": args.credibility,
            },
            token,
        )

    if args.command == "fact":
        return post_json_fn(
            args.base_url,
            "/api/agent/facts",
            {
                "task_id": args.task_id,
                "statement": args.statement,
                "subject": args.subject,
                "predicate": args.predicate,
                "object": args.object_value,
                "status": args.status,
                "confidence": args.confidence,
                "admiralty_code": args.admiralty_code,
                "evidence_ids": args.evidence_id,
            },
            token,
        )

    if args.command == "hypothesis":
        return post_json_fn(
            args.base_url,
            "/api/agent/hypotheses",
            {
                "task_id": args.task_id,
                "hypothesis_id": args.hypothesis_id,
                "statement": args.statement,
                "group": args.group,
            },
            token,
        )

    if args.command == "score-hypotheses":
        return post_json_fn(
            args.base_url,
            "/api/agent/hypotheses/score",
            {
                "task_id": args.task_id,
                "evidence_items": json.loads(args.evidence_json),
            },
            token,
        )

    if args.command == "relationship":
        return post_json_fn(
            args.base_url,
            "/api/agent/relationships",
            {
                "task_id": args.task_id,
                "from": args.from_value,
                "to": args.to_value,
                "relationship_type": args.relationship_type,
                "confidence": args.confidence,
            },
            token,
        )

    if args.command == "complete":
        report_markdown = args.report
        if args.report_file:
            report_markdown = Path(args.report_file).read_text(encoding="utf-8")
        return post_json_fn(
            args.base_url,
            f"/api/agent/tasks/{args.task_id}/complete",
            {
                "agent_id": args.agent_id,
                "status": args.status,
                "summary": args.summary,
                "report_markdown": report_markdown,
                "confidence": args.confidence,
            },
            token,
        )

    if args.command == "run-tool":
        return dispatch_run_tool(args, token=token, post_json_fn=post_json_fn)

    if args.command == "llm-check":
        client = LLMClient()
        status = client.status()
        if args.no_call:
            return status
        content = client.chat_completion(
            [
                {"role": "system", "content": "你是情报官系统的连通性测试助手。"},
                {"role": "user", "content": args.prompt},
            ],
            temperature=0,
            max_tokens=120,
        )
        return {**status, "reply": content}

    if args.command == "risk-report":
        payload = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
        return build_social_risk_report(
            entities=payload.get("entities", []),
            evidence=payload.get("evidence", []),
            relationships=payload.get("relationships", []),
            declared_region=args.declared_region,
        )

    if args.command == "plan-tools":
        return _plan_tools_payload(args)

    raise ValueError(f"unsupported command: {args.command}")


def _plan_tools_payload(args: argparse.Namespace) -> dict:
    runtime_env = _runtime_env_with_dotenv()
    runtime_env.update(_parse_env_overrides(args.env))
    plan = build_intel_plan(
        target_type=args.target_type,
        target_value=args.target,
        strategy_name=args.strategy,
        registry=default_tool_registry(),
        runtime_env=runtime_env,
    )
    return {
        "target_type": plan.target_type,
        "target_value": plan.target_value,
        "strategy": plan.strategy_name,
        "routes": [route.__dict__ for route in plan.routes],
        "skipped_routes": [route.__dict__ for route in plan.skipped_routes],
    }


def _parse_env_overrides(items: list[str]) -> dict[str, str]:
    overrides = {}
    for item in items:
        if "=" not in item:
            raise ValueError("--env must use KEY=VALUE format")
        key, value = item.split("=", 1)
        overrides[key] = value
    return overrides


def _runtime_env_with_dotenv(dotenv_path: Path | None = None) -> dict[str, str]:
    runtime_env = dict(os.environ)
    path = dotenv_path or Path(".env")
    if not path.exists():
        return runtime_env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in runtime_env:
            continue
        runtime_env[key] = _clean_env_value(value)
    return runtime_env


def _clean_env_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        return cleaned[1:-1]
    return cleaned


def dispatch_run_tool(args: argparse.Namespace, token: str, post_json_fn) -> dict:
    adapter = get_adapter(args.tool)
    artifact_path = Path(args.input_file) if args.input_file else None
    run_result = None

    if artifact_path is None:
        workdir = Path(args.workdir or f"data/jobs/{args.tool}_{args.target}")
        timeout = args.timeout or _default_timeout(args.tool)
        if hasattr(adapter, "run"):
            run_result = adapter.run(
                target_type=args.target_type,
                target_value=args.target,
                workdir=workdir,
                timeout_seconds=timeout,
            )
            artifact_path = run_result.command.expected_artifact
        else:
            command = adapter.build_command(
                target_type=args.target_type,
                target_value=args.target,
                workdir=workdir,
                timeout_seconds=timeout,
            )
            run_result = run_tool_command(command)
            artifact_path = command.expected_artifact

    parsed = adapter.parse_artifact(artifact_path, target_value=args.target)
    output = parsed.to_dict()

    if run_result is not None:
        output["run"] = {
            "returncode": run_result.returncode,
            "stdout_excerpt": run_result.stdout_excerpt,
            "stderr_excerpt": run_result.stderr_excerpt,
            "artifact": str(run_result.command.expected_artifact),
        }

    if args.dry_run:
        output["posted"] = {"entities": 0, "evidence": 0, "relationships": 0}
        return output

    if not args.task_id or not args.agent_id:
        raise ValueError("run-tool requires --task-id and --agent-id unless --dry-run is used")

    post_json_fn(
        args.base_url,
        "/api/agent/events",
        {
            "task_id": args.task_id,
            "agent_id": args.agent_id,
            "level": "info",
            "message": f"完成工具解析：{args.tool}",
            "metadata": {
                "tool": args.tool,
                "target_type": args.target_type,
                "target": args.target,
                "counts": output["counts"],
            },
        },
        token,
    )

    if parsed.entities:
        post_json_fn(
            args.base_url,
            "/api/agent/entities",
            {
                "task_id": args.task_id,
                "entities": [
                    {
                        "type": item.type,
                        "value": item.value,
                        "source_tool": item.source_tool,
                        "confidence": item.confidence,
                    }
                    for item in parsed.entities
                ],
            },
            token,
        )

    for item in parsed.evidence:
        post_json_fn(
            args.base_url,
            "/api/agent/evidence",
            {
                "task_id": args.task_id,
                "entity_value": item.entity_value,
                "evidence_kind": item.evidence_kind,
                "source_tool": item.source_tool,
                "snippet": item.snippet,
            },
            token,
        )

    for item in parsed.relationships:
        post_json_fn(
            args.base_url,
            "/api/agent/relationships",
            {
                "task_id": args.task_id,
                "from": item.from_value,
                "to": item.to_value,
                "relationship_type": item.relationship_type,
                "confidence": item.confidence,
            },
            token,
        )

    output["posted"] = output["counts"]
    return output


def _default_timeout(tool_name: str) -> int:
    return {
        "sherlock": 120,
        "theharvester": 600,
        "amass": 1200,
        "subfinder": 600,
        "httpx": 300,
        "katana": 600,
        "ghunt": 180,
        "phoneinfoga": 120,
        "spiderfoot": 1800,
        "reconng": 900,
        "company_news": 180,
        "official_site_search": 90,
        "maigret": 300,
        "socialscan": 120,
        "profile_parser": 60,
        "official_site_extractor": 60,
    }[tool_name]


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
