'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Icon, type IconName } from '@/components/Icons';
import { DataBasisBadge } from '@/components/Cards';
import {
  ApiError, getClicksSummary, getSession, getSourceStatus,
  type ClicksSummary, type SessionInfo, type SourceStatus,
} from '@/lib/api';

const COMPLIANCE: { icon: IconName; title: string; body: string }[] = [
  {
    icon: 'shield',
    title: '我们不提供真伪鉴定',
    body: '平台只做版本差异科普、临期风险筛查与渠道优劣提示，不判定真伪、不承诺正品。商品正品性与售后维权由跳转电商平台全权负责。',
  },
  {
    icon: 'scale',
    title: '排序由到手价决定',
    body: '佣金与赞助位不参与默认排序、永不置顶。付费推广位强制标注「赞助/佣金」。若赞助位价格更低，其真实价格仍会展示，但「最低到手价」徽章只授予非赞助位。',
  },
  {
    icon: 'database',
    title: '数据来源逐条可辨',
    body: '每条报价都带数据来源标注：真实渠道行情 / 演示数据集 / 历史快照。接入联盟凭据前会明确显示为演示数据集，不会伪装成实时行情。',
  },
  {
    icon: 'info',
    title: '价格为行情参考价',
    body: '所有价格均为聚合的行情参考价，非锁定成交价，不构成交易要约。实际结算以平台下单页为准。',
  },
  {
    icon: 'link',
    title: '跳转链接真实可用',
    body: '所有「去购买」都指向真实渠道页面。未启用佣金归因时走该渠道官方页面，并如实标注，不会出现空链或死链。',
  },
  {
    icon: 'clock',
    title: '隐私最小化',
    body: '不需要注册即可使用对话、比价与行情功能。设备标识为随机串，不含设备指纹信息；降价订阅只与你的匿名会话绑定。',
  },
];

