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
- `.github/workflows/deploy.yml` — push 到 main 时构建并部署 GitHub Pages。
- `.github/workflows/sync-cnblogs.yml` — 手动/每周定时从 cnblogs 同步并提交。

## Conventions & Gotchas

- Run: `npm run dev`
- Build: `npm run build`
- Preview: `npm run preview`
- 同步文章: `python3 scripts/sync_cnblogs.py`（可加 `--update N` / `--no-tags` / `--dry-run` / `--limit N`）
- 小红书草稿: `python3 scripts/publish_xhs.py <pid> --dry-run [--title "..."] [--out xhs_drafts]`
- 发布小红书: `python3 scripts/publish_xhs.py <pid> --to-draft` 或 `--publish`（需本机扫码）
- Python 脚本依赖: `pip install markdownify beautifulsoup4 lxml pyyaml pillow playwright`
- 敏感文件不入库: `.xhs_cookies.json`、`xhs_drafts/`、`xhs_drafts_trimmed/` 已在 `.gitignore`。
- 发布前先 `npm run build` 检查构建是否通过；图片必须放在 `public/images/` 并在文章中引用相对 base 路径。

## Next Steps

- [ ] 确认自定义域名改动无误后，提交 `astro.config.mjs`、`.gitignore`、`public/CNAME` 并 push。
- [ ] 决定 `scripts/publish_xhs.py` 是否纳入仓库（已实现，尚未提交）。
- [ ] 处理本地领先的 3 个提交与未提交改动（合并/推送）。
- [ ] 验证小红书 `--dry-run` 生成的草稿格式，再走真实 `--to-draft`。

## Handoff

- last_updated: 2026-09-28 10:15
- tool: Codex
- notes: 当前有未提交改动，且 `scripts/publish_xhs.py` 是新增文件；下次会话先检查 `git status`。
