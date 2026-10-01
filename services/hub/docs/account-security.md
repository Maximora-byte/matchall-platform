---
title: 统一账户与安全
summary: 登录、恢复、邀请注册、验证码与会话安全说明。
category: 账户
version: 1.0
updated: 2026-08-30
---
# 统一账户与安全

MatchAll Account 基于 OIDC 为各服务提供统一认证。每个应用使用独立客户端和精确回调地址，并启用 PKCE。

- 登录入口：`https://auth.maximoraverse.org/`
- 账户中心：`https://auth.maximoraverse.org/if/user/`
- 忘记密码时使用登录页的恢复流程，不要新建重复账户。

注册和恢复流程可能使用 Turnstile 或 Google reCAPTCHA。高风险网络环境可能出现可见挑战。
