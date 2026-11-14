#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析「添加博主」Issue，把链接写进 config.json。

环境变量：ISSUE_BODY, XHS_COOKIE（可选）
输出：/tmp/add_msg.md（给 Issue 回复用）、/tmp/add_ok（1/0）
"""

import json
import os
import re
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config.json")


def field(body, name):
    m = re.search(r"###\s*" + re.escape(name) + r"\s*\n+(.*?)(?=\n###|\Z)", body, re.S)
    if not m:
        return ""
    text = m.group(1).strip()
    return "" if text in ("_No response_", "无") else text


def uid_from(text):
    m = re.search(r"user/profile/([0-9a-fA-F]{24})", text)
    if m:
        return m.group(1).lower()
    m = re.search(r"^\s*([0-9a-fA-F]{24})\s*$", text, re.M)
    if m:
        return m.group(1).lower()
    m = re.search(r"https?://[^\s)）]+", text)
    if m:
        url = m.group(0)
        try:
            r = requests.get(url, timeout=20, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            m2 = re.search(r"user/profile/([0-9a-fA-F]{24})", r.url)
            if m2:
                return m2.group(1).lower()
        except Exception:
            pass
    return None


def nickname_of(uid, cookie):
    if not cookie:
        return ""
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from build_feed import client
        info = client(cookie).get_user_info(uid)
        return ((info or {}).get("basic_info") or {}).get("nickname", "")
    except Exception:
        return ""


def main():
    body = os.environ.get("ISSUE_BODY", "")
    link = field(body, "博主主页链接")
    note = field(body, "备注名（可选）")
    msg, ok = "", False

    if not link:
        msg = "❌ 没读到链接，请重新提一个 Issue，把主页链接填进第一栏。"
    else:
        uid = uid_from(link)
        if not uid:
            msg = ("❌ 没认出 user_id。\n\n请在小红书里点博主主页 → 分享 → 复制链接，"
                   "整段贴进来；链接里应包含 `user/profile/` 加 24 位字符。")
        else:
            cfg = json.load(open(CFG, encoding="utf-8"))
            users = cfg.setdefault("users", [])
            exists = next((u for u in users if u["user_id"] == uid), None)
            if exists:
                ok = True
                msg = f"ℹ️ 这个博主已经在订阅里了：**{exists.get('nickname') or uid}**（`{uid}`）"
            else:
                name = note or nickname_of(uid, os.environ.get("XHS_COOKIE", "")) or uid
                users.append({"user_id": uid, "nickname": name})
                json.dump(cfg, open(CFG, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                ok = True
                msg = (f"✅ 已添加 **{name}**（`{uid}`）\n\n"
                       f"订阅地址：`feeds/{uid}.xml`\n"
                       "正在重新抓取，约 1 分钟后可在订阅里看到。")

    open("/tmp/add_msg.md", "w", encoding="utf-8").write(msg)
    open("/tmp/add_ok", "w").write("1" if ok else "0")
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
