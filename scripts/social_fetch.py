#!/usr/bin/env python3
"""按平台取回社交平台公开页面正文。

用法：
    python3 social_fetch.py login <site>            一次性登录，profile 会保存
    python3 social_fetch.py fetch <url> [--out DIR] [--wait 秒] [--headed]
    python3 social_fetch.py bilibili <BV号或URL>

<site> 取值：zhihu weibo xhs x douyin bilibili
profile 目录：~/.config/miles-detective/browser-profile
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

PROFILE_DIR = Path.home() / ".config" / "miles-detective" / "browser-profile"
DEFAULT_OUT = Path.home() / ".config" / "miles-detective" / "captures"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SITES = {
    "zhihu": ("https://www.zhihu.com/signin", ["main", ".QuestionAnswer-content", ".RichText"]),
    "weibo": ("https://m.weibo.cn/", [".card", ".card-wrap"]),
    "xhs": ("https://www.xiaohongshu.com/", ["#detail-title", ".note-text", ".note-content"]),
    "x": ("https://x.com/login", ['article[data-testid="tweet"]']),
    "douyin": ("https://www.douyin.com/", ['[data-e2e="user-detail"]', '[data-e2e="user-post-list"]']),
    "bilibili": ("https://www.bilibili.com/", [".video-title", ".desc-info"]),
}

LOGIN_HINTS = ("signin", "login", "unhuman", "passport.weibo", "/account/")
LOGIN_TITLES = ("安全验证", "登录", "Sina Visitor System", "Log in", "Sign up")

# 登录态自检：站点 → (检查地址, 登录后才出现的选择器)
CHECK = {
    "zhihu": ("https://www.zhihu.com/", None),
    "xhs": ("https://www.xiaohongshu.com/explore", None),
    "x": ("https://x.com/home", '[data-testid="SideNav_AccountSwitcher_Button"]'),
    "douyin": ("https://www.douyin.com/user/self", '[data-e2e="user-avatar"]'),
}


def normalize(url):
    host = urlparse(url).netloc
    if host.endswith("weibo.com") and "/u/" in url:
        uid = re.search(r"/u/(\d+)", url)
        if uid:
            return "https://m.weibo.cn/u/" + uid.group(1)
    return url


def site_of(url):
    host = urlparse(url).netloc.lower()
    for key, domains in {
        "zhihu": ("zhihu.com",),
        "weibo": ("weibo.com", "weibo.cn"),
        "xhs": ("xiaohongshu.com", "xhslink.com"),
        "x": ("x.com", "twitter.com"),
        "douyin": ("douyin.com", "iesdouyin.com"),
        "bilibili": ("bilibili.com", "b23.tv"),
    }.items():
        if any(host.endswith(d) for d in domains):
            return key
    return None


def launch(p, headless):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        locale="zh-CN",
        viewport={"width": 1440, "height": 900},
        user_agent=UA,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    return ctx


def is_login_wall(page):
    url = page.url.lower()
    if any(h in url for h in LOGIN_HINTS):
        return True
    title = page.title() or ""
    if any(t in title for t in LOGIN_TITLES):
        return True
    try:
        body = page.inner_text("body", timeout=3000)
    except Exception:
        return False
    return len(body.strip()) < 120


def extract(page, site):
    """返回 (正文, 命中的选择器)。"""
    selectors = SITES.get(site, (None, ["article", "main"]))[1]
    for sel in selectors:
        try:
            nodes = page.query_selector_all(sel)
        except Exception:
            continue
        texts = []
        for n in nodes:
            try:
                t = n.inner_text().strip()
            except Exception:
                continue
            if t:
                texts.append(t)
        if texts and sum(len(t) for t in texts) > 80:
            return "\n\n".join(texts), sel
    return page.inner_text("body").strip(), "body"


def fetch(url, out_dir, wait_s, headed):
    from playwright.sync_api import sync_playwright

    url = normalize(url)
    site = site_of(url)
    with sync_playwright() as p:
        ctx = launch(p, headless=not headed)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=wait_s * 1000)
        except Exception:
            pass
        page.wait_for_timeout(min(wait_s, 8) * 1000)

        wall = is_login_wall(page)
        if site == "douyin" and "/user/" in page.url:
            if not page.query_selector('[data-e2e="user-avatar"]'):
                wall = True
        if wall:
            print("LOGIN_REQUIRED")
            print("最终地址：" + page.url)
            print("请先运行：python3 %s login %s" % (sys.argv[0], site or "<site>"))
            ctx.close()
            return 2

        text, sel = extract(page, site)
        title = page.title()
        meta = {
            "url": url,
            "final_url": page.url,
            "site": site,
            "title": title,
            "selector": sel,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "chars": len(text),
        }

        out_dir = Path(out_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^0-9A-Za-z._-]+", "_", (site or "page") + "_" + (title or "untitled"))[:80]
        (out_dir / (stem + ".md")).write_text(
            "# %s\n\n- 来源：%s\n- 最终地址：%s\n- 取回时间：%s\n- 提取选择器：%s\n\n---\n\n%s\n"
            % (title, url, page.url, meta["fetched_at"], sel, text),
            encoding="utf-8",
        )
        (out_dir / (stem + ".html")).write_text(page.content(), encoding="utf-8")
        (out_dir / (stem + ".json")).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("OK %s | %s | %d 字 | %s" % (site, title[:60], len(text), out_dir / (stem + ".md")))
        print(text[:400].replace("\n", " | "))
        ctx.close()
        return 0


def bilibili(target):
    """B 站公开接口：视频信息 + 分 P。不需要登录。"""
    import urllib.request

    m = re.search(r"(BV[0-9A-Za-z]+)", target)
    if not m:
        print("没有识别出 BV 号")
        return 2
    bvid = m.group(1)
    api = "https://api.bilibili.com/x/web-interface/view?bvid=" + bvid
    req = urllib.request.Request(api, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if data.get("code") != 0:
        print("ERROR", data.get("message"))
        return 1
    d = data["data"]
    print("标题：%s\nUP主：%s\n发布：%s\n播放：%s\n简介：%s" % (
        d.get("title"), d.get("owner", {}).get("name"),
        time.strftime("%Y-%m-%d", time.localtime(d.get("pubdate", 0))),
        d.get("stat", {}).get("view"), (d.get("desc") or "")[:300]))
    return 0


def login(site):
    from playwright.sync_api import sync_playwright

    if site not in SITES:
        print("未知站点，可选：" + " ".join(SITES))
        return 2
    url = SITES[site][0]
    with sync_playwright() as p:
        ctx = launch(p, headless=False)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print("浏览器已打开：%s" % url)
        print("请在这个窗口完成登录（扫码/验证码），登录成功后直接关闭窗口。")
        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                if not ctx.pages:
                    break
                page.wait_for_timeout(1000)
            except Exception:
                break
        try:
            ctx.close()
        except Exception:
            pass
    print("登录态已保存到：%s" % PROFILE_DIR)
    return 0


def status():
    """逐个平台检查 profile 里的登录态。"""
    import urllib.request
    from playwright.sync_api import sync_playwright

    rows = [("weibo", True, "免登录可用")]
    try:
        req = urllib.request.Request(
            "https://api.bilibili.com/x/web-interface/nav", headers={"User-Agent": UA}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r).get("data", {})
        rows.append(("bilibili", bool(d.get("isLogin")), "账号 " + (d.get("uname") or "-")))
    except Exception as e:
        rows.append(("bilibili", None, type(e).__name__))

    with sync_playwright() as p:
        ctx = launch(p, headless=True)
        page = ctx.new_page()
        for site, (url, marker) in CHECK.items():
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                ok = not is_login_wall(page)
                if ok and marker:
                    ok = bool(page.query_selector(marker))
                rows.append((site, ok, page.url[:70]))
            except Exception as e:
                rows.append((site, None, type(e).__name__))
        ctx.close()

    for site, ok, note in sorted(rows):
        print("%-9s %s  %s" % (site, "已登录" if ok else ("未登录" if ok is False else "无法判断"), note))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    lg = sub.add_parser("login")
    lg.add_argument("site")
    ft = sub.add_parser("fetch")
    ft.add_argument("url")
    ft.add_argument("--out", default=str(DEFAULT_OUT))
    ft.add_argument("--wait", type=int, default=8)
    ft.add_argument("--headed", action="store_true")
    bl = sub.add_parser("bilibili")
    bl.add_argument("target")
    a = ap.parse_args()
    if a.cmd == "status":
        return status()
    if a.cmd == "login":
        return login(a.site)
    if a.cmd == "bilibili":
        return bilibili(a.target)
    return fetch(a.url, a.out, a.wait, a.headed)


if __name__ == "__main__":
    sys.exit(main())
