#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书图文笔记发布助手（本地半自动）

用法：
  # 仅生成适配草稿（不登录），用于预览 / 调试
  python scripts/publish_xhs.py <pid> --dry-run [--title "自定义标题"] [--out xhs_drafts]

  # 登录并发布到草稿箱（需本地扫码，仅在你自己的电脑运行）
  python scripts/publish_xhs.py <pid> --to-draft

  # 登录并正式发布
  python scripts/publish_xhs.py <pid> --publish

重要说明：
  - 小红书个人号没有官方的「发布笔记」开放 API，发布只能走创作者后台网页 + 浏览器自动化（Playwright）。
  - 登录态 cookie 只保存在本地 .xhs_cookies.json，绝不进仓库、不上传、不给任何人。
  - 真实的登录与发布必须在【你本机】运行，并由你本人扫码确认；云端 / 服务器环境无法代你登录。
  - 小红书用户协议禁止使用脚本批量发布，请低频、只发自己的原创内容，并人工确认每篇。
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "src/content/posts"
PUBLIC_IMG = ROOT / "public/images"
OUT_DEFAULT = ROOT / "xhs_drafts"
COOKIE_FILE = ROOT / ".xhs_cookies.json"

XHS_PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?from=official"

# 长度阈值：超过则默认走「长文」，否则走「图文笔记」。
NOTE_MAX_CHARS = 1000


# ------------------------- 读取文章 -------------------------
def load_post(pid):
    p = POSTS / f"{pid}.md"
    if not p.exists():
        p = Path(pid)
    if not p.exists():
        sys.exit(f"[错误] 找不到文章：{pid}")
    text = p.read_text(encoding="utf-8")
    fm_end = text.find("\n---", 3)
    if fm_end == -1:
        sys.exit("[错误] 文章缺少 frontmatter")
    fm = yaml.safe_load(text[3:fm_end]) or {}
    body = text[fm_end + 4:].lstrip("\n")
    return fm, body, p


# ------------------------- 文本适配 -------------------------
def clean_md(body):
    # markdown 图片 → 配图占位（真实图片稍后单独上传）
    body = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", "[配图]", body)
    # 去掉外链，只保留文字（小红书屏蔽站外链接）
    body = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", body)
    # 去掉引用块符号
    body = re.sub(r"(?m)^>\s?", "", body)
    # 粗体/斜体/行内代码：去掉 markdown 标记，只留文字
    body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)
    body = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", body)
    body = re.sub(r"(?<!`)`([^`\n]+)`(?!`)", r"\1", body)
    # 反斜杠转义（如 mysqld\_safe）还原为普通字符
    body = re.sub(r"\\([\\`*_{}\[\]()#+\-.!])", r"\1", body)
    return body


def adapt_body(body):
    """把 markdown 正文转成小红书风格纯文本（保留分段、emoji 引导、代码块标注）。"""
    lines = clean_md(body).splitlines()
    out = []
    in_code = False
    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            continue
        if s.strip().startswith("```"):
            if in_code:
                out.append("▌代码结束")
                in_code = False
            else:
                out.append("▌代码：")
                in_code = True
            continue
        if in_code:
            out.append("    " + s)
            continue
        if s.strip().startswith("#"):
            txt = s.strip().lstrip("#").strip()
            if not txt:
                continue
            out.append(f"📌 {txt}")
        else:
            out.append(s)
    if in_code:
        out.append("▌代码结束")
    return "\n".join(out)


def split_body(body, n):
    """把正文按一级小节（##）拆成 n 篇，尽量让每篇字数均衡。"""
    heads = [m.start() for m in re.finditer(r"(?m)^##\s+", body)]
    if len(heads) >= n - 1 and n > 1:
        total = len(body)
        cuts = []
        for k in range(1, n):
            target = total * k / n
            best = min(heads, key=lambda h: abs(h - target))
            if best not in cuts:
                cuts.append(best)
        cuts = sorted(cuts)
        parts, prev = [], 0
        for c in cuts:
            parts.append(body[prev:c])
            prev = c
        parts.append(body[prev:])
        return parts

    # 标题不够拆，或 n==1：按行均分兜底
    lines = body.split("\n")
    per = (len(lines) + n - 1) // n
    return ["\n".join(lines[i * per:(i + 1) * per]) for i in range(n)]


def split_suffix(part, total):
    if total == 2:
        return "（上）" if part == 1 else "（下）"
    if total == 3:
        return ("（上）", "（中）", "（下）")[part - 1]
    return f"（{part}/{total}）"


def make_split_title(orig, part, total):
    suffix = split_suffix(part, total)
    t = (orig or "").strip()
    limit = max(1, 20 - len(suffix))
    if len(t) + len(suffix) > 20:
        t = t[:limit]
    return t + suffix


def detect_kind(body, override=None):
    """根据正文长度判断发布类型：短=笔记(note)，长=长文(article)。"""
    if override:
        override = override.lower()
        if override in ("note", "笔记"):
            return "note"
        if override in ("article", "长文"):
            return "article"
        sys.exit(f"[错误] 未知 --kind：{override}（可选 note/article）")
    xbody = adapt_body(body)
    return "article" if len(xbody) > NOTE_MAX_CHARS else "note"


