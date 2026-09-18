import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/[^_]*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    category: z.string().default('未分类'),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
    pinned: z.boolean().default(false),
  }),
});

const projects = defineCollection({
  loader: glob({ pattern: '**/[^_]*.md', base: './src/content/projects' }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    tags: z.array(z.string()).default([]),
    url: z.string().optional(),
    repo: z.string().optional(),
    cover: z.string().optional(),
    order: z.number().default(0),
    status: z.string().default('已完成'),
  }),
});

export const collections = { posts, projects };
