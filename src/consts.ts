export interface GiscusConfig {
  repo: string;
  repoId: string;
  category: string;
  categoryId: string;
}

export const SITE = {
  title: 'FutureAI-Zeng 的博客',
  description: '一个用 Astro + GitHub Pages 搭建的个人博客',
  author: 'Your Name',
  lang: 'zh-CN',

  // ===== GitHub Pages 配置（部署前请填写）=====
  githubUser: 'FutureAI-Zeng', // 你的 GitHub 用户名
  repo: 'blog-zeng', // 仓库名；项目站点网址为 https://futureai-zeng.github.io/blog-zeng

  // ===== Giscus 评论配置（仓库开启 Discussions 并安装 giscus app 后填写，见 https://giscus.app）=====
  giscus: {
    repo: 'FutureAI-Zeng/blog-zeng', // 例如 'octocat/blog'
    repoId: 'R_kgDOUfd_fg', // 从 https://giscus.app 获取
    category: 'Announcements',
    categoryId: 'DIC_kwDOUfd_fs4DF17O', // 从 https://giscus.app 获取
  } satisfies GiscusConfig,
};
