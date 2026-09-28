#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cnblogs 单篇/最新几篇 → 小红书发布看板数据

用法（在项目根目录 blog/ 下执行）：
    # 单个 cnblogs URL（本地已有该文章则直接读本地，否则抓取）
    python3 scripts/prepare_cnblogs.py "https://www.cnblogs.com/zjdxr-up/p/23049231"
    # 直接用文章 pid
    python3 scripts/prepare_cnblogs.py 23049231
    # 取 sitemap 里最新 N 篇（默认 5）批量生成看板
    python3 scripts/prepare_cnblogs.py --latest 5

    # 本地标记某篇为「已发布」，随后 commit & push 即可同步到看板
    python3 scripts/prepare_cnblogs.py --mark-published 23049231

产出：
    public/publish/<pid>/cover.png     # 小红书封面
    src/data/publish.json              # 看板数据（标题/正文/话题/配图/状态）
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import sync_cnblogs  # noqa: E402  复用 fetch / parse_post
import publish_xhs   # noqa: E402  复用适配逻辑（正文/标题/话题/封面/类型）

POSTS = ROOT / "src/content/posts"
PUBLISH_PUBLIC = ROOT / "public" / "publish"
DATA_FILE = ROOT / "src" / "data" / "publish.json"
ACTIVITY_FILE = ROOT / "src" / "data" / "activity.json"
VALID_STATUS = ("draft", "pending", "published", "archived")
CNBLOGS_PID_RE = re.compile(r"/p/(\d+)")

DEFAULT_LATEST = 5


