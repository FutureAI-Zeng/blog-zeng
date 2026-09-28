# FutureAI-Zeng 的博客（blog-zeng）

个人技术博客，基于 Astro 5，内容从 cnblogs 同步，部署到 GitHub Pages（自定义域名 `future.zj.cn`）。

## 环境要求

- Node.js 20+
- npm
- Python 3.11+（仅运行 `scripts/` 下的同步/发布脚本时需要）

## 本地启动

### 1. 安装依赖

```bash
cd blog
npm install
```

### 2. 开发模式（日常调试用）

```bash
npm run dev
```

- 启动后访问：**http://localhost:4321/**
- 特点：文件修改后自动热更新，适合边改边看效果
- 注意：`astro dev` 默认端口是 `4321`，如果被占用会自动换端口，以终端实际输出为准

### 3. 构建 + 预览（接近线上效果）

```bash
npm run build
npm run preview
```

- 构建产物在 `dist/`，`preview` 会本地起一个静态服务器
- 访问：**http://localhost:4321/**（同样是 4321 端口）
- 特点：和 GitHub Pages 上看到的效果最接近，适合上线前最终确认

## 启动命令的区别

| 命令 | 用途 | 是否热更新 | 访问地址 | 对应产物 |
|---|---|---|---|---|
| `npm run dev` | 开发调试 | ✅ 是 | http://localhost:4321/ | 内存中实时编译 |
| `npm run build` | 生成静态产物 | ❌ 否 | — | `dist/` |
| `npm run preview` | 预览构建产物 | ❌ 否 | http://localhost:4321/ | `dist/` |

## 为什么本地访问根路径（`/`）而不是 `/blog-zeng/`

站点使用自定义域名 `https://future.zj.cn/`，Astro 的 `base` 已改为 `/`：

- 自定义域名：`https://future.zj.cn/`（base = `/`）
- 项目站点（旧）：`https://futureai-zeng.github.io/blog-zeng/`（base = `/blog-zeng/`，已不再使用）

因此本地访问直接用根路径 `http://localhost:4321/`，**不要再带 `/blog-zeng/` 前缀**。

## 本地访问 `/` 返回 404 怎么排查

最常见的原因是：**端口 `4321` 上还挂着一个改 `base` 之前启动的旧进程**（例如旧的 `astro preview`），它还在按旧路由 `/blog-zeng/` 服务，所以访问根路径 `/` 会 404。

排查步骤：

```bash
# 1. 看谁占用了 4321 端口
lsof -nP -iTCP:4321 -sTCP:LISTEN

# 2. 结束旧进程（把 PID 换成上面查到的进程号）
kill <PID>

# 3. 重新启动开发服务器
npm run dev
```

判断标准：`curl -s -o /dev/null -w '%{http_code}\n' http://localhost:4321/` 返回 `200`，而 `http://localhost:4321/blog-zeng/` 返回 `404`，即为正确状态（因为现在 base 是 `/`）。

## 部署方式（GitHub Pages）

1. 推送到 `main` 分支：

```bash
git add -A
git commit -m "更新内容"
git push origin main
```

2. GitHub Actions 会自动运行 `.github/workflows/deploy.yml`：
   - `npm ci` 安装依赖
   - `npm run build` 构建
   - 部署到 GitHub Pages

3. 自定义域名 `future.zj.cn` 通过 `public/CNAME` 文件保留，无需每次手动设置。

## 小红书发布台（独立界面）

为规避小红书脚本发布带来的账号风控，本项目提供一个**独立的小红书发布台**，把文章自动整理成「标题 / 正文 / 话题 / 封面 / 配图」，在手机上打开网页、复制发布即可。

入口地址（独立于博客界面，不在博客导航中暴露，需自己收藏）：

```
https://future.zj.cn/publish-xhs/
```

发布台包含以下页面：
- `/publish-xhs/` — 发布看板（来源/状态筛选、统计）
- `/publish-xhs/tool/` — 手动整理（粘贴或上传 .md，生成可复制内容）
- `/publish-xhs/activity/` — 同步记录（生成、状态变更等操作日志）
- `/publish-xhs/assets/` — 素材库（封面、配图集中查看）
- `/publish-xhs/settings/` — 账号设置（作者信息、发布偏好）

### 生成看板数据

```bash
# 单个 cnblogs URL 或文章 pid
python3 scripts/prepare_cnblogs.py "https://www.cnblogs.com/zjdxr-up/p/23049231"
python3 scripts/prepare_cnblogs.py 23049231

# 取 sitemap 最新 N 篇批量生成（默认 5）
python3 scripts/prepare_cnblogs.py --latest 5
```

产出：
- `public/publish/<pid>/cover.png` — 小红书封面（技术主题风）
- `src/data/publish.json` — 看板数据（标题/正文/话题/配图/状态/来源类型）
- `src/data/activity.json` — 同步记录（生成、状态变更日志）

### 状态管理

每条内容有四种状态：`draft（草稿）`、`pending（待发布）`、`published（已发布）`、`archived（已归档）`。

```bash
# 设置任意状态
python3 scripts/prepare_cnblogs.py --set-status 23049231:published
python3 scripts/prepare_cnblogs.py --set-status 23049231:draft

# 快捷标记已发布（等价于 --set-status :published）
python3 scripts/prepare_cnblogs.py --mark-published 23049231
```

### 手动整理（粘贴或上传 .md）

在 `/publish-xhs/tool/` 页面，可粘贴 Markdown/纯文本，或上传 `.md` 文件，自动生成标题、正文、话题，判断笔记/长文，并支持分段复制。

### GitHub Actions 自动生成

仓库已提供 `.github/workflows/prepare-xhs.yml`，在 GitHub → Actions → “Prepare XHS publish board” → Run workflow，可选填单个 `source` 或批量 `latest` 数量。它会自动抓取、生成封面、提交并触发部署。

> 注意：GitHub Pages 是纯静态站，无法做真正的密码鉴权。看板靠「不暴露入口 + 难猜 URL」达到“只有本人知道”的实际效果；���未来需要强鉴权，再单独上带登录的服务。

## 常用脚本

```bash
# 从 cnblogs 增量同步文章
python3 scripts/sync_cnblogs.py

# 文章转小红书发布包（手动复制发布，不自动登录）
python3 scripts/publish_xhs.py <pid> --manual

# 生成/更新小红书发布看板数据
python3 scripts/prepare_cnblogs.py --latest 5

# 生成小红书草稿（预览）
python3 scripts/publish_xhs.py <pid> --dry-run
```

Python 脚本依赖：

```bash
pip install markdownify beautifulsoup4 lxml pyyaml pillow
```

## 目录结构

- `src/content/posts/` — 博客文章（Markdown）
- `src/content/projects/` — 项目展示
- `src/pages/` — Astro 页面
- `src/components/` — 组件
- `src/layouts/` — 布局
- `src/consts.ts` — 站点配置
- `public/images/` — 图片（本地化存储）
- `scripts/` — cnblogs 同步、小红书发布看板生成等 Python 脚本
- `src/data/publish.json` — 小红书看板数据
- `src/data/activity.json` — 小红书同步记录
- `src/layouts/PublishLayout.astro` — 小红书发布台独立布局
- `src/pages/publish-xhs/` — 小红书发布台（看板/手动整理/同步记录/素材库/账号设置）
- `.github/workflows/` — 部署与同步 Actions
