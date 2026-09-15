import type { Metadata, Viewport } from 'next';
import './globals.css';
import { AppShell } from '@/components/AppShell';

export const metadata: Metadata = {
  title: {
    default: '采选美妆 AI · 国际大牌护肤美妆 AI 比价平台',
    template: '%s · 采选美妆 AI',
  },
  description:
    '国际大牌护肤美妆 AI 参谋：一句话说清需求，自动跨天猫 / 京东 / 拼多多 / 唯品会 / 保税仓比价，'
    + '看版本差异与价格行情，筛查临期与售后风险。',
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
