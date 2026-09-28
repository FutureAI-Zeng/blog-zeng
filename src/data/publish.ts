export type SourceType = 'cnblogs' | 'zhihu' | 'juejin' | 'wechat' | 'other' | 'manual';
export type PublishStatus = 'draft' | 'pending' | 'published' | 'archived';

export interface PublishItem {
  id: string;
  source: string;
  source_type: SourceType;
  title: string;
  kind: 'note' | 'article';
  status: PublishStatus;
  topics: string[];
  body: string;
  cover: string;
  images: string[];
  created_at: string;
  published_at: string | null;
}

export const SOURCE_META: Record<SourceType, { label: string; short: string; color: string }> = {
  cnblogs: { label: '博客园', short: '博客园', color: '#2a65f5' },
  zhihu: { label: '知乎', short: '知乎', color: '#0084ff' },
  juejin: { label: '掘金', short: '掘金', color: '#1e80ff' },
  wechat: { label: '微信公众号', short: '公众号', color: '#07c160' },
  other: { label: '其他网站', short: '其他', color: '#8b949e' },
  manual: { label: '手动整理', short: '手动', color: '#e8590c' },
};

export const STATUS_META: Record<PublishStatus, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#8b949e' },
  pending: { label: '待发布', color: '#d97706' },
  published: { label: '已发布', color: '#16a34a' },
  archived: { label: '已归档', color: '#6b7280' },
};

import raw from './publish.json';

function normalize(item: any): PublishItem {
  return {
    ...item,
    source_type: item.source_type ?? 'cnblogs',
    status: item.status ?? 'pending',
  };
}

const arr = Array.isArray(raw) ? raw : [];
export const publishItems: PublishItem[] = arr.map(normalize);
