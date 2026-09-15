/**
 * 采选美妆 AI · 前端 API 客户端（v3.0）
 *
 * 设计原则（这一版最重要的改动）：
 *
 *  1. **不再提供伪造的兜底数据。**
 *     旧实现里 `FALLBACK_COMPARE` 硬编码了一套看起来很像真的价格（¥748 / ¥820 …）。
 *     后端一旦挂掉，页面照常显示这些数字 —— 用户无法分辨「这是真行情」还是
 *     「这是写死的假数据」。对一个比价产品来说这是致命的信任问题。
 *     现在后端不可用时，页面进入明确的「未连接」状态并给出重试入口，
 *     绝不显示任何价格数字。
 *
 *  2. **错误不再是 `throw new Error('HTTP 500')`。**
 *     后端统一错误体是 `{error:{code,message,request_id}}`，这里解析成
 *     `ApiError`，把 message（可直接展示给用户）与 request_id（报障用）带出来。
 *
 *  3. **会话由 device_id 换取并自动附加到请求头**，写操作不再依赖匿名可用的接口。
 */
import { getDeviceId, getSessionId, setSessionId } from './session';

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000';

// ---------------------------------------------------------------------------
// 口径常量（与 backend/core/domain.py 保持一一对应，改一处必须同步另一处）
// ---------------------------------------------------------------------------

export type ChannelName = '天猫' | '京东' | '拼多多' | '唯品会' | '保税仓';
export type Version = '国行' | '保税免税' | '海外版';
export type RiskTag = '临期预警' | '无专柜联保' | '捆绑消费溢价' | '第三方店铺售后风险';
export type PriceLevel = '低位' | '中位' | '高位';
export type Advice = '立即入手' | '观望等待' | '低位囤货';
/** 数据来源：live 真实渠道 / seed 演示数据集 / mixed 混合 / snapshot 历史快照 */
export type DataBasis = 'live' | 'seed' | 'mixed' | 'snapshot';
export type TrendShape = '先涨后降' | '先降后涨' | '持续下行' | '持续上行' | '区间震荡' | '无数据';
export type PushState = 'ready' | 'not_configured' | 'disabled';

export const RISK_TAGS: RiskTag[] = [
  '临期预警', '无专柜联保', '捆绑消费溢价', '第三方店铺售后风险',
];
export const VERSIONS: Version[] = ['国行', '保税免税', '海外版'];

// ---------------------------------------------------------------------------
// 错误
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;
  /** true 表示「后端根本没连上」（网络层失败），页面据此区分提示语气 */
  readonly offline: boolean;

  constructor(
    message: string,
    opts: { code?: string; status?: number; requestId?: string; offline?: boolean } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = opts.code ?? 'UNKNOWN';
    this.status = opts.status ?? 0;
    this.requestId = opts.requestId;
    this.offline = opts.offline ?? false;
  }
}

function isAbort(err: unknown): boolean {
  return err instanceof Error && err.name === 'AbortError';
}

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = 12000, ...rest } = init ?? {};
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;

  const sid = getSessionId();
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...((rest.headers as Record<string, string>) ?? {}),
  };
  if (sid) headers['X-Session-Id'] = sid;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: 'no-store',
      ...rest,
      headers,
      signal: controller?.signal,
    });
  } catch (err) {
    if (timer) clearTimeout(timer);
    if (isAbort(err)) {
      throw new ApiError('请求超时，请检查网络后重试。', { code: 'TIMEOUT', offline: true });
    }
    throw new ApiError(
      '无法连接服务端，请确认后端已启动或稍后重试。',
      { code: 'OFFLINE', offline: true },
    );
  } finally {
    if (timer) clearTimeout(timer);
  }

  const requestId = res.headers.get('x-request-id') ?? undefined;

  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = `请求失败（HTTP ${res.status}）`;
    try {
      const body = (await res.json()) as {
        error?: { code?: string; message?: string; request_id?: string };
      };
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch {
      /* 非 JSON 响应（如网关 HTML 错误页）：保留默认文案 */
    }
    throw new ApiError(message, {
      code,
      status: res.status,
      requestId,
    });
  }

  return (await res.json()) as T;
}

let sessionPromise: Promise<string> | null = null;

/**
 * 写操作前确保会话存在。
 * 并发调用只会发一次请求（小程序 / H5 首屏常见多个组件同时初始化）。
 */
export async function ensureSession(): Promise<string> {
  const existing = getSessionId();
  if (existing) return existing;
  if (sessionPromise) return sessionPromise;

  sessionPromise = (async () => {
    try {
      const deviceId = getDeviceId();
      const res = await fetch(`${API_BASE}/api/auth/session`, {
        method: 'POST',
        cache: 'no-store',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId || null }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        throw new ApiError(body?.error?.message ?? '创建会话失败，请稍后重试。', {
          code: 'SESSION_FAILED',
          status: res.status,
        });
      }
      const data = (await res.json()) as { session_id: string };
      setSessionId(data.session_id);
      return data.session_id;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('无法连接服务端，请确认后端已启动。', {
        code: 'OFFLINE',
        offline: true,
      });
    } finally {
      // 失败后允许下一次重试
      sessionPromise = null;
    }
  })();

  return sessionPromise;
}

