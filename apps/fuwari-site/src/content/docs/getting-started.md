---
title: MatchAll 快速开始
description: 从邀请注册、统一登录到 Drive、Network、Mirrors 与 Console 的完整入门流程。
lastUpdated: 2026-09-30
---

这篇指南适合第一次使用 MatchAll 的用户。一个统一账户可以进入 Drive、Network、Mirrors 和 Console，各服务不需要重复创建密码。

## 开始前准备

- 一个仍然有效的邀请入口；
- 能接收账户恢复邮件的邮箱；
- 支持 Cookie、JavaScript 和 HTTPS 的现代浏览器；
- 准确的设备时间，时间偏差可能导致安全校验失败。

只在 `maximoraverse.org` 及其子域名输入登录信息。工作人员不会索要密码、验证码、恢复代码、订阅地址或 Token。

## 1. 创建或登录统一账户

打开 [MatchAll Account](https://auth.maximoraverse.org/)。已有账户选择登录；新用户通过邀请入口注册。认证后进入账户中心，确认显示名称和邮箱正确。

若出现验证码，这是正常风控步骤。连续失败时不要反复提交，先关闭会改写页面的扩展、确认系统时间，再从官方首页重新进入。

## 2. 认识服务入口

- [Console](https://console.maximoraverse.org/)：服务入口、通知和账户关联状态；
- [Drive](https://drive.maximoraverse.org/)：文件、同步、分享、日历与通讯录；
- [Network](https://proxyservice.maximoraverse.org/)：线路、订阅、设备与流量；
- [Mirrors](https://mirrors.maximoraverse.org/)：软件版本、下载与更新授权；
- [Status](https://status.maximoraverse.org/)：维护和故障状态。

首次进入服务时，浏览器可能跳转到 Account 后再返回。这是标准 OIDC 登录流程。

## 3. 完成第一次检查

1. 登录 Console，确认页面能识别账户；
2. 打开 Drive，创建一个测试文件夹；
3. 如已开通 Network，检查套餐、到期时间和设备数量；
4. 打开 Mirrors，确认公开项目可以浏览；
5. 收藏 Status，遇到异常时先查看公告。

## 基本安全建议

- 不在聊天、工单或截图中暴露 Token、订阅地址和恢复代码；
- 公共设备使用后退出账户，不保存密码；
- 为重要分享设置密码和有效期；
- 收到异常登录提示时，从 Account 官方首页重新进入，不点击未知链接。

## 下一步

- [统一账户与安全](/docs/account-security/)
- [Drive 同步与分享指南](/docs/drive-guide/)
- [Network 客户端与线路选择](/docs/network-guide/)
- [常见问题排查](/docs/troubleshooting/)

---

<form class="docs-feedback" method="post" action="/docs/getting-started/feedback">
  <strong>这篇文档有帮助吗？</strong>
  <button name="helpful" value="1">有帮助</button>
  <button name="helpful" value="0">需要改进</button>
</form>
