---
title: DNS 配置入口与验证
description: 从原 DNS 账户获取个人地址，按设备配置并验证，不暴露令牌。
lastUpdated: 2026-10-01
---

DNS 的个人接入地址、配额、过滤与统计仍在原 DNS 账户页管理。Console 提供入口，不复制或保存你的个人 DNS 令牌。

## 1. 进入账户，确认状态

从 [DNS 官方登录入口](https://dns.maximoraverse.org/login)进入，确认当前账户可用，再复制页面展示的个人配置。统一登录本身不代表设备已经使用该 DNS，也不代表自定义过滤已开通。

## 2. 按设备选择接入方式

[DNS 原生配置指南](https://dns.maximoraverse.org/guide)是设备步骤和当前接入参数的维护位置：

- [Android 私人 DNS](https://dns.maximoraverse.org/guide#android)：按指南填写账户页的 DoT 主机名；
- [Apple 设备](https://dns.maximoraverse.org/guide#apple)：从自己的账户页获取描述文件，检查内容后自行决定是否安装；
- [浏览器与 Windows](https://dns.maximoraverse.org/guide#browser)：复制完整 DoH 地址，不省略路径与令牌；
- [DoQ 客户端](https://dns.maximoraverse.org/guide#doq)：先确认客户端支持 DNS over QUIC；
- [过滤与递归](https://dns.maximoraverse.org/guide#filter)：了解主动开通过滤与仅保存规则的区别。

这里不提供可直接复制的个人地址、服务器 IP 或替代上游。以原账户页与配置指南为准，不要手工猜测地址，不要关闭证书校验。

## 3. 验证与恢复

配置后按[验证与排错](https://dns.maximoraverse.org/guide#verify)核对原账户页的请求统计。浏览器能打开网页不一定证明使用了目标 DNS；缓存、应用内 DNS、代理或 VPN 都可能影响结果。查询明细默认关闭，不必为了入门就启用。

如果出现问题，按指南恢复原设备设置后再排查。恢复原设置后，后续查询可能不再经过 MatchAll。不要反复重置账号令牌；重置会使旧设备地址失效，需要重新配置。

反馈时提供设备、客户端版本、协议、发生时间及已打码的错误提示。不要提交完整个人地址、令牌或描述文件。

## 返回入口

- [MatchAll 快速开始](/docs/getting-started/)
- [Console](https://console.maximoraverse.org/console)
- [联系与支持](https://www.maximoraverse.org/contact/)

---

<form class="docs-feedback" method="post" action="/docs/dns-guide/feedback">
  <strong>这篇文档有帮助吗？</strong>
  <button name="helpful" value="1">有帮助</button>
  <button name="helpful" value="0">需要改进</button>
</form>
