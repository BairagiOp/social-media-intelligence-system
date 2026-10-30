"""Generic same-site HTML crawler with a CSS-selector extractor (Phase 3).

Deliberately conservative:

* stays on an **allow-list of domains** (by default the start URL's host only),
* honours ``robots.txt`` per origin and a minimum delay between requests,
* capped by ``max_pages`` / ``max_depth`` / byte and timeout limits,
* reuses the SSRF guard in :mod:`app.services.fetch_service` for every hop,
* extracts only the fields you name — no rendered JavaScript, no login flows.

The selector engine is implemented on the standard library ``html.parser``
so the crawler adds **no new dependencies**. Supported syntax: comma groups,
descendant (space) and child (``>``) combinators, and compound simple
selectors of the form ``tag``, ``.class``, ``#id``, ``tag.class``, ``tag#id.class``.
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from app.config import settings
from app.services.fetch_service import fetch_document
from app.utils.errors import FetchFailed, ValidationFailed

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
# Elements whose raw text is never content.
SKIP_CONTENT = {"script", "style", "noscript", "template", "svg", "head"}

_WS_RE = re.compile(r"\s+")


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


# ---------------------------------------------------------------------------
# Minimal DOM
# ---------------------------------------------------------------------------

@dataclass
class Node:
    tag: str
    attrs: dict
    parent: "Node | None" = None
    children: list = field(default_factory=list)

    @property
    def id(self) -> str | None:  # noqa: A003 - mirrors the DOM
        return self.attrs.get("id")

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def get(self, name: str) -> str | None:
        return self.attrs.get(name)

    def text(self) -> str:
        parts: list[str] = []

        def walk(node: "Node") -> None:
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                elif child.tag not in SKIP_CONTENT:
                    walk(child)

        walk(self)
        return _WS_RE.sub(" ", " ".join(parts)).strip()

    def iter(self):
        """Depth-first traversal including the root."""
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.iter()


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self._stack: list[Node] = [self.root]
        self._skip_tag: str | None = None
        self._skip_depth = 0
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        # <title> lives inside <head>, which we otherwise skip as non-content.
        if tag == "title":
            self._in_title = True
        if self._skip_tag is not None:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if tag in SKIP_CONTENT:
            self._skip_tag = tag
            self._skip_depth = 1
            return

        node = Node(tag, {k: (v or "") for k, v in attrs}, parent=self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in VOID_ELEMENTS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs) -> None:
        if self._skip_tag is not None:
            return
        node = Node(tag.lower(), {k: (v or "") for k, v in attrs}, parent=self._stack[-1])
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if self._skip_tag is not None:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth <= 0:
                    self._skip_tag = None
            return
        if tag in VOID_ELEMENTS:
            return
        # Pop to the nearest matching open tag (tolerates unclosed markup).
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip_tag is not None:
            return
        if data.strip():
            self._stack[-1].children.append(data)


def parse_html(markup: str) -> tuple[Node, str]:
    """Parse HTML into a DOM tree and return ``(root, title)``."""
    builder = _TreeBuilder()
    try:
        builder.feed(markup)
        builder.close()
    except Exception:  # pragma: no cover - html.parser is very tolerant
        pass
    return builder.root, _WS_RE.sub(" ", builder.title).strip()


# ---------------------------------------------------------------------------
# CSS selector subset
# ---------------------------------------------------------------------------

_SIMPLE_TOKEN_RE = re.compile(
    r"(?P<tag>[a-zA-Z][\w-]*)"
    r"|(?P<hash>#[\w-]+)"
    r"|(?P<cls>\.[\w-]+)"
    r"|(?P<attr>\[[^\]]*\])"
)
_SPLIT_RE = re.compile(r"(\s+|>)")


def _parse_simple(token: str) -> dict:
    """Parse one compound simple selector: ``tag``, ``.class``, ``#id``, ``[attr]``."""
    element_id = None
    classes: list[str] = []
    attrs: list[tuple[str, str | None]] = []
    tag: str | None = None
    position = 0

    while position < len(token):
        match = _SIMPLE_TOKEN_RE.match(token, position)
        if not match:
            raise ValidationFailed(
                f"Unsupported selector segment '{token}'. Use tag, .class, #id, "
                "[attr] or tag.class (chained with descendants or '>')."
            )
        if match.group("tag"):
            if position != 0:
                raise ValidationFailed(
                    f"Unsupported selector segment '{token}': a tag name may only "
                    "appear first."
                )
            tag = match.group("tag").lower()
        elif match.group("hash"):
            element_id = match.group("hash")[1:]
        elif match.group("cls"):
            classes.append(match.group("cls")[1:])
        else:
            raw = match.group("attr")[1:-1].strip()
            if "=" in raw:
                name, _, value = raw.partition("=")
                attrs.append((name.strip().lower(), value.strip().strip("\"'")))
            else:
                attrs.append((raw.lower(), None))
        position = match.end()

    if not tag and not classes and element_id is None and not attrs:
        raise ValidationFailed(f"Unsupported selector segment '{token}'.")
    return {"tag": tag, "id": element_id, "classes": classes, "attrs": attrs}


