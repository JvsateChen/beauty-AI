'use client';

import { useEffect, useRef, useState } from 'react';
import { Icon, type IconName } from '@/components/Icons';
import { DataBasisBadge, OfflineNotice, SectionLink } from '@/components/Cards';
import {
  ApiError,
  getSuggestions,
  postChat,
  type ChatResponse,
  type DialogueSection,
  type Product,
} from '@/lib/api';
import { setLastQuery, withQuery } from '@/lib/session';

const SECTION_ICON: Record<string, IconName> = {
  fit: 'target',
  price: 'scale',
  version: 'tag',
  advice: 'chart',
  risk: 'risk',
};

interface Msg {
  role: 'u' | 'a';
  text?: string;
  data?: ChatResponse;
}

const FALLBACK_EXAMPLES = [
  '预算800，混油皮，抗初老，推荐一款大牌精华，帮我全网比价',
  '兰蔻小黑瓶50ml，看近3个月降价记录，对比天猫和保税仓价格',
  '想买SK-II神仙水，怎么区分国行和免税版，哪个性价比更高',
  '迪奥999，哪家渠道最便宜，有没有临期风险',
];

export default function HomePage() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [thinking, setThinking] = useState(false);
  const [examples, setExamples] = useState<string[]>(FALLBACK_EXAMPLES);
  const [products, setProducts] = useState<Product[]>([]);
  const [modules, setModules] = useState<{ key: string; title: string }[]>([
    { key: 'fit', title: '适配推荐' },
    { key: 'price', title: '全网比价' },
    { key: 'version', title: '版本差异' },
    { key: 'advice', title: '入手建议' },
    { key: 'risk', title: '风险提示' },
  ]);
  const [bootError, setBootError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getSuggestions()
      .then((s) => {
        setExamples(s.examples?.length ? s.examples : FALLBACK_EXAMPLES);
        setProducts(s.products ?? []);
        setModules(s.modules?.length ? s.modules : []);
        setBootError(null);
      })
      .catch((e: unknown) =>
        setBootError(e instanceof ApiError ? e.message : '无法加载引导数据'),
      );
  }, []);

  useEffect(() => {
    boxRef.current?.scrollTo({ top: boxRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, thinking]);

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || thinking) return;
    setMessages((m) => [...m, { role: 'u', text: t }]);
    setInput('');
    setThinking(true);
    try {
      const res = await postChat(t);
      if (res.product_key) setLastQuery(res.product_key);
      setMessages((m) => [...m, { role: 'a', data: res }]);
    } catch (err) {
      const e = err as ApiError;
      setMessages((m) => [
        ...m,
        {
          role: 'a',
          data: {
            intent: {
              budget: null, skin_type: null, needs: [], product: null,
              product_alias: null, requested_spec: null, channels_pref: [],
              asks_version: false, asks_price: false,
              unmatched_reason: e?.message ?? '请求失败',
            },
            sections: [
              {
                key: 'risk',
                title: '请求未完成',
                text:
                  e?.offline
                    ? '无法连接服务端，本次没有取到任何行情数据。为避免误导，这里不展示任何示例价格。'
                    : e?.message ?? '服务暂时不可用，请稍后重试。',
              },
            ],
            reply: '',
            product_key: null,
            product_label: null,
            suggestions: [],
            data_basis: null,
            data_sources: [],
            unavailable_channels: [],
            note: e?.requestId ? `追踪号：${e.requestId}` : null,
            disclaimer: '',
            session_id: null,
          },
        },
      ]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-ink">
          AI 对话选型 · 多平台比价 · 货源风险筛查
        </h1>
        <p className="text-muted mt-2 text-sm md:text-base">
          一句话说清预算、肤质、诉求，AI 帮你选品、跨 5 大渠道比价、区分版本差异、判定入手时机，
          并筛查临期与售后风险。
        </p>
      </div>

      {/* 已收录商品（可点选，避免用户不知道该问什么） */}
      {products.length > 0 && (
        <div className="mb-4">
          <div className="text-[11px] text-muted mb-1.5">已收录商品（点击直接问价）</div>
          <div className="flex flex-wrap gap-1.5">
            {products.map((p) => (
              <button
                key={p.key}
                onClick={() => send(`${p.brand} ${p.name} ${p.spec} 帮我比价`)}
                className="text-[11px] bg-white border border-line rounded-lg px-2.5 py-1.5 hover:border-brand-rose hover:text-brand-rose-dark transition-colors"
                title={`${p.brand} ${p.name} · ${p.spec} · 官方价 ¥${p.list_price}`}
              >
                {p.key}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-6">
        {examples.map((s) => (
          <button
            key={s}
            onClick={() => send(s)}
            className="text-xs md:text-sm bg-white border border-brand-rose text-brand-rose-dark rounded-full px-3 py-1.5 hover:bg-brand-rose-soft transition-colors text-left"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-2xl border border-line p-4 md:p-6 min-h-[420px] md:min-h-[520px] flex flex-col">
        <div ref={boxRef} className="flex-1 space-y-4 overflow-y-auto">
          {/* 欢迎语 + 输出结构说明 */}
          <div className="flex justify-start">
            <div className="max-w-[92%] bg-cream border border-line rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="text-xs text-brand-rose-dark font-bold mb-1">采选参谋</div>
              <div className="text-sm">
                嗨，想买哪款大牌护肤 / 彩妆？说一下<b>预算、肤质、诉求</b>，我按固定结构给你结论：
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 mt-3">
                {modules.map((m) => (
                  <div
                    key={m.key}
                    className="text-[11px] bg-white border border-line rounded-lg px-2.5 py-1.5 inline-flex items-center gap-1.5"
                  >
                    <Icon
                      name={SECTION_ICON[m.key] ?? 'info'}
                      size={12}
                      className="text-brand-rose-dark"
                    />
                    <b className="text-brand-rose-dark">{m.title}</b>
                  </div>
                ))}
              </div>
              <div className="text-[10px] text-muted mt-3 leading-relaxed">
                我只做版本差异科普与风险筛查，<b>不做真伪鉴定、不承诺正品</b>；
                给出的都是「行情参考价」。每次回答都会标明数据来源。
              </div>
            </div>
          </div>

          {messages.map((m, i) => {
            if (m.role === 'u') {
              return (
                <div key={`u-${i}`} className="flex justify-end">
                  <div className="max-w-[85%] text-sm px-4 py-2.5 rounded-2xl bg-brand-rose text-white rounded-br-sm">
                    {m.text}
                  </div>
                </div>
              );
            }
            const d = m.data;
            if (!d) return null;
            return (
              <div key={`a-${i}`} className="flex justify-start">
                <div className="max-w-[95%] w-full">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className="text-xs text-brand-rose-dark font-bold">采选参谋</span>
                    {d.data_basis && (
                      <DataBasisBadge basis={d.data_basis} sources={d.data_sources} />
                    )}
                    {d.intent.asks_version && (
                      <span className="text-[10px] text-muted inline-flex items-center gap-1">
                        <Icon name="tag" size={10} />
                        版本问题
                      </span>
                    )}
                    {d.intent.unmatched_reason && (
                      <span className="text-[10px] text-warn inline-flex items-center gap-1">
                        <Icon name="info" size={10} />
                        {d.intent.unmatched_reason}
                      </span>
                    )}
                  </div>

                  <div className="space-y-2">
                    {d.sections.map((s: DialogueSection) => (
                      <div key={s.key} className="bg-white border border-line rounded-xl p-3.5">
                        <div className="flex items-center gap-2 mb-1.5">
                          <Icon
                            name={SECTION_ICON[s.key] ?? 'info'}
                            size={13}
                            className="text-brand-rose-dark"
                          />
                          <span className="text-xs font-bold text-brand-rose-dark">{s.title}</span>
                        </div>
                        <p className="text-xs text-ink leading-relaxed whitespace-pre-wrap">
                          {s.text}
                        </p>
                      </div>
                    ))}
                  </div>

                  {d.note && (
                    <div className="text-[10px] text-muted mt-2 border-l-2 border-gold pl-2 leading-relaxed">
                      {d.note}
                    </div>
                  )}

                  {d.product_key && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      <SectionLink
                        href={withQuery('/compare', d.product_key)}
                        icon="scale"
                        label="查看比价看板"
                        primary
                      />
                      <SectionLink
                        href={withQuery('/trend', d.product_key)}
                        icon="chart"
                        label="查看 90 天行情"
                      />
                      <SectionLink
                        href={withQuery('/alert', d.product_key)}
                        icon="bell"
                        label="设降价提醒"
                      />
                    </div>
                  )}

                  {!d.product_key && d.suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {d.suggestions.map((k) => (
                        <button
                          key={k}
                          onClick={() => send(`${k} 帮我比价`)}
                          className="text-[11px] bg-white border border-line rounded-lg px-2.5 py-1.5 hover:border-brand-rose transition-colors"
                        >
                          {k}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {thinking && (
            <div className="flex justify-start">
              <div className="bg-cream border border-line rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-rose animate-bounce" />
                <span className="w-1.5 h-1.5 rounded-full bg-brand-rose animate-bounce [animation-delay:0.2s]" />
                <span className="w-1.5 h-1.5 rounded-full bg-brand-rose animate-bounce [animation-delay:0.4s]" />
              </div>
            </div>
          )}

          {bootError && messages.length === 0 && (
            <OfflineNotice
              message={`${bootError} 请确认后端服务已启动（默认 http://127.0.0.1:8000），然后重新加载本页。`}
              onRetry={() => window.location.reload()}
            />
          )}
        </div>

        <div className="mt-4 flex items-center gap-2 border-t border-line pt-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
            placeholder="描述你的需求，如：预算800，混油皮，抗初老，帮我全网比价"
            className="flex-1 bg-cream rounded-full px-4 h-10 text-sm focus:outline-none focus:ring-2 focus:ring-brand-rose/30"
            aria-label="输入你的选购需求"
          />
          <button
            onClick={() => send(input)}
            disabled={thinking || !input.trim()}
            className="w-10 h-10 rounded-full bg-brand-rose text-white flex items-center justify-center hover:bg-brand-rose-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="发送"
          >
            <Icon name="send" size={16} />
          </button>
        </div>
      </div>

      <p className="text-[10px] text-muted mt-4 leading-relaxed">
        提示：AI 结论基于公开价格与行情信息聚合，所有价格均为「行情参考价」。
        排序由到手价决定，佣金与赞助位不参与默认排序。
      </p>
    </div>
  );
}
