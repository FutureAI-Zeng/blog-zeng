import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { SITE } from './src/consts';

// 自定义域名：绑定到 GitHub Pages 根目录时，base 必须是 '/'。
// 项目站点（futureai-zeng.github.io/blog-zeng）：base 为 '/blog-zeng/'。
const customDomain = 'future.zj.cn';
const isUserSite = SITE.repo.endsWith('.github.io');
const base = customDomain ? '/' : (isUserSite ? '/' : `/${SITE.repo}/`);
const site = customDomain
  ? `https://${customDomain}`
  : (isUserSite
      ? `https://${SITE.githubUser.toLowerCase()}.github.io`
      : `https://${SITE.githubUser.toLowerCase()}.github.io/${SITE.repo}`);

export default defineConfig({
  site,
  base,
  integrations: [sitemap()],
  trailingSlash: 'always',
});
