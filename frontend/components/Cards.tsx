'use client';

import Link from 'next/link';
import { Icon, type IconName } from '@/components/Icons';
import { trackClick, goUrl, type Benefits, type DataBasis, type Offer, type RiskTag, type Version, type VersionRow } from '@/lib/api';

/** 风险标签配色（全站四个标签） */
export const RISK_TAG_CLS: Record<RiskTag, string> = {
  临期预警: 'bg-warn/10 text-warn',
  无专柜联保: 'bg-danger/10 text-danger',
  捆绑消费溢价: 'bg-gold-light text-gold',
  第三方店铺售后风险: 'bg-danger/10 text-danger',
};

const RISK_TAG_ICON: Record<RiskTag, IconName> = {
  临期预警: 'clock',
  无专柜联保: 'shield',
  捆绑消费溢价: 'gift',
  第三方店铺售后风险: 'risk',
};

export const VERSION_CLS: Record<Version, string> = {
  国行: 'bg-success/10 text-success',
  保税免税: 'bg-brand-rose-soft text-brand-rose-dark',
  海外版: 'bg-warn/10 text-warn',
};

export const LEVEL_CLS: Record<string, string> = {
  低位: 'bg-success/10 text-success',
  中位: 'bg-cream text-muted',
  高位: 'bg-danger/10 text-danger',
};

/** 数据来源徽标 —— 让「真实行情」与「演示数据集」一眼可辨 */
export function DataBasisBadge({ basis, sources }: { basis: DataBasis; sources?: string[] }) {
  const map: Record<DataBasis, { label: string; cls: string; icon: IconName; title: string }> = {
    live: {
      label: '真实渠道行情',
      cls: 'bg-success/10 text-success',
      icon: 'database',
      title: `数据来自已接入的联盟 / 渠道接口${sources?.length ? `：${sources.join('、')}` : ''}`,
    },
    mixed: {
      label: '混合来源',
      cls: 'bg-warn/10 text-warn',
      icon: 'layers',
      title: '部分渠道为真实数据，缺失渠道由演示数据集补齐，逐条已标注',
    },
    seed: {
      label: '演示数据集',
      cls: 'bg-warn/10 text-warn',
      icon: 'info',
      title: '内置演示数据，用于验证功能链路；接入联盟凭据后自动切换为真实行情',
    },
    snapshot: {
      label: '历史快照',
      cls: 'bg-brand-rose-soft text-brand-rose-dark',
      icon: 'clock',
      title: '基于本平台累积的真实价格快照',
    },
  };
  const m = map[basis] ?? map.seed;
  return (
    <span
      title={m.title}
      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded ${m.cls}`}
    >
      <Icon name={m.icon} size={11} />
      {m.label}
    </span>
  );
}

export function RiskTags({ tags }: { tags: RiskTag[] }) {
  if (!tags || tags.length === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-muted">
        <Icon name="check" size={11} />
        无风险标签
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap gap-1">
      {tags.map((t) => (
        <span
          key={t}
          className={`inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded ${RISK_TAG_CLS[t]}`}
        >
          <Icon name={RISK_TAG_ICON[t]} size={10} />
          {t}
        </span>
      ))}
    </span>
  );
}

export function VersionTag({ version, origin }: { version: Version; origin?: string | null }) {
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${VERSION_CLS[version]}`}>
      {version}
      {origin ? `（${origin}）` : ''}
    </span>
  );
}

/** 优惠拆解 —— 还原到手价的四要素 */
export function BenefitBreakdown({ benefits, total }: { benefits: Benefits; total: number }) {
  const items: [string, number][] = [
    ['优惠券', benefits.coupon],
    ['平台满减', benefits.platform_discount],
    ['赠品折算', benefits.gift_value],
    ['平台补贴', benefits.subsidy],
  ];
  const shown = items.filter(([, v]) => v > 0);
  if (shown.length === 0) {
    return <span className="text-[10px] text-muted">无额外优惠</span>;
  }
  return (
    <span className="text-[10px] text-muted">
      {shown.map(([k, v], i) => (
        <span key={k}>
          {i > 0 && ' + '}
          {k} ¥{v}
        </span>
      ))}
      <span className="text-success font-bold"> = 共省 ¥{total}</span>
    </span>
  );
}

/**
 * M5 跳转按钮。
 *
 * 关键修复：旧实现是 `href={offer.cps_url || '#'}`，而 cps_url 从不产出
 * → 所有「去购买」都是死链。现在：
 *   · 走后端 /api/offer/go 由服务端记点击后 302，归因可靠且换链不用改前端
 *   · 用 <a target="_blank" rel="noopener noreferrer nofollow sponsored">，
 *     赞助位显式带 sponsored 属性（对搜索引擎也是合规声明）
 *   · 未启用佣金归因时（cps_tracked=false）如实提示，不假装有佣金
 */
