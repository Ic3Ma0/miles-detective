#!/usr/bin/env python3
"""MediaCrawler 统一入口（批量采集层）。

用法：
    python3 mediacrawler.py --root <MediaCrawler目录> xhs search "人物名" --limit 20
    python3 mediacrawler.py --root <MediaCrawler目录> zhihu detail "<URL>"

前提：MediaCrawler 已在该目录执行过 uv sync；Chrome 已开启远程调试
（chrome://inspect/#remote-debugging），运行时在浏览器里点“接受”。

许可证提醒：MediaCrawler 为非商用学习许可，仅用于个人研究。
"""

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("MILES_DETECTIVE_HOME", Path.home() / ".config" / "miles-detective"))


def cdp_open(port=9222):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    ap = argparse.ArgumentParser(description="MediaCrawler 统一入口")
    ap.add_argument("platform", choices=["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"])
    ap.add_argument("kind", choices=["search", "detail", "creator"])
    ap.add_argument("target", nargs="?", default="", help="关键词 / 帖子URL或ID / 创作者ID")
    ap.add_argument("--root", default=os.environ.get("MILES_MC_ROOT", str(HOME / "MediaCrawler")),
                    help="MediaCrawler 目录")
    ap.add_argument("--data-dir", default=os.environ.get("MILES_MC_DATA", str(HOME / "mc-data")),
                    help="抓取结果输出目录")
    ap.add_argument("--limit", type=int, default=15, help="最多抓取条数")
    ap.add_argument("--lt", default="qrcode", choices=["qrcode", "phone", "cookie"])
    ap.add_argument("--no-comment", action="store_true", help="不抓评论")
    ap.add_argument("--sub-comment", action="store_true", help="抓二级评论")
    ap.add_argument("--media", action="store_true", help="下载图片/视频")
    a = ap.parse_args()

    root = Path(a.root).expanduser().resolve()
    if not (root / "main.py").is_file():
        print("找不到 MediaCrawler：%s（需要包含 main.py）" % root)
        return 2
    if not cdp_open():
        print("127.0.0.1:9222 未监听。请先在 Chrome 打开")
        print("  chrome://inspect/#remote-debugging")
        print("勾选“Allow remote debugging for this browser instance”，看到")
        print("  Server running at: 127.0.0.1:9222")
        return 2

    cmd = [
        "uv", "run", "--directory", str(root), "main.py",
        "--platform", a.platform,
        "--type", a.kind,
        "--lt", a.lt,
        "--crawler_max_notes_count", str(a.limit),
        "--save_data_path", str(Path(a.data_dir).expanduser()),
        "--get_comment", "no" if a.no_comment else "yes",
        "--get_sub_comment", "yes" if a.sub_comment else "no",
        "--get_media", "yes" if a.media else "no",
    ]
    if a.kind == "search":
        if not a.target:
            print("search 模式需要关键词")
            return 2
        cmd += ["--keywords", a.target]
    elif a.kind == "detail":
        cmd += ["--specified_id", a.target]
    else:
        cmd += ["--creator_id", a.target]

    print("运行：" + " ".join(cmd))
    rc = subprocess.call(cmd)
    print("\n输出目录：%s" % (Path(a.data_dir).expanduser() / a.platform))
    return rc


if __name__ == "__main__":
    sys.exit(main())
