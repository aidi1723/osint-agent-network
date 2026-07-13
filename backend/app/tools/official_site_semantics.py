from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


BUSINESS_SCOPE_PATTERNS = (
    "auto parts",
    "automotive spare parts",
    "spare parts",
    "brake components",
    "suspension parts",
    "engine parts",
    "uPVC windows",
    "aluminum curtain wall systems",
    "curtain wall",
    "sliding doors",
    "doors",
    "windows",
)
MAX_SCOPE_CANDIDATES = 8
MAX_CONTACT_CANDIDATES = 12
MAX_SNIPPET_CHARS = 280
MAX_JSON_LD_DEPTH = 32
MAX_JSON_LD_NODES = 256
MAX_JSON_LD_STRING_VALUES = 32


@dataclass(frozen=True)
class ScopeCandidate:
    value: str
    evidence_kind: str
    snippet: str
    confidence: float


@dataclass(frozen=True)
class ContactCandidate:
    entity_type: str
    value: str
    classification: str
    snippet: str


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+\d[\d .()/-]{7,}\d|\b0?\d{2,3}[\s.-]\d{3,4}[\s.-]\d{4}\b|\b\d{3}[\s.-]\d{3}[\s.-]\d{4}\b)"
)
_ENGLISH_SCOPE_CUE_RE = re.compile(
    r"\b(?:we\s+)?(?:manufacture|manufactures|supply|supplies|provide|provides|offer|offers|"
    r"produce|produces|design|designs|develop|develops|sell|sells|speciali[sz]e(?:s|d)?\s+in|"
    r"focus(?:es)?\s+on)\s+(?P<value>[^.!?;]{3,220})",
    flags=re.IGNORECASE,
)
_CHINESE_SCOPE_CUE_RE = re.compile(
    r"(?:\u63d0\u4f9b|\u751f\u4ea7|\u5236\u9020|\u4e3b\u8425|\u4f9b\u5e94|\u9500\u552e|\u4e13\u6ce8\u4e8e)\s*"
    r"(?P<value>[^\u3002\uff01\uff1f.!?;]{2,220})"
)
_SCOPE_FRAGMENT_SPLIT_RE = re.compile(r"\s*(?:,|;|\u3001|\u3002|\u548c|\band\b|&)\s*", flags=re.IGNORECASE)
_TRAILING_SCOPE_CONTEXT_RE = re.compile(
    r"\s+(?:for|to|with|in|used\s+for)\s+.+$", flags=re.IGNORECASE
)
_HEADING_PREFIX_RE = re.compile(
    r"^(?:(?:our\s+)?(?:products?|services?|capabilities|what\s+we\s+(?:make|offer))|"
    r"\u4ea7\u54c1|\u670d\u52a1|\u4e1a\u52a1\u8303\u56f4)\s*[:\uff1a-]\s*",
    flags=re.IGNORECASE,
)
_HEADING_SCOPE_VOCAB_RE = re.compile(
    r"\b(?:products?|services?|equipment|systems?|pumps?|windows?|doors?|parts?|components?|"
    r"filtration|filters?|machinery|hardware|curtain\s+wall|pompes?|maintenance|hydraulique)\b|"
    r"\u4ea7\u54c1|\u670d\u52a1|\u8bbe\u5907|\u7cfb\u7edf|\u6cf5|\u8fc7\u6ee4",
    flags=re.IGNORECASE,
)
_ORGANIZATION_SUFFIX_RE = re.compile(
    r"\b(?:llc|inc|ltd|limited|company|corporation|corp|co\.?\s*ltd\.?)\b", flags=re.IGNORECASE
)
_EXCLUDED_SCOPE_VALUES = {
    "about",
    "about us",
    "a quotation",
    "a quote",
    "catalog",
    "contact",
    "contact us",
    "home",
    "leadership",
    "menu",
    "our products",
    "our services",
    "products",
    "product",
    "quality",
    "quotation",
    "quote",
    "services",
    "service",
    "solutions",
    "solution",
    "team",
    "\u4ea7\u54c1",
    "\u5173\u4e8e\u6211\u4eec",
    "\u54c1\u8d28",
    "\u670d\u52a1",
    "\u89e3\u51b3\u65b9\u6848",
    "\u8054\u7cfb\u6211\u4eec",
}
_EXCLUDED_SCOPE_TEXT_RE = re.compile(
    r"\b(?:cookie|privacy|contact(?:\s+us)?|login|sign\s+in|navigation|customer\s+service)\b|"
    r"\u9690\u79c1|\u8054\u7cfb|\u5ba2\u670d|\u5ba2\u6237\u670d\u52a1"
    ,
    flags=re.IGNORECASE,
)
_FAX_RE = re.compile(r"\bfax\b|\u4f20\u771f", flags=re.IGNORECASE)
_FIELD_LABEL_RE = re.compile(
    r"\bfax\b|\b(?:phone|telephone|tel|email|e-mail)\b|\u4f20\u771f|\u7535\u8bdd|\u90ae\u7bb1",
    flags=re.IGNORECASE,
)
_CUSTOMER_SERVICE_RE = re.compile(
    r"\bcustomer\s+service\b|\bcustomer\s+support\b|\bsupport\b|\bservice\s+hotline\b|"
    r"\u5ba2\u670d|\u5ba2\u6237\u670d\u52a1|\u552e\u540e",
    flags=re.IGNORECASE,
)
_GENERIC_EMAIL_LOCALS = {
    "admin",
    "contact",
    "customerservice",
    "hello",
    "info",
    "inquiries",
    "sales",
    "service",
    "support",
}
_NON_PERSONAL_CONTACT_CONTEXT_RE = re.compile(
    r"\b(?:generic|public)\s+(?:contact|inbox|email|phone|hotline|line)\b|"
    r"\b(?:general\s+(?:inquiries|contact)|main\s+(?:line|phone)|switchboard)\b|"
    r"\b(?:sales|support|service|customer|marketing|procurement|purchasing|export)\s+"
    r"(?:team|department|dept|desk|hotline|line|phone|email|contact|inbox)\b|"
    r"\b(?:team|department|dept|desk)\s+(?:phone|email|hotline|line|contact|inbox)\b|\bhotline\b|"
    r"\u901a\u7528(?:\u90ae\u7bb1|\u7535\u8bdd)|\u516c\u5f00(?:\u8054\u7cfb|\u7535\u8bdd)|\u603b\u673a",
    flags=re.IGNORECASE,
)
_SCHEMA_SCOPE_TYPES = {
    "catalog",
    "itemlist",
    "offer",
    "offercatalog",
    "product",
    "productgroup",
    "service",
}
_CLASSIFICATION_RANK = {"public_general": 1, "customer_service": 2, "fax": 3}