def make_title(orig, override=None):
    t = override or orig or ""
    t = t.strip()
    if len(t) > 20:
        t = t[:19] + "…"
    return t


def make_topics(tags):
    pool = ["Docker", "MariaDB", "MySQL", "运维", "故障排查", "避坑", "程序员", "技术笔记"]
    topics = []
    for t in (tags or []) + pool:
        if t and t not in topics:
            topics.append(t)
        if len(topics) >= 10:
            break
    return topics


def collect_images(body):
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body)
    res = []
    for u in imgs:
        name = Path(u).name
        f = PUBLIC_IMG / name
        if f.exists():
            res.append(f)
    return res


# ------------------------- 封面图 -------------------------
def load_font(size):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def make_cover(title, topics, out_path, subtitle=None):
    W, H = 1080, 1440
    img = Image.new("RGB", (W, H), (26, 26, 46))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 18], fill=(255, 36, 66))  # 顶部红色装饰条
    tf = load_font(66)
    lines = wrap_text(d, title, tf, W - 120)
    y = 160
    for ln in lines[:4]:
        d.text((60, y), ln, font=tf, fill=(255, 255, 255))
        y += 86
    sf = load_font(34)
    if subtitle:
        # 副标题也按宽度折行，避免超出封面
        sub_lines = wrap_text(d, subtitle, sf, W - 120)[:3]
        sy = y + 24
        for ln in sub_lines:
            d.text((60, sy), ln, font=sf, fill=(180, 190, 210))
            sy += 46
    bf = load_font(30)
    tag = "  ".join("#" + t for t in topics[:6])
    d.text((60, H - 120), tag, font=bf, fill=(255, 120, 140))
    img.save(out_path)


# ------------------------- 技术主题识别 -------------------------
TECH_THEMES = {
    "database": {
        "kw": ("mysql", "mariadb", "postgres", "redis", "mongodb", "sql", "xa", "innodb",
               "数据库", "事务", "sqlite", "oracle", "主从", "读写分离", "分库分表"),
        "label": "DATABASE / MYSQL",
        "accent": (46, 204, 113),
    },
    "container": {
        "kw": ("docker", "swarm", "k8s", "kubernetes", "compose", "容器", "镜像", "pvc",
               "volume", "deployment", "pod"),
        "label": "DOCKER / SWARM",
        "accent": (36, 169, 244),
    },
    "java": {
        "kw": ("java", "jvm", "spring", "springboot", "spring cloud", "maven", "gradle",
               "tomcat", "mybatis", "多线程", "并发", "gc"),
        "label": "JAVA / JVM",
        "accent": (240, 137, 42),
    },
    "bigdata": {
        "kw": ("spark", "flink", "hadoop", "hive", "kafka", "zookeeper", "大数据", "数仓",
               "etl", "clickhouse", "doris", "datalake"),
        "label": "BIG DATA",
        "accent": (132, 94, 247),
    },
    "frontend": {
        "kw": ("vue", "react", "javascript", "typescript", "webpack", "vite", "css", "html",
               "前端", "小程序", "node", "next", "nuxt"),
        "label": "FRONTEND",
        "accent": (255, 179, 71),
    },
    "ai": {
        "kw": ("大模型", "llm", "gpt", "chatgpt", "langchain", "rag", "embedding", "向量",
               "transformer", "深度学习", "机器学习", "神经网络", "agent", "prompt"),
        "label": "AI / LLM",
        "accent": (255, 92, 141),
    },
    "ops": {
        "kw": ("运维", "linux", "shell", "nginx", "监控", "告警", "故障", "排查", "cpu",
               "内存", "磁盘", "日志", "网络", "ansible", "prometheus", "grafana"),
        "label": "OPS / LINUX",
        "accent": (255, 152, 0),
    },
}


def detect_tech_theme(title, topics, body):
    text = f"{title} {' '.join(topics)} {body}".lower()
    best, best_score = None, 0
    for name, cfg in TECH_THEMES.items():
        score = sum(text.count(k) for k in cfg["kw"])
        if score > best_score:
            best, best_score = name, score
    return best or "ops"


def extract_code_lines(body, limit=8):
    """从 markdown 正文抽取真实代码/命令/日志行，让配图更贴内容。"""
    lines = []
    in_code = False
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            if len(s) > 60:
                s = s[:57] + "…"
            lines.append(s)
            if len(lines) >= limit:
                break
            continue
        # markdown 标题 / 引用块 / 图片不当作代码
        if s.startswith(("#", ">", "![", "![")):
            continue
        # 命令行、错误日志、路径、常见命令开头
        if (s.startswith(("$", "docker", "mysql", "mysqld", "java", "python", "npm",
                          "git", "kubectl", "kafka", "spark", "flink", "curl", "ansible",
                          "ERROR", "WARN", "Exception", "Caused", "XA", "select",
                          "SELECT", "show", "SHOW"))
                or re.match(r"^\d{4}[-/]\d{2}", s)
                or "://" in s):
            if len(s) > 60:
                s = s[:57] + "…"
            lines.append(s)
            if len(lines) >= limit:
                break
    return lines


