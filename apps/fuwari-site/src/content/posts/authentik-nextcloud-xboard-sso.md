---
title: 用 Authentik 打造 Nextcloud 与 Xboard 的统一身份中心
published: 2026-08-25
description: "从账号迁移、OIDC 映射到邀请码注册与双 CAPTCHA 分支，记录一套可维护的统一认证落地方法。"
tags: ["Authentik", "OIDC", "Nextcloud", "Xboard", "SSO", "安全"]
category: 运维
draft: false
---

当网盘、订阅面板和其他服务各自维护一套账号时，用户需要反复注册、登录和找回密码，管理员也很难统一处理封禁、邮箱验证与安全策略。解决这个问题的关键不是在页面前面加一层反向代理，而是让各业务系统真正成为同一个身份提供方的 OIDC 客户端。

本文记录 MatchAll 将 Authentik、Nextcloud 与 Xboard 整合为统一身份体系时采用的架构、关键决策和踩坑经验。

## 最终架构

统一身份中心只负责“你是谁”，业务系统继续负责“你能使用什么”。

```text
                     ┌──────────────────┐
                     │ MatchAll Account │
                     │    Authentik     │
                     └────────┬─────────┘
                              │ OIDC
                  ┌───────────┴───────────┐
                  │                       │
          ┌───────▼────────┐      ┌──────▼──────┐
          │ MatchAll Drive │      │   Xboard    │
          │   Nextcloud    │      │ Network/Pay │
          └────────────────┘      └─────────────┘
```

- **Authentik**：账号、密码、邮箱验证、邀请注册、CAPTCHA、会话和 2FA
- **Nextcloud**：文件、分享、配额、WebDAV 与客户端同步
- **Xboard**：套餐、订单、支付、订阅和节点权限

这种边界很重要。SSO 不等于把所有用户数据塞进一个数据库，也不应该同步密码哈希。身份由 Authentik 统一，套餐与容量仍由业务系统根据自身规则管理。

## 为什么选择 OIDC

OIDC 建立在 OAuth 2.0 之上，适合浏览器、移动端和桌面客户端。每个业务系统都使用独立的 Client ID、回调地址和密钥，但共享同一个 Authentik 登录会话。

一次登录后的典型流程是：

1. 用户访问 Nextcloud 或 Xboard 的登录入口；
2. 业务系统生成 `state`、`nonce` 和 PKCE 参数；
3. 浏览器跳转到 Authentik；
4. Authentik 完成身份验证并返回授权码；
5. 业务系统在后端换取并验证 ID Token；
6. 根据稳定的 `sub` 和经过验证的邮箱关联本地账户。

需要同时启用严格回调地址、PKCE S256、签名验证、`state` 与 `nonce` 校验。只解析 JWT 内容而不验证签名，或只按可修改的用户名绑定账户，都可能留下安全问题。

## 迁移用户时避免产生空账户

Nextcloud 中已经存在文件的用户，最容易在首次 OIDC 登录后被创建成另一个空账户。迁移时应先确定业务系统真正使用的不可变用户 ID，再设计 OIDC 属性映射。

我们的处理顺序是：

1. 先备份原文件、数据库和配置；
2. 迁移文件并完成数量、大小与哈希校验；
3. 让统一身份的用户名映射到现有 Nextcloud 用户 ID；
4. 保留 Authentik 的不可变 `sub` 作为长期身份绑定依据；
5. 首次真实登录后检查是否复用了原账户与原文件。

邮箱适合用于首次匹配，但不适合作为唯一的永久主键，因为邮箱以后可能变更。

## Xboard 的 OIDC 接入

当业务系统没有现成的 OIDC 登录模块时，仅在 Caddy 前面增加 `forward_auth` 并不等于真正 SSO。它只能阻挡未登录请求，不能自动创建 Xboard 内部用户、套餐记录或业务会话。

正确做法是增加独立的 OIDC 后端回调：

- 登录入口生成一次性 `state`、`nonce` 和 PKCE verifier；
- 回调后在服务端交换 Token；
- 使用 Authentik 的 JWKS 验证 RS256 签名；
- 首次登录按已验证邮箱关联现有用户，没有匹配时再进行 JIT 建号；
- 用不可变 `sub` 保存后续关联；
- 最后签发 Xboard 自己的业务会话。

