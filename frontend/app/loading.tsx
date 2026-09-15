import { Icon } from '@/components/Icons';

export default function Loading() {
  return (
    <div className="max-w-3xl mx-auto py-10" aria-busy="true" aria-live="polite">
      <div className="h-7 w-2/3 rounded bg-white border border-line animate-pulse" />
      <div className="h-4 w-1/2 rounded bg-white border border-line animate-pulse mt-3" />
      <div className="mt-6 space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-24 rounded-2xl bg-white border border-line animate-pulse" />
        ))}
      </div>
      <div className="flex items-center justify-center gap-2 text-xs text-muted mt-8">
        <Icon name="refresh" size={13} className="animate-spin" />
        正在加载行情数据…
      </div>
    </div>
  );
}
