#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 config.json 里的博主抓成 RSS，输出到 public/。

本地测试（不联网、不登录）：
    python3 scripts/build_feed.py --mock
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from urllib.parse import urlparse, parse_qsl

import xhs.core as _xhs_core
from xhs import XhsClient
from xhs.exception import DataFetchError, IPBlockError, NeedVerifyError, SignError
from xhshow import Xhshow

# xhs 库会把每个接口返回都 print 出来，Actions 日志里太吵，关掉
_xhs_core.print = lambda *a, **k: None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public")
DETAIL_LIMIT = int(os.environ.get("DETAIL_LIMIT") or 10)
SLEEP = float(os.environ.get("SLEEP") or 1.0)

_XH = Xhshow()


def xhs_sign(uri, data=None, a1="", web_session=""):
    ck = {"a1": a1 or "", "web_session": web_session or ""}
    path = urlparse(uri).path or uri
    rap = path.startswith("/api/sns/web/v1/feed") or "/search/" in path
    if data is None:
        u = urlparse(uri)
        params = dict(parse_qsl(u.query, keep_blank_values=True))
        return _XH.sign_headers_get(u.path or uri, ck, params=params or None,
                                    x_rap=rap)
    return _XH.sign_headers_post(path, ck, payload=data, x_rap=rap)


def client(cookie):
    return XhsClient(cookie=cookie, timeout=25, sign=xhs_sign)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def cdata(s):
    return "<![CDATA[" + str(s).replace("]]>", "]]&gt;") + "]]>"


def cover_url(note):
    cover = note.get("cover") or {}
    for k in ("url_default", "url_pre", "url"):
        if cover.get(k):
            return cover[k].replace("http://", "https://")
    for info in (cover.get("info_list") or []):
        if info.get("url"):
            return info["url"].replace("http://", "https://")
    return ""


def note_link(nid):
    return f"https://www.xiaohongshu.com/explore/{nid}"


def fetch_user(cli, uid):
    res = cli.get_user_notes(uid)
    notes = []
    for n in res.get("notes", []):
        nid = n.get("note_id")
        if not nid:
            continue
        notes.append({
            "note_id": nid,
            "title": (n.get("display_title") or "").strip(),
            "cover": cover_url(n),
            "type": n.get("type", "normal"),
            "liked": ((n.get("interact_info") or {}).get("liked_count") or ""),
            "desc": "",
            "images": [],
            "xsec_token": n.get("xsec_token") or "",
            "time": (n.get("time") or 0) / 1000.0,
        })
    for n in notes[:DETAIL_LIMIT]:
        try:
            res = cli.post("/api/sns/web/v1/feed", {
                "source_note_id": n["note_id"],
                "xsec_token": n.get("xsec_token", ""),
                "xsec_source": "pc_user",
                "image_scenes": ["CRD_WM_WEBP"],
            })
            card = res["items"][0]["note_card"]
        except (DataFetchError, NeedVerifyError, IPBlockError) as e:
            print(f"  ! 详情失败 {n['note_id']}: {str(e)[:80]}")
            break
        except Exception as e:
            print(f"  ! 详情异常 {n['note_id']}: {str(e)[:80]}")
            break
        n["desc"] = card.get("desc") or ""
        n["title"] = n["title"] or (card.get("title") or "").strip()
        n["time"] = (card.get("time") or 0) / 1000.0
        imgs = []
        for img in (card.get("image_list") or [])[:9]:
            u = img.get("url_default") or img.get("url_pre") or ""
            if not u:
                for info in (img.get("info_list") or []):
                    if info.get("url"):
                        u = info["url"]
                        break
            if u:
                imgs.append(u.replace("http://", "https://"))
        n["images"] = imgs
        time.sleep(SLEEP)
    return notes


def item_xml(n, items_meta):
    images = n["images"] or ([n["cover"]] if n["cover"] else [])
    body = ['<div class="xhs-note">']
    for u in images[:9]:
        body.append(f'<p><img src="{esc(u)}" /></p>')
    if n["desc"]:
        body.append("<p>" + esc(n["desc"]).replace("\n", "<br/>") + "</p>")
    tail = []
    if n["liked"]:
        tail.append(f"♥ {esc(n['liked'])}")
    if items_meta.get("nickname"):
        tail.append(esc(items_meta["nickname"]))
    tail.append(f'<a href="{esc(note_link(n["note_id"]))}">在小红书打开</a>')
    body.append('<p style="color:#888">' + " · ".join(tail) + "</p></div>")

    ts = n.get("time") or time.time()
    title = n["title"] or "无标题笔记"
    return {
        "ts": ts,
        "xml": f"""    <item>
      <title>{esc(title)}</title>
      <link>{esc(note_link(n["note_id"]))}</link>
      <guid isPermaLink="true">{esc(note_link(n["note_id"]))}</guid>
      <pubDate>{format_datetime(datetime.fromtimestamp(ts, timezone.utc))}</pubDate>
      <description>{cdata(''.join(body))}</description>
    </item>""",
    }


