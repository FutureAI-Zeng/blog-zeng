# AI_CONTEXT: blog-zeng

个人技术博客，Astro 静态站点，从 cnblogs 同步文章，可发布到小红书草稿箱，部署到 GitHub Pages（自定义域名 future.zj.cn）。

## Goal

- 维护一个低维护成本、自动化程度高的个人博客：cnblogs 内容自动/半自动同步 → Astro 构建 → GitHub Pages 发布。
- 近期目标：支持把博客文章一键转成小红书图文/长文草稿并发布。

## Current State

- 基础功能已完成：分类、标签、归档、项目页、搜索、5 套主题、Giscus 评论、RSS、sitemap。
- 已同步约 700+ 篇 cnblogs 文章到 `src/content/posts/`（文件名为博客园文章 ID）。
- 自定义域名 `future.zj.cn` 的 base 配置已改好，但本地有未提交改动（`astro.config.mjs`、`.gitignore`、`public/CNAME`）。
- `scripts/publish_xhs.py` 小红书发布脚本已写好，但尚未提交进 git。
- 本地 git 领先远程 3 个提交，且有未提交的本地改动。
- 小红书发布台已完成：独立界面（独立于博客布局）+ 看板/手动整理/同步记录/素材库/账号设置五个页面；数据模型支持来源类型（cnblogs/zhihu/juejin/wechat/other/manual）与状态（draft/pending/published/archived）。

## Key Decisions

- 用 **cnblogs 文章 ID 作为本地文件名**（如 `10099561.md`），保证增量同步时能去重、不覆盖本地修改。
- 图片全部本地化到 `public/images/`，避免 cnblogs 防盗链导致 403。
- 自定义域名 `future.zj.cn` 绑定后 `base` 必须是 `/`；项目站点则用 `/blog-zeng/`。
- 小红书没有官方发布 API，发布走 Playwright 浏览器自动化 + 本地扫码，登录 cookie 只存本地 `.xhs_cookies.json`，不进仓库。
- 同步/发布等脚本用 Python 独立实现，不混进 Astro 的 npm 脚本。

## Structure

- `src/content/posts/` — 博客文章（Markdown，frontmatter: title/description/pubDate/category/tags/draft/pinned）。
- `src/content/projects/` — 项目展示条目。
- `src/consts.ts` — 站点信息、GitHub Pages 配置、Giscus 评论配置。
- `src/pages/` — Astro 页面：首页、归档、分类、标签、项目、搜索、RSS、sitemap、文章详情。
- `src/utils/posts.ts` — 文章读取/排序/分页工具。
- `scripts/sync_cnblogs.py` — 从 cnblogs 增量同步文章（含图片本地化、标签反查）。
- `scripts/publish_xhs.py` — 把文章转成小红书草稿并半自动发布。
- `scripts/prepare_cnblogs.py` — cnblogs 单篇/最新几篇 → 生成小红书看板数据（含封面，复用 publish_xhs 适配逻辑）。
- `src/data/publish.json` + `src/data/publish.ts` — 看板数据源（含 source_type、status）。
- `src/data/activity.json` + `src/data/activity.ts` — 同步记录数据源。
- `src/layouts/PublishLayout.astro` — 小红书发布台独立布局（侧边栏菜单、顶部工具条）。
- `src/pages/publish-xhs/` — 发布台：看板 `index.astro`、详情 `[id].astro`、手动整理 `tool.astro`、同步记录 `activity.astro`、素材库 `assets.astro`、账号设置 `settings.astro`。
- `.github/workflows/deploy.yml` — push 到 main 时构建并部署 GitHub Pages。
- `.github/workflows/sync-cnblogs.yml` — 手动/每周定时从 cnblogs 同步并提交。
- `.github/workflows/prepare-xhs.yml` — 手动触发生成小红书看板数据（装 Noto CJK 字体后跑 prepare_cnblogs.py 并提交）。

## Conventions & Gotchas

- 本地开发: `npm run dev` → 访问 http://localhost:4321/（base=`/`，不要再带 `/blog-zeng/`）
- 构建: `npm run build`（产物在 `dist/`）
- 预览: `npm run preview` → 访问 http://localhost:4321/（接近线上效果）
- 部署: push 到 main 后，GitHub Actions `deploy.yml` 自动构建并部署 GitHub Pages（自定义域名 future.zj.cn）
- 完整启动/部署说明见 `README.md`
- 同步文章: `python3 scripts/sync_cnblogs.py`（可加 `--update N` / `--no-tags` / `--dry-run` / `--limit N`）
- 小红书草稿: `python3 scripts/publish_xhs.py <pid> --dry-run [--title "..."] [--out xhs_drafts]`
- 发布小红书: `python3 scripts/publish_xhs.py <pid> --to-draft` 或 `--publish`（需本机扫码）
- 看板生成: `python3 scripts/prepare_cnblogs.py <pid|URL>` 或 `--latest N`（会写 activity.json）
- 看板状态: `python3 scripts/prepare_cnblogs.py --set-status <pid>:<status>`（draft/pending/published/archived）
- 看板标记已发布: `python3 scripts/prepare_cnblogs.py --mark-published <pid>`，然后 commit & push
- Python 脚本依赖: `pip install markdownify beautifulsoup4 lxml pyyaml pillow playwright`
- 敏感文件不入库: `.xhs_cookies.json`、`xhs_drafts/`、`xhs_drafts_trimmed/` 已在 `.gitignore`。
- 发布前先 `npm run build` 检查构建是否通过；图片必须放在 `public/images/` 并在文章中引用相对 base 路径。

## Next Steps

- [ ] 把发布台（prepare_cnblogs.py、publish-xhs 页面、workflow）提交并 push，验证线上 `/publish-xhs/`。
- [ ] 在 GitHub Actions 跑一次 `Prepare XHS publish board`，确认云端生成封面（Noto CJK 字体）正常。
- [ ] 继续验证解析效果：先取较新 5~10 篇，确认笔记/长文判断、配图契合度，再决定是否全量。
- [ ] 扩展微信/知乎/掘金独立脚本（prepare_wechat.py、prepare_zhihu.py、prepare_juejin.py 等），复用 source_type 字段。
- [ ] 若需强鉴权，引入带登录的后端（当前靠难猜 URL 隐藏入口）。

## Handoff

- last_updated: 2026-09-28 12:15
- tool: Codex
- notes: 域名修复已推送；小红书发布看板（/publish-xhs/ 隐藏页 + prepare_cnblogs.py + GitHub Actions）已完成并本地构建通过（954 页），待提交推送。