def classify_code_line(line):
    """给抽到的行打个小类别，用于配色。"""
    low = line.lower()
    if low.startswith(("error", "warn", "exception", "caused")):
        return "err"
    if low.startswith(("#", "$", ">", "docker", "kubectl", "git", "npm", "curl")):
        return "cmd"
    if "://" in low or " at " in low or low.endswith((".py", ".java", ".js", ".sh")):
        return "path"
    return "data"


def make_tech_cover(title, topics, out_path, body=None, subtitle=None):
    """技术风封面：终端窗口 + 主题色 + 真实代码/日志片段，视觉更贴技术内容。"""
    W, H = 1080, 1440
    theme_name = detect_tech_theme(title, topics, body or "")
    cfg = TECH_THEMES[theme_name]
    accent = cfg["accent"]
    base = (18, 24, 38)
    panel = (27, 34, 51)
    img = Image.new("RGB", (W, H), base)
    d = ImageDraw.Draw(img)

    # 顶部装饰条
    d.rectangle([0, 0, W, 16], fill=accent)

    # 终端窗口
    win_x, win_y, win_w, win_h = 60, 210, W - 120, 900
    d.rounded_rectangle([win_x, win_y, win_x + win_w, win_y + win_h], radius=18, fill=panel)
    # 标题栏 + 三个圆点
    d.rounded_rectangle([win_x, win_y, win_x + win_w, win_y + 70], radius=18, fill=(37, 46, 66))
    d.rectangle([win_x, win_y + 40, win_x + win_w, win_y + 70], fill=(37, 46, 66))
    for i, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = win_x + 42 + i * 40
        d.ellipse([cx - 10, win_y + 35 - 10, cx + 10, win_y + 35 + 10], fill=col)
    tf2 = load_font(34)
    d.text((win_x + 170, win_y + 26), cfg["label"], font=tf2, fill=(150, 160, 180))

    # 终端内容：大标题 + 副标题 + 真实代码/日志
    ty = win_y + 120
    tfont = load_font(56)
    for ln in wrap_text(d, title, tfont, win_w - 90)[:3]:
        d.text((win_x + 45, ty), ln, font=tfont, fill=(235, 240, 248))
        ty += 74
    if subtitle:
        sf = load_font(32)
        for ln in wrap_text(d, subtitle, sf, win_w - 90)[:2]:
            d.text((win_x + 45, ty), ln, font=sf, fill=(150, 160, 180))
            ty += 46

    ty += 30
    d.text((win_x + 45, ty), "$", font=load_font(40), fill=accent)
    d.text((win_x + 90, ty), " ____", font=load_font(40), fill=(150, 160, 180))
    ty += 62

    code_font = load_font(34)
    for ln in extract_code_lines(body or "", limit=8):
        kind = classify_code_line(ln)
        if kind == "err":
            color = (255, 92, 92)
        elif kind == "cmd":
            color = (120, 210, 255)
        elif kind == "path":
            color = (255, 214, 120)
        else:
            color = (190, 200, 215)
        d.text((win_x + 45, ty), ln, font=code_font, fill=color)
        ty += 56

    # 底部标签
    bf = load_font(30)
    tag = "  ".join("#" + t for t in topics[:6])
    d.text((60, H - 130), tag, font=bf, fill=accent)

    # 顶部大标题（窗口外，弱化）
    d.text((60, 70), f"$ {title[:22]}", font=load_font(46), fill=(220, 228, 240))

    img.save(out_path)


# ------------------------- 手动发布包 -------------------------
def write_manual_package(out, title, xbody, topics, kind, img_names):
    """生成「复制即发」的手动发布包：内容 txt + 操作说明。"""
    kind_label = "长文" if kind == "article" else "图文笔记"
    body_txt = xbody
    topics_txt = " ".join("#" + t for t in topics)

    # 1) 纯内容文件：按 标题 / 正文 / 话题 分块，方便逐段复制
    content = (
        f"【标题】\n{title}\n\n"
        f"【正文】\n{body_txt}\n\n"
        f"【话题】\n{topics_txt}\n"
    )
    (out / "复制内容.txt").write_text(content, encoding="utf-8")

    # 2) 操作说明
    steps = []
    steps.append(f"小红书手动发布包（{kind_label}）")
    steps.append("")
    steps.append("一、复制内容（按顺序）")
    steps.append(f"1. 标题：{title}")
    steps.append("2. 正文：打开「复制内容.txt」的【正文】段，全选复制")
    steps.append(f"3. 话题：{topics_txt}")
    steps.append("")
    steps.append("二、图片")
    steps.append("- 封面图：cover.png（1080x1440）")
    if img_names:
        steps.append("- 配图：images/ 目录下 " + "、".join(img_names))
    else:
        steps.append("- 配图：无（本段无图片）")
    steps.append("")
    steps.append("三、发布步骤")
    if kind == "article":
        steps.append("1. 打开小红书 App → 底部「+」→ 选择「写文章/发布长文」")
        steps.append("2. 输入标题 → 粘贴正文 → 添加话题")
        steps.append("3. 上传封面图 cover.png")
        steps.append("4. 检查无误后点击「发布」（长文无需担心 1000 字上限）")
    else:
        steps.append("1. 打开小红书 App → 底部「+」→ 选择「发布笔记」")
        steps.append("2. 先上传封面图 cover.png，再上传 images/ 里的配图")
        steps.append("3. 粘贴标题 → 粘贴正文 → 粘贴话题")
        steps.append("4. 检查无误后点击「发布」")
    steps.append("")
    steps.append("四、提示")
    steps.append("- 发布前可在「预览」里检查排版")
    steps.append("- 全部内容已按小红书格式适配（外链已去除、代码块已标注、话题≤10 个）")
    (out / "发布说明.txt").write_text("\n".join(steps), encoding="utf-8")

    print(f"[手动包] 已生成复制内容 + 发布说明：{out}")