def parse_selector(expression: str) -> list[list[tuple[str | None, dict]]]:
    """Parse a comma-separated selector into groups of ``(combinator, simple)``."""
    groups: list[list[tuple[str | None, dict]]] = []
    for part in str(expression).split(","):
        part = part.strip()
        if not part:
            continue
        chain: list[tuple[str | None, dict]] = []
        pending: str | None = None
        for token in _SPLIT_RE.split(part):
            if token is None:
                continue
            if token.isspace():
                if chain and pending is None:
                    pending = " "
                continue
            if token == ">":
                pending = ">"
                continue
            if not token:
                continue
            chain.append((pending if chain else None, _parse_simple(token)))
            pending = None
        if not chain:
            raise ValidationFailed(f"Empty selector '{expression}'.")
        groups.append(chain)
    if not groups:
        raise ValidationFailed("A selector expression is required.")
    return groups


def _matches_simple(node: Node, simple: dict) -> bool:
    if simple["tag"] and node.tag != simple["tag"]:
        return False
    if simple["id"] and node.id != simple["id"]:
        return False
    if simple["classes"]:
        owned = set(node.classes)
        if not all(cls in owned for cls in simple["classes"]):
            return False
    for name, value in simple.get("attrs") or ():
        if name not in node.attrs:
            return False
        if value is not None and node.attrs.get(name) != value:
            return False
    return True


def _matches_chain(node: Node, chain: list[tuple[str | None, dict]]) -> bool:
    if not _matches_simple(node, chain[-1][1]):
        return False
    current = node
    for index in range(len(chain) - 1, 0, -1):
        combinator = chain[index][0]
        wanted = chain[index - 1][1]
        if combinator == ">":
            current = current.parent
            if current is None or not _matches_simple(current, wanted):
                return False
        else:
            ancestor = current.parent
            while ancestor is not None and not _matches_simple(ancestor, wanted):
                ancestor = ancestor.parent
            if ancestor is None:
                return False
            current = ancestor
    return True


def select(root: Node, expression: str) -> list[Node]:
    groups = parse_selector(expression)
    found: list[Node] = []
    seen: set[int] = set()
    for node in root.iter():
        if isinstance(node, Node) and any(_matches_chain(node, g) for g in groups):
            if id(node) not in seen:
                seen.add(id(node))
                found.append(node)
    return found


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------

@dataclass
class FieldSpec:
    name: str
    selector: str
    match_all: bool = False
    attribute: str | None = None


def _field_value(node: Node, attribute: str | None) -> str:
    if attribute:
        return node.get(attribute) or ""
    return node.text()


def _extract(root: Node, spec: FieldSpec) -> str:
    nodes = select(root, spec.selector)
    if not nodes:
        return ""
    values = [_field_value(n, spec.attribute) for n in nodes]
    values = [v for v in values if v]
    if not values:
        return ""
    return " | ".join(values) if spec.match_all else values[0]


# Selectors tried, in order, when no user field maps to a canonical text column.
_AUTO_TEXT_SELECTORS = ("article", "main", "div.post", "section", "body")
_AUTO_TEXT_LIMIT = 5000


def _auto_text(root: Node) -> str:
    """Best-effort main-content extraction so crawled data feeds the ML pipeline."""
    for selector in _AUTO_TEXT_SELECTORS:
        try:
            nodes = select(root, selector)
        except ValidationFailed:  # pragma: no cover - all built-ins are valid
            continue
        for node in nodes:
            text = node.text()
            if len(text) >= 40:
                return text[:_AUTO_TEXT_LIMIT]
    try:
        paragraphs = [n.text() for n in select(root, "p")]
    except ValidationFailed:  # pragma: no cover
        paragraphs = []
    joined = " ".join(p for p in paragraphs if p).strip()
    return joined[:_AUTO_TEXT_LIMIT]


def _normalize_link(base: str, href: str) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    try:
        absolute, _ = urldefrag(urljoin(base, href))
    except ValueError:
        return None
    parts = urlparse(absolute)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return absolute


