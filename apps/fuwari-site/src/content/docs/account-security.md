---
title: 统一账户与安全
description: 统一登录、邀请注册、账户恢复、验证码、会话管理和异常处理说明。
lastUpdated: 2026-09-30
---

MatchAll Account 使用 OIDC 为各项服务提供统一身份认证。业务服务会把登录交给 Account，认证成功后再返回原服务；它们不会直接保存统一账户密码。

## 官方入口与回调

- 账户首页：[auth.maximoraverse.org](https://auth.maximoraverse.org/)
- 登录入口：`https://auth.maximoraverse.org/login`
- 账户中心：从账户首页进入，不要收藏带临时参数的回调地址。

登录 URL 中出现 `state`、`code` 等参数是正常现象，但通常只能使用一次。不要复制给别人，也不要保存为书签。

## 邀请注册

注册采用邀请制。使用自己长期可控的邮箱。若邀请过期或与当前会话不匹配，请重新打开邀请链接，不要创建第二个重复账户。

注册或恢复流程可能使用 Turnstile 或 reCAPTCHA。无法加载时：

1. 确认 JavaScript 与 Cookie 已启用；
2. 暂停会改写页面的隐私或脚本扩展；
3. 检查系统时间和网络；
4. 从 Account 首页重新进入。

## 会话与退出

成功登录一个服务后，其他服务通常可复用统一会话，但每个应用仍有独立授权。退出一个业务应用不一定等于退出全部服务。在共享设备上应同时退出业务应用和统一账户，并关闭浏览器。

若页面在 Account 与业务服务间循环跳转：

- 停止重复点击登录；
- 清除相关两个站点的 Cookie；
- 暂停会拦截跨站跳转的扩展；
- 从服务首页重新开始，不复用历史回调 URL。

## 忘记密码与恢复

使用登录页的恢复流程。邮件可能需要几分钟送达，请检查垃圾邮件。多次请求后只使用最新邮件，旧链接可能已经失效。

若邮箱不可用，不要新建同名账户。通过官方联系入口提交账户名、可验证的历史信息和大致发生时间；不要发送旧密码、验证码或恢复代码。

## 发现异常时

1. 从官方 Account 首页重新登录；
2. 修改密码并检查账户资料；
3. 退出不再使用的会话或设备；
4. 撤销不认识的应用授权；
5. 检查邮箱安全；
6. 记录时间和应用名称后联系支持。

永远不要分享密码、验证码、恢复代码、回调 URL 参数、Network 订阅、DNS Token 或 Mirrors 更新 Token。

---

<form class="docs-feedback" method="post" action="/docs/account-security/feedback">
  <strong>这篇文档有帮助吗？</strong>
  <button name="helpful" value="1">有帮助</button>
  <button name="helpful" value="0">需要改进</button>
</form>
