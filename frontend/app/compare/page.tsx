'use client';

import { useCallback, useEffect, useState } from 'react';
import { Icon, type IconName } from '@/components/Icons';
import {
  DataBasisBadge, EmptyNotice, OfferRow, OfflineNotice,
  RiskTags, SectionLink, VersionCard, VersionTag,
} from '@/components/Cards';
import {
  ApiError, getCompareResult, getSourceStatus,
  type CompareResult, type Offer, type SourceStatus,
} from '@/lib/api';
import { resolveQuery, setLastQuery, withQuery } from '@/lib/session';

const TABS: { key: 'price' | 'version' | 'risk' | 'benefit'; label: string; icon: IconName }[] = [
  { key: 'price', label: '价格维度', icon: 'money' },
  { key: 'version', label: '版本维度', icon: 'tag' },
  { key: 'risk', label: '风险维度', icon: 'risk' },
  { key: 'benefit', label: '优惠维度', icon: 'gift' },
];

export default function ComparePage() {
  const [q, setQ] = useState('');
  const [input, setInput] = useState('');
  const [data, setData] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; offline: boolean; requestId?: string } | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]['key']>('price');
  const [groupByVersion, setGroupByVersion] = useState(false);
  const [sources, setSources] = useState<SourceStatus | null>(null);

  const load = useCallback((query: string) => {
    setLoading(true);
    setError(null);
    getCompareResult(query)
      .then((d) => {
        setData(d);
        setLastQuery(d.product.key);
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
    setInput(initial);
    load(initial);
    getSourceStatus().then(setSources).catch(() => setSources(null));
  }, [load]);

  const submit = () => {
    const next = input.trim();
    if (!next) return;
    setQ(next);
    load(next);
  };

  const offers = data?.offers ?? [];

  // 按版本分组（不同版本不混排）
  const byVersion = offers.reduce<Record<string, Offer[]>>((acc, o) => {
    (acc[o.version] = acc[o.version] || []).push(o);
    return acc;
  }, {});

  // 风险维度汇总
  const riskSummary = (
    ['临期预警', '无专柜联保', '捆绑消费溢价', '第三方店铺售后风险'] as const
  ).map((t) => ({ tag: t, hits: offers.filter((o) => o.risk_tags.includes(t)) }));

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-baseline justify-between mb-2 gap-3 flex-wrap">
        <h1 className="text-2xl md:text-3xl font-bold">全网结构化比价看板</h1>
        {data && <DataBasisBadge basis={data.data_basis} sources={data.data_sources} />}
      </div>
      <p className="text-muted text-sm mb-4">
        聚合 <b className="text-ink">天猫 · 京东 · 拼多多 · 唯品会 · 保税仓</b> 5 大渠道，
        统一到手价、版本、风险、优惠四个维度的对比口径。
      </p>

      {/* 查询框 */}
      <div className="flex items-center gap-2 mb-5">
        <div className="flex-1 flex items-center gap-2 bg-white border border-line rounded-full px-4 h-10">
          <Icon name="search" size={15} className="text-muted" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="输入商品名，如「小棕瓶」「神仙水」「迪奥999」"
            className="flex-1 bg-transparent text-sm focus:outline-none"
            aria-label="商品查询"
          />
        </div>
        <button
          onClick={submit}
          className="h-10 px-5 rounded-full bg-brand-rose text-white text-sm font-bold hover:bg-brand-rose-dark transition-colors"
        >
          比价
        </button>
      </div>

      {loading && (
        <div className="space-y-2.5" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-xl bg-white border border-line animate-pulse" />
          ))}
        </div>
      )}

      {!loading && error && (
        <OfflineNotice
          title={error.offline ? '服务未连接' : '查询未完成'}
          message={error.message}
          detail={error.requestId ? `追踪号：${error.requestId}` : null}
          onRetry={() => load(q)}
        />
      )}

      {!loading && !error && data && (
        <>
          {/* 商品卡 + 关键结论 */}
          <div className="bg-white border border-line rounded-2xl p-5 mb-5">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <div className="text-xs text-gold font-bold tracking-wide">
                  {(data.product.brand_en || data.product.brand).toUpperCase()} · {data.product.brand}
                </div>
                <div className="text-lg font-bold mt-1">{data.product.name}</div>
                <div className="text-xs text-muted mt-1">
                  货号 {data.product.sku} · {data.product.spec} · {data.product.category} · 官方价 ¥
                  {data.product.list_price}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[11px] text-muted">当前最低到手价（{data.price_label}）</div>
                <div className="text-2xl font-extrabold text-brand-rose-dark">
                  ¥{data.lowest_price ?? '—'}
                </div>
                {data.lowest_label && (
                  <div className="text-[10px] text-muted mt-0.5">
                    来自 {data.lowest_label} · 共 {data.deal_count} 条报价
                  </div>
                )}
                {data.absolute_lowest_is_sponsored && data.absolute_lowest != null && (
                  <div className="text-[10px] text-gold mt-1">
                    另有赞助位报 ¥{data.absolute_lowest}（{data.absolute_lowest_channel}），
                    已标注且不参与排序
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 四维度 Tab */}
          <div className="flex gap-1.5 mb-4 overflow-x-auto">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`shrink-0 inline-flex items-center gap-1.5 text-xs md:text-sm font-medium px-3.5 py-2 rounded-lg transition-colors ${
                  tab === t.key
                    ? 'bg-brand-rose text-white'
                    : 'bg-white border border-line text-muted hover:text-ink'
                }`}
              >
                <Icon name={t.icon} size={13} />
                {t.label}
              </button>
            ))}
            {tab === 'price' && (
              <button
                onClick={() => setGroupByVersion((v) => !v)}
                className="ml-auto shrink-0 inline-flex items-center gap-1.5 text-xs font-medium px-3.5 py-2 rounded-lg bg-cream border border-line text-muted hover:text-ink"
              >
                <Icon name="layers" size={13} />
                {groupByVersion ? '按到手价排序' : '按版本分组'}
              </button>
            )}
          </div>

          {/* 价格维度 */}
          {tab === 'price' && (
            <div className="space-y-2.5">
              {!groupByVersion &&
                offers.map((o) => (
                  <OfferRow key={o.id} offer={o} productKey={data.product.key} />
                ))}

              {groupByVersion &&
                Object.entries(byVersion).map(([ver, list]) => {
                  const min = Math.min(...list.map((o) => o.price_cents));
                  return (
                    <div key={ver} className="mb-4">
                      <div className="flex items-center gap-2 mb-2 px-1">
                        <VersionTag version={list[0].version} origin={list[0].origin} />
                        <span className="text-[10px] bg-cream text-muted px-2 py-0.5 rounded">
                          {list.length} 个渠道
                        </span>
                        <span className="text-[11px] text-muted ml-auto">
                          组内最低{' '}
                          <b className="text-brand-rose-dark">¥{(min / 100).toFixed(2)}</b>
                        </span>
                      </div>
                      <div className="space-y-2.5">
                        {list.map((o) => (
                          <OfferRow
                            key={o.id}
                            offer={o}
                            productKey={data.product.key}
                            grouped={o.price_cents === min}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}

              <div className="text-[10px] text-muted border-l-2 border-gold pl-3 mt-3 leading-relaxed space-y-1">
                <p>价格为<b>行情参考价</b>，非锁定成交价；不同版本已单独成组，不做跨版本混比。</p>
                <p>排序按到手价升序，<b>赞助位不参与默认排序、永不置顶</b>。</p>
              </div>
            </div>
          )}

          {/* 版本维度 */}
          {tab === 'version' && (
            <div className="space-y-3">
              <p className="text-xs text-muted">
                v3.0 版本口径为 <b className="text-ink">国行 / 保税免税 / 海外版</b> 三类；
                日版、韩免、欧版作为「海外版」下的产地细分。仅做差异科普，不做真伪判定。
              </p>
              {data.versions.map((v) => (
                <VersionCard key={v.version} row={v} />
              ))}
            </div>
          )}

          {/* 风险维度 */}
          {tab === 'risk' && (
            <div className="space-y-2.5">
              {riskSummary.map((r) => (
                <div key={r.tag} className="bg-white border border-line rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <RiskTags tags={[r.tag]} />
                    <span className="text-[10px] text-muted ml-auto">
                      {r.hits.length} 个渠道命中
                    </span>
                  </div>
                  {r.hits.length > 0 ? (
                    <div className="text-[11px] text-ink space-y-1">
                      {r.hits.map((o) => (
                        <div key={o.id} className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold">{o.shop_name}</span>
                          <VersionTag version={o.version} origin={o.origin} />
                          <span className="text-brand-rose-dark font-bold">¥{o.price}</span>
                          {o.note && <span className="text-warn">{o.note}</span>}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[11px] text-muted">本次无渠道命中该风险标签。</div>
                  )}
                </div>
              ))}
              <p className="text-[10px] text-muted border-l-2 border-gold pl-3 leading-relaxed">
                本平台仅做风险筛查与提示，<b>不提供真伪鉴定服务、不承诺正品</b>；
                商品正品性与售后维权由跳转电商平台全权负责。
                临期判定口径为剩余保质期 ≤ 6 个月。
              </p>
            </div>
          )}

          {/* 优惠维度 */}
          {tab === 'benefit' && (
            <div className="bg-white border border-line rounded-2xl p-5 overflow-x-auto">
              <h2 className="text-sm font-bold text-brand-rose-dark mb-3 inline-flex items-center gap-1.5">
                <Icon name="gift" size={14} />
                优惠拆解 · 还原到手价
              </h2>
              <table className="w-full text-[11px] md:text-xs">
                <thead>
                  <tr className="text-muted border-b border-line">
                    <th className="text-left py-2 font-semibold">渠道 / 店铺</th>
                    <th className="text-left py-2 font-semibold">版本</th>
                    <th className="text-right py-2 font-semibold">官方价</th>
                    <th className="text-right py-2 font-semibold">优惠券</th>
                    <th className="text-right py-2 font-semibold">平台满减</th>
                    <th className="text-right py-2 font-semibold">赠品折算</th>
                    <th className="text-right py-2 font-semibold">平台补贴</th>
                    <th className="text-right py-2 font-semibold">优惠合计</th>
                    <th className="text-right py-2 font-semibold">到手价</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {offers.map((o) => (
                    <tr key={o.id}>
                      <td className="py-2.5">
                        <div className="font-semibold">{o.shop_name}</div>
                        <div className="text-[10px] text-muted">{o.channel}</div>
                      </td>
                      <td className="py-2.5">
                        <VersionTag version={o.version} origin={o.origin} />
                      </td>
                      <td className="py-2.5 text-right text-muted line-through">¥{o.list_price}</td>
                      <td className="py-2.5 text-right">¥{o.benefits.coupon || '—'}</td>
                      <td className="py-2.5 text-right">¥{o.benefits.platform_discount || '—'}</td>
                      <td className="py-2.5 text-right">¥{o.benefits.gift_value || '—'}</td>
                      <td className="py-2.5 text-right">¥{o.benefits.subsidy || '—'}</td>
                      <td className="py-2.5 text-right text-success font-bold">¥{o.benefit_total}</td>
                      <td className="py-2.5 text-right font-extrabold text-brand-rose-dark">
                        ¥{o.price}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[10px] text-muted mt-3 border-l-2 border-gold pl-3 leading-relaxed">
                赠品折算价值为按同款单件零售价折算的估算值，仅用于还原性价比；
                到手价与优惠以平台下单页实际结算为准。
              </p>
            </div>
          )}

          {/* 数据来源与渠道缺口（诚实性区块） */}
          {sources && (
            <div className="bg-white border border-line rounded-2xl p-5 mt-5">
              <h2 className="text-sm font-bold text-brand-rose-dark mb-3 inline-flex items-center gap-1.5">
                <Icon name="database" size={14} />
                数据来源与覆盖情况
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {sources.channels.map((c) => (
                  <div
                    key={c.channel}
                    className="flex items-center gap-2 text-[11px] bg-cream rounded-lg px-2.5 py-2"
                  >
                    {c.configured ? (
                      <Icon name="check" size={12} className="text-success" />
                    ) : (
                      <Icon name="unplugged" size={12} className="text-muted" />
                    )}
                    <span className="font-semibold">{c.channel}</span>
                    <span className="text-muted ml-auto">
                      {c.configured ? '已接入' : c.mode === 'seed' ? '演示数据' : '未接入'}
                    </span>
                  </div>
                ))}
              </div>
              {data.unavailable_channels.length > 0 && (
                <p className="text-[10px] text-warn mt-3">
                  本次未取到报价的渠道：{data.unavailable_channels.join('、')}
                </p>
              )}
              <p className="text-[10px] text-muted mt-3 leading-relaxed">{sources.note}</p>
            </div>
          )}

          {/* 关联模块入口 */}
          <div className="flex flex-wrap gap-2 mt-6">
            <SectionLink
              href={withQuery('/trend', data.product.key)}
              icon="chart"
              label="查看 90 天价格行情"
              primary
            />
            <SectionLink href={withQuery('/alert', data.product.key)} icon="bell" label="设置降价提醒" />
            <SectionLink href={withQuery('/', data.product.key)} icon="chat" label="回到 AI 对话" />
          </div>
        </>
      )}

      {!loading && !error && !data && (
        <EmptyNotice
          title="没有可用报价"
          message="该商品当前没有任何渠道报价，请换个商品或稍后重试。"
        />
      )}
    </div>
  );
}
