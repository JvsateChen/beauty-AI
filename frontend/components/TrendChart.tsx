'use client';

import { Icon } from '@/components/Icons';
import { DataBasisBadge } from '@/components/Cards';
import type { Trend } from '@/lib/api';

/**
 * 价格行情曲线（M3）—— 内联 SVG 手绘，无第三方图表库。
 *
 * 与旧实现的差别：
 *  · 不再在「无数据」时也给一张示意曲线 —— 那会让人以为有行情数据
 *  · 低点标注只在**真实落在数据点上**时出现，且标签来自后端（真实大促日历窗）
 *  · 增加「走势形态」与「是否为已确认的真实低点」的说明，档位判断可追溯
 */
export function TrendChart({ trend }: { trend: Trend }) {
  const pts = trend.points;

  if (!pts || pts.length === 0) {
    return (
      <div className="bg-cream border border-dashed border-line rounded-xl h-56 flex flex-col items-center justify-center gap-2 text-xs text-muted">
        <Icon name="unplugged" size={20} />
        <span>暂无行情数据</span>
        <span className="text-[10px]">为避免误判，此处不显示任何示意曲线</span>
      </div>
    );
  }

  const W = 660;
  const H = 240;
  const PAD = { t: 20, r: 62, b: 28, l: 14 };
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  const prices = pts.map((p) => p.price);
  const min = Math.min(...prices, trend.low_90d);
  const max = Math.max(...prices, trend.high_90d);
  const span = max - min || 1;
  const lo = min - span * 0.12;
  const hi = max + span * 0.12;

  const x = (i: number) => PAD.l + (i / Math.max(1, pts.length - 1)) * innerW;
  const y = (v: number) => PAD.t + innerH - ((v - lo) / (hi - lo)) * innerH;

  const line = pts
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.price).toFixed(1)}`)
    .join(' ');
  const area =
    `${line} L${x(pts.length - 1).toFixed(1)},${(PAD.t + innerH).toFixed(1)} ` +
    `L${PAD.l},${(PAD.t + innerH).toFixed(1)} Z`;

  const ticks = [0, Math.floor(pts.length / 2), pts.length - 1];

  // 低点事件标注：标签太密会糊成一团，只保留间隔 ≥12 天的几个
  const eventIdx = new Set<number>();
  let lastKept = -999;
  pts.forEach((p, i) => {
    if (!p.event) return;
    if (i - lastKept < 12) return;
    eventIdx.add(i);
    lastKept = i;
  });

  const refLine = (v: number, label: string, color: string) => (
    <g key={label}>
      <line
        x1={PAD.l}
        x2={W - PAD.r}
        y1={y(v)}
        y2={y(v)}
        stroke={color}
        strokeWidth="1"
        strokeDasharray="4 4"
      />
      <text x={W - PAD.r + 6} y={y(v) + 3.5} fontSize="10" fill="#6B6B73">
        {label} ¥{v}
      </text>
    </g>
  );

  const last = pts[pts.length - 1];

  return (
    <div className="bg-white border border-line rounded-2xl p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
        <h2 className="text-sm font-bold text-brand-rose-dark inline-flex items-center gap-1.5">
          <Icon name="chart" size={14} />
          近 {trend.days} 天到手价走势
        </h2>
        <DataBasisBadge basis={trend.data_basis} />
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        role="img"
        aria-label={`近 ${trend.days} 天价格行情曲线，当前 ¥${trend.current}`}
      >
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#C76B7E" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#C76B7E" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <line
            key={f}
            x1={PAD.l}
            x2={W - PAD.r}
            y1={PAD.t + innerH * f}
            y2={PAD.t + innerH * f}
            stroke="#F0E7E1"
            strokeWidth="1"
          />
        ))}

        {refLine(trend.avg_90d, `${trend.days}天均价`, '#B8995A')}
        {refLine(trend.low_90d, '区间低', '#3F9D6D')}
        {refLine(trend.high_90d, '区间高', '#D9534F')}

        <path d={area} fill="url(#trendFill)" />
        <path
          d={line}
          fill="none"
          stroke="#C76B7E"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {pts.map((p, i) =>
          eventIdx.has(i) && p.event ? (
            <g key={`${p.date}-${p.event}`}>
              <circle cx={x(i)} cy={y(p.price)} r="3" fill="#3F9D6D" />
              <text
                x={x(i)}
                y={y(p.price) - 7}
                fontSize="9"
                fill="#3F9D6D"
                textAnchor="middle"
              >
                {p.event}
              </text>
            </g>
          ) : null,
        )}

        {trend.peak && (
          <text
            x={x(trend.peak.index)}
            y={y(trend.peak.price) - 8}
            fontSize="9"
            fill="#D9534F"
            textAnchor="middle"
          >
            峰值 ¥{trend.peak.price}
          </text>
        )}

        <circle cx={x(pts.length - 1)} cy={y(last.price)} r="5" fill="#A84E63" />
        <text
          x={x(pts.length - 1) - 8}
          y={y(last.price) - 10}
          fontSize="10"
          fill="#A84E63"
          textAnchor="end"
          fontWeight="700"
        >
          当前 ¥{last.price}
        </text>

        {ticks.map((i) => (
          <text
            key={i}
            x={x(i)}
            y={H - 8}
            fontSize="10"
            fill="#6B6B73"
            textAnchor={i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle'}
          >
            {pts[i].date.slice(5)}
          </text>
        ))}
      </svg>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-[10px] text-muted">
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: '#3F9D6D' }} />
          真实价格低点
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-3 h-0.5" style={{ background: '#C76B7E' }} />
          到手价走势
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-3 h-0.5" style={{ background: '#B8995A' }} />
          {trend.days} 天均价
        </span>
        <span className="ml-auto text-right">{trend.disclaimer}</span>
      </div>
    </div>
  );
}
