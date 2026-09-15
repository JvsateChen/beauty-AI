'use client';

/**
 * 全局错误边界（连根 layout 都渲染失败时兜底）。
 * 这里不能用 AppShell / Icon 等依赖应用层的组件，样式全部内联，保证一定能渲染出来。
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-CN">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#FBF7F4',
          color: '#2A2A2E',
          fontFamily:
            '-apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif',
          padding: 24,
        }}
      >
        <div style={{ maxWidth: 420, textAlign: 'center' }}>
          <h1 style={{ fontSize: 18, margin: '0 0 8px' }}>应用启动失败</h1>
          <p style={{ fontSize: 13, color: '#6B6B73', lineHeight: 1.7, margin: 0 }}>
            页面无法正常初始化。请刷新重试；若持续出现，请确认后端服务已启动并检查浏览器控制台。
          </p>
          {error.digest && (
            <p style={{ fontSize: 11, color: '#9A9AA2', fontFamily: 'monospace', marginTop: 8 }}>
              追踪号：{error.digest}
            </p>
          )}
          <button
            onClick={reset}
            style={{
              marginTop: 20,
              padding: '9px 20px',
              borderRadius: 999,
              border: 'none',
              background: '#C76B7E',
              color: '#fff',
              fontSize: 13,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            重新加载
          </button>
        </div>
      </body>
    </html>
  );
}