def crawl(
    start_url: str,
    *,
    fields: list[FieldSpec] | None = None,
    link_selector: str = "a[href]",
    link_attribute: str = "href",
    max_pages: int | None = None,
    max_depth: int | None = None,
    delay: float | None = None,
    allow_domains: list[str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[list[dict], dict]:
    """Breadth-first same-site crawl returning ``(records, stats)``."""
    fields = fields or []
    if not fields:
        raise ValidationFailed("At least one extraction field (name + selector) is required.")

    pages_cap = max(1, min(max_pages or settings.crawl_max_pages, 200))
    depth_cap = max(0, min(max_depth if max_depth is not None else settings.crawl_max_depth, 10))
    gap = settings.fetch_min_interval if delay is None else max(0.0, float(delay))

    from app.services.fetch_service import validate_url

    start = validate_url(start_url)
    start_host = (urlparse(start).hostname or "").lower()
    permitted = {d.strip().lower() for d in (allow_domains or []) if d.strip()}
    permitted = permitted or {start_host}

    started = time.perf_counter()
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    visited: set[str] = set()
    records: list[dict] = []
    errors: list[dict] = []
    counters = {
        "pages_crawled": 0,
        "pages_skipped": 0,
        "pages_failed": 0,
        "robots_blocked": 0,
        "links_discovered": 0,
        "links_rejected": 0,
    }

    while queue and counters["pages_crawled"] < pages_cap:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        host = (urlparse(url).hostname or "").lower()
        if host not in permitted:
            counters["links_rejected"] += 1
            continue

        try:
            status, headers, body, final_url, _hops = fetch_document(
                url, transport=transport, respect_robots=settings.fetch_robots_obey
            )
        except FetchFailed as exc:
            if "robots.txt" in exc.message:
                counters["robots_blocked"] += 1
            else:
                counters["pages_failed"] += 1
                errors.append({"url": url, "reason": exc.message})
            continue
        except ValidationFailed as exc:
            counters["links_rejected"] += 1
            errors.append({"url": url, "reason": str(exc)})
            continue

        if status >= 400:
            counters["pages_failed"] += 1
            errors.append({"url": url, "reason": f"HTTP {status}"})
            continue

        content_type = (headers.get("content-type") or "").lower()
        if content_type and "html" not in content_type and "xml" not in content_type:
            counters["pages_skipped"] += 1
            continue

        text = body.decode("utf-8", errors="replace")
        if "<" not in text[:2048]:
            counters["pages_skipped"] += 1
            continue

        root, page_title = parse_html(text)
        counters["pages_crawled"] += 1

        record = {
            "url": final_url,
            "title": page_title,
            "depth": depth,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "platform": "web",
            "source": host,
            "domain": host,
            "language": None,
            "collected_via": "smdpis_crawler",
        }
        for spec in fields:
            record[spec.name] = _extract(root, spec)

        # Guarantee a canonical text column so sentiment/topics work out of the box.
        from app.utils.column_detect import CANONICAL_COLUMNS

        text_aliases = {_normalize_key(a) for a in CANONICAL_COLUMNS["text"]}
        if not {_normalize_key(name) for name in record} & text_aliases:
            record["text"] = _auto_text(root)

        records.append(record)

        if depth >= depth_cap:
            continue

        for node in select(root, link_selector):
            href = _field_value(node, link_attribute)
            target = _normalize_link(final_url, href)
            if not target:
                continue
            counters["links_discovered"] += 1
            target_host = (urlparse(target).hostname or "").lower()
            if target_host not in permitted:
                counters["links_rejected"] += 1
                continue
            if target not in visited:
                queue.append((target, depth + 1))

        if queue and gap > 0:
            time.sleep(gap)

    stats = {
        **counters,
        "start_url": start,
        "allowed_domains": sorted(permitted),
        "max_pages": pages_cap,
        "max_depth": depth_cap,
        "records": len(records),
        "errors": errors[:20],
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
    if not records:
        counts = (
            f"pages crawled {counters['pages_crawled']}, "
            f"failed {counters['pages_failed']}, "
            f"blocked by robots.txt {counters['robots_blocked']}, "
            f"skipped as non-HTML {counters['pages_skipped']}"
        )
        reasons = "; ".join(f"{e['url']} -> {e['reason']}" for e in errors[:3])
        detail = f" ({counts})" + (f". First errors: {reasons}" if reasons else "")
        raise ValidationFailed(
            "The crawl produced no records: no page could be fetched and parsed as HTML"
            f"{detail}. Confirm the URL serves HTML in its raw response (content that "
            "renders only via JavaScript is not visible to this crawler). Selector "
            "problems cannot cause this — they would yield empty fields, not zero records."
        )
    return records, stats
