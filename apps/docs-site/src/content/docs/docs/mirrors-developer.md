---
title: Mirrors 开发者发布指南
description: 团队、私有项目、发布令牌、Webhook 与自动更新 API。
lastUpdated: 2026-08-31
---
开发者中心支持团队项目、公开或私有可见性、浏览器/CI 托管上传、外部 CDN 地址、发布 Token、Webhook 和审计记录。

- Owner 管理团队成员和令牌。
- Editor 创建项目和发布草稿。
- Viewer 只读取私有项目。
- 发布 Token 按团队和 scope 限制，并可随时撤销。

## CI 托管上传

在开发者中心生成 Token 后，将它保存为 CI 的受保护 Secret。官方示例提供 GitHub Actions、GitLab CI，以及 Python、JavaScript、Go 三种上传器。上传端自动计算 SHA-256，服务端再次计算并以服务端结果为准。

所有 CI 上传先进入 draft。Owner 审批后才进入更新 API；可设置 1–100% 灰度比例。客户端应为每台安装生成稳定且不包含隐私的 client_id，更新检查时附带该值。

没有 client_id 的旧客户端只接收 100% 发布。快速回滚会立即将版本从项目页、下载入口和更新 API 中移除。

## 私有对象存储

私有或付费制品必须使用托管上传。本地存储和 S3/R2 使用相同授权边界；S3/R2 下载在权限校验后生成短期签名 URL，永久对象地址不会暴露给浏览器。未配置对象存储凭据时平台安全回退到本地存储。

Webhook 使用 HMAC-SHA256 签名。接收端必须校验时间戳、事件 ID 和签名，并按事件 ID 幂等处理。

---

<form class="docs-feedback" method="post" action="/docs/mirrors-developer/feedback">
  <strong>这篇文档有帮助吗？</strong>
  <button name="helpful" value="1">有帮助</button>
  <button name="helpful" value="0">需要改进</button>
</form>
