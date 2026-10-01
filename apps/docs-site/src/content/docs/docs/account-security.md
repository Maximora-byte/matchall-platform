---
title: 统一账户与安全
description: 登录、恢复、邀请注册、验证码与会话安全说明。
lastUpdated: 2026-08-30
---
MatchAll Account 基于 OIDC 为各服务提供统一认证。每个应用使用独立客户端和精确回调地址，并启用 PKCE。

- 登录入口：`https://auth.maximoraverse.org/`
- 账户中心：`https://auth.maximoraverse.org/if/user/`
- 忘记密码时使用登录页的恢复流程，不要新建重复账户。

注册和恢复流程可能使用 Turnstile 或 Google reCAPTCHA。高风险网络环境可能出现可见挑战。

---

<form class="docs-feedback" method="post" action="/docs/account-security/feedback">
  <strong>这篇文档有帮助吗？</strong>
  <button name="helpful" value="1">有帮助</button>
  <button name="helpful" value="0">需要改进</button>
</form>
