#!/usr/bin/env python3
"""把 MediaCrawler 的 JSONL 转成 miles-detective 的 records.jsonl 记录。

用法：
    python3 mc_to_records.py --case research/R011-某人 --platform zhihu
    python3 mc_to_records.py --case research/R011-某人 --jsonl <文件>

每条内容生成一条 visit（访问）和一条 source（来源），已存在的 URL 会跳过；
原始 JSONL 复制到案例的 raw/ 目录。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "research_log.py"
HOME = Path(os.environ.get("MILES_DETECTIVE_HOME", Path.home() / ".config" / "miles-detective"))
DEFAULT_DATA = Path(os.environ.get("MILES_MC_DATA", HOME / "mc-data"))


def read_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def timestamp_date(value):
    try:
        v = int(value)
    except Exception:
        return ""
    if v > 10 ** 12:  # 毫秒时间戳
        v //= 1000
    try:
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d")
    except Exception:
        return ""


def pick(row, keys):
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def normalize(platform, row):
    """返回 (url, title, author, date, text)。"""
    if platform == "xhs":
        url = pick(row, ["note_url"]) or (
            "https://www.xiaohongshu.com/explore/" + row.get("note_id", ""))
        title = pick(row, ["title"]) or pick(row, ["desc"])[:30]
        author = pick(row, ["nickname"])
        date = timestamp_date(row.get("time"))
        text = pick(row, ["desc"])
    elif platform == "zhihu":
        url = pick(row, ["content_url"])
        if not url:
            cid = row.get("content_id", "")
            url = ("https://www.zhihu.com/answer/" + cid
                   if row.get("content_type") == "answer"
                   else "https://zhuanlan.zhihu.com/p/" + cid)
        title = pick(row, ["title"]) or pick(row, ["desc"])[:30]
        author = pick(row, ["user_nickname", "nickname"])
        date = timestamp_date(row.get("created_time") or row.get("updated_time"))
        text = pick(row, ["content_text"])
    else:
        url = pick(row, ["note_url", "content_url", "aweme_url", "video_url", "url"])
        title = pick(row, ["title", "desc", "content_text"])[:60]
        author = pick(row, ["nickname", "user_nickname", "author", "up_name"])
        date = timestamp_date(row.get("time") or row.get("created_time") or row.get("create_time"))
        text = pick(row, ["desc", "content_text", "text"])
    return url, title, author, date, text


def next_number(records, prefix):
    nums = []
    for r in records:
        rid = r.get("id", "")
        if rid.startswith(prefix) and rid[len(prefix):].isdigit():
            nums.append(int(rid[len(prefix):]))
    return (max(nums) + 1) if nums else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, help="案例目录，需已 init")
    ap.add_argument("--platform", choices=["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"])
    ap.add_argument("--jsonl", help="指定 JSONL 文件；默认取该平台最新一份")
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA), help="MediaCrawler 输出目录")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    case = Path(a.case).expanduser().resolve()
    if not (case / "records.jsonl").is_file():
        print("案例未初始化：%s\n先运行 research_log.py init" % case)
        return 2

    if a.jsonl:
        src = Path(a.jsonl).expanduser()
        platform = a.platform or src.parent.parent.name
    else:
        if not a.platform:
            print("需要 --platform 或 --jsonl")
            return 2
        platform = a.platform
        files = sorted((Path(a.data_dir) / platform / "jsonl").glob("*.jsonl"),
                       key=lambda p: p.stat().st_mtime)
        if not files:
            print("没有找到 %s 的抓取结果" % platform)
            return 2
        src = files[-1]

    rows = read_jsonl(src)
    old = read_jsonl(case / "records.jsonl")
    seen = {r.get("url") for r in old if r.get("kind") == "source"}

    raw_dir = case / "raw"
    raw_dir.mkdir(exist_ok=True)
    raw_name = "mc-%s-%s.jsonl" % (platform, datetime.now().strftime("%Y%m%d"))
    raw_path = "raw/" + raw_name
    if not (case / raw_path).is_file() and not a.dry_run:
        shutil.copyfile(src, case / raw_path)

    vnum = next_number(old, "V")
    snum = next_number(old, "S")
    out = []
    skipped = 0
    for row in rows:
        url, title, author, date, text = normalize(platform, row)
        if not url or not title:
            skipped += 1
            continue
        if url in seen:
            skipped += 1
            continue
        seen.add(url)
        vid, sid = "V%03d" % vnum, "S%03d" % snum
        vnum += 1
        snum += 1
        detail = "MediaCrawler 经 CDP 连接已登录 Chrome，取平台搜索/详情接口；字段含标题、正文、作者、时间与互动数"
        out.append({
            "kind": "visit", "id": vid, "url": url,
            "method": "MediaCrawler (CDP, logged-in Chrome)",
            "detail": detail, "raw_path": raw_path, "outcome": "content",
        })
        out.append({
            "kind": "source", "id": sid, "title": title, "url": url,
            "author": author, "date": date,
            "access": "full_text", "voice": "unresolved", "form": "original",
            "identity": "unresolved",
            "limitation": "%s 平台公开帖子；正文由抓取得到，未逐字回看页面；互动数为抓取时快照" % platform,
            "visit_ids": [vid], "platform": platform,
        })

    if not out:
        print("没有新记录（全部已存在或字段缺失）")
        return 0
    if a.dry_run:
        print("将写入 %d 条记录（visit %d / source %d），示例：\n%s"
              % (len(out), len(out) // 2, len(out) // 2,
                 json.dumps(out[:2], ensure_ascii=False, indent=2)))
        return 0

    tmp = case / "mc-pending.json"
    tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    rc = subprocess.call([sys.executable, str(LOG), "append", str(case), "--input", str(tmp)])
    tmp.unlink(missing_ok=True)
    if rc != 0:
        return rc
    print("已写入 %d 条记录，跳过 %d 条；原始数据 %s" % (len(out), skipped, case / raw_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