完成 OIDC 验证后，旧的密码登录、邮件链接登录、本地注册和本地找回入口应在服务端关闭，而不只是把前端按钮隐藏。否则攻击者仍可能直接调用旧 API 绕过统一认证。

## 邀请码注册与邮箱验证

统一注册采用以下顺序：

```text
选择 CAPTCHA → 执行一个验证分支 → 校验管理员邀请码
→ 填写账户资料 → 邮箱确认 → 创建内部用户
```

邀请码由管理员生成，可设置过期时间和一次性使用。无邀请码、错误邀请码、过期邀请码或已使用的邀请码都必须在创建账户之前被拒绝。

邮箱验证也应该发生在账户激活之前。这样可以避免批量创建不可用账号，同时确保后续找回密码与业务通知有真实的投递目标。

## Turnstile 与 Google reCAPTCHA 备用分支

单一 CAPTCHA 提供商可能在某些代理、VPN 或数据中心网络上误判，也可能因为区域可达性导致脚本加载失败。我们保留 Cloudflare Turnstile 和 Google reCAPTCHA 两种选择，但服务端每次只执行其中一个 Stage。

关键约束是：

- 选择器之后必须命中且仅命中一个 CAPTCHA Stage；
- 未选择或策略异常时按失败安全方式执行默认验证，不能跳过；
- 不能把两种 Stage 直接串联，否则用户需要连续验证两次；
- 不能在主验证失败后自动无条件降级，否则会形成绕过路径；
- 登录、注册和找回密码应复用同样的分支策略。

无感验证也不代表永远不会出现交互挑战。高风险网络下，Google Invisible 或 Turnstile 仍可能要求进一步操作，因此页面需要保留合理的失败提示和重试路径。

## 网页唯一登录与客户端兼容

关闭本地网页登录时，还要区分网页认证与协议客户端：

- Nextcloud 网页登录可以强制进入 OIDC；
- 桌面端和手机客户端仍需要 Login Flow v2；
- WebDAV 应继续支持应用密码；
- OIDC discovery、JWKS、授权、Token 和回调路径不能被交互式 WAF Challenge 阻断；
- 匿名 WebDAV 应保持 `401`，而不是跳转到 HTML 登录页。

将 CAPTCHA 或 Cloudflare Access 直接套在整个身份域名前面，往往会破坏移动端、桌面端或 Token 交换。人机验证应该放在 Authentik 的登录、注册和找回 Flow 内，而不是协议端点外层。

## 上线前验证清单

每次修改认证流程后，至少检查以下内容：

- 登录、注册、找回三个 Flow 都无法跳过 CAPTCHA；
- 无有效邀请码不能创建账户；
- Nextcloud 与 Xboard 使用不同 OIDC Client；
- 同一浏览器登录一次后可进入两个服务；
- 已迁移用户复用原 Nextcloud 文件账户；
- Xboard 本地认证 API 返回拒绝；
- Nextcloud Login Flow v2、WebDAV 和应用密码仍可用；
- OIDC discovery、JWKS、Token 和回调端点没有被 WAF 拦截；
- 服务、数据库、后台 Worker 与邮件投递均健康；
- 修改前后都有可校验的备份和明确回滚路径。

## 总结

统一身份系统最难的部分不是把登录按钮换成“使用统一账户登录”，而是处理账户映射、业务会话、注册边界、协议客户端和失败安全策略。

采用 Authentik 作为身份源、Nextcloud 管文件、Xboard 管套餐和支付，可以在不共享密码数据库的前提下实现真正的 SSO。只要坚持独立客户端、不可变身份绑定、服务端校验、最小暴露和可回滚部署，这套架构也能继续扩展到更多 MatchAll 服务。

相关入口：

- [MatchAll Account](https://auth.maximoraverse.org/)
- [MatchAll Drive](https://drive.maximoraverse.org/)
- [MatchAll Network](https://proxyservice.maximoraverse.org/)
- [MatchAll 服务导航](https://www.maximoraverse.org/)
