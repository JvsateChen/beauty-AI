/**
 * 会话与本地偏好。
 *
 * 一期策略（与后端 core/security.py 对齐）：
 *  · 对话 / 比价 / 行情是公开只读能力，无会话也能用
 *  · 写操作（降价订阅、点击埋点）需要会话；会话由 device_id 换取，
 *    同一 device_id 永远复用同一 sid，避免刷新后「订阅换了个主人」
 *  · 所有状态只存本地，不上报任何设备指纹细节（device_id 是随机串，
 *    不含 UA / 屏幕 / 指纹信息）
 */

const DEVICE_KEY = 'caixuan.device_id';
const SID_KEY = 'caixuan.session_id';
const QUERY_KEY = 'caixuan.last_query';

function randomId(prefix: string): string {
  const g = globalThis as unknown as { crypto?: Crypto };
  if (g.crypto?.randomUUID) return `${prefix}${g.crypto.randomUUID().replace(/-/g, '')}`;
  const rand = () => Math.random().toString(36).slice(2, 10);
  return `${prefix}${Date.now().toString(36)}${rand()}${rand()}`;
}

export function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

export function getDeviceId(): string {
  if (!isBrowser()) return '';
  let id = window.localStorage.getItem(DEVICE_KEY);
  if (!id || id.length < 8) {
    id = randomId('dv');
    window.localStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

export function getSessionId(): string | null {
  if (!isBrowser()) return null;
  return window.localStorage.getItem(SID_KEY);
}

export function setSessionId(sid: string): void {
  if (isBrowser()) window.localStorage.setItem(SID_KEY, sid);
}

export function clearSession(): void {
  if (isBrowser()) window.localStorage.removeItem(SID_KEY);
}

/** 上一次查询的商品（用于跨页跳转时带上上下文，替代写死的「小棕瓶」） */
export function getLastQuery(): string | null {
  if (!isBrowser()) return null;
  return window.localStorage.getItem(QUERY_KEY);
}

export function setLastQuery(q: string): void {
  if (isBrowser() && q.trim()) window.localStorage.setItem(QUERY_KEY, q.trim());
}

/** 从 URL 读 ?q=；没有则回退到上次查询，再回退到默认商品 */
export function resolveQuery(fallback = '小棕瓶'): string {
  if (!isBrowser()) return fallback;
  const fromUrl = new URLSearchParams(window.location.search).get('q');
  if (fromUrl && fromUrl.trim()) return fromUrl.trim();
  return getLastQuery() || fallback;
}

/** 带 q 的站内链接 */
export function withQuery(path: string, q?: string | null): string {
  if (!q) return path;
  return `${path}${path.includes('?') ? '&' : '?'}q=${encodeURIComponent(q)}`;
}