def channel_xml(title, description, link, self_url, entries):
    now = format_datetime(datetime.now(timezone.utc))
    items = "\n".join(e["xml"] for e in entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(title)}</title>
    <link>{esc(link)}</link>
    <description>{esc(description)}</description>
    <language>zh-CN</language>
    <lastBuildDate>{now}</lastBuildDate>
    <generator>xhs-rss-cloud</generator>
    <atom:link href="{esc(self_url)}" rel="self" type="application/rss+xml"/>
{items}
  </channel>
</rss>
"""


INDEX_HTML = """<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>小红书 RSS</title>
<style>
body{{font:16px/1.7 -apple-system,"PingFang SC",system-ui,sans-serif;max-width:640px;
margin:0 auto;padding:24px 16px;color:#1b1d22;background:#f6f7f9}}
h1{{font-size:20px;margin:0 0 4px}}p.sub{{color:#767b84;font-size:13px;margin:0 0 20px}}
.card{{background:#fff;border:1px solid #e6e8ec;border-radius:14px;padding:14px;margin-bottom:12px}}
.name{{font-weight:600}}a{{color:#ff2442;word-break:break-all;font-size:13px}}
code{{display:block;background:#f4f5f7;padding:8px 10px;border-radius:8px;
font-size:12px;word-break:break-all;margin-top:6px}}
.ts{{color:#9aa0aa;font-size:12px}}
</style></head><body>
<h1>小红书 RSS</h1>
<p class="sub">由 GitHub Actions 定时更新 · 最近更新 {now}</p>
{cards}
<div class="card"><div class="name">全部合成一个源</div>
<div class="ts">想一个源看所有博主就用这个</div><code>{base}/all.xml</code></div>
</body></html>
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def mock_user(uid, name):
    now = time.time()
    return [{
        "note_id": f"mock{i}", "title": f"{name} 的演示笔记 {i}",
        "cover": "", "type": "normal", "liked": str(100 * i),
        "desc": "这是 --mock 生成的假数据，用来检查排版。",
        "images": [], "time": now - i * 3600,
    } for i in range(1, 4)]


def main():
    mock = "--mock" in sys.argv
    cfg_path = os.path.join(ROOT, "config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    users = [u for u in cfg.get("users", []) if u.get("user_id")]
    if not users:
        print("config.json 里还没有博主")
        return 1

    base = (os.environ.get("SITE_URL") or "").rstrip("/")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if repo:
            owner, name = repo.split("/")
            base = f"https://{owner}.github.io/{name}"
    if not base:
        base = "https://example.github.io/repo"

    cookie = os.environ.get("XHS_COOKIE", "").strip()
    if not cookie and not mock:
        print("缺少 XHS_COOKIE 环境变量（仓库 Secret）")
        return 1
    cli = None if mock else client(cookie)

    all_entries = []
    failed = []
    for u in users:
        uid = u["user_id"].lower()
        name = u.get("nickname") or uid
        print(f"抓取 {name} ({uid}) ...")
        try:
            notes = mock_user(uid, name) if mock else fetch_user(cli, uid)
        except Exception as e:
            print(f"  × 失败：{type(e).__name__} {str(e)[:120]}")
            failed.append(name)
            continue
        if not notes:
            print("  - 没有笔记")
            continue
        entries = [item_xml(n, {"nickname": name}) for n in notes]
        entries.sort(key=lambda e: e["ts"], reverse=True)
        limit = int(cfg.get("feed_limit") or 20)
        entries = entries[:limit]
        all_entries.extend(entries)
        xml = channel_xml(f"小红书 · {name}", f"{name} 的小红书笔记",
                          f"https://www.xiaohongshu.com/user/profile/{uid}",
                          f"{base}/feeds/{uid}.xml", entries)
        write(os.path.join(PUBLIC, "feeds", f"{uid}.xml"), xml)
        print(f"  ✓ {len(entries)} 条")
        if not mock:
            time.sleep(SLEEP * 2)

    if all_entries:
        all_entries.sort(key=lambda e: e["ts"], reverse=True)
        write(os.path.join(PUBLIC, "all.xml"),
              channel_xml("小红书 · 全部关注", "所有博主的最新笔记", base,
                          f"{base}/all.xml", all_entries[:60]))

    stamp = datetime.now().strftime("%m-%d %H:%M")
    cards = "\n".join(
        f'<div class="card"><div class="name">{esc(u.get("nickname") or u["user_id"])}</div>'
        f'<code>{base}/feeds/{u["user_id"].lower()}.xml</code></div>'
        for u in users
    )
    write(os.path.join(PUBLIC, "index.html"),
          INDEX_HTML.format(now=stamp, cards=cards, base=base))
    write(os.path.join(PUBLIC, ".nojekyll"), "")

    if failed:
        print("失败的博主：" + "、".join(failed))
        return 1
    print("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
