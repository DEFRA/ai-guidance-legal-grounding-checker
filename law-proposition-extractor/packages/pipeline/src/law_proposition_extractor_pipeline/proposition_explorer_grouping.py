"""Explorer grouping mirrors ``proposition-explorer-helpers.tsx`` (lineage keys, merge, partition)."""

from __future__ import annotations

import random
import re
from typing import Any

from .repealed_provisions import is_repealed_or_empty_fragment

CLUSTER_KEY_SEP = "\u001f"
PARTITION_SUBGROUP_APPEND_SEP = "\u001e"
SEMANTIC_MERGE_KEY_FIELD_SEP = "\u001d"
SEMANTIC_MERGE_GROUP_ROW_SEP = "\u001e"

GENERIC_FRAGMENT_LOCATORS = frozenset(
    {"document:full", "full", "document", ""}
)


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def proposition_artifact_fields(row: dict[str, Any]) -> dict[str, str]:
    oa = _as_record(row.get("original_artifact"))
    pk = str(oa.get("proposition_key") or row.get("proposition_key") or "").strip()
    pid = str(oa.get("id") or row.get("id") or "").strip()
    fl = str(oa.get("fragment_locator") or row.get("fragment_locator") or "").strip()
    text = str(oa.get("proposition_text") or row.get("proposition_text") or "").strip()
    return {"id": pid, "proposition_key": pk, "fragment_locator": fl, "proposition_text": text}


def normalize_proposition_text_for_lineage_group(s: str) -> str:
    t = " ".join(s.strip().split()).lower()
    t = re.sub(r"\bshall\b", "must", t)
    t = t.replace("that the information", "that information")
    return t


def normalize_proposition_text(s: str) -> str:
    return " ".join(s.strip().split())


def wording_fingerprint_for_proposition_group_compare(oa: dict[str, Any]) -> str:
    t = str(oa.get("proposition_text") or "") if isinstance(oa.get("proposition_text"), str) else ""
    lab = str(oa.get("label") or "") if isinstance(oa.get("label"), str) else ""
    return f"{normalize_proposition_text(t)}\u001f{normalize_proposition_text(lab)}"


def is_coarse_article_scoped_locator(loc: str) -> bool:
    t = loc.strip().replace("__", "-")
    if not t or t.lower() in GENERIC_FRAGMENT_LOCATORS or ":list:" in t:
        return False
    si = t.find("/")
    if 0 < si <= 200:
        t = t[:si].strip()
    colon_idx = t.find(":")
    if 0 < colon_idx < 24:
        head = t[:colon_idx].lower()
        rest = t[colon_idx + 1 :].strip()
        head_is_role = head in ("article", "section")
        if not head_is_role and re.match(r"^[a-z][a-z0-9_-]{0,20}$", head):
            t = rest
    return bool(re.match(r"^(article|section):\d+[a-z]?$", t, re.I))


def normalize_structured_list_path_segments(path: str) -> str:
    return "-".join(
        s.strip().lower()
        for s in path.replace("__", "-").split("-")
        if s.strip()
    )


def canonical_structured_list_path_key(fragment_locator: str) -> str | None:
    if ":list:" not in fragment_locator:
        return None
    parts = fragment_locator.split(":list:", 2)
    base = (parts[0] or "").strip()
    path = (parts[1].split("/", 1)[0] if len(parts) > 1 else "").strip().replace("__", "-")
    if not path:
        return None
    art_m = re.search(r"(?:article|section)[:/_-]?(\d+[a-z]?)", base, re.I)
    article_num = (art_m.group(1) or "").lower() if art_m else ""
    if not article_num:
        return None
    return f"{article_num}:{path}"


def human_readable_article_locator_lineage_stem(raw_loc: str) -> str | None:
    t = raw_loc.strip()
    multi = re.match(
        r"^article\s+(\d+[a-z]?)\s*((?:\(\s*[^()]+\s*\))+)\s*$",
        t,
        re.I,
    )
    if multi:
        art = multi.group(1).lower()
        inner = [m.group(1).strip().lower() for m in re.finditer(r"\(\s*([^()]+)\s*\)", multi.group(2))]
        if len(inner) >= 2 and re.match(r"^\d+$", inner[0] or ""):
            path = "-".join(inner)
            return f"article:{art}:list:{path}"
    para = re.match(r"^article\s+(\d+[a-z]?)\s*\(\s*(\d+)\s*\)\s*$", t, re.I)
    if para:
        return f"article:{para.group(1).lower()}:para:{para.group(2)}"
    return None


