'use client';

import { useEffect } from 'react';
import { Icon } from '@/components/Icons';

/**
 * 路由级错误边界。
 *
 * 原则：出错时**不展示任何业务数字**（价格 / 阈值 / 档位），
 * 只给出可操作的恢复路径与追踪号，避免把「渲染异常」误当成「行情数据」。
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 生产环境接入前端监控后，这里应上报 error.digest
    console.error('[caixuan] 页面渲染异常', error);
  }, [error]);

  return (
    <div className="max-w-lg mx-auto py-16 text-center">
      <div className="w-12 h-12 rounded-full bg-danger/10 text-danger flex items-center justify-center mx-auto mb-4">
        <Icon name="risk" size={22} />
      </div>
      <h1 className="text-lg font-bold">页面出现异常</h1>
      <p className="text-xs text-muted mt-2 leading-relaxed">
        本次没有加载到有效行情数据，因此不展示任何价格。可以重试，或返回对话页重新查询。
      </p>
      {error.digest && (
        <p className="text-[10px] text-muted/80 mt-2 font-mono">追踪号：{error.digest}</p>
      )}
      <div className="flex items-center justify-center gap-2 mt-5">
        <button
          onClick={reset}
          className="inline-flex items-center gap-1.5 text-xs font-bold bg-brand-rose text-white rounded-full px-4 py-2 hover:bg-brand-rose-dark transition-colors"
        >
          <Icon name="refresh" size={13} />
          重试
        </button>
        <a
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-bold bg-white border border-brand-rose text-brand-rose-dark rounded-full px-4 py-2 hover:bg-brand-rose-soft transition-colors"
        >
          <Icon name="chat" size={13} />
          返回对话
        </a>
      </div>
    </div>
  );
}
