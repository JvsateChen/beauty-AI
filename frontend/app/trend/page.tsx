'use client';

import { useCallback, useEffect, useState } from 'react';
import { Icon, type IconName } from '@/components/Icons';
import { AdviceCard, DataBasisBadge, OfflineNotice, SectionLink } from '@/components/Cards';
import { TrendChart } from '@/components/TrendChart';
import {
  ApiError, getTrend,
  type Product, type Trend, type TrendShape,
} from '@/lib/api';
import { resolveQuery, setLastQuery, withQuery } from '@/lib/session';

type TrendResp = Trend & {
  query: string;
  product: Product;
  current_lowest: number;
  current_label: string | null;
};

const SHAPE_ICON: Record<TrendShape, IconName> = {
  先涨后降: 'trendDown',
  先降后涨: 'trendUp',
  持续下行: 'trendDown',
  持续上行: 'trendUp',
  区间震荡: 'layers',
  无数据: 'info',
};

const WINDOWS: (30 | 90 | 180)[] = [30, 90, 180];

export default function TrendPage() {
  const [q, setQ] = useState('');
  const [input, setInput] = useState('');
  const [days, setDays] = useState<30 | 90 | 180>(90);
  const [data, setData] = useState<TrendResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; offline: boolean; requestId?: string } | null>(null);

  const load = useCallback((query: string, window: 30 | 90 | 180) => {
    setLoading(true);
    setError(null);
    getTrend(query, window)
      .then((d) => {
        setData(d);
        setLastQuery(d.product.key);
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
    setInput(initial);
    load(initial, 90);
  }, [load]);

  const submit = () => {
    const next = input.trim();
    if (!next) return;
    setQ(next);
    load(next, days);
  };

  const t = data;

  const stats = t
    ? [
        { label: '当前到手价', value: `¥${t.current}`, cls: 'text-brand-rose-dark' },
        { label: '30 天最低', value: `¥${t.low_30d}`, cls: 'text-ink' },
        { label: `${t.days} 天最低`, value: `¥${t.low_90d}`, cls: 'text-success' },
        { label: `${t.days} 天最高`, value: `¥${t.high_90d}`, cls: 'text-danger' },
        { label: `${t.days} 天均价`, value: `¥${t.avg_90d}`, cls: 'text-gold' },
      ]
    : [];

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-baseline justify-between mb-2 gap-3 flex-wrap">
        <h1 className="text-2xl md:text-3xl font-bold">价格行情曲线</h1>
        {t && <DataBasisBadge basis={t.data_basis} />}
      </div>
      <p className="text-muted text-sm mb-4">
        价格涨跌走势，标注<b className="text-ink">真实</b>大促低点、区间均价与高点，
        自动识别走势形态并给出入手建议。
      </p>

      {/* 查询 + 窗口 */}
      <div className="flex items-center gap-2 mb-5 flex-wrap">
        <div className="flex-1 min-w-[200px] flex items-center gap-2 bg-white border border-line rounded-full px-4 h-10">
          <Icon name="search" size={15} className="text-muted" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="输入商品名，如「小棕瓶」"
            className="flex-1 bg-transparent text-sm focus:outline-none"
            aria-label="商品查询"
          />
        </div>
        <div className="flex gap-1 bg-white border border-line rounded-full p-1">
          {WINDOWS.map((d) => (
            <button
              key={d}
              onClick={() => {
                setDays(d);
                if (q) load(q, d);
              }}
              className={`text-xs font-medium px-3 py-1.5 rounded-full transition-colors ${
                days === d ? 'bg-brand-rose text-white' : 'text-muted hover:text-ink'
              }`}
            >
              {d} 天
            </button>
          ))}
        </div>
        <button
          onClick={submit}
          className="h-10 px-5 rounded-full bg-brand-rose text-white text-sm font-bold hover:bg-brand-rose-dark transition-colors"
        >
          查询
        </button>
      </div>

      {loading && (
        <div className="space-y-3" aria-busy="true">
          <div className="h-20 rounded-2xl bg-white border border-line animate-pulse" />
          <div className="h-64 rounded-2xl bg-white border border-line animate-pulse" />
        </div>
      )}

      {!loading && error && (
        <OfflineNotice
          title={error.offline ? '服务未连接' : '查询未完成'}
          message={error.message}
          detail={error.requestId ? `追踪号：${error.requestId}` : undefined}
          onRetry={() => load(q, days)}
        />
      )}

      {!loading && !error && t && (
        <>
          <div className="bg-white border border-line rounded-2xl p-5 mb-4">
            <div className="text-xs text-gold font-bold tracking-wide">
              {(t.product.brand_en || t.product.brand).toUpperCase()} · {t.product.brand}
            </div>
            <div className="text-lg font-bold mt-1">{t.product.name}</div>
            <div className="text-xs text-muted mt-1">
              货号 {t.product.sku} · {t.product.spec} · 官方价 ¥{t.product.list_price}
              {t.current_label && (
                <>
                  {' · '}
                  当前最低来自 <b className="text-ink">{t.current_label}</b>
                </>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 mb-4">
            {stats.map((s) => (
              <div key={s.label} className="bg-white border border-line rounded-xl px-3.5 py-3">
                <div className="text-[10px] text-muted">{s.label}</div>
                <div className={`text-lg font-extrabold mt-0.5 ${s.cls}`}>{s.value}</div>
              </div>
            ))}
          </div>

          <div className="mb-4">
            <TrendChart trend={t} />
          </div>

          {/* 形态识别（真实算法结论，可追溯） */}
          <div className="bg-white border border-line rounded-xl p-4 mb-4">
            <div className="flex items-center gap-2 flex-wrap">
              <Icon name={SHAPE_ICON[t.shape]} size={15} className="text-brand-rose-dark" />
              <span className="text-sm font-bold text-brand-rose-dark">走势形态</span>
              <span className="text-sm font-extrabold">{t.shape}</span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  t.real_low_confirmed ? 'bg-success/10 text-success' : 'bg-cream text-muted'
                }`}
                title={
                  t.real_low_confirmed
                    ? '区间最低点之后已出现 ≥1% 的反弹，低点得到确认'
                    : '区间最低点尚未被后续反弹确认，或低点就在近期'
                }
              >
                {t.real_low_confirmed ? '低点已确认' : '低点未确认'}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-[11px]">
              <div>
                <div className="text-muted">区间峰值</div>
                <div className="font-bold">
                  {t.peak ? `¥${t.peak.price}` : '—'}
                </div>
              </div>
              <div>
                <div className="text-muted">较峰值回落</div>
                <div className="font-bold">{t.fall_pct_from_peak}%</div>
              </div>
              <div>
                <div className="text-muted">低点后反弹</div>
                <div className="font-bold">{t.rebound_after_low}%</div>
              </div>
              <div>
                <div className="text-muted">低点位置</div>
                <div className="font-bold">
                  {t.trough ? `区间第 ${(t.trough.index ?? 0) + 1} 天` : '—'}
                </div>
              </div>
            </div>
          </div>

          <div className="mb-4">
            <AdviceCard
              level={t.level}
              advice={t.advice}
              reason={t.advice_reason}
              extra={
                <p className="text-[10px] text-muted mt-2">
                  档位判定口径：现价 ≤ {t.days} 天最低 × 1.03 为低位；≥ {t.days} 天最高 × 0.97 为高位；
                  其余按与均价比较给中位建议。
                </p>
              }
            />
          </div>

          {t.promo_points.length > 0 ? (
            <div className="bg-white border border-line rounded-2xl p-5 mb-4">
              <h2 className="text-sm font-bold text-brand-rose-dark mb-1 inline-flex items-center gap-1.5">
                <Icon name="target" size={14} />
                区间价格低点
              </h2>
              <p className="text-[10px] text-muted mb-3">
                低点来自实际数据（局部极小且显著低于周边）；仅当日期落在真实大促日历窗内才标注大促名称。
              </p>
              <div className="divide-y divide-line">
                {t.promo_points.map((p) => (
                  <div
                    key={p.date}
                    className="flex items-center justify-between py-2 text-xs gap-3"
                  >
                    <span className="text-muted">{p.date}</span>
                    <span
                      className={
                        p.event && p.event !== '价格低点'
                          ? 'text-gold font-semibold'
                          : 'text-muted'
                      }
                    >
                      {p.event}
                    </span>
                    <span className="font-bold text-brand-rose-dark">¥{p.price}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-white border border-dashed border-line rounded-2xl p-5 mb-4 text-center text-xs text-muted">
              区间内未识别到显著价格低点。
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <SectionLink
              href={withQuery('/alert', t.product.key)}
              icon="bell"
              label="按此行情设置降价提醒"
              primary
            />
            <SectionLink href={withQuery('/compare', t.product.key)} icon="scale" label="查看比价看板" />
          </div>
        </>
      )}
    </div>
  );
}