# ------------------------- 草稿输出 -------------------------
def build_draft(pid, fm, body, args, out_key=None, title_override=None):
    if out_key is None:
        out = (Path(args.out) if args.out else OUT_DEFAULT) / pid
    else:
        out = (Path(args.out) if args.out else OUT_DEFAULT) / pid / out_key
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)

    if title_override is not None:
        title = title_override
    else:
        title = make_title(fm.get("title", ""), args.title)
    xbody = adapt_body(body)
    topics = make_topics(fm.get("tags", []))
    imgs = collect_images(body)

    img_names = []
    for f in imgs:
        shutil.copy(f, out / "images" / f.name)
        img_names.append(f.name)

    if args.trim and len(xbody) > args.trim:
        cut = xbody[: args.trim]
        if "\n" in cut:
            cut = cut[: cut.rfind("\n")]
        xbody = cut + "\n\n（完整内容见我的博客，主页有置顶）"

    cover = out / "cover.png"
    make_tech_cover(title, topics, cover, body=body, subtitle=fm.get("title") or "")

    note = f"# {title}\n\n{xbody}\n\n" + "\n".join("#" + t for t in topics) + "\n"
    (out / "note.md").write_text(note, encoding="utf-8")

    manifest = {
        "pid": pid,
        "title": title,
        "body": xbody,
        "topics": topics,
        "cover": "cover.png",
        "images": img_names,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    kind = getattr(args, "manual_kind", None) or detect_kind(body, getattr(args, "kind", None))
    if getattr(args, "manual", False):
        write_manual_package(out, title, xbody, topics, kind, img_names)

    print(f"[草稿] 已生成：{out}")
    print(f"  标题：{title}（{len(title)} 字）")
    print(f"  话题：{' '.join('#' + t for t in topics)}")
    print(f"  配图：{len(img_names)} 张 + 封面 1 张")
    if len(xbody) > 1000:
        print(f"  ⚠️ 正文约 {len(xbody)} 字，小红书建议 ≤1000 字，发布前请精简。")
    return manifest


# ------------------------- 发布（需本地登录） -------------------------
def dump_debug(page, out_dir):
    """编辑器未识别时，输出页面含关键字的可交互元素结构，便于修正选择器。"""
    try:
        page.screenshot(path=str(out_dir / "xhs_debug.png"))
    except Exception:
        pass
    try:
        items = page.evaluate("""() => {
            const tags = ['button','a','input','textarea','[contenteditable]','[role=textbox]','div','span','li','p','h1','h2','h3'];
            const kw = /图文|图片|视频|上传|下一步|存草稿|发布|标题|正文|标签|话题|写/;
            const out = [];
            document.querySelectorAll(tags.join(',')).forEach(e => {
                const t = (e.innerText||e.getAttribute('placeholder')||e.getAttribute('data-placeholder')||'').trim().slice(0,28);
                if (t && kw.test(t)) out.push({tag:e.tagName, type:e.getAttribute('type')||'', ph:(e.getAttribute('placeholder')||e.getAttribute('data-placeholder')||''), text:t, cls:(e.className||'').toString().slice(0,44), accept:e.getAttribute('accept')||''});
            });
            return out.slice(0,80);
        }""")
        print("[DEBUG] 页面含关键字的元素（贴给我即可定位准确选择器）：")
        for x in items:
            print("   ", x)
    except Exception as e:
        print("[DEBUG] 无法抓取结构：", e)


def dump_editor(page, out_dir):
    """填写标题/正文或点按钮失败时，输出 contenteditable 与关键按钮的真实结构。"""
    try:
        # 先滚所有可滚动容器到底再全页截图，确保底部「存草稿/发布」按钮被渲染出来
        page.evaluate("""() => {
            const all = [document.body, document.documentElement,
                ...document.querySelectorAll('div,section,main')]
                .filter(e => e.scrollHeight > e.clientHeight);
            all.forEach(e => e.scrollTo(0, e.scrollHeight));
        }""")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out_dir / "xhs_editor_debug.png"), full_page=True)
    except Exception:
        pass
    try:
        data = page.evaluate(
            """() => {
                const rect = e => {
                    const r = e.getBoundingClientRect();
                    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
                };
                const vin = {w:window.innerWidth, h:window.innerHeight};

                // 标题/正文：contenteditable 或 input/textarea
                const eds = [...document.querySelectorAll('div[contenteditable], input[type="text"], textarea')]
                    .map((e,i)=>({
                        i, tag:e.tagName, type:e.getAttribute('type')||'',
                        ph:(e.getAttribute('data-placeholder')||e.getAttribute('placeholder')||e.getAttribute('aria-label')||e.getAttribute('title')||''),
                        cls:(e.className||'').toString().slice(0,52),
                        text:(e.innerText||e.value||'').slice(0,50), pos:rect(e)}));

                // 所有「可能可点击」控件：有文字/aria/图标 class 的 button/role/a/span/div/svg
                const items = [...document.querySelectorAll('button,[role="button"],a,span,div[class*="btn"],div[class*="icon"],svg')]
                    .map(e=>{
                        const r = rect(e);
                        return {
                            tag:e.tagName, text:(e.innerText||'').trim().slice(0,24),
                            aria:(e.getAttribute('aria-label')||e.getAttribute('title')||'').trim().slice(0,24),
                            cls:(e.className||'').toString().slice(0,46),
                            role:e.getAttribute('role')||'', pos:r};
                    })
                    .filter(x => {
                        if (x.tag === 'SVG') return x.pos.w > 0 && x.pos.h > 0;
                        return (x.text || x.aria || x.cls) && x.pos.w > 0 && x.pos.h > 0;
                    });
                return {vin, eds, items};
            }"""
        )
        print("[DEBUG] 视口尺寸：", data.get("vin"))
        print("[DEBUG] 标题/正文输入元素：")
        for x in data.get("eds", []):
            print("   ", x)
        print("[DEBUG] 可点击元素（含图标/文字/aria + 位置，y>视口高=在页面底部）：")
        for x in data.get("items", []):
            print("   ", x)
        try:
            dump_path = out_dir / "xhs_dom_dump.json"
            dump_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[DEBUG] 完整结构已写到 {dump_path}")
        except Exception:
            pass
    except Exception as e:
        print("[DEBUG] 无法抓取编辑器结构：", e)