export default function MyPage() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [sources, setSources] = useState<SourceStatus | null>(null);
  const [clicks, setClicks] = useState<ClicksSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    Promise.allSettled([getSession(), getSourceStatus(), getClicksSummary()]).then((rs) => {
      const [s, src, clk] = rs;
      if (s.status === 'fulfilled') setSession(s.value);
      else {
        const e = s.reason as ApiError;
        setError(e?.message ?? '无法连接服务端');
      }
      if (src.status === 'fulfilled') setSources(src.value);
      if (clk.status === 'fulfilled') setClicks(clk.value);
      setBusy(false);
    });
  }, []);

  const configured = sources?.configured_channels ?? [];
  const overallBasis = configured.length === 0 ? 'seed' : configured.length >= 5 ? 'live' : 'mixed';

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl md:text-3xl font-bold mb-6">我的</h1>

      {/* 会话 */}
      <div className="bg-white border border-line rounded-2xl p-6 mb-5">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-14 h-14 rounded-full bg-gradient-to-br from-brand-rose to-brand-rose-dark flex items-center justify-center">
            <Icon name="user" size={24} className="text-white" />
          </div>
          <div className="min-w-0">
            <div className="text-lg font-bold">
              {busy ? '读取中…' : session ? '匿名设备会话' : '会话未建立'}
            </div>
            <div className="text-xs text-muted mt-1">
              {session
                ? `订阅与点击记录已绑定到该会话${
                    session.push_reachable ? '，微信推送可达' : '，微信推送暂不可达'
                  }`
                : session === null && !busy
                  ? error ?? '请稍后重试'
                  : '正在建立会话'}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5 mb-4">
          <Field label="会话 ID" value={session?.session_id ?? '—'} mono />
          <Field label="微信绑定" value={session?.wechat_bound ? '已绑定' : '未绑定'} />
          <Field label="微信推送可达" value={session?.push_reachable ? '可达' : '不可达'} />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            disabled
            title="微信登录需配置公众号 / 小程序凭据后启用"
            className="inline-flex items-center gap-1.5 bg-cream text-muted border border-line rounded-full px-4 py-2 text-xs font-bold cursor-not-allowed"
          >
            <Icon name="unplugged" size={13} />
            微信一键登录（待接入凭据）
          </button>
          <Link
            href="/alert"
            className="inline-flex items-center gap-1.5 bg-brand-rose text-white rounded-full px-4 py-2 text-xs font-bold hover:bg-brand-rose-dark transition-colors"
          >
            <Icon name="bell" size={13} />
            管理降价订阅
          </Link>
        </div>
        <p className="text-[10px] text-muted mt-2 leading-relaxed">
          一期为 H5 优先：无需登录即可使用全部只读能力；登录能力（微信 OAuth）需运营侧
          配置 AppID / AppSecret 后启用，当前不伪造登录态。
        </p>
      </div>

      {/* 跳转记录 */}
      {clicks && (
        <div className="bg-white border border-line rounded-2xl p-5 mb-5">
          <h2 className="text-sm font-bold text-brand-rose-dark mb-3 inline-flex items-center gap-1.5">
            <Icon name="external" size={14} />
            我的跳转记录
          </h2>
          <div className="grid grid-cols-2 gap-2.5 mb-3">
            <Field label="累计跳转次数" value={String(clicks.total)} />
            <Field label="已带归因标识" value={String(clicks.with_attribution)} />
          </div>
          {clicks.by_channel.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {clicks.by_channel.map((c) => (
                <span
                  key={c.channel}
                  className="text-[10px] bg-cream text-muted rounded px-2 py-1"
                >
                  {c.channel} · {c.count}
                </span>
              ))}
            </div>
          )}
          <p className="text-[10px] text-muted mt-3 leading-relaxed">{clicks.note}</p>
        </div>
      )}

      {/* 数据源现状 */}
      <div className="bg-white border border-line rounded-2xl p-5 mb-5">
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <h2 className="text-sm font-bold text-brand-rose-dark inline-flex items-center gap-1.5">
            <Icon name="database" size={14} />
            数据源现状
          </h2>
          <DataBasisBadge basis={overallBasis} sources={configured} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3">
          {(sources?.channels ?? []).map((c) => (
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
          {!sources && (
            <div className="text-[11px] text-muted col-span-2">
              {busy ? '读取中…' : '数据源状态暂不可用'}
            </div>
          )}
        </div>
        <p className="text-[10px] text-muted leading-relaxed">
          {sources?.note ?? '接入各渠道联盟凭据后，将 DATA_MODE 置为 hybrid / live 即切换为真实行情。'}
        </p>
      </div>

      {/* 合规与透明度 */}
      <div className="mb-5">
        <h2 className="text-sm font-bold text-brand-rose-dark mb-3">合规与透明度</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          {COMPLIANCE.map((c) => (
            <div key={c.title} className="bg-white border border-line rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1.5">
                <Icon name={c.icon} size={14} className="text-brand-rose-dark" />
                <span className="text-xs font-bold text-ink">{c.title}</span>
              </div>
              <p className="text-[11px] text-muted leading-relaxed">{c.body}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 会员（如实标注状态） */}
      <div className="bg-brand-rose-soft border border-brand-rose rounded-2xl p-5 mb-5">
        <div className="flex items-end justify-between mb-2 flex-wrap gap-2">
          <div>
            <div className="text-sm font-bold text-brand-rose-dark">采选会员</div>
            <div className="text-[11px] text-muted mt-0.5">无广告 · 底价预警 · 专属选购方案</div>
          </div>
          <div className="text-right">
            <span className="text-2xl font-extrabold text-brand-rose-dark">¥9.9</span>
            <span className="text-[11px] text-muted"> / 月</span>
            <span className="text-[11px] text-muted ml-2">或 ¥88 / 年</span>
          </div>
        </div>
        <button
          disabled
          className="w-full bg-cream text-muted border border-line rounded-full py-2.5 font-bold text-sm cursor-not-allowed mt-2"
          title="支付能力待接入"
        >
          会员能力开发中（当前全部功能免费使用）
        </button>
        <p className="text-[10px] text-muted mt-2 leading-relaxed">
          平台主要收入来自联盟 CPS 佣金；会员为可选增值。佣金不影响排序与结论，详见上方「排序由到手价决定」。
        </p>
      </div>

      <p className="text-[10px] text-muted border-l-2 border-gold pl-3 leading-relaxed">
        本平台仅聚合公开价格、货源及行情信息，不提供真伪鉴定服务，不承诺正品；
        商品正品性、售后维权由跳转电商平台全权负责。所有价格为行情参考价，非锁定成交价。
        平台不承接商品履约与售后。
      </p>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-cream rounded-lg px-3 py-2">
      <div className="text-[10px] text-muted">{label}</div>
      <div className={`text-[11px] font-semibold text-ink truncate ${mono ? 'font-mono' : ''}`} title={value}>
        {value}
      </div>
    </div>
  );
}
