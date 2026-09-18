import type { APIRoute } from 'astro';
import { getPosts } from '../utils/posts';

export const GET: APIRoute = async () => {
  const posts = await getPosts();
  const base = import.meta.env.BASE_URL;
  const items = posts.map((p) => ({
    title: p.data.title,
    description: p.data.description ?? '',
    url: `${base}posts/${p.id}/`,
    category: p.data.category,
    tags: p.data.tags,
    date: p.data.pubDate.toISOString().slice(0, 10),
    text: (p.body ?? '')
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/[#>*_`~\[\]()!-]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 1500),
  }));
  return new Response(JSON.stringify(items), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};