// ---------------------------------------------------------------------------
// 数据契约（与后端响应字段一一对应）
// ---------------------------------------------------------------------------

export interface Benefits {
  coupon: number;
  platform_discount: number;
  gift_value: number;
  subsidy: number;
}

export interface Offer {
  id: string;
  channel: ChannelName;
  shop_name: string;
  shop_type: string;
  version: Version;
  origin?: string | null;
  /** 到手价（行情参考价，由优惠拆解推导） */
  price: number;
  price_cents: number;
  list_price: number;
  benefits: Benefits;
  benefit_total: number;
  benefit_total_cents: number;
  drop_pct: number;
  /** 价格与优惠拆解是否自洽（真实源未完整拆解时为 false） */
  price_consistent: boolean;
  risk_tags: RiskTag[];
  sponsored: boolean;
  shelf_life_months?: number | null;
  warranty?: string | null;
  note?: string | null;
  /** 是否最低到手价 —— 由后端判定（非赞助位最低），前端不得自行比较浮点 */
  is_lowest?: boolean;
  is_fact_lowest?: boolean;
  /** 该渠道的跳转链接；永远非空（可能是联盟推广链，也可能是官方搜索深链） */
  cps_url: string;
  /** true = 联盟佣金归因已生效；false = 官方深链兜底，不产生佣金 */
  cps_tracked: boolean;
  sub_id: string;
  search_keyword?: string | null;
  history_30d_low?: number;
  history_90d_low?: number;
  price_level?: PriceLevel;
  data_basis?: DataBasis;
}

export interface TrendPoint {
  date: string;
  price: number;
  event?: string | null;
}

export interface Trend {
  days: number;
  points: TrendPoint[];
  low_90d: number;
  high_90d: number;
  low_30d: number;
  avg_90d: number;
  current: number;
  level: PriceLevel;
  advice: Advice;
  advice_reason: string;
  shape: TrendShape;
  rise_then_fall: boolean;
  fall_pct_from_peak: number;
  rebound_after_low: number;
  real_low_confirmed: boolean;
  peak: { index: number; price: number } | null;
  trough: { index: number; price: number } | null;
  promo_points: TrendPoint[];
  data_basis: DataBasis;
  disclaimer: string;
}

export interface VersionRow {
  version: Version;
  ingredient_diff: string;
  shelf_life: string;
  warranty: string;
  fit: string;
  risk_tags: RiskTag[];
  lowest_price: number | null;
  price_gap: number | null;
  price_gap_note: string;
  available: boolean;
  origins: string[];
}

export interface Product {
  key: string;
  name: string;
  brand: string;
  brand_en: string;
  spec: string;
  category: string;
  sku: string;
  list_price: number;
}

export interface CompareResult {
  query: string;
  product: Product;
  offers: Offer[];
  versions: VersionRow[];
  trend: Trend;
  lowest_price: number | null;
  lowest_label: string | null;
  absolute_lowest: number | null;
  absolute_lowest_channel: string | null;
  absolute_lowest_is_sponsored: boolean;
  deal_count: number;
  data_basis: DataBasis;
  data_sources: string[];
  /** 本次没拿到报价的渠道 */
  unavailable_channels: string[];
  /** 联盟凭据未接入的渠道（商务进度，不等于「没这个渠道」） */
  unconfigured_channels: string[];
  note: string | null;
  price_label: string;
  disclaimer: string;
}

export interface DialogueSection {
  key: 'fit' | 'price' | 'version' | 'advice' | 'risk';
  title: string;
  text: string;
}

export interface DialogueIntent {
  budget: number | null;
  skin_type: string | null;
  needs: string[];
  product: string | null;
  product_alias: string | null;
  requested_spec: string | null;
  channels_pref: string[];
  asks_version: boolean;
  asks_price: boolean;
  unmatched_reason: string | null;
}

export interface ChatResponse {
  intent: DialogueIntent;
  sections: DialogueSection[];
  reply: string;
  product_key: string | null;
  product_label: string | null;
  suggestions: string[];
  data_basis: DataBasis | null;
  data_sources: string[];
  unavailable_channels: string[];
  note: string | null;
  disclaimer: string;
  session_id: string | null;
}

export interface SuggestionResponse {
  products: Product[];
  examples: string[];
  modules: { key: string; title: string }[];
}

export type NotifyStatus = 'not_configured' | 'no_recipient' | 'pending' | 'sent' | 'failed';

export interface AlertSub {
  id: string;
  product_input: string;
  product_key: string | null;
  product_label: string;
  target_price: number;
  channel: string | null;
  status: string;
  triggered: boolean;
  reasons: string[];
  current_lowest: number | null;
  trend_low: number | null;
  notify_status: NotifyStatus;
  notify_status_label: string;
  notify_error: string | null;
  push_ready: boolean;
  push_channels: string[];
  push_user_message: string;
  push_results: { channel: string; status: string; detail: string; error: string | null }[];
  checked_at: string | null;
  notified_at: string | null;
  created_at: string | null;
  note: string | null;
}

