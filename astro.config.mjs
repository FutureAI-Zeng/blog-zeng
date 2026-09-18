import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { SITE } from './src/consts';

// 用户站点：repo 填 'username.github.io' → base 为 '/'，site 为 https://username.github.io
// 项目站点：repo 填 'blog-zeng'        → base 为 '/blog-zeng/'（带尾斜杠，保证 BASE_URL 拼链接正确）
const isUserSite = SITE.repo.endsWith('.github.io');
const base = isUserSite ? '/' : `/${SITE.repo}/`;
const host = SITE.githubUser ? `https://${SITE.githubUser.toLowerCase()}.github.io` : 'https://example.com';
const site = isUserSite ? host : `${host}/${SITE.repo}`;

export default defineConfig({
  site,
  base,
  integrations: [sitemap()],
  trailingSlash: 'always',
});