def strip_locator_namespace_for_stem(loc: str) -> str:
    t = loc.strip().replace("__", "-")
    colon_idx = t.find(":")
    if 0 < colon_idx < 24:
        head = t[:colon_idx].lower()
        rest = t[colon_idx + 1 :].strip()
        if head not in ("article", "section") and re.match(r"^[a-z][a-z0-9_-]{0,20}$", head):
            return rest.lower()
    return t.lower()


def canonical_lineage_key_for_grouping(raw_loc: str) -> str | None:
    t = raw_loc.strip()
    if not t or t.lower() in GENERIC_FRAGMENT_LOCATORS:
        return None
    t = t.replace("__", "-")
    si = t.find("/")
    if 0 < si <= 200:
        t = t[:si].strip()
    colon_idx0 = t.find(":")
    if 0 < colon_idx0 < 24:
        head = t[:colon_idx0].lower()
        rest = t[colon_idx0 + 1 :].strip()
        head_is_role = head in ("article", "section")
        if not head_is_role and re.match(r"^[a-z][a-z0-9_-]{0,20}$", head):
            t = rest

    if ":list:" in t.lower():
        path_key = canonical_structured_list_path_key(t)
        if not path_key:
            return None
        io = path_key.find(":")
        if io <= 0:
            return None
        art = path_key[:io].lower()
        path = normalize_structured_list_path_segments(path_key[io + 1 :])
        if not path:
            return None
        return f"article:{art}:list:{path}"

    colon_para = re.match(r"^(article|section):(\d+[a-z]?):para:(\d+)$", t, re.I)
    if colon_para:
        role = "section" if colon_para.group(1).lower() == "section" else "article"
        return f"{role}:{colon_para.group(2).lower()}:para:{colon_para.group(3)}"

    # Pipeline form `article:6:paragraph:1`, `article:6:paragraph:1(a)(i)` — align with `:para:`/`:list:`.
    colon_paragraph = re.match(
        r"^(article|section):(\d+[a-z]?):paragraph:(\d+[a-z]?)((?:\([^()]+\))*)$", t, re.I
    )
    if colon_paragraph:
        role = "section" if colon_paragraph.group(1).lower() == "section" else "article"
        art = colon_paragraph.group(2).lower()
        para = colon_paragraph.group(3).lower()
        subs = [s.strip().lower() for s in re.findall(r"\(([^()]+)\)", colon_paragraph.group(4) or "")]
        if subs:
            return f"{role}:{art}:list:{'-'.join([para, *subs])}"
        return f"{role}:{art}:para:{para}"

    if re.match(r"^article_", t, re.I):
        t = re.sub(r"_", "-", t)
    hyphen_para = re.match(r"^(article|section)-(\d+[a-z]?)-para-(\d+)$", t, re.I)
    if hyphen_para:
        role = "section" if hyphen_para.group(1).lower() == "section" else "article"
        return f"{role}:{hyphen_para.group(2).lower()}:para:{hyphen_para.group(3)}"
    slug_m = re.match(r"^article-(\d+[a-z]?)-(\S+)$", t, re.I)
    if slug_m:
        tail = slug_m.group(2).replace("_", "-")
        if ":" not in tail and not re.match(r"^article\b", tail, re.I):
            path = normalize_structured_list_path_segments(tail)
            if "-" in path:
                return f"article:{slug_m.group(1).lower()}:list:{path}"

    return human_readable_article_locator_lineage_stem(t)


def _source_metadata(as_source: dict[str, Any]) -> dict[str, Any]:
    return _as_record(as_source.get("metadata"))


def parse_year_slash_instrument_token(text: str) -> str | None:
    t = text.replace("\u00a0", " ")
    m = re.search(r"\b(20\d{2})\s*/\s*(\d{3,4})\b", t)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def source_instrument_family_key_from_source_record(source: dict[str, Any]) -> str:
    md = _source_metadata(source)
    inst = str(
        md.get("instrument_id") or md.get("instrumentId") or md.get("instrument_identity") or ""
    ).strip()
    if inst:
        return " ".join(inst.split())
    citation = str(source.get("citation") or "").strip()
    title = str(source.get("title") or "").strip()
    tok = parse_year_slash_instrument_token(f"{citation} {title}")
    if tok:
        return tok
    sid = str(source.get("id") or "").strip()
    return f"__source:{sid}" if sid else "__unknown_source__"


def jurisdiction_for_source(sources: list[dict[str, Any]], source_id: str) -> str:
    for s in sources:
        if str(s.get("id") or "").strip() == source_id:
            j = str(s.get("jurisdiction") or "").strip()
            return j or "—"
    return "—"


