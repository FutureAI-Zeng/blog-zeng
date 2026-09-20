#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cnblogs → Astro 博客「增量」同步脚本

用法（在项目根目录 blog/ 下执行）：
    python3 scripts/sync_cnblogs.py              # 只同步 cnblogs 上新增的文章（默认）
    python3 scripts/sync_cnblogs.py --update 30  # 额外检查最新 30 篇是否有内容更新
    python3 scripts/sync_cnblogs.py --no-tags    # 跳过标签反查（更快，新文章标签为空）
    python3 scripts/sync_cnblogs.py --dry-run    # 只报告将要做什么，不写文件
    python3 scripts/sync_cnblogs.py --limit 3    # 只处理 3 篇（测试用）

同步完的后续动作：
    npm run build && npm run preview   # 本地预览确认
    git add -A && git commit -m "sync" && git push   # 上线

依赖：pip install markdownify beautifulsoup4 lxml pyyaml
注意：已存在的本地文章默认不会被覆盖（保护你在本地做的修改，如 pinned 置顶）。
"""
import os, re, sys, json, time, glob, hashlib, argparse
import urllib.parse, urllib.request
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from markdownify import markdownify as md

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS = os.path.join(ROOT, "src", "content", "posts")
IMAGES = os.path.join(ROOT, "public", "images")
CACHE = os.path.join(ROOT, "scripts", ".tagmap_cache.json")

BLOG_USER = "zjdxr-up"
SITE = f"https://www.cnblogs.com/{BLOG_USER}"
SITEMAP = f"{SITE}/sitemap.xml"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}

# ---------- 站点 base（/blog-zeng/），用于图片链接前缀 ----------
def detect_base():
    consts = os.path.join(ROOT, "src", "consts.ts")
    try:
        t = open(consts, encoding="utf-8").read()
        m = re.search(r"repo:\s*['\"]([^'\"]+)['\"]", t)
        if m and not m.group(1).endswith(".github.io"):
            return f"/{m.group(1)}/"
    except Exception:
        pass
    return "/"

IMG_BASE = None  # 运行时设置： f"{base}images/"

# ---------- 网络 ----------
def fetch(url, retries=3, timeout=30):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception:
            if i == retries - 1:
                return ""
            time.sleep(1.2 * (i + 1))
    return ""

def fetch_bytes(url, retries=3, timeout=35):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ct = r.headers.get("Content-Type", "")
                return ct, r.read()
        except Exception:
            if i == retries - 1:
                return "", b""
            time.sleep(1.2 * (i + 1))
    return "", b""

# ---------- sitemap / 本地 ----------
PID_RE = re.compile(rf"{re.escape(SITE)}/p/(\d+)")

def sitemap_pids():
    xml = fetch(SITEMAP)
    pids, seen = [], set()
    for m in PID_RE.finditer(xml):
        p = m.group(1)
        if p not in seen:
            seen.add(p)
            pids.append(p)
    return pids

def local_pids():
    return {os.path.splitext(os.path.basename(f))[0]
            for f in glob.glob(os.path.join(POSTS, "*.md"))}

# ---------- 文章解析 ----------
DATE_RE = re.compile(r"posted @ (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
DATE2_RE = re.compile(r'id="post-date"[^>]*>(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})')

def clean_title(t):
    return re.sub(r"\s*-\s*(未来AI笔记|zjdxr-up)\s*$", "", (t or "").strip()).strip()

def body_to_md(html):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find(id="cnblogs_post_body")
    if not body:
        return ""
    for bad in body.select(".cnblogs_code_toolbar, .postFoot, #blog_post_info, script, style"):
        bad.decompose()
    text = md(str(body), heading_style="ATX", bullets="-", strip=["a", "span"], strong_em_symbol="*")
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def make_description(mdtext, limit=120):
    plain = re.sub(r"[#>*`\-\[\]()!]", "", mdtext)
    plain = re.sub(r"转载请注明出处[:：]?", "", plain)
    return re.sub(r"\s+", " ", plain).strip()[:limit]

def parse_post(pid):
    html = fetch(f"{SITE}/p/{pid}")
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    t = soup.find(id="cb_post_title_url")
    title = clean_title(t.get_text(strip=True)) if t else clean_title(
        soup.find("title").get_text() if soup.find("title") else pid)
    body = body_to_md(html)
    if not body:
        return None
    dm = DATE_RE.search(html) or DATE2_RE.search(html)
    pub = (dm.group(1).split(" ")[0] if dm else time.strftime("%Y-%m-%d"))
    return {"pid": pid, "title": title, "pubDate": pub,
            "body": body, "description": make_description(body)}

# ---------- 标签反查（tag 页 → pid→tags）----------
TAG_URL_RE = re.compile(rf"{re.escape(SITE)}/tag/[^\"<> ]+")
TAG_PID_RE = re.compile(rf"{re.escape(SITE)}/p/(\d+)")

def scrape_tag(tag_url):
    """抓一个标签页（含分页），返回 (tag名, pid集合)"""
    tag = urllib.parse.unquote(tag_url.rstrip("/").split("/tag/")[-1])
    html = fetch(tag_url)
    pids = set(TAG_PID_RE.findall(html))
    pages = [int(x) for x in re.findall(r"[?&]page=(\d+)", html)]
    maxp = max(pages) if pages else 1
    for n in range(2, maxp + 1):
        h = fetch(tag_url + ("&" if "?" in tag_url else "?") + f"page={n}")
        if not h:
            break
        got = set(TAG_PID_RE.findall(h))
        if not got:
            break
        pids |= got
    return tag, pids

def build_tagmap(verbose=True):
    idx = fetch(f"{SITE}/tag/")
    tag_urls = sorted(set(TAG_URL_RE.findall(idx)))
    if verbose:
        print(f"  标签数: {len(tag_urls)}，开始反查（约需 1~2 分钟）…")
    pid_tags = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(scrape_tag, u) for u in tag_urls]
        for f in as_completed(futs):
            tag, pids = f.result()
            for p in pids:
                pid_tags.setdefault(p, set()).add(tag)
    return {p: sorted(v) for p, v in pid_tags.items()}

def load_cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return {}

def save_cache(m):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(m, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

# ---------- 分类（标签 + 标题）----------
ESSAY_TAGS = {"人生吧", "读书", "毛选", "随笔", "生活", "感悟", "随想", "杂谈",
              "旅行", "年终", "年度", "碎碎念", "心情", "日常", "读书记",
              "随记", "回忆", "职场", "工作感悟"}
INTERVIEW_TAGS = {"面试"}
ESSAY_TITLE = ["随笔", "生活", "感悟", "年终", "年度", "碎碎念", "心情", "日常", "随记",
               "杂谈", "读书", "旅行", "游记", "随想", "杂感", "故事", "回忆",
               "工作感悟", "职场", "这一年", "闲谈", "唠嗑", "碎念", "随感"]
INTERVIEW_TITLE = ["面试", "面经", "校招", "秋招", "春招", "笔试", "offer", "内推",
                   "简历", "职级", "薪资", "薪酬", "谈薪", "求职", "实习", "手撕", "复盘"]

def classify(title, tags):
    tl = (title or "").lower()
    if any(k.lower() in tl for k in INTERVIEW_TITLE) or (set(tags) & INTERVIEW_TAGS):
        return "面试"
    if any(k in (title or "") for k in ESSAY_TITLE) or (set(tags) & ESSAY_TAGS):
        return "随笔"
    return "技术"

# ---------- 图片本地化 ----------
IMG_MD_RE = re.compile(r'(!\[[^\]]*\]\((https?://[^)\s]+)\))')
IMG_TAG_RE = re.compile(r'(<img[^>]+src="(https?://[^"]+)"[^>]*>)')

def _local_name(u):
    bn = os.path.basename(urllib.parse.urlparse(u).path) or "image"
    stem, ext = os.path.splitext(bn)
    if not ext or len(ext) > 5:
        ext = ".png"
    return stem + ext, stem, ext

IMG_INDEX = {}   # 已有图片的内容 md5 → 文件名（用于复用，避免重复落盘）

def build_image_index():
    """扫描 public/images，按内容 md5 建索引；增量同步时复用已有图片，不产生重复文件"""
    idx = {}
    if not os.path.isdir(IMAGES):
        return idx
    for fn in os.listdir(IMAGES):
        p = os.path.join(IMAGES, fn)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "rb") as f:
                idx[hashlib.md5(f.read()).hexdigest()] = fn
        except Exception:
            pass
    return idx

def _download_one(u):
    ct, data = fetch_bytes(u)
    if not ct.startswith("image/") or len(data) < 200:
        return (u, None)  # 装饰小图标/失效 → 移除
    digest = hashlib.md5(data).hexdigest()
    if digest in IMG_INDEX:
        return (u, IMG_INDEX[digest])        # 内容相同 → 复用已有文件
    name, stem, ext = _local_name(u)
    dest = os.path.join(IMAGES, name)
    if os.path.exists(dest):
        name = f"{stem}_{digest[:8]}{ext}"   # 同名但是不同的图 → 加 hash 区分
        dest = os.path.join(IMAGES, name)
    with open(dest, "wb") as f:
        f.write(data)
    IMG_INDEX[digest] = name
    return (u, name)

def localize_images(text):
    refs = [(m.group(0), m.group(2)) for m in IMG_MD_RE.finditer(text)]
    refs += [(m.group(0), m.group(2)) for m in IMG_TAG_RE.finditer(text)]
    if not refs:
        return text, 0, 0
    urls = sorted({u for _, u in refs})
    mapping = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for u, name in ex.map(_download_one, urls):
            mapping[u] = name
    new = text
    saved = removed = 0
    for full, u in refs:
        name = mapping.get(u)
        if name:
            new = new.replace(full, full.replace(u, IMG_BASE + name))
            saved += 1
        else:
            new = re.sub(re.escape(full) + r"\n?", "", new)
            removed += 1
    return new, saved, removed

# ---------- 写文章 ----------
def write_post(data, tags, dry=False, local_img=True):
    body = data["body"]
    img_saved = img_removed = 0
    if local_img:
        body, img_saved, img_removed = localize_images(body)
    meta = {
        "title": data["title"],
        "description": data["description"],
        "pubDate": data["pubDate"],
        "category": classify(data["title"], tags),
        "tags": tags,
        "draft": False,
    }
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    content = "---\n" + fm + "\n---\n\n" + body + "\n"
    if not dry:
        os.makedirs(POSTS, exist_ok=True)
        with open(os.path.join(POSTS, f"{data['pid']}.md"), "w", encoding="utf-8") as f:
            f.write(content)
    return meta, img_saved, img_removed

def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()

# ---------- 主流程 ----------
def main():
    global IMG_BASE
    ap = argparse.ArgumentParser(description="cnblogs → Astro 增量同步")
    ap.add_argument("--update", type=int, default=0, metavar="N",
                    help="额外检查 sitemap 里最新 N 篇文章是否有内容更新（0=不检查）")
    ap.add_argument("--no-tags", action="store_true", help="跳过标签反查（更快）")
    ap.add_argument("--no-images", action="store_true", help="跳过图片本地化")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--limit", type=int, default=0, help="最多处理多少篇新增")
    args = ap.parse_args()

    IMG_BASE = detect_base() + "images/"
    os.makedirs(IMAGES, exist_ok=True)
    if not args.no_images:
        _t0 = time.time()
        IMG_INDEX.update(build_image_index())
        print(f"（已索引本地图片 {len(IMG_INDEX)} 张，耗时 {time.time()-_t0:.1f}s；重复图片自动复用）")

    print("=" * 58)
    print(f"cnblogs({BLOG_USER}) → Astro 增量同步   图片前缀: {IMG_BASE}")
    print("=" * 58)

    print("\n[1/5] 获取 sitemap 全量清单…")
    all_pids = sitemap_pids()
    have = local_pids()
    print(f"      线上 {len(all_pids)} 篇 | 本地 {len(have)} 篇")
    new_pids = [p for p in all_pids if p not in have]
    print(f"      新增待同步: {len(new_pids)} 篇")
    if args.limit:
        new_pids = new_pids[:args.limit]

    if not new_pids and not args.update:
        print("\n✅ 没有新文章，已是最新。")
        return 0

    print("\n[2/5] 抓取文章正文…")
    posts = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(parse_post, p): p for p in new_pids}
        for f in as_completed(futs):
            r = f.result()
            if r:
                posts.append(r)
                print(f"      ✓ {r['pubDate']} {r['title'][:40]}")
    print(f"      成功解析 {len(posts)} 篇")

    print("\n[3/5] 标签反查…")
    tagmap = {}
    if args.no_tags:
        print("      （已跳过）")
    else:
        tagmap = load_cache()
        fresh = build_tagmap()
        tagmap.update(fresh)          # 新结果覆盖/合并缓存
        save_cache(tagmap)
        print(f"      标签映射覆盖 {len(tagmap)} 篇文章")

    print("\n[4/5] 写入文章 + 图片本地化…")
    img_total = img_drop = 0
    for d in posts:
        tags = tagmap.get(d["pid"], [])
        meta, s, r = write_post(d, tags, dry=args.dry_run, local_img=not args.no_images)
        img_total += s
        img_drop += r
        flag = "[DRY]" if args.dry_run else "[新增]"
        print(f"      {flag} {meta['category']} | {meta['pubDate']} | {meta['title'][:38]}"
              + (f" | 图{s}" if s else ""))

    # 可选：检查已有文章是否被更新
    updated = 0
    if args.update:
        print(f"\n[5/5] 检查最新 {args.update} 篇是否有内容更新…")
        for pid in all_pids[:args.update]:
            if pid in new_pids or pid not in have:
                continue
            path = os.path.join(POSTS, f"{pid}.md")
            raw = open(path, encoding="utf-8").read()
            m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
            if not m:
                continue
            meta = yaml.safe_load(m.group(1))
            old_body = norm(m.group(2))
            d = parse_post(pid)
            if d and norm(d["body"]) != old_body:
                tags = meta.get("tags", []) or tagmap.get(pid, [])
                keep = {k: meta.get(k) for k in ("pinned", "draft", "updatedDate") if k in meta}
                nm, s, r = write_post(d, tags, dry=args.dry_run, local_img=not args.no_images)
                for k, v in keep.items():
                    nm[k] = v
                if not args.dry_run:
                    fm = yaml.safe_dump(nm, allow_unicode=True, sort_keys=False).strip()
                    nb = d["body"]
                    if not args.no_images:
                        nb, s, r = localize_images(nb)
                    open(path, "w", encoding="utf-8").write("---\n" + fm + "\n---\n\n" + nb + "\n")
                img_total += s
                img_drop += r
                updated += 1
                print(f"      [更新] {d['title'][:40]}")
    else:
        print("\n[5/5] （未启用更新检查，使用 --update N 可检查已有文章）")

    print("\n" + "=" * 58)
    print(f"同步完成：新增 {len(posts)} 篇 | 更新 {updated} 篇 | "
          f"下载图片 {img_total} 张 | 清理无效图 {img_drop} 张")
    if args.dry_run:
        print("（dry-run 模式，未写入任何文件）")
    else:
        print("下一步：npm run build && npm run preview  →  确认后 git commit && git push")
    print("=" * 58)
    return 0

if __name__ == "__main__":
    sys.exit(main())