def extract_scope_candidates(
    structured_items: Sequence[dict],
    meta_descriptions: Sequence[str],
    headings: Sequence[str],
    text_blocks: Sequence[str],
    fixed_patterns: Sequence[str] = BUSINESS_SCOPE_PATTERNS,
) -> list[ScopeCandidate]:
    candidates: list[ScopeCandidate] = []
    seen: set[str] = set()

    def add(value: str, evidence_kind: str, snippet: str, confidence: float) -> None:
        normalized_value = _normalize_space(value).strip(" .,:;:-")
        if not _is_scope_value(normalized_value):
            return
        key = normalized_value.casefold()
        if key in seen or len(candidates) >= MAX_SCOPE_CANDIDATES:
            return
        seen.add(key)
        candidates.append(
            ScopeCandidate(
                value=normalized_value,
                evidence_kind=evidence_kind,
                snippet=_bounded_snippet(snippet),
                confidence=confidence,
            )
        )

    nodes = list(_iter_json_nodes(structured_items))
    for node in nodes:
        if not _has_schema_scope_type(node):
            continue
        for field in ("name", "category"):
            for value in _string_values(node.get(field)):
                add(value, "official_site_business_scope_json_ld", value, 0.88)

    for node in nodes:
        for description in _string_values(node.get("description")):
            for value in _cued_scope_values(description):
                add(value, "official_site_business_scope_json_ld", description, 0.82)

    for description in meta_descriptions:
        for value in _cued_scope_values(description):
            add(value, "official_site_business_scope_meta", description, 0.78)

    for heading in headings:
        for value in _heading_scope_values(heading):
            add(value, "official_site_business_scope_heading", heading, 0.74)

    for text_block in text_blocks:
        for sentence in _sentences(text_block):
            for value in _cued_scope_values(sentence):
                add(value, "official_site_business_scope_text", sentence, 0.70)

    fallback_text = _normalize_space(" ".join(text_blocks))
    lowered_text = fallback_text.casefold()
    for pattern in fixed_patterns:
        if pattern.casefold() not in lowered_text:
            continue
        add(
            pattern,
            "official_site_business_scope",
            _snippet_around(fallback_text, pattern),
            0.64,
        )

    return candidates


