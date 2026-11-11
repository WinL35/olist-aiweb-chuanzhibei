/**
 * Next.js 配置
 *
 * 架构说明：
 *   浏览器  →  Next.js(3000)  →  FastAPI(8000)  →  MySQL
 *
 * 1. rewrites 把 /api/* 同源转发给 FastAPI，浏览器端不产生跨域请求，
 *    也不需要在前端写死后端地址（部署到任何机器只改 PY_API_BASE 环境变量）。
 * 2. rewrites 默认在 "afterFiles" 阶段生效，所以 app/api/ 下已存在的
 *    Route Handler（如流式对话 /api/chat）优先生效，不会被代理覆盖。
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  async rewrites() {
    const target = process.env.PY_API_BASE || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },

  // ECharts 体积较大，交给 Next 做 tree-shaking 提示
  experimental: {
    optimizePackageImports: ["echarts"],
  },
};

export default nextConfig;