def load_index():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_index(items):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_activity():
    if ACTIVITY_FILE.exists():
        try:
            return json.loads(ACTIVITY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_activity(records):
    ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVITY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_activity(records, atype, pid, title, detail):
    records.insert(0, {
        "id": f"act_{int(datetime.now(timezone.utc).timestamp())}_{pid}",
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": atype,
        "source_type": "cnblogs",
        "pid": pid,
        "title": title[:40],
        "detail": detail,
    })
    save_activity(records)


def read_local_post(pid):
    """读本地 markdown，返回 (fm, body)；不存在返回 None。"""
    p = POSTS / f"{pid}.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    fm_end = text.find("\n---", 3)
    if fm_end == -1:
        return None
    fm = yaml.safe_load(text[3:fm_end]) or {}
    body = text[fm_end + 4:].lstrip("\n")
    return fm, body


def fetch_single(pid):
    """抓取 cnblogs 单篇，返回 (fm, body)。"""
    data = sync_cnblogs.parse_post(pid)
    if not data:
        sys.exit(f"[错误] 抓取失败：{pid}")
    return {"title": data["title"], "tags": []}, data["body"]


def latest_pids(n):
    """从 sitemap 取最新 n 个 pid。"""
    pids = sync_cnblogs.sitemap_pids()
    if not pids:
        sys.exit("[错误] 获取 cnblogs sitemap 失败")
    return pids[:n]


def extract_pid(target):
    m = CNBLOGS_PID_RE.search(target)
    if m:
        return m.group(1)
    if target.isdigit():
        return target
    sys.exit(f"[错误] 无法从输入中解析出 pid：{target}")


def build_item(pid, fm, body, status="pending"):
    """生成一条看板数据，并把封面写到 public/publish/<pid>/。"""
    title = publish_xhs.make_title((fm.get("title") or pid), None)
    adapted = publish_xhs.adapt_body(body)
    kind = publish_xhs.detect_kind(body, None)
    topics = publish_xhs.make_topics(fm.get("tags") or [])

    out_dir = PUBLISH_PUBLIC / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    cover_path = out_dir / "cover.png"
    publish_xhs.make_tech_cover(
        title, topics, str(cover_path), body=body, subtitle=(fm.get("title") or title)
    )

    images = []
    for f in publish_xhs.collect_images(body):
        images.append(f"/images/{f.name}")

    return {
        "id": pid,
        "source": f"https://www.cnblogs.com/zjdxr-up/p/{pid}",
        "source_type": "cnblogs",
        "title": title,
        "kind": kind,
        "status": status,
        "topics": topics,
        "body": adapted,
        "cover": f"/publish/{pid}/cover.png",
        "images": images,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "published_at": None,
    }


def upsert_index(items, item):
    """按 id 更新条目，已有发布状态保留，其余字段刷新。"""
    out = []
    replaced = False
    for it in items:
        if it.get("id") == item["id"]:
            item["status"] = it.get("status", "pending")
            item["published_at"] = it.get("published_at")
            out.append(item)
            replaced = True
        else:
            out.append(it)
    if not replaced:
        out.append(item)
    return out


def set_status(pid, status):
    """把某篇设为 draft/pending/published/archived。"""
    index = load_index()
    found = False
    title = pid
    for it in index:
        if it.get("id") == pid:
            it["status"] = status
            if status == "published":
                it["published_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            elif status in ("draft", "pending", "archived"):
                it["published_at"] = None
            title = it.get("title", pid)
            found = True
            break
    if not found:
        sys.exit(f"[错误] 看板中没有 {pid}，请先运行 prepare 生成")
    save_index(index)
    acts = load_activity()
    label = {"draft": "设为草稿", "pending": "设为待发布", "published": "标记为已发布", "archived": "设为已归档"}[status]
    add_activity(acts, "set_status", pid, title, label)
    print(f"[看板] {pid} 已{label}。记得 commit & push 同步到线上。")


def mark_published(pid):
    """本地标记某篇为已发布。"""
    set_status(pid, "published")


def main():
    ap = argparse.ArgumentParser(description="cnblogs → 小红书发布看板数据")
    ap.add_argument("target", nargs="?", help="cnblogs URL 或文章 pid")
    ap.add_argument("--latest", type=int, default=0, metavar="N",
                    help="取 sitemap 最新 N 篇批量生成（与 target 二选一）")
    ap.add_argument("--mark-published", metavar="PID",
                    help="本地标记某篇为已发布（写入 publish.json）")
    ap.add_argument("--set-status", metavar="PID:STATUS",
                    help="设置状态：draft/pending/published/archived，例如 --set-status 23049231:published")
    args = ap.parse_args()

    if args.mark_published:
        mark_published(extract_pid(args.mark_published))
        return

    if args.set_status:
        raw = args.set_status
        if ":" not in raw:
            sys.exit("[错误] --set-status 格式：PID:STATUS，例如 23049231:published")
        pid_part, status = raw.rsplit(":", 1)
        status = status.strip().lower()
        if status not in VALID_STATUS:
            sys.exit(f"[错误] 未知状态：{status}（可选 draft/pending/published/archived）")
        set_status(extract_pid(pid_part), status)
        return

    index = load_index()

    if args.latest:
        pids = latest_pids(args.latest)
        for pid in pids:
            got = read_local_post(pid)
            if not got:
                print(f"[信息] 本地无 {pid}.md，改从 cnblogs 抓取…")
                got = fetch_single(pid)
            fm, body = got
            item = build_item(pid, fm, body)
            index = upsert_index(index, item)
            print(f"[看板] {pid} {item['title'][:30]} ({item['kind']})")
        save_index(index)
        acts = load_activity()
        for pid in pids:
            rec = next((it for it in index if it.get("id") == pid), None)
            if rec:
                add_activity(acts, "generate", pid, rec.get("title", pid), "从 cnblogs 批量生成看板数据")
        print(f"\n[完成] 已生成 {len(pids)} 篇，写入 {DATA_FILE.relative_to(ROOT)}")
        return

    if not args.target:
        sys.exit("[用法] 传 cnblogs URL/pid，或加 --latest N")

    pid = extract_pid(args.target)
    got = read_local_post(pid)
    if not got:
        print(f"[信息] 本地无 {pid}.md，改从 cnblogs 抓取…")
        got = fetch_single(pid)
    fm, body = got
    item = build_item(pid, fm, body)
    index = upsert_index(index, item)
    save_index(index)
    acts = load_activity()
    add_activity(acts, "generate", pid, item["title"], "从 cnblogs 生成/更新看板数据")
    print(f"[看板] {pid} {item['title'][:30]} ({item['kind']}) 已写入 {DATA_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
