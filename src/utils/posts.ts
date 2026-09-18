import { getCollection, type CollectionEntry } from 'astro:content';

export type Post = CollectionEntry<'posts'>;

/** 获取已发布文章，按时间倒序 */
export async function getPosts(): Promise<Post[]> {
  return (await getCollection('posts', ({ data }) => !data.draft)).sort(
    (a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf()
  );
}

/** 估算阅读时长（中文按 350 字/分，英文按 200 词/分） */
export function readingTime(post: Post): number {
  const text = post.body ?? '';
  const cjk = (text.match(/[一-鿿]/g) || []).length;
  const words = (text.replace(/[一-鿿]/g, ' ').match(/\b\w+\b/g) || []).length;
  return Math.max(1, Math.ceil(cjk / 350 + words / 200));
}

/** 统计每个标签的文章数，按数量倒序 */
export function groupByTags(posts: Post[]): [string, number][] {
  const map = new Map<string, number>();
  for (const p of posts) for (const t of p.data.tags) map.set(t, (map.get(t) ?? 0) + 1);
  return [...map.entries()].sort((a, b) => b[1] - a[1]);
}

/** 统计每个分类的文章数，按名称排序 */
export function groupByCategories(posts: Post[]): [string, number][] {
  const map = new Map<string, number>();
  for (const p of posts) {
    const c = p.data.category || '未分类';
    map.set(c, (map.get(c) ?? 0) + 1);
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0], 'zh'));
}

/** 按年份归档 */
export function groupByYear(posts: Post[]): [number, Post[]][] {
  const map = new Map<number, Post[]>();
  for (const p of posts) {
    const y = p.data.pubDate.getFullYear();
    if (!map.has(y)) map.set(y, []);
    map.get(y)!.push(p);
  }
  return [...map.entries()].sort((a, b) => b[0] - a[0]);
}

/** 按年月归档，返回 [{ key:'YYYY-MM', year, month, label, count, posts }] 倒序 */
export function groupByMonth(posts: Post[]): {
  key: string; year: number; month: number; label: string; count: number; posts: Post[];
}[] {
  const map = new Map<string, Post[]>();
  for (const p of posts) {
    const d = p.data.pubDate;
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(p);
  }
  return [...map.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([key, ps]) => {
      const [year, month] = key.split('-').map(Number);
      return { key, year, month, label: `${year} 年 ${month} 月`, count: ps.length, posts: ps };
    });
}
