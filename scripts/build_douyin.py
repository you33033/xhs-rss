#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音博主 → RSS。用无头浏览器带 Cookie 抓，签名交给浏览器算。

环境变量：DOUYIN_COOKIE（必填）
输出：public/douyin/feeds/<sec_uid>.xml、public/douyin/all.xml
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public", "douyin")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def as_cookie_list(raw):
    out = []
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out.append({"name": k, "value": v, "domain": ".douyin.com", "path": "/"})
    return out


def parse_aweme(item):
    a = item.get("aweme") or item
    aid = a.get("aweme_id")
    desc = (a.get("desc") or "").strip()
    t = a.get("create_time") or 0
    cover = ""
    video = a.get("video") or {}
    for key in ("cover", "origin_cover", "dynamic_cover"):
        urls = (video.get(key) or {}).get("url_list") or []
        if urls:
            cover = urls[-1]
            break
    if not cover:
        imgs = ((a.get("images") or [{}])[0] or {}).get("url_list") or []
        cover = imgs[-1] if imgs else ""
    author = (a.get("author") or {}).get("nickname", "")
    stats = a.get("statistics") or {}
    like = stats.get("digg_count")
    return {"id": aid, "desc": desc, "time": t, "cover": cover,
            "author": author, "like": like}


def fetch_posts(page, sec_uid, timeout=45000):
    url = f"https://www.douyin.com/user/{sec_uid}"
    try:
        with page.expect_response(
                lambda r: "/aweme/v1/web/aweme/post/" in r.url,
                timeout=timeout) as ei:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        data = ei.value.json()
    except Exception:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return []
    items = data.get("aweme_list") or []
    return [parse_aweme(x) for x in items if x]


def item_xml(p, nickname):
    body = ['<div class="douyin">']
    if p["cover"]:
        body.append(f'<p><img src="{esc(p["cover"])}" /></p>')
    if p["desc"]:
        body.append("<p>" + esc(p["desc"]).replace("\n", "<br/>") + "</p>")
    tail = []
    if p["like"]:
        tail.append(f"♥ {esc(p['like'])}")
    tail.append(f'<a href="https://www.douyin.com/video/{esc(p["id"])}">在抖音打开</a>')
    body.append('<p style="color:#888">' + " · ".join(tail) + "</p></div>")
    title = (p["desc"] or "无标题视频").split("\n")[0][:80]
    ts = p["time"] or time.time()
    return {
        "ts": ts,
        "xml": f"""    <item>
      <title>{esc(title)}</title>
      <link>https://www.douyin.com/video/{esc(p["id"])}</link>
      <guid isPermaLink="true">https://www.douyin.com/video/{esc(p["id"])}</guid>
      <pubDate>{format_datetime(datetime.fromtimestamp(ts, timezone.utc))}</pubDate>
      <description><![CDATA[{''.join(body)}]]></description>
    </item>""",
    }


def channel(title, desc, link, self_url, entries):
    now = format_datetime(datetime.now(timezone.utc))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(title)}</title>
    <link>{esc(link)}</link>
    <description>{esc(desc)}</description>
    <language>zh-CN</language>
    <lastBuildDate>{now}</lastBuildDate>
    <generator>douyin-rss</generator>
    <atom:link href="{esc(self_url)}" rel="self" type="application/rss+xml"/>
{chr(10).join(e["xml"] for e in entries)}
  </channel>
</rss>
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    mock = "--mock" in sys.argv
    cfg_path = os.path.join(ROOT, "douyin.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    users = [u for u in cfg.get("users", []) if u.get("sec_user_id")]
    if not users:
        print("douyin.json 里还没有博主")
        return 1

    base = (os.environ.get("SITE_URL") or "").rstrip("/")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if repo:
            owner, name = repo.split("/")
            base = f"https://{owner}.github.io/{name}"
    if not base:
        base = "https://example.github.io/repo"

    cookie = os.environ.get("DOUYIN_COOKIE", "").strip()
    if not cookie and not mock:
        print("缺少 DOUYIN_COOKIE")
        return 1

    all_entries, failed = [], []
    limit = int(cfg.get("feed_limit") or 20)

    if mock:
        for u in users:
            posts = [{"id": f"mock{i}", "desc": f"{u.get('nickname')} 演示视频 {i}",
                      "time": time.time() - i * 3600, "cover": "", "author": "",
                      "like": 100 * i} for i in range(1, 4)]
            entries = [item_xml(p, u.get("nickname", "")) for p in posts]
            all_entries.extend(entries)
            write(os.path.join(PUBLIC, "feeds", f"{u['sec_user_id']}.xml"),
                  channel(f"抖音 · {u.get('nickname', '')}", "演示",
                          base, f"{base}/douyin/feeds/{u['sec_user_id']}.xml", entries))
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                      viewport={"width": 1366, "height": 900})
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            ctx.add_cookies(as_cookie_list(cookie))
            page = ctx.new_page()
            for u in users:
                uid = u["sec_user_id"]
                name = u.get("nickname") or uid
                print(f"抓取 {name} ...")
                try:
                    posts = fetch_posts(page, uid)
                except Exception as e:
                    print(f"  × {type(e).__name__}: {str(e)[:100]}")
                    failed.append(name)
                    continue
                if not posts:
                    print("  - 没抓到（可能 Cookie 失效或该用户无作品）")
                    failed.append(name)
                    continue
                if name == uid:
                    for x in posts:
                        if x.get("author"):
                            name = x["author"]
                            break
                posts.sort(key=lambda x: x["time"], reverse=True)
                entries = [item_xml(x, name) for x in posts[:limit]]
                all_entries.extend(entries)
                write(os.path.join(PUBLIC, "feeds", f"{uid}.xml"),
                      channel(f"抖音 · {name}", f"{name} 的抖音作品",
                              f"https://www.douyin.com/user/{uid}",
                              f"{base}/douyin/feeds/{uid}.xml", entries))
                print(f"  ✓ {len(entries)} 条")
                time.sleep(2)
            browser.close()

    if all_entries:
        all_entries.sort(key=lambda e: e["ts"], reverse=True)
        write(os.path.join(PUBLIC, "all.xml"),
              channel("抖音 · 全部关注", "所有博主的最新作品", base,
                      f"{base}/douyin/all.xml", all_entries[:60]))
    write(os.path.join(PUBLIC, ".nojekyll"), "")

    if failed:
        print("失败：" + "、".join(failed))
        return 1
    print("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