def source_instrument_family_key_for_row(
    row: dict[str, Any], sources: list[dict[str, Any]]
) -> str:
    oa = _as_record(row.get("original_artifact"))
    sid = str(oa.get("source_record_id") or "").strip()
    if not sid:
        return "__no_source__"
    for s in sources:
        if str(s.get("id") or "").strip() == sid:
            return source_instrument_family_key_from_source_record(s)
    return f"__orphan__:{sid}"


def parse_article_number_from_reference(ar: str) -> tuple[str, str, str] | None:
    """Returns (role, num, suffix) or None."""
    t = ar.strip()
    if not t:
        return None
    labeled = re.search(r"\b(?:article|art\.?)\s*(\d+[a-z]?)(?:\s*[—–-]\s*.*)?$", t, re.I)
    if labeled:
        return ("article", labeled.group(1).lower(), "")
    sec_lab = re.search(r"\b(?:section|sec\.?)\s*(\d+[a-z]?)(?:\s*[—–-]\s*.*)?$", t, re.I)
    if sec_lab:
        return ("section", sec_lab.group(1).lower(), "")
    bare_num = re.match(r"^(\d+[a-z]?)$", t)
    if bare_num:
        return ("article", bare_num.group(1).lower(), "")
    return None


def canonical_article_from_fragment_locator(raw_loc: str) -> tuple[str, str, str] | None:
    t = raw_loc.strip()
    if not t or t.lower() in GENERIC_FRAGMENT_LOCATORS:
        return None
    li = t.find(":list:")
    if li >= 0:
        t = t[:li].strip()
    si = t.find("/")
    if 0 < si <= 200:
        t = t[:si].strip()
    colon_idx = t.find(":")
    if 0 < colon_idx < 24:
        head = t[:colon_idx].lower()
        rest = t[colon_idx + 1 :].strip()
        head_is_role = head in ("article", "section")
        if not head_is_role and re.match(r"^[a-z][a-z0-9_-]{0,20}$", head):
            t = rest
    t = re.sub(r"__+", "-", t)
    role_hint: str = "section" if re.search(r"section", t, re.I) else "article"
    art_seg = re.search(r"(?:article|section)[:/_-](\d+[a-z]?)", t, re.I)
    if art_seg:
        r = (
            "section"
            if re.search(r"section", art_seg.group(0), re.I)
            else ("section" if re.search(r"section", t, re.I) else "article")
        )
        return (r, art_seg.group(1).lower(), "")
    hyphen_art = re.search(
        r"(?:article|section)-(\d+[a-z]?)(?:[-_.\/](?:\d+|[ivxlcdm]+).*)?$",
        t,
        re.I,
    )
    if hyphen_art:
        frag0 = hyphen_art.group(0).lower()
        r = "section" if "section" in frag0 else ("section" if role_hint == "section" else "article")
        return (r, hyphen_art.group(1).lower(), "")
    glued = re.search(r"(?:article|section)(\d+[a-z]?)(?:[-_./](?:\d+|[ivxlcdm]+).*)?$", t, re.I)
    if glued:
        frag0 = glued.group(0).lower()
        r = "section" if "section" in frag0 else ("section" if role_hint == "section" else "article")
        return (r, glued.group(1).lower(), "")
    spaced_article = re.match(r"^article\s+(\d+[a-z]?)\b", t, re.I)
    if spaced_article and not re.match(r"^section\b", t, re.I):
        return ("article", spaced_article.group(1).lower(), "")
    return None


def _cmp_str(a: str, b: str) -> int:
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def canonical_article_cluster_key(oa: dict[str, Any]) -> str | None:
    ar = str(oa.get("article_reference") or "").strip()
    loc = str(oa.get("fragment_locator") or "").strip()
    from_loc = canonical_article_from_fragment_locator(loc) if loc else None

    if from_loc:
        role, num, suf = from_loc
        return f"{role}:{num}{suf}"

    if ar:
        p = parse_article_number_from_reference(ar)
        if p:
            role, num, suf = p
            return f"{role}:{num}{suf}"
        norm = re.sub(r"[^\w\s_./:-]", "", ar.lower(), flags=re.UNICODE)
        norm = " ".join(norm.split())[:160].strip()
        if norm:
            return f"ref:{norm}"

    if loc and loc.lower() not in GENERIC_FRAGMENT_LOCATORS:
        base = loc.split(":list:", 1)[0].strip() if ":list:" in loc else loc
        slash_idx = base.find("/")
        if slash_idx > 0:
            base = base[:slash_idx].strip()
        base = base.lower().replace("__", "-").strip()
        if 0 < len(base) <= 140:
            return f"loc:{base}"
    return None