def _native_click(page, loc, timeout=6000):
    """用原生 JS click 触发（绕开视口外/actionability 限制），失败回退 force。"""
    try:
        loc.evaluate("(e) => e.click()")
        return True
    except Exception:
        try:
            loc.click(force=True, timeout=timeout)
            return True
        except Exception:
            return False


def _fill_editor(page, loc, text):
    """可靠地把文本填进【指定元素】（含 ProseMirror/tiptap 富文本）。

    不使用 document.activeElement：点击 contenteditable 不一定转移焦点，
    之前会误把正文贴进仍保持焦点的标题框。这里直接绑定 locator 对应的元素。
    """
    handled = loc.evaluate(
        """(el, text) => {
            if (!el) return false;
            el.focus();
            if (el.isContentEditable) {
                // 富文本编辑器（ProseMirror/tiptap）：清空 + 粘贴事件，
                // 让编辑器的数据模型真正更新。
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                const dt = new DataTransfer();
                dt.setData('text/plain', text);
                const ev = new ClipboardEvent('paste', {
                    bubbles: true, cancelable: true, clipboardData: dt
                });
                el.dispatchEvent(ev);
                el.dispatchEvent(new InputEvent('input', {
                    bubbles: true, data: text, inputType: 'insertText'
                }));
                return true;
            }
            if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                const proto = el.tagName === 'TEXTAREA'
                    ? HTMLTextAreaElement.prototype
                    : HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(el, text);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }
            return false;
        }""",
        text,
    )
    if handled:
        return True

    # 兜底：Playwright 原生 fill（对非富文本仍有效）
    try:
        loc.fill(text)
        return True
    except Exception:
        return False


def _find_editor(page, kind):
    """定位标题/正文编辑器（小红书真实 DOM）。kind: 'title' | 'body'。"""
    if kind == "title":
        for attr in ("placeholder", "data-placeholder", "aria-label", "title"):
            loc = page.locator(
                f'input[{attr}*="标题"], textarea[{attr}*="标题"], '
                f'div[contenteditable="true"][{attr}*="标题"]'
            )
            if loc.count() > 0:
                return loc.first
        loc = page.locator('input[type="text"]')
        return loc.first if loc.count() > 0 else None
    loc = page.locator('div[contenteditable="true"]')
    return loc.first if loc.count() > 0 else None


def _js_click_by_text(page, texts, tag_sel="button,[role=button],a,span,div"):
    """按「文本 或 aria-label/title」精确命中并原生点击（选最小可见叶子节点）。"""
    ok = page.evaluate(
        """([texts, tag_sel]) => {
            const els = [...document.querySelectorAll(tag_sel)];
            const match = e => {
                const t = (e.innerText || '').trim();
                const aria = (e.getAttribute('aria-label') || e.getAttribute('title') || '').trim();
                return texts.some(x => t === x || aria === x);
            };
            const cands = els.filter(match).filter(e => {
                const r = e.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            });
            if (cands.length === 0) return false;
            cands.sort((a,b) => {
                const ra=a.getBoundingClientRect(), rb=b.getBoundingClientRect();
                return (ra.width*ra.height) - (rb.width*rb.height);
            });
            const target = cands[0];
            target.scrollIntoView({block:'center', inline:'center'});
            target.click();
            return true;
        }""",
        [texts, tag_sel],
    )
    return bool(ok)