def extract_contact_candidates(
    static_contexts: Sequence[str], structured_items: Sequence[dict]
) -> list[ContactCandidate]:
    candidates: list[ContactCandidate] = []
    indexes: dict[str, int] = {}

    static_context_iter = iter(static_contexts)
    while len(candidates) < MAX_CONTACT_CANDIDATES:
        try:
            context = next(static_context_iter)
        except StopIteration:
            break
        normalized_context = _normalize_space(context)
        if not normalized_context:
            continue
        for match in _EMAIL_RE.finditer(normalized_context):
            if len(candidates) >= MAX_CONTACT_CANDIDATES:
                break
            contact_context, block_context, field_label = _contact_field_context(
                normalized_context, match.start(), match.end()
            )
            classification = _static_contact_classification(block_context, field_label)
            _add_contact_candidate(
                candidates,
                indexes,
                ContactCandidate("email", match.group(), classification, _bounded_snippet(block_context)),
            )
        for match in _PHONE_RE.finditer(normalized_context):
            if len(candidates) >= MAX_CONTACT_CANDIDATES:
                break
            contact_context, block_context, field_label = _contact_field_context(
                normalized_context, match.start(), match.end()
            )
            classification = _static_contact_classification(block_context, field_label)
            entity_type = "fax" if classification == "fax" else "phone"
            _add_contact_candidate(
                candidates,
                indexes,
                ContactCandidate(entity_type, match.group(), classification, _bounded_snippet(block_context)),
            )

    structured_iter = iter(_iter_json_nodes(structured_items))
    while len(candidates) < MAX_CONTACT_CANDIDATES:
        try:
            node = next(structured_iter)
        except StopIteration:
            break
        context = _json_contact_context(node)
        for field in ("email", "telephone", "phone", "faxNumber"):
            if len(candidates) >= MAX_CONTACT_CANDIDATES:
                break
            for value in _string_values(node.get(field)):
                if len(candidates) >= MAX_CONTACT_CANDIDATES:
                    break
                classification = "fax" if field == "faxNumber" else _contact_classification(context)
                entity_type = "fax" if classification == "fax" and field != "email" else (
                    "email" if field == "email" else "phone"
                )
                snippet = _bounded_snippet(" ".join(part for part in (context, value) if part))
                _add_contact_candidate(
                    candidates,
                    indexes,
                    ContactCandidate(entity_type, value, classification, snippet),
                )

    return candidates[:MAX_CONTACT_CANDIDATES]


def is_role_linkable_contact(candidate: ContactCandidate) -> bool:
    if candidate.entity_type not in {"email", "phone"} or candidate.classification != "public_general":
        return False
    if _NON_PERSONAL_CONTACT_CONTEXT_RE.search(candidate.snippet):
        return False
    if candidate.entity_type != "email":
        return True
    local_part = candidate.value.split("@", 1)[0].casefold().replace("-", "").replace("_", "")
    return local_part not in _GENERIC_EMAIL_LOCALS


def _iter_json_nodes(items: Iterable[dict]) -> Iterable[dict]:
    try:
        roots = iter(items)
    except TypeError:
        return

    seen_containers: dict[int, object] = {}
    stack = []
    visited_nodes = 0
    while visited_nodes < MAX_JSON_LD_NODES:
        if not stack:
            try:
                stack.append((next(roots), 0))
            except StopIteration:
                break
            except (RuntimeError, TypeError):
                break
        value, depth = stack.pop()
        visited_nodes += 1
        if not isinstance(value, (dict, list)):
            continue
        marker = id(value)
        if marker in seen_containers:
            continue
        seen_containers[marker] = value
        if isinstance(value, dict):
            yield value
        if depth >= MAX_JSON_LD_DEPTH:
            continue
        try:
            children = value.values() if isinstance(value, dict) else value
            bounded_children = []
            for child in children:
                if len(bounded_children) >= MAX_JSON_LD_NODES - visited_nodes:
                    break
                bounded_children.append(child)
            stack.extend((child, depth + 1) for child in reversed(bounded_children))
        except (RuntimeError, TypeError):
            continue


def _has_schema_scope_type(node: dict) -> bool:
    raw_types = node.get("@type")
    types = raw_types if isinstance(raw_types, list) else [raw_types]
    return any(str(item or "").casefold() in _SCHEMA_SCOPE_TYPES for item in types)


def _string_values(value) -> list[str]:
    values: list[str] = []
    seen_containers: dict[int, object] = {}
    stack = [(value, 0)]
    visited_nodes = 0
    while stack and len(values) < MAX_JSON_LD_STRING_VALUES:
        current, depth = stack.pop()
        visited_nodes += 1
        if isinstance(current, str):
            values.append(current)
            continue
        if not isinstance(current, list):
            continue
        marker = id(current)
        if marker in seen_containers or visited_nodes > MAX_JSON_LD_NODES:
            continue
        seen_containers[marker] = current
        if depth >= MAX_JSON_LD_DEPTH:
            continue
        try:
            bounded_items = []
            for item in current:
                if len(bounded_items) >= MAX_JSON_LD_NODES - visited_nodes:
                    break
                bounded_items.append(item)
            stack.extend((item, depth + 1) for item in reversed(bounded_items))
        except (RuntimeError, TypeError):
            continue
    return values


