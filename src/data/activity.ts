export type ActivityType = 'generate' | 'set_status' | 'mark_published' | 'manual_create' | 'manual_copy';

export interface ActivityRecord {
  id: string;
  time: string;
  type: ActivityType;
  source_type: string;
  pid?: string;
  title?: string;
  detail?: string;
}

export const ACTIVITY_META: Record<ActivityType, { label: string; color: string; icon: string }> = {
  generate: { label: '生成', color: '#2a65f5', icon: '🔄' },
  set_status: { label: '状态变更', color: '#d97706', icon: '🏷️' },
  mark_published: { label: '标记发布', color: '#16a34a', icon: '✅' },
  manual_create: { label: '手动整理', color: '#e8590c', icon: '✍️' },
  manual_copy: { label: '复制内容', color: '#8b949e', icon: '📋' },
};

let raw: ActivityRecord[] = [];
try {
  const mod = await import('./activity.json');
  raw = Array.isArray((mod as any).default) ? (mod as any).default : [];
} catch {
  raw = [];
}

export const activityItems: ActivityRecord[] = raw;
