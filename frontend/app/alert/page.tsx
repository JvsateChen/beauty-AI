'use client';

import { useCallback, useEffect, useState } from 'react';
import { Icon } from '@/components/Icons';
import { OfflineNotice, SectionLink } from '@/components/Cards';
import {
  ApiError, addAlert, deleteAlert, getAlertCapability, getAlerts,
  type AlertListResult, type AlertSub, type PushCapability,
} from '@/lib/api';
import { resolveQuery, setLastQuery, withQuery } from '@/lib/session';

const NOTIFY_CLS: Record<string, string> = {
  已推送: 'bg-success/10 text-success',
  推送失败: 'bg-danger/10 text-danger',
  推送通道未接入: 'bg-cream text-muted',
  未授权微信接收: 'bg-warn/10 text-warn',
  待推送: 'bg-cream text-muted',
};

export default function AlertPage() {
  const [q, setQ] = useState('');
  const [data, setData] = useState<AlertListResult | null>(null);
  const [cap, setCap] = useState<PushCapability | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; offline: boolean; requestId?: string } | null>(null);

  const [product, setProduct] = useState('');
  const [target, setTarget] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const load = useCallback((query?: string) => {
    setLoading(true);
    getAlerts(query)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        const err = e as ApiError;
        setData(null);
        setError({
          message: err?.message ?? '加载失败',
          offline: Boolean(err?.offline),
          requestId: err?.requestId,
        });
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const initial = resolveQuery();
    setQ(initial);
    setProduct(initial);
    load();
    getAlertCapability().then(setCap).catch(() => setCap(null));
  }, [load]);

  const submit = async () => {
    const p = product.trim();
    const t = Number(target);
    setMsg(null);
    if (!p) {
      setMsg({ kind: 'err', text: '请填写要监测的商品名称。' });
      return;
    }
    if (!Number.isFinite(t) || t <= 0) {
      setMsg({ kind: 'err', text: '请填写有效的心理底价（元）。' });
      return;
    }
    if (cap && t < cap.thresholds.min_target_price) {
      setMsg({
        kind: 'err',
        text: `目标价过低，至少 ¥${cap.thresholds.min_target_price}。`,
      });
      return;
    }
    setSubmitting(true);
    try {
      const res = await addAlert(p, t);
      setLastQuery(res.sub.product_key ?? p);
      setMsg({ kind: 'ok', text: res.message });
      setProduct('');
      setTarget('');
      load();
    } catch (e) {
      const err = e as ApiError;
      setMsg({ kind: 'err', text: err?.message ?? '创建失败，请稍后重试。' });
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (id: string) => {
    setMsg(null);
    try {
      const res = await deleteAlert(id);
      setMsg({ kind: 'ok', text: res.message });
      setData((d) => (d ? { ...d, subs: d.subs.filter((s) => s.id !== id), count: d.count - 1 } : d));
    } catch (e) {
      const err = e as ApiError;
      setMsg({ kind: 'err', text: err?.message ?? '删除失败。' });
    }
  };

  const subs = data?.subs ?? [];
  const triggered = subs.filter((s) => s.triggered);

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl md:text-3xl font-bold mb-2">降价订阅提醒</h1>
      <p className="text-muted text-sm mb-4">
        设定心仪商品与心理底价。命中「跌破底价 / 创历史新低 / 大额补贴」任一条件即提醒。
      </p>

      {/* 推送能力诚实说明 */}
      {cap && (
        <div
          className={`rounded-2xl p-4 mb-5 border ${
            cap.ready
              ? 'bg-success/5 border-success/30'
              : 'bg-warn/5 border-warn/30'
          }`}
        >
          <div className="flex items-start gap-2">
            <Icon
              name={cap.ready ? 'check' : 'unplugged'}
              size={15}
              className={cap.ready ? 'text-success mt-0.5' : 'text-warn mt-0.5'}
            />
            <div className="min-w-0">
              <div className="text-xs font-bold text-ink">
                微信推送能力：{cap.ready ? `已接入（${cap.channels.join(' + ')}）` : '尚未接入'}
              </div>
              <p className="text-[11px] text-muted mt-1 leading-relaxed">{cap.user_message}</p>
              <p className="text-[10px] text-muted mt-1.5 leading-relaxed">
                监测本身在你关闭页面后仍会由服务端定时执行（每 {cap.interval_minutes} 分钟一轮）；
                命中后的推送有 {cap.cooldown_hours} 小时冷却，避免价格抖动时反复打扰。
              </p>
              {!cap.ready && (
                <p className="text-[10px] text-muted mt-1.5 font-mono break-all">
                  接入方式：配置 WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET / WECHAT_MP_TEMPLATE_ID
                  （或小程序 WECHAT_MINI_*）并置 PUSH_ENABLED=true
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 创建订阅 */}
      <div className="bg-white border border-line rounded-2xl p-5 mb-5">
        <h2 className="text-sm font-bold text-brand-rose-dark mb-3 inline-flex items-center gap-1.5">
          <Icon name="target" size={14} />
          新建降价提醒
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label className="block">
            <span className="text-[11px] text-muted">商品</span>
            <input
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              placeholder="如「小棕瓶」「神仙水」"
              className="mt-1 w-full bg-cream rounded-lg px-3 h-9 text-sm focus:outline-none focus:ring-2 focus:ring-brand-rose/30"
            />
          </label>
          <label className="block">
            <span className="text-[11px] text-muted">
              心理底价（元）{cap && `· 不低于 ¥${cap.thresholds.min_target_price}`}
            </span>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              inputMode="decimal"
              placeholder="如 800"
              className="mt-1 w-full bg-cream rounded-lg px-3 h-9 text-sm focus:outline-none focus:ring-2 focus:ring-brand-rose/30"
            />
          </label>
          <div className="flex items-end">
            <button
              onClick={submit}
              disabled={submitting}
              className="w-full bg-brand-rose text-white rounded-lg h-9 text-sm font-bold hover:bg-brand-rose-dark transition-colors disabled:opacity-50"
            >
              {submitting ? '创建中…' : '创建订阅'}
            </button>
          </div>
        </div>
        <p className="text-[10px] text-muted mt-3">
          同一商品重复创建只会更新目标价，不会产生多条订阅。商品暂未收录也可以先订阅，
          收录后自动开始监测。
        </p>
        {msg && (
          <div
            className={`text-[11px] mt-2 inline-flex items-start gap-1.5 ${
              msg.kind === 'ok' ? 'text-success' : 'text-danger'
            }`}
          >
            <Icon name={msg.kind === 'ok' ? 'check' : 'warn'} size={12} className="mt-0.5" />
            {msg.text}
          </div>
        )}
      </div>

      {loading && <div className="h-40 rounded-2xl bg-white border border-line animate-pulse" />}

      {!loading && error && (
        <OfflineNotice
          title={error.offline ? '服务未连接' : '加载未完成'}
          message={error.message}
          detail={error.requestId ? `追踪号：${error.requestId}` : undefined}
          onRetry={() => load()}
        />
      )}

      {!loading && !error && data && (
        <>
          {/* 已触发提醒 */}
          {triggered.length > 0 && (
            <div className="mb-5">
              <h2 className="text-sm font-bold text-brand-rose-dark mb-2.5 inline-flex items-center gap-1.5">
                <Icon name="bell" size={14} />
                已触发提醒（{triggered.length}）
              </h2>
              <div className="space-y-2.5">
                {triggered.map((s) => (
                  <TriggeredCard key={s.id} sub={s} />
                ))}
              </div>
            </div>
          )}

          {/* 订阅列表 */}
          <div className="bg-white border border-line rounded-2xl p-5">
            <h2 className="text-sm font-bold text-brand-rose-dark mb-3 inline-flex items-center gap-1.5">
              <Icon name="layers" size={14} />
              我的订阅（{subs.length}）
            </h2>
            {subs.length === 0 ? (
              <div className="text-xs text-muted py-8 text-center">
                暂无订阅。在上方填写商品与心理底价即可创建。
              </div>
            ) : (
              <div className="divide-y divide-line">
                {subs.map((s) => (
                  <div key={s.id} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold truncate">{s.product_label}</div>
                        <div className="text-[10px] text-muted mt-0.5 flex flex-wrap gap-x-2">
                          {s.created_at && <span>创建于 {fmt(s.created_at)}</span>}
                          {s.channel && <span>仅盯 {s.channel}</span>}
                          {s.current_lowest != null && <span>现价 ¥{s.current_lowest}</span>}
                          {s.trend_low != null && <span>此前低点 ¥{s.trend_low}</span>}
                        </div>
                        {s.note && (
                          <div className="text-[10px] text-warn mt-1">{s.note}</div>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-sm font-bold text-brand-rose-dark">
                          ≤ ¥{s.target_price}
                        </div>
                        <div
                          className={`text-[10px] font-bold inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${
                            NOTIFY_CLS[s.notify_status_label] ?? 'bg-cream text-muted'
                          }`}
                           title={s.notify_error ?? undefined}
                        >
                          {s.notify_status_label}
                        </div>
                      </div>
                      <button
                        onClick={() => remove(s.id)}
                        className="shrink-0 text-muted hover:text-danger transition-colors p-1"
                        title="删除该提醒"
                        aria-label={`删除 ${s.product_label} 的提醒`}
                      >
                        <Icon name="trash" size={15} />
                      </button>
                    </div>
                    {s.reasons.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {s.reasons.map((r) => (
                          <li key={r} className="text-[11px] text-ink inline-flex items-start gap-1.5">
                            <Icon name="target" size={11} className="text-brand-rose mt-0.5" />
                            {r}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2 mt-5">
            <SectionLink href={withQuery('/compare', q)} icon="scale" label="查看比价看板" primary />
            <SectionLink href={withQuery('/trend', q)} icon="chart" label="查看 90 天行情" />
          </div>
        </>
      )}

      <p className="text-[10px] text-muted mt-4 border-l-2 border-gold pl-3 leading-relaxed">
        提醒基于行情参考价触发，非锁定成交价；实际可购价格以下单页为准。
        本平台不提供真伪鉴定服务，商品正品性与售后维权由跳转电商平台全权负责。
      </p>
    </div>
  );
}

/**
 * 已触发卡片。
 *
 * 关键：这里不再无条件写「已通过公众号 / 小程序推送」。
 * 只有后端回报 notify_status=sent 才说「已推送」，其余状态如实说明原因。
 */
function TriggeredCard({ sub }: { sub: AlertSub }) {
  const sent = sub.notify_status === 'sent';
  return (
    <div className="bg-brand-rose-soft border border-brand-rose rounded-xl p-4">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <span className="text-sm font-bold text-brand-rose-dark inline-flex items-center gap-1.5">
          <Icon name="bell" size={14} />
          {sub.product_label}
        </span>
        <span className="flex items-center gap-2">
          <span className="text-[10px] bg-brand-rose text-white rounded px-2 py-0.5">
            已命中条件
          </span>
          <span
            className={`text-[10px] font-bold rounded px-2 py-0.5 ${
              NOTIFY_CLS[sub.notify_status_label] ?? 'bg-white text-muted'
            }`}
          >
            {sub.notify_status_label}
          </span>
        </span>
      </div>

      <ul className="space-y-1 mb-2">
        {sub.reasons.map((r) => (
          <li key={r} className="text-[11px] text-ink inline-flex items-start gap-1.5">
            <Icon name="target" size={11} className="text-brand-rose mt-0.5" />
            {r}
          </li>
        ))}
      </ul>

      <div className="text-[10px] text-muted">
        {sent && sub.notified_at && <span>已于 {fmt(sub.notified_at)} 推送。</span>}
        {!sent && <span>{sub.push_user_message}</span>}
        {sub.notify_error && <span className="block mt-0.5">通道返回：{sub.notify_error}</span>}
      </div>
    </div>
  );
}

function fmt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
