/**
 * 全站统一图标体系（内联 SVG，零依赖、零 emoji）。
 *
 * 为什么不用 emoji：emoji 在不同系统字体下形状/线宽/颜色不一致，
 * 在信息密度高的比价看板里会显得廉价且不可控；同时 emoji 无法继承
 * `currentColor`，做不了 hover / 激活态染色。这里统一用 24×24 网格、
 * 1.75 描边、圆角端点的线性图标，通过 `currentColor` 自动跟随文字颜色。
 *
 * 用法：<Icon name="scale" size={16} className="text-brand-rose" />
 */
import type { ReactNode } from 'react';

export type IconName =
  // 导航
  | 'chat' | 'scale' | 'chart' | 'bell' | 'user'
  // 语义
  | 'target' | 'tag' | 'gift' | 'money' | 'shield' | 'risk'
  | 'trendUp' | 'trendDown' | 'sparkles' | 'box' | 'clock'
  | 'info' | 'warn' | 'check' | 'close' | 'search'
  // 动作
  | 'external' | 'refresh' | 'trash' | 'arrowRight' | 'send'
  // 状态
  | 'layers' | 'database' | 'unplugged' | 'medal' | 'link' | 'settings';

const PATHS: Record<IconName, ReactNode> = {
  chat: (
    <path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7A8.4 8.4 0 0 1 4 11.5a8.5 8.5 0 0 1 4.7-7.6A8.4 8.4 0 0 1 12.5 3h.5a8.5 8.5 0 0 1 8 8v.5Z" />
  ),
  scale: (
    <>
      <path d="M12 3v18" />
      <path d="M5 7h14" />
      <path d="M5 7 2.2 13.1a2.9 2.9 0 0 0 5.6 0Z" />
      <path d="M19 7l2.8 6.1a2.9 2.9 0 0 1-5.6 0Z" />
      <path d="M8 21h8" />
    </>
  ),
  chart: (
    <>
      <path d="M4 4v16h16" />
      <path d="M7.5 14.5 11.5 10l3 3 5-6" />
    </>
  ),
  bell: (
    <>
      <path d="M18 8.5a6 6 0 1 0-12 0c0 6.5-2.5 8-2.5 8h17S18 15 18 8.5" />
      <path d="M13.7 20.5a2 2 0 0 1-3.4 0" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 21a7.5 7.5 0 0 1 15 0" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
  tag: (
    <>
      <path d="M20.6 13.4 12 22l-9-9V4h9l8.6 8.6a2 2 0 0 1 0 2.8Z" />
      <circle cx="7.5" cy="7.5" r="1.2" />
    </>
  ),
  gift: (
    <>
      <rect x="3" y="8.5" width="18" height="12.5" rx="1.8" />
      <path d="M3 12.8h18" />
      <path d="M12 8.5V21" />
      <path d="M12 8.5S10.7 3.5 8.2 3.5a2.5 2.5 0 0 0 0 5Z" />
      <path d="M12 8.5s1.3-5 3.8-5a2.5 2.5 0 0 1 0 5Z" />
    </>
  ),
  money: (
    <>
      <path d="M7 6.5l5 5.5 5-5.5" />
      <path d="M12 12v7.5" />
      <path d="M8 14h8" />
      <path d="M8 17h8" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l8 3v6c0 5-3.4 8.2-8 9.5C7.4 20.2 4 17 4 12V6Z" />
      <path d="M9.4 12.4l2 2 3.6-4.2" />
    </>
  ),
  risk: (
    <>
      <path d="M10.4 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.6 3.9a2 2 0 0 0-3.2 0Z" />
      <path d="M12 9.5v4" />
      <path d="M12 17h.01" />
    </>
  ),
  trendUp: (
    <>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </>
  ),
  trendDown: (
    <>
      <path d="M3 7l6 6 4-4 8 8" />
      <path d="M15 17h6v-6" />
    </>
  ),
  sparkles: (
    <>
      <path d="M11 3l1.5 4.1L16.6 8.6 12.5 10.1 11 14.2 9.5 10.1 5.4 8.6l4.1-1.5Z" />
      <path d="M18 14.5l.8 2.1 2.2.8-2.2.8-.8 2.1-.8-2.1-2.2-.8 2.2-.8Z" />
    </>
  ),
  box: (
    <>
      <path d="M21 8.5 12 3.5 3 8.5v7l9 5 9-5Z" />
      <path d="M3 8.5l9 5 9-5" />
      <path d="M12 13.5v7" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11.5v5" />
      <path d="M12 8h.01" />
    </>
  ),
  warn: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 8.5v4" />
      <path d="M12 16h.01" />
    </>
  ),
  check: <path d="M4.5 12.5l5 5 10-11" />,
  close: (
    <>
      <path d="M6 6l12 12" />
      <path d="M18 6 6 18" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.6-3.6" />
    </>
  ),
  external: (
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4l-9 9" />
      <path d="M19 14.5V19a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h4.5" />
    </>
  ),
  refresh: (
    <>
      <path d="M20.5 12a8.5 8.5 0 1 1-2.5-6" />
      <path d="M20.5 3.5V9h-5.5" />
    </>
  ),
  trash: (
    <>
      <path d="M4 7h16" />
      <path d="M10 11v6M14 11v6" />
      <path d="M6.5 7l.9 12.1a1 1 0 0 0 1 .9h7.2a1 1 0 0 0 1-.9L17.5 7" />
      <path d="M9.5 7V5.2a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V7" />
    </>
  ),
  arrowRight: (
    <>
      <path d="M4.5 12h15" />
      <path d="M13.5 6l6 6-6 6" />
    </>
  ),
  send: (
    <>
      <path d="M7 17 17 7" />
      <path d="M8.5 7H17v8.5" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3 3 7.5l9 4.5 9-4.5Z" />
      <path d="M3 12.5 12 17l9-4.5" />
      <path d="M3 17 12 21.5 21 17" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="6" rx="7.5" ry="3" />
      <path d="M4.5 6v12c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3V6" />
      <path d="M4.5 12c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3" />
    </>
  ),
  unplugged: (
    <>
      <path d="M9 3.5v4.5M15 3.5v4.5" />
      <path d="M6.5 8h11v2.5a5.5 5.5 0 0 1-11 0Z" />
      <path d="M12 16v4.5" />
    </>
  ),
  medal: (
    <>
      <circle cx="12" cy="9" r="5.5" />
      <path d="M8.4 13.6 7 21l5-2.6L17 21l-1.4-7.4" />
    </>
  ),
  link: (
    <>
      <path d="M10 13.2a5 5 0 0 0 7.1 0l2.4-2.4a5 5 0 0 0-7.1-7.1l-1.4 1.4" />
      <path d="M14 10.8a5 5 0 0 0-7.1 0l-2.4 2.4a5 5 0 0 0 7.1 7.1l1.4-1.4" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.8v2.4M12 18.8v2.4M5.6 5.6l1.7 1.7M16.7 16.7l1.7 1.7M2.8 12h2.4M18.8 12h2.4M5.6 18.4l1.7-1.7M16.7 7.3l1.7-1.7" />
    </>
  ),
};

export interface IconProps {
  name: IconName;
  /** 像素尺寸，默认 16（等于 1em 的常见正文字号） */
  size?: number;
  className?: string;
  strokeWidth?: number;
  title?: string;
}

export function Icon({
  name,
  size = 16,
  className = '',
  strokeWidth = 1.75,
  title,
}: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`inline-block shrink-0 align-[-0.125em] ${className}`}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}

export const NAV_ICONS: Record<string, IconName> = {
  '/': 'chat',
  '/compare': 'scale',
  '/trend': 'chart',
  '/alert': 'bell',
  '/my': 'user',
};