def article_cluster_key_from_original_artifact_nodep(oa: dict[str, Any]) -> str:
    canon = canonical_article_cluster_key(oa)
    if canon is not None:
        return canon
    sid = str(oa.get("source_record_id") or "").strip() or "__no_source__"
    return f"{sid}{CLUSTER_KEY_SEP}__no_canonical_article__"


def article_cluster_key_from_row(row: dict[str, Any]) -> str:
    oa = _as_record(row.get("original_artifact"))
    return article_cluster_key_from_original_artifact_nodep(oa)


def group_key_core_for_proposition_row(row: dict[str, Any]) -> str:
    oa = _as_record(row.get("original_artifact"))
    pf = proposition_artifact_fields(row)
    loc = pf["fragment_locator"]
    lineage_key = canonical_lineage_key_for_grouping(loc)
    if lineage_key:
        # `:list:` paths are precise (one proposition per sub-item) → key directly so EU/UK merge.
        # Bare `:para:` paragraphs can hold several distinct rules (e.g. article:39:paragraph:1 → 4)
        # → discriminate by text so identical EU/UK wording merges but distinct rules stay apart.
        if ":list:" in lineage_key:
            return lineage_key
        nt = normalize_proposition_text_for_lineage_group(pf["proposition_text"])
        return f"{lineage_key}::{nt}" if nt else lineage_key
    if loc and is_coarse_article_scoped_locator(loc):
        nt = normalize_proposition_text_for_lineage_group(pf["proposition_text"])
        if nt:
            return f"__coarse_article:{strip_locator_namespace_for_stem(loc)}::{nt}"
    pk = str(oa.get("proposition_key") or "").strip() or pf["proposition_key"]
    if pk:
        return pk
    pid = str(oa.get("id") or "").strip() or pf["id"]
    if pid:
        return f"__opaque:{pid}"
    return f"__row:{random.random().hex(8)}"


