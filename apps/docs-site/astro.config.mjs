import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://docs.maximoraverse.org',
  integrations: [
    starlight({
      title: 'MatchAll Docs',
      description: 'MatchAll 产品文档、教程与安全排障中心',
      defaultLocale: 'root',
      locales: {
        root: { label: '简体中文', lang: 'zh-CN' },
      },
      favicon: '/favicon.svg',
      customCss: ['./src/styles/matchall.css'],
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/maximoraverse' },
      ],
      sidebar: [
        { label: '开始使用', items: [{ label: '快速开始', slug: 'docs/getting-started' }] },
        { label: '账户与安全', items: [
          { label: '统一账户与安全', slug: 'docs/account-security' },
          { label: '通知投递与偏好', slug: 'docs/notification-delivery' },
        ] },
        { label: '服务指南', items: [
          { label: 'Drive 同步与分享', slug: 'docs/drive-guide' },
          { label: 'Network 客户端与线路', slug: 'docs/network-guide' },
          { label: 'Mirrors 下载与授权', slug: 'docs/mirrors-user' },
        ] },
        { label: '开发者', items: [{ label: 'Mirrors 发布指南', slug: 'docs/mirrors-developer' }] },
        { label: '支持', items: [{ label: '常见问题排查', slug: 'docs/troubleshooting' }] },
      ],
      lastUpdated: true,
      credits: false,
    }),
  ],
});
