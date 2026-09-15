import Link from 'next/link';
import { Icon } from '@/components/Icons';

export default function NotFound() {
  return (
    <div className="max-w-lg mx-auto py-16 text-center">
      <div className="w-12 h-12 rounded-full bg-cream text-muted flex items-center justify-center mx-auto mb-4">
        <Icon name="search" size={22} />
      </div>
      <h1 className="text-lg font-bold">页面不存在</h1>
      <p className="text-xs text-muted mt-2">
        你访问的地址没有对应页面。可以回到对话页，用一句话描述需求重新开始。
      </p>
      <div className="mt-5">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-bold bg-brand-rose text-white rounded-full px-4 py-2 hover:bg-brand-rose-dark transition-colors"
        >
          <Icon name="chat" size={13} />
          回到 AI 对话
        </Link>
      </div>
    </div>
  );
}