export interface AlertListResult {
  query: string | null;
  count: number;
  subs: AlertSub[];
  notify_via: string[];
  push_ready: boolean;
  push_state: PushState;
  push_user_message: string;
  triggered_count: number;
}

export interface PushCapability {
  state: PushState;
  ready: boolean;
  channels: string[];
  interval_minutes: number;
  cooldown_hours: number;
  note: string;
  user_message: string;
  thresholds: { big_subsidy_ratio: number; min_target_price: number };
}

export interface BestOffer {
  product_key: string;
  product_label: string;
  offer_id: string;
  channel: string;
  shop_name: string;
  price: number;
  cps_url: string;
  cps_tracked: boolean;
  sub_id: string;
  data_basis: DataBasis;
}

export interface SourceStatus {
  data_mode: string;
  data_source_label: string;
  channels: { channel: string; configured: boolean; mode: string }[];
  configured_channels: string[];
  note: string;
}

export interface SessionInfo {
  session_id: string;
  device_id: string | null;
  is_member: boolean;
  member_expire_at: string | null;
  logged_in: boolean;
  wechat_bound: boolean;
  push_reachable: boolean;
  created_at: string | null;
}

export interface ClicksSummary {
  total: number;
  by_channel: { channel: string; count: number }[];
  tracked_with_sub_id?: number;
  latest?: { channel: string; shop_name: string | null; at: string | null } | null;
  note: string;
}

// ---------------------------------------------------------------------------
// 接口方法
// ---------------------------------------------------------------------------

export function postChat(text: string): Promise<ChatResponse> {
  return request<ChatResponse>('/api/dialogue/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text }),
  });
}

export function getSuggestions(): Promise<SuggestionResponse> {
  return request<SuggestionResponse>('/api/dialogue/suggestions');
}

export function getCompareResult(q: string): Promise<CompareResult> {
  return request<CompareResult>(`/api/compare/result?q=${encodeURIComponent(q)}`);
}

export function getProducts(): Promise<{ count: number; products: (Product & { aliases: string[] })[] }> {
  return request('/api/compare/products');
}

export function getSourceStatus(): Promise<SourceStatus> {
  return request<SourceStatus>('/api/compare/sources');
}

export function getTrend(
  q: string,
  days: 30 | 90 | 180 = 90,
): Promise<Trend & {
  query: string;
  product: Product;
  current_lowest: number;
  current_label: string | null;
}> {
  return request(`/api/trend/series?q=${encodeURIComponent(q)}&days=${days}`);
}

export function getAlertCapability(): Promise<PushCapability> {
  return request<PushCapability>('/api/alert/capability');
}

export async function getAlerts(q?: string): Promise<AlertListResult> {
  await ensureSession();
  const qs = q ? `?q=${encodeURIComponent(q)}` : '';
  return request<AlertListResult>(`/api/alert/list${qs}`, { timeoutMs: 25000 });
}

export async function addAlert(
  product: string,
  targetPrice: number,
  channel?: string | null,
): Promise<{ ok: boolean; sub: AlertSub; message: string }> {
  await ensureSession();
  return request('/api/alert/add', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ product, target_price: targetPrice, channel: channel || null }),
  });
}

export async function deleteAlert(subId: string): Promise<{ ok: boolean; message: string }> {
  await ensureSession();
  return request(`/api/alert/${encodeURIComponent(subId)}`, { method: 'DELETE' });
}

export function getBestOffer(q: string): Promise<BestOffer> {
  return request<BestOffer>(`/api/offer/best?q=${encodeURIComponent(q)}`);
}

export async function getClicksSummary(): Promise<ClicksSummary> {
  await ensureSession();
  return request<ClicksSummary>('/api/offer/clicks/summary');
}

/** 服务端跳转入口：由后端记一次点击后 302 到真实地址（归因更可靠） */
export function goUrl(q: string, offerId: string, sid?: string | null): string {
  const p = new URLSearchParams({ q, offer_id: offerId });
  if (sid) p.set('sid', sid);
  return `${API_BASE}/api/offer/go?${p.toString()}`;
}

/**
 * 点击埋点（可选）。页面在用户点「去购买」时调用，
 * 用 keepalive 保证跳转过程中请求不被取消。
 */
export async function trackClick(payload: {
  product_key?: string | null;
  offer_id: string;
  channel: string;
  shop_name?: string | null;
  version?: string | null;
  price?: number | null;
  sub_id?: string | null;
  cps_url?: string | null;
}): Promise<void> {
  try {
    const sid = getSessionId();
    await fetch(`${API_BASE}/api/offer/click`, {
      method: 'POST',
      keepalive: true,
      headers: {
        'content-type': 'application/json',
        ...(sid ? { 'X-Session-Id': sid } : {}),
      },
      body: JSON.stringify(payload),
    });
  } catch {
    /* 埋点失败不影响用户跳转 */
  }
}

export async function getSession(): Promise<SessionInfo> {
  await ensureSession();
  return request<SessionInfo>('/api/auth/me');
}

export function getHealth(): Promise<{ ok: boolean; version: string }> {
  return request('/healthz', { timeoutMs: 4000 });
}