export function BuyButton({ offer, productKey }: { offer: Offer; productKey?: string }) {
  const href = goUrl(productKey ?? offer.id, offer.id, offer.sub_id);
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <a
        href={href}
        target="_blank"
        rel={offer.sponsored ? 'noopener noreferrer nofollow sponsored' : 'noopener noreferrer nofollow'}
        onClick={() =>
          trackClick({
            product_key: productKey ?? null,
            offer_id: offer.id,
            channel: offer.channel,
            shop_name: offer.shop_name,
            version: offer.version,
            price: offer.price,
            sub_id: offer.sub_id,
            cps_url: offer.cps_url,
          })
        }
        className="inline-flex items-center gap-1 text-xs font-bold bg-brand-rose text-white rounded-full px-3.5 py-1.5 hover:bg-brand-rose-dark transition-colors"
        title="跳转到该渠道官方页面（链接由服务端下发）"
      >
        去购买
        <Icon name="external" size={12} />
      </a>
      <span className="text-[9px] text-muted" title={offer.cps_tracked ? '已启用佣金归因' : '当前为该渠道官方页面，未启用佣金归因'}>
        {offer.cps_tracked ? '已启用佣金归因' : '官方页面 · 未启用佣金'}
      </span>
    </span>
  );
}

/** M2 比价行 —— 到手价 · 版本 · 风险 · 优惠 · 跳转 */
export function OfferRow({
  offer,
  productKey,
  grouped,
}: {
  offer: Offer;
  productKey?: string;
  /** 按版本分组展示时，组内最低用说明文字而非徽章，避免与全场「最低到手价」混淆 */
  grouped?: boolean;
}) {
  const isLowest = Boolean(offer.is_lowest);
  return (
    <div
      className={`bg-white border rounded-xl p-4 transition-colors ${
        isLowest ? 'border-brand-rose border-2 bg-brand-rose-soft/40' : 'border-line hover:border-brand-rose/40'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-lg bg-gold-light flex items-center justify-center text-[10px] font-bold text-gold shrink-0">
          {offer.channel.slice(0, 2)}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold">{offer.shop_name}</span>
            {isLowest && (
              <span className="inline-flex items-center gap-1 text-[10px] bg-brand-rose text-white rounded px-1.5 py-0.5">
                <Icon name="medal" size={10} />
                {grouped ? '组内最低' : '最低到手价'}
              </span>
            )}
            {offer.sponsored && (
              <span
                className="inline-flex items-center gap-1 text-[10px] bg-gold-light text-gold rounded px-1.5 py-0.5"
                title="付费推广位：已强制标注，且不参与默认排序、不影响名次"
              >
                <Icon name="tag" size={10} />
                赞助/佣金
              </span>
            )}
            <VersionTag version={offer.version} origin={offer.origin} />
          </div>
          <div className="text-[11px] text-muted mt-1 flex items-center gap-2 flex-wrap">
            <span>
              {offer.channel} · {offer.shop_type}
            </span>
            {offer.shelf_life_months != null && <span>剩余效期约 {offer.shelf_life_months} 个月</span>}
            {offer.warranty && <span>{offer.warranty}</span>}
          </div>
          <div className="mt-2">
            <RiskTags tags={offer.risk_tags} />
          </div>
          {offer.note && <div className="text-[10px] text-warn mt-1.5">{offer.note}</div>}
          {offer.price_consistent === false && (
            <div className="text-[10px] text-warn mt-1.5 inline-flex items-center gap-1">
              <Icon name="warn" size={10} />
              该渠道未完整拆解优惠项，到手价以平台结算为准
            </div>
          )}
        </div>

        <div className="text-right shrink-0">
          <div className="text-lg font-extrabold text-brand-rose-dark">¥{offer.price}</div>
          <div className="text-[10px] text-muted line-through">¥{offer.list_price}</div>
          <div className="text-[10px] text-success font-bold">省 {offer.drop_pct}%</div>
        </div>

        <div className="shrink-0 self-center">
          <BuyButton offer={offer} productKey={productKey} />
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-line/70 flex items-center justify-between gap-3 flex-wrap">
        <BenefitBreakdown benefits={offer.benefits} total={offer.benefit_total} />
        <span className="text-[10px] text-muted">
          {offer.history_30d_low != null && <>30天最低 ¥{offer.history_30d_low} · </>}
          {offer.history_90d_low != null && <>90天最低 ¥{offer.history_90d_low}</>}
          {offer.price_level && (
            <span className={`ml-2 font-bold px-1.5 py-0.5 rounded ${LEVEL_CLS[offer.price_level]}`}>
              {offer.price_level}
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

/** 版本维度对比卡 */
export function VersionCard({ row }: { row: VersionRow }) {
  return (
    <div
      className={`bg-white border rounded-xl p-4 ${
        row.available ? 'border-line' : 'border-dashed border-line opacity-70'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <VersionTag version={row.version} />
          {row.origins.length > 0 && (
            <span className="text-[10px] text-muted">产地细分：{row.origins.join(' / ')}</span>
          )}
          {!row.available && <span className="text-[10px] text-muted">本次无报价</span>}
        </div>
        {row.available && (
          <div className="text-right">
            <span className="text-sm font-extrabold text-brand-rose-dark">¥{row.lowest_price}</span>
            <span className="text-[10px] text-muted ml-2">{row.price_gap_note}</span>
          </div>
        )}
      </div>
      <div className="mt-2 mb-2">
        <RiskTags tags={row.risk_tags} />
      </div>
      <dl className="text-[11px] space-y-1.5">
        {(
          [
            ['成分差异', row.ingredient_diff],
            ['保质期标准', row.shelf_life],
            ['国内联保', row.warranty],
            ['适配人群', row.fit],
          ] as [string, string][]
        ).map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <dt className="text-muted shrink-0 w-20">{k}</dt>
            <dd className="text-ink">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** 入手建议卡（M3） */
export function AdviceCard({
  level,
  advice,
  reason,
  extra,
}: {
  level: string;
  advice: string;
  reason: string;
  extra?: React.ReactNode;
}) {
  const iconName: IconName = advice === '低位囤货' ? 'trendDown' : advice === '立即入手' ? 'check' : 'clock';
  return (
    <div className="bg-brand-rose-soft border border-brand-rose rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon name={iconName} size={16} className="text-brand-rose-dark" />
        <span className="text-sm font-bold text-brand-rose-dark">入手建议</span>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${LEVEL_CLS[level]}`}>{level}</span>
        <span className="text-sm font-extrabold text-brand-rose-dark ml-auto">{advice}</span>
      </div>
      <p className="text-xs text-ink leading-relaxed">{reason}</p>
      {extra}
      <p className="text-[10px] text-muted mt-2">
        以上为行情参考价，非锁定成交价；实际以下单页为准。
      </p>
    </div>
  );
}

/**
 * 未连接状态占位。
 *
 * 这是「不伪造数据」原则的可视化落地：后端不可用时，页面显示这个卡片，
 * **不显示任何价格数字** —— 因为一个比价产品显示假价格比显示「加载失败」更糟。
 */
export function OfflineNotice({
  title = '服务未连接',
  message,
  onRetry,
  detail,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  detail?: string | null;
}) {
  return (
    <div className="bg-white border border-dashed border-danger/40 rounded-2xl p-8 text-center">
      <div className="w-11 h-11 rounded-full bg-danger/10 text-danger flex items-center justify-center mx-auto mb-3">
        <Icon name="unplugged" size={20} />
      </div>
      <div className="text-sm font-bold text-ink">{title}</div>
      <p className="text-xs text-muted mt-2 max-w-md mx-auto leading-relaxed">{message}</p>
      {detail && (
        <p className="text-[10px] text-muted/80 mt-2 font-mono break-all">{detail}</p>
      )}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold bg-brand-rose text-white rounded-full px-4 py-2 hover:bg-brand-rose-dark transition-colors"
        >
          <Icon name="refresh" size={13} />
          重新加载
        </button>
      )}
      <p className="text-[10px] text-muted mt-4">
        为不误导决策，本页在服务不可用时不会展示任何缓存或示例价格。
      </p>
    </div>
  );
}

/** 空态占位（查得到商品但确实没有数据时用） */
export function EmptyNotice({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-dashed border-line rounded-2xl p-8 text-center">
      <div className="w-11 h-11 rounded-full bg-cream text-muted flex items-center justify-center mx-auto mb-3">
        <Icon name="search" size={19} />
      </div>
      <div className="text-sm font-bold text-ink">{title}</div>
      <p className="text-xs text-muted mt-2 max-w-md mx-auto leading-relaxed">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function SectionLink({
  href,
  icon,
  label,
  primary,
}: {
  href: string;
  icon: IconName;
  label: string;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={
        primary
          ? 'inline-flex items-center gap-1.5 text-[11px] font-bold bg-brand-rose text-white rounded-full px-3.5 py-2 hover:bg-brand-rose-dark transition-colors'
          : 'inline-flex items-center gap-1.5 text-[11px] font-bold bg-white border border-brand-rose text-brand-rose-dark rounded-full px-3.5 py-2 hover:bg-brand-rose-soft transition-colors'
      }
    >
      <Icon name={icon} size={12} />
      {label}
    </Link>
  );
}