def group_key_for_proposition_row(row: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    core = group_key_core_for_proposition_row(row)
    if not sources:
        return core
    fam = source_instrument_family_key_for_row(row, sources)
    return f"{fam}{CLUSTER_KEY_SEP}{core}"


def should_suppress_coarse_parent_proposition_in_default_view(
    row: dict[str, Any], universe: list[dict[str, Any]]
) -> bool:
    pf = proposition_artifact_fields(row)
    # Repealed/omitted placeholders ("Article 5. . . .", "(2). . .", "ANNEX II") carry no
    # extractable content; hide them from the default view (still visible in raw/debug).
    if is_repealed_or_empty_fragment(pf["proposition_text"]):
        return True
    loc = pf["fragment_locator"]
    if not loc or not is_coarse_article_scoped_locator(loc):
        return False
    host_art = canonical_article_from_fragment_locator(loc)
    if not host_art or host_art[0] != "article":
        return False
    has_structured_list_child = False
    for other in universe:
        o = proposition_artifact_fields(other)
        if o["id"] == pf["id"] or o["fragment_locator"] == loc:
            continue
        o_lineage = canonical_lineage_key_for_grouping(o["fragment_locator"])
        o_is_list_row = ":list:" in o["fragment_locator"] or (
            o_lineage is not None and ":list:" in o_lineage
        )
        if not o_is_list_row:
            continue
        ca = canonical_article_from_fragment_locator(o["fragment_locator"])
        if ca and ca[0] == "article" and ca[1] == host_art[1]:
            has_structured_list_child = True
            break
    if not has_structured_list_child:
        return False
    text_lower = pf["proposition_text"].lower()
    return "(a)" in text_lower and "individually identified" in text_lower


def explorer_section_cluster_key_from_row(row: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    if sources:
        fam = source_instrument_family_key_for_row(row, sources)
    else:
        sid = str((_as_record(row.get("original_artifact"))).get("source_record_id") or "").strip()
        fam = f"__src:{sid}" if sid else "__no_source__"
    prov = article_cluster_key_from_row(row)
    return f"{fam}{CLUSTER_KEY_SEP}{prov}"


def _parse_cluster_key_for_sort(key: str) -> tuple[int, int, str, str]:
    no_part = key.split(PARTITION_SUBGROUP_APPEND_SEP, 1)[0]
    si = no_part.find(CLUSTER_KEY_SEP)
    prov = no_part[si + 1 :].strip() if si >= 0 else no_part
    am = re.match(r"^article:(\d+)([a-z]?)$", prov, re.I)
    if am:
        return 0, int(am.group(1)), (am.group(2) or "").lower(), ""
    sm = re.match(r"^section:(\d+)([a-z]?)$", prov, re.I)
    if sm:
        return 1, int(sm.group(1)), (sm.group(2) or "").lower(), ""
    if prov.startswith("ref:"):
        return 2, 0, "", prov[4:]
    if prov.startswith("loc:"):
        return 3, 0, "", prov[4:]
    if prov != key and prov:
        return 4, 0, "", prov
    return 5, 0, "", key


def compare_article_cluster_keys(a: str, b: str) -> int:
    pa = _parse_cluster_key_for_sort(a)
    pb = _parse_cluster_key_for_sort(b)
    if pa[0] != pb[0]:
        return pa[0] - pb[0]
    if pa[0] <= 1:
        if pa[1] != pb[1]:
            return pa[1] - pb[1]
        c = _cmp_str(pa[2], pb[2])
        if c != 0:
            return c
        return 0
    return _cmp_str(pa[3], pb[3])


def compare_explorer_section_cluster_keys(a: str, b: str) -> int:
    sa = a.find(CLUSTER_KEY_SEP)
    sb = b.find(CLUSTER_KEY_SEP)
    fa = a[:sa] if sa >= 0 else ""
    fb = b[:sb] if sb >= 0 else ""
    if fa != fb:
        return _cmp_str(fa, fb)
    pa = a[sa + 1 :] if sa >= 0 else a
    pb = b[sb + 1 :] if sb >= 0 else b
    return compare_article_cluster_keys(pa, pb)


def is_primary_scope_link_row(ln: dict[str, Any]) -> bool:
    relevance = str(ln.get("relevance") or "").strip().lower()
    confidence = str(ln.get("confidence") or "").strip().lower()
    return relevance == "direct" and confidence == "high"


def scope_matches_taxonomy_filter(
    filter_token: str, scope_id: str, scope: dict[str, Any] | None
) -> bool:
    want = filter_token.strip().lower()
    if not want:
        return True
    sid = scope_id.strip().lower()
    if sid == want:
        return True
    if not scope:
        return False
    slug = str(scope.get("slug") or "").strip().lower()
    if slug == want:
        return True
    label = str(scope.get("label") or "").strip().lower()
    if label == want:
        return True
    syn = scope.get("synonyms")
    if isinstance(syn, list):
        for raw in syn:
            if str(raw).strip().lower() == want:
                return True
    return False


def proposition_matches_primary_visible_scope_filter(
    proposition_id: str,
    filter_token: str,
    all_links: list[dict[str, Any]],
    scope_by_id: dict[str, dict[str, Any]],
) -> bool:
    want = filter_token.strip()
    if not want:
        return True
    pid = proposition_id.strip()
    if not pid:
        return False
    for_prop = [ln for ln in all_links if str(ln.get("proposition_id") or "").strip() == pid]
    primary = [ln for ln in for_prop if is_primary_scope_link_row(ln)]
    if not primary:
        return False
    for ln in primary:
        sco = str(ln.get("scope_id") or "").strip()
        sc = scope_by_id.get(sco)
        if scope_matches_taxonomy_filter(want, sco, sc):
            return True
    return False


def dedupe_proposition_rows_by_artifact_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        oa = _as_record(r.get("original_artifact"))
        pid = str(oa.get("id") or "").strip()
        if pid:
            if pid in seen:
                continue
            seen.add(pid)
        out.append(r)
    return out


def sort_proposition_explorer_group_rows(
    rows: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    def rank_j(sid: str) -> int:
        j = jurisdiction_for_source(sources, sid).upper()
        return 0 if j == "EU" else (1 if j == "UK" else 2)

    def sort_key(r: dict[str, Any]) -> tuple[int, str]:
        oa = _as_record(r.get("original_artifact"))
        sid = str(oa.get("source_record_id") or "").strip()
        return (rank_j(sid), sid)

    return sorted(rows, key=sort_key)


def partition_proposition_groups_by_article_cluster(
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in groups:
        rows = list(g.get("rows") or [])
        if not rows:
            continue
        by_cluster: dict[str, list[dict[str, Any]]] = {}
        cluster_order: list[str] = []
        for row in rows:
            ck = article_cluster_key_from_row(row)
            if ck not in by_cluster:
                cluster_order.append(ck)
                by_cluster[ck] = []
            by_cluster[ck].append(row)
        gkey = str(g.get("key") or "")
        for ck in cluster_order:
            chunk = by_cluster[ck]
            if not chunk:
                continue
            sub_key = gkey if len(cluster_order) == 1 else f"{gkey}{PARTITION_SUBGROUP_APPEND_SEP}{ck}"
            out.append({"key": sub_key, "rows": chunk})
    return out


def _primary_scope_ids_signature_for_explorer_merge(
    proposition_id: str, scope_link_rows_by_prop_id: dict[str, list[dict[str, Any]]]
) -> str:
    pid = proposition_id.strip()
    if not pid:
        return ""
    links = scope_link_rows_by_prop_id.get(pid) or []
    ids = [str(ln.get("scope_id") or "").strip() for ln in links if is_primary_scope_link_row(ln)]
    ids.sort()
    return ",".join(ids)


def row_explorer_semantic_merge_key(
    row: dict[str, Any],
    sources: list[dict[str, Any]],
    scope_link_rows_by_prop_id: dict[str, list[dict[str, Any]]] | None = None,
    scope_by_id: dict[str, dict[str, Any]] | None = None,
) -> str:
    oa = _as_record(row.get("original_artifact"))
    pf = proposition_artifact_fields(row)
    fam = source_instrument_family_key_for_row(row, sources)
    sid = str(oa.get("source_record_id") or "").strip()
    jur = jurisdiction_for_source(sources, sid).strip().lower()
    art = article_cluster_key_from_row(row)
    loc_raw = str(pf["fragment_locator"] or "").strip()
    lin = canonical_lineage_key_for_grouping(loc_raw) if loc_raw else None
    lineage_part = lin or (
        f"__no_lineage__:{loc_raw}:"
        f"{str(oa.get('proposition_key') or pf['proposition_key'] or '').strip()}"
    )
    text = normalize_proposition_text_for_lineage_group(pf["proposition_text"])
    status = str(row.get("effective_status") or "").strip().lower()
    kind = str(oa.get("kind") or oa.get("proposition_type") or "").strip().lower()
    pid = str(oa.get("id") or "").strip()
    scope_sig = ""
    if scope_link_rows_by_prop_id is not None and scope_by_id is not None and pid:
        scope_sig = _primary_scope_ids_signature_for_explorer_merge(pid, scope_link_rows_by_prop_id)
    return SEMANTIC_MERGE_KEY_FIELD_SEP.join(
        [fam, jur, art, lineage_part, text, status, kind, scope_sig]
    )


def _group_semantic_merge_signature(
    group: dict[str, Any],
    sources: list[dict[str, Any]],
    scope_link_rows_by_prop_id: dict[str, list[dict[str, Any]]] | None,
    scope_by_id: dict[str, dict[str, Any]] | None,
) -> str:
    rows = list(group.get("rows") or [])
    keys = [
        row_explorer_semantic_merge_key(r, sources, scope_link_rows_by_prop_id, scope_by_id)
        for r in rows
    ]
    keys.sort()
    return SEMANTIC_MERGE_GROUP_ROW_SEP.join(keys)


def collect_row_contributions_for_merge_debug(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    oa = _as_record(row.get("original_artifact"))
    pf = proposition_artifact_fields(row)
    locator_forms: list[str] = []
    fl = str(pf["fragment_locator"] or "").strip()
    if fl:
        locator_forms.append(fl)
    ar = str(oa.get("article_reference") or "").strip()
    if ar:
        locator_forms.append(f"article_ref:{ar}")
    lab = str(oa.get("label") or "").strip()
    if lab:
        locator_forms.append(f"label:{lab}")
    ack = article_cluster_key_from_row(row)
    if ack:
        locator_forms.append(f"article_cluster:{ack}")
    proposition_keys: list[str] = []
    pk = str(oa.get("proposition_key") or pf["proposition_key"] or "").strip()
    if pk:
        proposition_keys.append(pk)
    return locator_forms, proposition_keys


def _canonical_lineage_key_from_merged_rows(rows: list[dict[str, Any]]) -> str | None:
    for r in rows:
        pf = proposition_artifact_fields(r)
        loc = str(pf["fragment_locator"] or "").strip()
        if not loc:
            continue
        c = canonical_lineage_key_for_grouping(loc)
        if c:
            return c
    return None


def merge_semantically_duplicate_proposition_groups(
    groups: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    scope_link_rows_by_prop_id: dict[str, list[dict[str, Any]]] | None = None,
    scope_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for g in groups:
        rows = list(g.get("rows") or [])
        if not rows:
            continue
        sig = _group_semantic_merge_signature(g, sources, scope_link_rows_by_prop_id, scope_by_id)
        gkey = str(g.get("key") or "")
        existing = buckets.get(sig)
        if not existing:
            loc_forms: set[str] = set()
            prop_keys: set[str] = set()
            for r in rows:
                lf, pk = collect_row_contributions_for_merge_debug(r)
                loc_forms.update(lf)
                prop_keys.update(pk)
            buckets[sig] = {
                "key": gkey,
                "rows": dedupe_proposition_rows_by_artifact_id(list(rows)),
                "source_group_keys": [gkey],
                "locator_forms": loc_forms,
                "proposition_keys": prop_keys,
            }
        else:
            existing["source_group_keys"].append(gkey)
            for r in rows:
                lf, pk = collect_row_contributions_for_merge_debug(r)
                existing["locator_forms"].update(lf)
                existing["proposition_keys"].update(pk)
            existing["rows"] = dedupe_proposition_rows_by_artifact_id(existing["rows"] + rows)
            if gkey < existing["key"]:
                existing["key"] = gkey
    result: list[dict[str, Any]] = []
    for b in buckets.values():
        rows = sort_proposition_explorer_group_rows(b["rows"], sources)
        merged_ids = sorted(set(str(x) for x in b["source_group_keys"]), key=lambda x: x)
        merge_debug: dict[str, Any] | None = None
        if len(merged_ids) > 1:
            merged_artifact_ids = sorted(
                {
                    str(_as_record(r.get("original_artifact")).get("id") or "").strip()
                    for r in rows
                    if str(_as_record(r.get("original_artifact")).get("id") or "").strip()
                }
            )
            merge_debug = {
                "mergedGroupCount": len(merged_ids),
                "mergedGroupIds": merged_ids,
                "mergedArtifactIds": merged_artifact_ids,
                "canonicalLineageKey": _canonical_lineage_key_from_merged_rows(rows),
                "contributingLocatorForms": sorted(b["locator_forms"]),
                "contributingPropositionKeys": sorted(b["proposition_keys"]),
            }
        result.append({"key": b["key"], "rows": rows, "mergeDebug": merge_debug})
    return result


def jurisdiction_labels_represented(rows: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        oa = _as_record(row.get("original_artifact"))
        sid = str(oa.get("source_record_id") or "").strip()
        j = jurisdiction_for_source(sources, sid).strip().upper()
        if not j or j == "—" or j in seen:
            continue
        seen.add(j)
        out.append(j)

    def rank(x: str) -> int:
        return 0 if x == "EU" else (1 if x == "UK" else 2)

    return sorted(out, key=lambda x: (rank(x), x))


def prettify_article_heading_fragment(inner: str) -> str:
    t = inner.strip()
    if not t:
        return t
    t = re.sub(
        r"\barticle\s+(\d+[a-z]?)\b", lambda m: f"Article {m.group(1)}", t, flags=re.I
    )
    t = re.sub(
        r"\bsection\s+(\d+[a-z]?)\b", lambda m: f"Section {m.group(1)}", t, flags=re.I
    )
    return t


def format_article_cluster_heading(cluster_key: str) -> str:
    k = (
        cluster_key.split(PARTITION_SUBGROUP_APPEND_SEP, 1)[0]
        if PARTITION_SUBGROUP_APPEND_SEP in cluster_key
        else cluster_key
    )
    if CLUSTER_KEY_SEP in k:
        parts_tail = k.split(CLUSTER_KEY_SEP, 2)[1] if CLUSTER_KEY_SEP in k else ""
        if parts_tail == "__no_canonical_article__":
            return "Unspecified article / locator"
        return (
            format_article_cluster_heading(parts_tail)
            if parts_tail
            else "Unspecified article / locator"
        )
    ref_p = re.match(r"^ref:(.+)$", k)
    if ref_p:
        inner = prettify_article_heading_fragment(ref_p.group(1))
        return inner if len(inner) <= 72 else f"{inner[:68]}…"
    loc_p = re.match(r"^loc:(.+)$", k)
    if loc_p:
        inner = prettify_article_heading_fragment(loc_p.group(1))
        return inner if len(inner) <= 72 else f"{inner[:68]}…"
    art = re.match(r"^article:(\d+)([a-z]?)$", k, re.I)
    if art:
        suf = art.group(2).upper() if art.group(2) else ""
        return f"Article {art.group(1)}{suf}"
    sec = re.match(r"^section:(\d+)([a-z]?)$", k, re.I)
    if sec:
        suf = sec.group(2).upper() if sec.group(2) else ""
        return f"Section {sec.group(1)}{suf}"
    return k if len(k) <= 88 else f"{k[:84]}…"


ARTICLE_HEADLINE_SUBTITLE: dict[str, str] = {
    "109": "database of kept terrestrial animals",
    "114": "identification of kept equine animals",
}


def format_article_cluster_display_heading(
    cluster_key: str,
    *,
    legislative_heading: str | None = None,
) -> str:
    """Article chrome: captured source heading > compatibility subtitle > locator label."""
    art = re.match(r"^article:(\d+)([a-z]?)$", cluster_key, re.I)
    if art:
        # Preserve locator letter case (Article 49a), matching CLML number_label.
        suf = art.group(2) or ""
        num = art.group(1)
        captured = " ".join(str(legislative_heading or "").replace("\xa0", " ").split()).strip()
        if captured:
            return f"Article {num}{suf} — {captured}"
        sub = ARTICLE_HEADLINE_SUBTITLE.get(num.lower())
        if sub:
            return f"Article {num}{suf} — {sub}"
        return f"Article {num}{suf}"
    return format_article_cluster_heading(cluster_key)


def strip_proposition_subgroup_partition_suffix(key: str) -> str:
    i = key.find(PARTITION_SUBGROUP_APPEND_SEP)
    return key[:i] if i >= 0 else key


def build_proposition_groups_pipeline(
    filtered_rows: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    scope_link_rows_by_prop_id: dict[str, list[dict[str, Any]]],
    scope_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    order: list[str] = []
    m: dict[str, list[dict[str, Any]]] = {}
    for row in filtered_rows:
        gk = group_key_for_proposition_row(row, sources)
        if gk not in m:
            order.append(gk)
            m[gk] = []
        m[gk].append(row)
    grouped = [{"key": k, "rows": sort_proposition_explorer_group_rows(m[k], sources)} for k in order]
    partitioned = partition_proposition_groups_by_article_cluster(grouped)
    return merge_semantically_duplicate_proposition_groups(
        partitioned, sources, scope_link_rows_by_prop_id, scope_by_id
    )


def sort_merged_groups_for_explorer(
    groups: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    from functools import cmp_to_key

    def cmp_groups(ga: dict[str, Any], gb: dict[str, Any]) -> int:
        ra = ga.get("rows") or []
        rb = gb.get("rows") or []
        if not ra and not rb:
            return 0
        if not ra:
            return 1
        if not rb:
            return -1
        ka = explorer_section_cluster_key_from_row(ra[0], sources)
        kb = explorer_section_cluster_key_from_row(rb[0], sources)
        c = compare_explorer_section_cluster_keys(ka, kb)
        if c != 0:
            return c
        return _cmp_str(str(ga.get("key") or ""), str(gb.get("key") or ""))

    return sorted(groups, key=cmp_to_key(cmp_groups))


def scope_bucket_for_proposition_group(
    rows: list[dict[str, Any]],
    links_by_prop: dict[str, list[dict[str, Any]]],
    scope_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    slugs: list[str] = []
    for row in rows:
        oa = _as_record(row.get("original_artifact"))
        pid = str(oa.get("id") or "").strip()
        links = links_by_prop.get(pid) or []
        for ln in links:
            if not is_primary_scope_link_row(ln):
                continue
            sco = str(ln.get("scope_id") or "").strip()
            sc = scope_by_id.get(sco)
            if isinstance(sc, dict):
                slug = str(sc.get("slug") or sco).strip()
            else:
                slug = sco.strip()
            if slug and slug not in slugs:
                slugs.append(slug)
    if not slugs:
        return {"clusterKey": "scope:__none__", "label": "Unscoped / other"}
    slugs.sort()
    pick_slug = slugs[0]
    friendly = pick_slug
    for sc in scope_by_id.values():
        if not isinstance(sc, dict):
            continue
        if str(sc.get("slug") or "").strip() == pick_slug:
            friendly = str(sc.get("label") or pick_slug).strip() or pick_slug
            break
    return {"clusterKey": f"scope:{pick_slug}", "label": friendly}


def proposition_row_matches_search(row: dict[str, Any], q: str) -> bool:
    t = q.strip().lower()
    if not t:
        return True
    oa = _as_record(row.get("original_artifact"))
    blobs: list[str] = []
    for k in (
        "proposition_text",
        "label",
        "proposition_key",
        "fragment_locator",
        "article_reference",
        "legal_subject",
        "action",
    ):
        v = oa.get(k) if k in oa else row.get(k)
        if isinstance(v, str) and v.strip():
            blobs.append(v.lower())
    return any(t in b for b in blobs)


def article_filter_matches_group(article_token: str, group: dict[str, Any]) -> bool:
    tok = article_token.strip().lower()
    if not tok:
        return True
    rows = list(group.get("rows") or [])
    if not rows:
        return False
    ck = article_cluster_key_from_row(rows[0])
    heading = format_article_cluster_display_heading(ck).lower()
    core = strip_proposition_subgroup_partition_suffix(str(group.get("key") or "")).lower()
    return tok in ck.lower() or tok in heading or tok in core