def _scroll_all_to_bottom(page):
    """滚动所有可滚动容器到底，把懒加载的底部按钮渲染出来。"""
    page.evaluate("""() => {
        const all = [document.body, document.documentElement,
            ...document.querySelectorAll('div,section,main')]
            .filter(e => e.scrollHeight > e.clientHeight);
        all.forEach(e => e.scrollTo(0, e.scrollHeight));
    }""")
    page.wait_for_timeout(1200)


def publish_article(page, browser, m, out_dir, to_draft):
    """长文（文章）发布流程��点「发布笔记」下拉 → 选「发布文章」→ 填长文 → 存草稿/发布。"""
    # 1) 打开发布类型下拉，选「发布文章」（文案按需微调）
    opened = _js_click_by_text(page, ["发布笔记", "发布"])
    if opened:
        page.wait_for_timeout(1500)
        picked = _js_click_by_text(page, ["发布文章", "文章", "写文章"])
    else:
        picked = False

    if not picked:
        print("[提示] 未自动定位到「发布文章」入口，输出页面结构（请手动切到长文后回车）：")
        dump_debug(page, out_dir)
        input("请在页面左上角「发布笔记」下拉里选择「发布文章」，打开长文编辑器后按回车…")

    page.wait_for_timeout(3000)

    # 2) 长文编辑器定位：标题 input，正文 contenteditable/textarea（可能和笔记不同）
    title_loc = _find_editor(page, "title")
    if title_loc is None:
        t = page.locator('input[type="text"], input[placeholder*="标题"], textarea').first
        title_loc = t if t.count() > 0 else None

    body_loc = None
    for sel in ('div[contenteditable="true"]', 'textarea', '[role="textbox"]'):
        loc = page.locator(sel)
        if loc.count() > 0:
            body_loc = loc.first
            break

    # 3) 填标题
    try:
        if title_loc is None:
            raise RuntimeError("未定位到长文标题输入框")
        title_loc.wait_for(timeout=15000)
        _native_click(page, title_loc)
        page.wait_for_timeout(500)
        if not _fill_editor(page, title_loc, m["title"]):
            raise RuntimeError("富文本填充失败")
        print("[完成] 长文标题已填写。")
    except Exception as e:
        print(f"[跳过] 长文标题自动填写失败：{e}（请手动填写）")

    # 4) 填正文（长文不截断）
    try:
        if body_loc is None:
            raise RuntimeError("未定位到长文正文编辑器")
        body_loc.wait_for(timeout=15000)
        _native_click(page, body_loc)
        page.wait_for_timeout(500)
        if not _fill_editor(page, body_loc, m["body"]):
            raise RuntimeError("富文本填充失败")
        print("[完成] 长文正文已填写。")
    except Exception as e:
        print(f"[跳过] 长文正文自动填写失败：{e}")
        dump_editor(page, out_dir)

    # 5) 存草稿 / 发布
    btn_text = "存草稿" if to_draft else "发布"
    candidates = (
        ["存草稿", "存为草稿", "保存草稿", "存稿", "存至草稿"]
        if to_draft else
        ["发布", "发布文章"]
    )
    _scroll_all_to_bottom(page)
    clicked = _js_click_by_text(page, candidates)
    if not clicked:
        for t in candidates:
            try:
                b = page.locator(
                    f'button:has-text("{t}"), [role="button"]:has-text("{t}"), '
                    f'div:has-text("{t}"), span:has-text("{t}"), '
                    f'[aria-label="{t}"], [title="{t}"]'
                )
                if b.count() > 0:
                    _native_click(page, b.first)
                    clicked = True
                    break
            except Exception:
                pass

    if clicked:
        page.wait_for_timeout(3000)
        print(f"[完成] 已自动点击『{btn_text}』，请在浏览器里确认出现成功提示。")
    else:
        print(f"[提示] 未自动定位到『{btn_text}』按钮，请手动点击。")
        dump_editor(page, out_dir)

    input("请在浏览器里确认结果（草稿箱/发布成功提示）；若没有成功提示，请手动点一次再确认。确认后按回车关闭浏览器…")
    browser.close()


