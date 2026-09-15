/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Docker 部署用：产出 .next/standalone（自带最小 node_modules，镜像更小）
  output: 'standalone',

  // 不暴露框架版本，减少指纹信息
  poweredByHeader: false,

  compress: true,

  // 生产构建时不做 ESLint 阻塞（CI 里单独跑 lint，职责分开）
  eslint: { ignoreDuringBuilds: false },

  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          // 跳转到电商平台需要保留 referer 供对方统计，因此用 strict-origin-when-cross-origin
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
    ];
  },
};

export default nextConfig;
