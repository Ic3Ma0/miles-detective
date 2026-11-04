"""Shared mechanical evidence checks; declarations do not certify content truth."""
import posixpath

ENUMS = {
    "status": {"documented", "corroborated", "disputed", "unverified"},
    "date_precision": {"day", "month", "year", "range", "unknown"},
    "scope": {"main", "background", "outside_window"},
    "evidence_type": {"self_account", "journalist_report", "institution_record", "mixed", "unknown"},
}
REQUIRED = ("id", "title", "summary", "status", "date_precision", "scope", "evidence_type")


class EvidenceError(ValueError):
    pass


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_event_structure(event, index):
    if not isinstance(event, dict):
        raise EvidenceError(f"第 {index} 条不是对象")
    rid = event.get("id") or f"#{index}"
    for key in REQUIRED:
        if not nonempty(event.get(key)):
            raise EvidenceError(f"{rid}: 缺少非空 {key}")
    for key, allowed in ENUMS.items():
        if event[key] not in allowed:
            raise EvidenceError(f"{rid}: 无效 {key}={event[key]!r}")
    if event["date_precision"] != "unknown" and not nonempty(event.get("date")):
        raise EvidenceError(f"{rid}: 非 unknown 日期精度须有 date")

    source_ids = event.get("source_ids", [])
    claim_ids = event.get("claim_ids", [])
    locators = event.get("sources", [])
    for name, values in (("source_ids", source_ids), ("claim_ids", claim_ids)):
        if not isinstance(values, list) or not all(nonempty(v) for v in values):
            raise EvidenceError(f"{rid}: {name} 须为非空字符串数组")
    if not isinstance(locators, list):
        raise EvidenceError(f"{rid}: sources 须为数组")
    if not source_ids and not claim_ids and not locators:
        raise EvidenceError(f"{rid}: 须引用至少一个来源、结论或文件定位")

    for loc in locators:
        if not isinstance(loc, dict):
            raise EvidenceError(f"{rid}: sources 项须为对象")
        for field in ("source_id", "id", "file"):
            if field in loc and not nonempty(loc[field]):
                raise EvidenceError(f"{rid}: sources.{field} 须为非空字符串")
        sid = loc.get("source_id") or loc.get("id")
        if not nonempty(sid) and not nonempty(loc.get("file")):
            raise EvidenceError(f"{rid}: sources 项须有 source_id、id 或 file")
        if "lines" in loc and not nonempty(str(loc["lines"])):
            raise EvidenceError(f"{rid}: sources.lines 不能为空")
        if "group" in loc and not nonempty(loc["group"]):
            raise EvidenceError(f"{rid}: sources.group 不能为空")

    if "people" in event and (not isinstance(event["people"], list) or not all(nonempty(p) for p in event["people"])):
        raise EvidenceError(f"{rid}: people 须为非空字符串数组")



def usable(source):
    return source.get("access") not in {"unretrieved", "search_only"}


def canonical_groups(identities):
    """Duplicate identities connect group names; numbering cannot add origins."""
    parents, first = {}, {}

    def root(group):
        parents.setdefault(group, group)
        if parents[group] != group:
            parents[group] = root(parents[group])
        return parents[group]

    for identity, group in identities:
        if group:
            previous = first.setdefault(identity, group)
            parents[root(group)] = root(previous)
    return {group: root(group) for group in parents}


def independent_pair(supports):
    groups = canonical_groups(supports)
    return any(a != b and ga and gb and groups[ga] != groups[gb]
               for a, ga in supports for b, gb in supports)


def known_groups(sources):
    return canonical_groups((source["url"], source.get("same_source_group"))
                            for source in sources.values() if source.get("kind") == "source")


def claim_support(record, sources):
    groups = known_groups(sources)
    return [("url:" + sources[e["source_id"]]["url"],
             groups.get(sources[e["source_id"]].get("same_source_group")))
            for e in record.get("evidence", [])
            if e.get("relation") == "supports" and e.get("source_id") in sources
            and usable(sources[e["source_id"]])]


def event_support(event, sources=None):
    """Resolve aliases and declarations, using known source facts when available.

    Unknown file/ID locators remain declarations, preserving lightweight checks.
    A locator carrying both an ID and file links those identities for this event.
    """
    sources = sources or {}
    groups = known_groups(sources)
    rid = event["id"]
    declared = event.get("source_groups", {})
    if not isinstance(declared, dict):
        raise EvidenceError(f"{rid}: source_groups 须为对象")
    locators = [{"source_id": sid} for sid in event.get("source_ids", [])] + event.get("sources", [])
    parents = {}

    def root(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = root(parents[key])
        return parents[key]

    entries = []
    for loc in locators:
        sid = loc.get("source_id") or loc.get("id")
        keys = []
        known = sources.get(sid)
        if sid:
            keys.append("url:" + known["url"] if known else "id:" + sid)
        if loc.get("file"):
            keys.append("file:" + posixpath.normpath(loc["file"]))
        for key in keys[1:]:
            parents[root(key)] = root(keys[0])
        group = known.get("same_source_group") if known else None
        declarations = [g for g in (loc.get("group"), declared.get(sid)) if g is not None]
        for value in declarations:
            if not nonempty(value):
                raise EvidenceError(f"{rid}: 来源 {sid or loc.get('file')} 的 group 不能为空")
            if group is not None and value != group:
                raise EvidenceError(f"{rid}: 来源 {sid or loc.get('file')} 的同源组声明与已知来源或定位冲突")
            # A known source without a group cannot gain one from a locator.
            if known is None:
                group = value
        if known is not None and declarations and group is None:
            raise EvidenceError(f"{rid}: 来源 {sid} 的 group 声明与已知来源缺失的 same_source_group 冲突")
        entries.append((keys[0], group, known))

    by_identity = {}
    for key, group, known in entries:
        by_identity.setdefault(root(key), []).append((group, known))
    result = []
    for key, values in by_identity.items():
        known_values = [(group, source) for group, source in values if source is not None]
        local_groups = {group for group, source in values if source is None and group}
        if len(local_groups) > 1:
            raise EvidenceError(f"{rid}: 同一来源 {key} 的同源组声明冲突")
        if known_values:
            for group in local_groups:
                if any(group != known_group for known_group, _ in known_values):
                    raise EvidenceError(f"{rid}: 同一来源 {key} 的同源组声明与已知来源冲突")
            # File aliases inherit known acquisition limits, even when they
            # appear before the locator that links the file to a source ID.
            result.extend((key, group) for group, source in known_values if usable(source))
        else:
            result.append((key, next(iter(local_groups), None)))
    return [(key, groups.get(group, group)) for key, group in result]


def check_event_evidence(event, sources=None, claims=None):
    supports = event_support(event, sources)
    rid = event["id"]
    if event["status"] == "corroborated":
        if sources is None and any(not group for _, group in supports):
            raise EvidenceError(f"{rid}: corroborated 的来源或文件定位须标 group / source_groups")
        if not independent_pair(supports):
            raise EvidenceError(f"{rid}: corroborated 至少需要两个已取得、不同 URL / 来源且不同同源组的支持来源")
    if event["status"] != "unverified":
        usable_claim = (sources is None and bool(event.get("claim_ids"))) or any((claims or {}).get(cid, {}).get("status", "unverified") != "unverified"
                           for cid in event.get("claim_ids", []))
        if not supports and not usable_claim:
            raise EvidenceError(f"{rid}: 已记载事件不能只有未取得材料或搜索摘要")