def _cued_scope_values(value: str) -> list[str]:
    values: list[str] = []
    for pattern in (_ENGLISH_SCOPE_CUE_RE, _CHINESE_SCOPE_CUE_RE):
        for match in pattern.finditer(value):
            values.extend(_scope_fragments(match.group("value")))
    return values


def _heading_scope_values(value: str) -> list[str]:
    heading = _normalize_space(value).strip(" .,:;:-")
    if not heading or _ORGANIZATION_SUFFIX_RE.search(heading):
        return []
    has_scope_prefix = bool(_HEADING_PREFIX_RE.match(heading))
    stripped = _HEADING_PREFIX_RE.sub("", heading)
    fragments = _scope_fragments(stripped)
    if not fragments:
        return []
    if has_scope_prefix or _HEADING_SCOPE_VOCAB_RE.search(stripped):
        return fragments
    if len(fragments) >= 2 and _SCOPE_FRAGMENT_SPLIT_RE.search(stripped):
        return fragments
    return []


def _scope_fragments(value: str) -> list[str]:
    fragments = []
    for raw in _SCOPE_FRAGMENT_SPLIT_RE.split(value):
        cleaned = _TRAILING_SCOPE_CONTEXT_RE.sub("", _normalize_space(raw)).strip(" .,:;:-")
        cleaned = re.sub(r"^(?:and\s+|\u548c)", "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned and _is_scope_value(cleaned):
            fragments.append(cleaned)
    return fragments


def _is_scope_value(value: str) -> bool:
    normalized = _normalize_space(value).strip(" .,:;:-")
    if len(normalized) < 3 or len(normalized) > 180:
        return False
    lowered = normalized.casefold()
    if lowered in _EXCLUDED_SCOPE_VALUES or _EXCLUDED_SCOPE_TEXT_RE.search(normalized):
        return False
    return True


def _sentences(value: str) -> list[str]:
    return [
        _normalize_space(part)
        for part in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", value)
        if _normalize_space(part)
    ]


def _contact_classification(context: str) -> str:
    if _FAX_RE.search(context):
        return "fax"
    if _CUSTOMER_SERVICE_RE.search(context):
        return "customer_service"
    return "public_general"


def _json_contact_context(node: dict) -> str:
    return _normalize_space(
        " ".join(
            value
            for key in ("name", "contactType", "description", "jobTitle", "title")
            for value in _string_values(node.get(key))
        )
    )


def _contact_field_context(context: str, start: int, end: int) -> tuple[str, str, str]:
    block_start = max(context.rfind(marker, 0, start) for marker in (";", "|")) + 1
    block_context = context[block_start:end]
    labels = list(_FIELD_LABEL_RE.finditer(context, block_start, start))
    if not labels:
        return context[max(block_start, start - 96) : end], block_context, ""
    previous_label_end = labels[-2].end() if len(labels) > 1 else block_start
    return context[max(previous_label_end, start - 96) : end], block_context, labels[-1].group()


def _static_contact_classification(block_context: str, field_label: str) -> str:
    if field_label and _FAX_RE.fullmatch(field_label):
        return "fax"
    if _CUSTOMER_SERVICE_RE.search(block_context):
        return "customer_service"
    if not field_label:
        return _contact_classification(block_context)
    return "public_general"


def _add_contact_candidate(
    candidates: list[ContactCandidate], indexes: dict[str, int], candidate: ContactCandidate
) -> None:
    key = _contact_key(candidate)
    if not key:
        return
    existing_index = indexes.get(key)
    if existing_index is None:
        if len(candidates) >= MAX_CONTACT_CANDIDATES:
            return
        indexes[key] = len(candidates)
        candidates.append(candidate)
        return
    existing = candidates[existing_index]
    if _CLASSIFICATION_RANK[candidate.classification] > _CLASSIFICATION_RANK[existing.classification]:
        candidates[existing_index] = candidate


def _contact_key(candidate: ContactCandidate) -> str:
    if candidate.entity_type == "email":
        return "email:" + candidate.value.casefold()
    digits = re.sub(r"\D+", "", candidate.value)
    return "number:" + digits if digits else ""


def _snippet_around(text: str, needle: str) -> str:
    lowered_text = text.casefold()
    index = lowered_text.find(needle.casefold())
    if index < 0:
        return _bounded_snippet(text)
    start = max(0, index - 60)
    end = min(len(text), index + len(needle) + 160)
    return _bounded_snippet(text[start:end])


def _bounded_snippet(value: str) -> str:
    normalized = _normalize_space(value)
    if len(normalized) <= MAX_SNIPPET_CHARS:
        return normalized
    return normalized[: MAX_SNIPPET_CHARS - 3].rstrip() + "..."


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