def publish(manifest_path, to_draft, kind="note"):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("[错误] 未安装 playwright，请先执行：pip install playwright && playwright install chromium")

    import time
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = manifest_path.parent

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        if COOKIE_FILE.exists():
            try:
                ctx.add_cookies(json.loads(COOKIE_FILE.read_text(encoding="utf-8")))
            except Exception:
                pass
        page = ctx.new_page()
        page.goto(XHS_PUBLISH_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)

        # 长文（文章）走独立流程
        if kind == "article":
            publish_article(page, browser, m, out_dir, to_draft)
            return

        EDITOR = 'div[contenteditable="true"]'

        def editor_ready(timeout=5000):
            try:
                page.wait_for_selector(EDITOR, timeout=timeout)
                return True
            except Exception:
                return False

        def img_btn():
            for t in ("上传图片", "上传图文"):
                e = page.get_by_text(t, exact=False)
                if e.count() > 0:
                    return e.first
            return None

        def vid_btn():
            e = page.get_by_text("上传视频", exact=False)
            return e.first if e.count() > 0 else None

        # 1) 登录检测：发布页有「上传图片/视频」按钮或编辑器即视为已登录
        if not (img_btn() or vid_btn() or editor_ready(5000)):
            print("[信息] 未登录，请在弹出的浏览器中用手机小红书 App 扫码登录…")
            input("扫码并在手机上点『登录/确认』后，按回车继续…")
            try:
                COOKIE_FILE.write_text(json.dumps(ctx.cookies(), ensure_ascii=False), encoding="utf-8")
                print("[信息] 登录态已保存到本地 .xhs_cookies.json。")
            except Exception:
                pass
            page.goto(XHS_PUBLISH_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

        # 2) 切到「图文」模式：视频模式下只有「上传视频」，需先点「上传图文」标签
        def native_click(loc, timeout=6000):
            return _native_click(page, loc, timeout)

        img_button = page.get_by_text("上传图片", exact=False)
        if img_button.count() == 0:
            tab = page.get_by_text("上传图文", exact=False)
            if tab.count() > 0:
                print("[信息] 当前为视频模式，切换到图文…")
                native_click(tab.first)
                page.wait_for_timeout(2500)
                img_button = page.get_by_text("上传图片", exact=False)
        if img_button.count() == 0:
            print("[警告] 未找到『上传图片』入口，输出页面结构：")
            dump_debug(page, out_dir)
            print("请手动切到图文模式并上传图片，完成后按回车（或把 DEBUG 贴给我）…")
            input("上传完成后按回车继续…")
            if not editor_ready(60000):
                input("请手动完成发布，按回车关闭…")
                browser.close()
                return

        # 3) 上传图片：拦截文件选择框（最稳，不受隐藏 input/accept 影响）
        if not editor_ready(5000):
            try:
                with page.expect_file_chooser(timeout=15000) as fc_info:
                    native_click(img_button.first, timeout=8000)
                fc = fc_info.value
                upload_list = [str(out_dir / m["cover"])] + [str(out_dir / "images" / n) for n in m["images"]]
                fc.set_files(upload_list)
                print("[信息] 图片上传中，等待编辑器出现…")
                page.wait_for_timeout(6000)
            except Exception as e:
                print(f"[跳过] 自动上传失败：{e}；请你点『上传图片』选择封面+配图，完成后按回车")
                input("上传完成后按回车继续…")
            # 某些版本上传后需点「下一步」才进编辑器
            if not editor_ready(8000):
                try:
                    page.get_by_text("下一步", exact=True).first.click(timeout=5000)
                    page.wait_for_timeout(3000)
                except Exception:
                    pass
            if not editor_ready(60000):
                print("[警告] 上传后仍未出现编辑器，输出页面结构：")
                dump_debug(page, out_dir)
                input("请手动在浏览器完成发布，确认后按回车关闭…")
                browser.close()
                return

        # 4) 填标题/正文。
        def find_editor(kind):
            return _find_editor(page, kind)

        title_loc = find_editor("title")
        body_loc = find_editor("body")

        try:
            if title_loc is None:
                raise RuntimeError("未定位到标题编辑器")
            title_loc.wait_for(timeout=15000)
            native_click(title_loc)
            page.wait_for_timeout(500)
            if not _fill_editor(page, title_loc, m["title"]):
                raise RuntimeError("富文本填充失败")
            print("[完成] 标题已填写。")
        except Exception as e:
            print(f"[跳过] 标题自动填写失败：{e}（请手动填写）")

        try:
            if body_loc is None:
                raise RuntimeError("未定位到正文编辑器")
            body_loc.wait_for(timeout=10000)
            native_click(body_loc)
            page.wait_for_timeout(500)
            if not _fill_editor(page, body_loc, m["body"]):
                raise RuntimeError("富文本填充失败")
            print("[完成] 正文已填写。")
        except Exception as e:
            print(f"[跳过] 正文自动填写失败：{e}")
            dump_editor(page, out_dir)

        btn_text = "存草稿" if to_draft else "发布"
        candidates = (
            ["存草稿", "存为草稿", "保存草稿", "存稿", "存至草稿"]
            if to_draft else
            ["发布", "发布笔记"]
        )
        # 先滚动「所有可滚动容器」到底，把编辑器底部按钮渲染出来（懒加载/虚拟滚动）
        _scroll_all_to_bottom(page)
        clicked = _js_click_by_text(page, candidates)
        if not clicked:
            # 兜底：locator 文本匹配（button/role/div/span + aria/title）
            for t in candidates:
                try:
                    b = page.locator(
                        f'button:has-text("{t}"), [role="button"]:has-text("{t}"), '
                        f'div:has-text("{t}"), span:has-text("{t}"), '
                        f'[aria-label="{t}"], [title="{t}"]'
                    )
                    if b.count() > 0:
                        native_click(b.first)
                        clicked = True
                        break
                except Exception:
                    pass

        if clicked:
            page.wait_for_timeout(3000)
            print(f"[完成] 已自动点击『{btn_text}』，请在浏览器里确认出现成功提示。")
        else:
            print(f"[提示] 未自动定位到『{btn_text}』按钮，请手动点击。")
            dump_editor(page, out_dir)

        input("请在浏览器里确认结果（草稿箱/发布成功提示）；若没有成功提示，请手动点一次再确认。确认后按回车关闭浏览器…")
        browser.close()


# ------------------------- 入口 -------------------------
def main():
    ap = argparse.ArgumentParser(description="小红书图文笔记发布助手（本地半自动）")
    ap.add_argument("pid", help="文章 pid（即 posts 下的文件名，不含 .md）或 md 文件路径")
    ap.add_argument("--dry-run", action="store_true", help="仅生成适配草稿，不登录")
    ap.add_argument("--publish", action="store_true", help="登录并正式发布（需本机扫码）")
    ap.add_argument("--to-draft", action="store_true", help="登录并发到草稿箱（需本机扫码）")
    ap.add_argument("--title", help="自定义小红书标题（≤20 字）")
    ap.add_argument("--trim", type=int, default=0, help="正文超过该字数则自动截断（0=不截断）")
    ap.add_argument("--split", type=int, default=1, metavar="N",
                    help="把文章按章节拆成 N 篇（默认 1=不拆分）")
    ap.add_argument("--part", type=int, default=0, metavar="P",
                    help="配合 --split 只发布第 P 篇（1 起；0=全部）")
    ap.add_argument("--kind", choices=["note", "article"], default=None,
                    help="发布类型：note=图文笔记，article=长文（默认按字数自动判断）")
    ap.add_argument("--manual", action="store_true",
                    help="只生成手动发布包（标题/正文/话题/封面/配图），不登录不自动发布")
    ap.add_argument("--out", help="草稿输出根目录，默认 xhs_drafts")
    args = ap.parse_args()

    fm, body, _ = load_post(args.pid)

    # 手动模式：只产出内容包，不碰浏览器/登录，天然规避账号风控
    if args.manual:
        args.manual_kind = detect_kind(body, args.kind)
        print(f"[信息] 手动发布包类型：{'长文(article)' if args.manual_kind == 'article' else '图文笔记(note)'}"
              f"（正文约 {len(adapt_body(body))} 字）")
        if args.split > 1:
            parts = split_body(body, args.split)
            base_title = fm.get("title", "")
            for i, seg in enumerate(parts, 1):
                if args.part and i != args.part:
                    continue
                key = f"part{i}"
                t = make_split_title(base_title, i, args.split)
                seg_args = argparse.Namespace(**vars(args))
                if args.manual_kind == "article":
                    seg_args.trim = 0
                build_draft(args.pid, fm, seg, seg_args, out_key=key, title_override=t)
            print("\n（手动发布包已生成，按各 part 目录内的「发布说明.txt」操作）")
        else:
            build_args = argparse.Namespace(**vars(args))
            if args.manual_kind == "article":
                build_args.trim = 0
            build_draft(args.pid, fm, body, build_args)
            print("\n（手动发布包已生成：标题/正文/话题见「复制内容.txt」，操作步骤见「发布说明.txt」）")
        return

    kind = detect_kind(body, args.kind)
    print(f"[信息] 发布类型：{'长文(article)' if kind == 'article' else '图文笔记(note)'}（正文约 {len(adapt_body(body))} 字）")

    if args.split > 1:
        parts = split_body(body, args.split)
        base_title = fm.get("title", "")
        drafts = []
        for i, seg in enumerate(parts, 1):
            if args.part and i != args.part:
                continue
            key = f"part{i}"
            t = make_split_title(base_title, i, args.split)
            seg_args = args
            if kind == "article":
                # 长文不截断，拆出来的每篇保留完整内容
                seg_args = argparse.Namespace(**vars(args))
                seg_args.trim = 0
            man = build_draft(args.pid, fm, seg, seg_args, out_key=key, title_override=t)
            drafts.append((key, man))

        if args.dry_run or not (args.publish or args.to_draft):
            print(f"\n（已生成 {len(drafts)} 篇拆分草稿，未登录。要发布请加 --to-draft / --publish）")
            return

        for key, _man in drafts:
            print(f"\n========== 发布第 {key} 篇 ==========")
            mpath = (Path(args.out) if args.out else OUT_DEFAULT) / args.pid / key / "manifest.json"
            publish(mpath, args.to_draft, kind=kind)
        return

    if args.dry_run or not (args.publish or args.to_draft):
        build_args = args
        if kind == "article":
            build_args = argparse.Namespace(**vars(args))
            build_args.trim = 0
        build_draft(args.pid, fm, body, build_args)
        if not (args.publish or args.to_draft):
            print("\n（仅生成草稿，未登录。要发布请加 --to-draft / --publish，并在你本机运行脚本）")
        return

    build_args = args
    if kind == "article":
        build_args = argparse.Namespace(**vars(args))
        build_args.trim = 0
    build_draft(args.pid, fm, body, build_args)
    mpath = (Path(args.out) if args.out else OUT_DEFAULT) / args.pid / "manifest.json"
    publish(mpath, args.to_draft, kind=kind)


if __name__ == "__main__":
    main()
