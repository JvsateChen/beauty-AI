'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Icon, type IconName } from '@/components/Icons';
import { getHealth } from '@/lib/api';

// 导航 = MVP 五大核心模块一一对应
const navItems: { href: string; label: string; icon: IconName; title: string }[] = [
  { href: '/', label: '对话', icon: 'chat', title: 'M1 AI 智能对话选型' },
  { href: '/compare', label: '比价', icon: 'scale', title: 'M2 全网结构化比价看板' },
  { href: '/trend', label: '行情', icon: 'chart', title: 'M3 价格行情曲线' },
  { href: '/alert', label: '订阅', icon: 'bell', title: 'M4 降价订阅提醒' },
  { href: '/my', label: '我的', icon: 'user', title: '我的 · 数据源与合规' },
];

/**
 * 全站顶部免责条（一句话版）。
 *
 * 完整免责声明由后端 `settings.disclaimer` 下发，在各页面按需引用；
 * 这里只做全站可见的一句话提示，避免同一段话在页面上重复出现四五次。
 */
const DISCLAIMER = '不提供真伪鉴定服务、不承诺正品；价格为「行情参考价」，非锁定成交价。';

type Health = 'checking' | 'online' | 'offline';

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health>('checking');

  useEffect(() => {
    let alive = true;
    getHealth()
      .then(() => alive && setHealth('online'))
      .catch(() => alive && setHealth('offline'));
    return () => {
      alive = false;
    };
  }, []);

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : (pathname?.startsWith(href) ?? false);

  const healthChip =
    health === 'online' ? (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-success"
        title="后端服务可用"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-success" />
        服务正常
      </span>
    ) : health === 'offline' ? (
      <span
        className="inline-flex items-center gap-1 text-[10px] text-danger"
        title="后端服务不可达，页面不会显示任何价格数据"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-danger" />
        服务未连接
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 text-[10px] text-muted">
        <span className="w-1.5 h-1.5 rounded-full bg-muted/50" />
        检测中
      </span>
    );

  return (
    <div className="min-h-screen flex flex-col">
      {/* 全站固定免责条（M2 强制风控设计） */}
      <div className="bg-gold-light/60 border-b border-gold/30 text-[11px] text-gold-dark px-3 py-1.5 text-center leading-snug">
        <Icon name="warn" size={12} className="mr-1 align-[-0.15em]" />
        {DISCLAIMER}
      </div>

      {/* Desktop top nav */}
      <header className="hidden md:flex sticky top-0 z-30 bg-white/85 backdrop-blur border-b border-line">
        <div className="max-w-6xl mx-auto w-full flex items-center justify-between px-6 h-16">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-rose to-brand-rose-dark flex items-center justify-center text-white">
              <Icon name="sparkles" size={17} />
            </span>
            <span className="font-bold text-lg">采选美妆 AI</span>
          </Link>
          <nav className="flex items-center gap-1">
            {navItems.map((it) => (
              <Link
                key={it.href}
                href={it.href}
                title={it.title}
                className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive(it.href)
                    ? 'bg-brand-rose-soft text-brand-rose-dark'
                    : 'text-muted hover:text-ink hover:bg-cream'
                }`}
              >
                <Icon name={it.icon} size={15} />
                {it.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            {healthChip}
            <Link
              href="/my"
              className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink"
            >
              <Icon name="user" size={15} />
              我的
            </Link>
          </div>
        </div>
      </header>

      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-30 bg-gradient-to-r from-brand-rose to-brand-rose-dark text-white">
        <div className="flex items-center justify-between px-4 h-12">
          <Link href="/" className="flex items-center gap-2">
            <Icon name="sparkles" size={16} />
            <span className="font-bold text-sm">采选美妆 AI</span>
          </Link>
          <span className="inline-flex items-center text-[10px] bg-white/15 rounded px-2 py-1">
            {healthChip}
          </span>
        </div>
      </header>

      <main className="flex-1 pb-24 md:pb-8">
        <div className="max-w-6xl mx-auto w-full px-4 md:px-6 py-6 md:py-8">{children}</div>
      </main>

      {/* Compliance footer (desktop only) */}
      <footer className="hidden md:block border-t border-line bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 text-[11px] text-muted leading-relaxed">
          <Icon name="warn" size={12} className="mr-1 align-[-0.15em]" />
          排序由到手价决定，<b className="text-ink">佣金与赞助位不参与默认排序</b>，
          付费推广位强制标注「赞助/佣金」。
          <div className="mt-1">© 2026 采选美妆 AI</div>
        </div>
      </footer>

      {/* Mobile bottom tab */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-30 bg-white border-t border-line">
        <div className="grid grid-cols-5 h-20 pb-2">
          {navItems.map((it) => (
            <Link
              key={it.href}
              href={it.href}
              className={`flex flex-col items-center justify-center gap-1 text-[10px] font-medium ${
                isActive(it.href) ? 'text-brand-rose-dark' : 'text-muted'
              }`}
            >
              <Icon name={it.icon} size={20} />
              <span>{it.label}</span>
            </Link>
          ))}
        </div>
      </nav>
    </div>
  );
}
