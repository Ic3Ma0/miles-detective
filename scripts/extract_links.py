#!/usr/bin/env python3
"""Extract anchors from saved HTML so original links are not lost in text extraction.

Reads local HTML files only; no network access. Outputs every <a href> with its
anchor text, resolved URL, nearest heading and preceding context. Use it before
delivery on every saved page, then compare the result with records.jsonl and the
source catalog.

Examples:
    python3 extract_links.py raw/V39-cnblogs-sohublog.html
    python3 extract_links.py raw --recursive --json --output raw/links.json
    python3 extract_links.py page.html --base-url https://example.org/post/
"""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit

HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
HTML_SUFFIXES = {".html", ".htm", ".xhtml"}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def read_html(path):
    raw = path.read_bytes()
    head = raw[:4096].decode("ascii", "ignore").lower()
    match = re.search(r"charset=[\"']?([\w-]+)", head)
    candidates = [match.group(1)] if match else []
    candidates += ["utf-8", "gb18030", "big5", "latin-1"]
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def base_from_html(text):
    match = re.search(r"<base\s+[^>]*href=[\"']([^\"']+)[\"']", text, re.I)
    return match.group(1).strip() if match else ""


class LinkParser(HTMLParser):
    def __init__(self, base_url=""):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links = []
        self._anchor = None
        self._anchor_text = []
        self._heading = ""
        self._heading_text = []
        self._in_heading = False
        self._visible = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in HEADINGS:
            self._in_heading = True
            self._heading_text = []
        if tag == "a" and attrs.get("href"):
            self._anchor = attrs["href"].strip()
            self._anchor_text = []
            self._anchor_context = clean("".join(self._visible))[-160:]

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self._in_heading:
            self._heading_text.append(data)
        if self._anchor is not None:
            self._anchor_text.append(data)
        self._visible.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in HEADINGS and self._in_heading:
            heading = clean("".join(self._heading_text))
            if heading:
                self._heading = heading
            self._in_heading = False
        if tag == "a" and self._anchor is not None:
            href = self._anchor
            text = clean("".join(self._anchor_text))
            self.links.append({
                "text": text,
                "href": href,
                "resolved": self._resolve(href),
                "heading": self._heading,
                "context": self._anchor_context,
                "flags": self._flags(href),
            })
            self._anchor = None
            self._anchor_text = []

    def _resolve(self, href):
        if href.startswith("//"):
            return "https:" + href
        if self.base_url:
            return urljoin(self.base_url, href)
        return href

    @staticmethod
    def _flags(href):
        low = href.lower()
        flags = []
        if low.startswith("javascript:"):
            flags.append("javascript")
        if low.startswith("mailto:"):
            flags.append("mailto")
        if low.startswith("#"):
            flags.append("fragment")
        if not urlsplit(href).scheme and not href.startswith("//") and not href.startswith("#"):
            flags.append("relative")
        return flags


def extract(path, base_url=""):
    text = read_html(path)
    base = base_url or base_from_html(text)
    parser = LinkParser(base)
    parser.feed(text)
    parser.close()
    seen = {}
    for index, link in enumerate(parser.links, 1):
        link["index"] = index
        key = link["resolved"]
        if key in seen:
            link["flags"].append("duplicate")
        else:
            seen[key] = index
        if not link["text"]:
            link["flags"].append("empty_text")
        if base:
            a, b = urlsplit(base), urlsplit(link["resolved"])
            if a.netloc and b.netloc and a.netloc != b.netloc:
                link["flags"].append("external")
    return {"file": str(path), "base_url": base, "count": len(parser.links), "links": parser.links}


def collect_files(paths, recursive):
    files = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            files.extend(p for p in sorted(path.glob(pattern)) if p.suffix.lower() in HTML_SUFFIXES)
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(raw)
    return files


def passes(link, include, exclude, min_text):
    target = link["resolved"] or link["href"]
    if include and not re.search(include, target, re.I):
        return False
    if exclude and re.search(exclude, target, re.I):
        return False
    if len(link["text"]) < min_text:
        return False
    return True


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def to_markdown(results):
    lines = []
    for result in results:
        kept = result.get("kept", len(result["links"]))
        uniq = len({link["resolved"] for link in result["links"]})
        lines.append(f"### {result['file']}")
        lines.append("")
        lines.append(f"输出 {kept} 个（文件共 {result['count']} 个锚点），唯一地址 {uniq} 个。")
        lines.append("")
        lines.append("| # | 锚文本 | 链接 | 所在标题 | 上下文 | 标记 |")
        lines.append("|---|---|---|---|---|---|")
        for link in result["links"]:
            lines.append("| " + " | ".join(cell(v) for v in (
                link["index"], link["text"], link["resolved"], link["heading"],
                link["context"], ", ".join(link["flags"]) or "—")) + " |")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="HTML 文件或目录")
    parser.add_argument("--recursive", action="store_true", help="递归读取目录")
    parser.add_argument("--base-url", default="", help="解析相对链接用的基准地址；缺省读取 <base href>")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是 Markdown")
    parser.add_argument("--output", help="写入文件；缺省打印到标准输出")
    parser.add_argument("--include", help="只保留匹配该正则的地址")
    parser.add_argument("--exclude", help="排除匹配该正则的地址")
    parser.add_argument("--min-text", type=int, default=0, help="锚文本最少字符数")
    parser.add_argument("--dedupe", action="store_true", help="每个唯一地址只保留第一次出现")
    parser.add_argument("--quiet", action="store_true", help="不打印汇总")
    args = parser.parse_args()

    try:
        files = collect_files(args.paths, args.recursive)
    except FileNotFoundError as exc:
        parser.exit(2, f"路径不存在：{exc}\n")
    if not files:
        parser.exit(2, "没有找到 HTML 文件\n")

    results = []
    total = kept = 0
    for path in files:
        result = extract(path, args.base_url)
        links = [link for link in result["links"] if passes(link, args.include, args.exclude, args.min_text)]
        if args.dedupe:
            seen = set()
            unique = []
            for link in links:
                if link["resolved"] in seen:
                    continue
                seen.add(link["resolved"])
                unique.append(link)
            links = unique
        total += result["count"]
        kept += len(links)
        result["links"] = links
        result["kept"] = len(links)
        results.append(result)

    output = json.dumps(results, ensure_ascii=False, indent=2) if args.json else to_markdown(results)
    if args.output:
        Path(args.output).write_text(output + ("" if output.endswith("\n") else "\n"), encoding="utf-8")
    else:
        print(output)
    if not args.quiet:
        print(f"文件 {len(files)} 个；锚点 {total} 个；输出 {kept} 个。仅解析本地 HTML，未联网。", file=sys.stderr)


if __name__ == "__main__":
    main()
