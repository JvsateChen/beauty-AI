import type { Metadata, Viewport } from 'next';
import './globals.css';
import { AppShell } from '@/components/AppShell';

export const metadata: Metadata = {
  title: {
    default: '采选美妆 AI · 国际大牌护肤美妆 AI 比价平台',
    template: '%s · 采选美妆 AI',
  },
  description:
    'AI 对话选型 + 多平台比价 + 货源风险筛查：一句话说清预算、肤质、诉求，自动跨天猫 / 京东 / 拼多多 / 唯品会 / 保税仓比价，区分国行·保税免税·海外版版本差异，查看价格行情，并筛查临期与售后风险。不提供真伪鉴定服务，价格均为行情参考价。',
  applicationName: '采选美妆 AI',
  keywords: [
    '美妆比价', '大牌护肤', 'AI 选品', '多平台比价', '临期风险',
    '版本差异', '保税免税', '价格行情',
  ],
  robots: { index: true, follow: true },
  formatDetection: { telephone: false, email: false, address: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: '#C76B7E',
  colorScheme: 'light',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-cream text-ink antialiased font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
