---
title: MatchAll 快速开始
summary: 从邀请注册、服务权限确认到第一次使用与同步核对。
category: 入门
version: 1.1
updated: 2026-10-01
---

这篇指南适合第一次使用 MatchAll 的用户。统一账户用于登录，服务权限、套餐和授权由各业务分别管理。注册成功不代表所有服务已经开通。

## 开始前准备

- 一个仍然有效的邀请码或邀请入口；
- 能接收账户验证和恢复邮件的邮箱；
- 支持 Cookie、JavaScript 和 HTTPS 的现代浏览器；
- 准确的设备时间，时间偏差可能导致安全校验失败。

只在 `maximoraverse.org` 及其子域名输入登录信息。工作人员不会索要密码、验证码、恢复代码、订阅地址或 Token。

## 1. 创建或登录统一账户

已有账户：从 [Console 登录](https://console.maximoraverse.org/login)进入，认证成功后返回控制台。

新用户：使用 [邀请码注册入口](https://auth.maximoraverse.org/register)，按页面要求完成邀请校验与邮箱验证。当前入口是邀请注册，不是无需邀请的开放注册。没有邀请或邀请过期时，先向邀请方确认，或查看[联系与支持](https://www.maximoraverse.org/contact/)；不保证获得邀请或自动开通服务。

在账户中心确认显示名称和邮箱正确。若出现验证码，这是正常风控步骤。连续失败时不要反复提交，先关闭会改写页面的扩展、确认系统时间，再从官方入口重新进入。

## 2. 进入需要的服务，确认权限

只需选择自己准备使用的服务，不必全部开通。首次进入服务时，浏览器可能跳转到 Account 后再返回，这是标准登录流程。Console 只显示汇总与入口，不代替业务开通。

### Drive：第一次文件访问

打开 [Drive](https://drive.maximoraverse.org/login)，选择统一登录并确认能看到自己的文件列表、容量和账户。页面仍提示未授权或停用时，按服务提示联系支持，不要重新注册多个账户。

确认可用后，可自行创建一个不含个人敏感信息的测试文件夹，再按 [Drive 同步与分享指南](/docs/drive-guide/)配置客户端。成功标志是原服务能看到自己的文件，而非 Console 出现关联字样。

### Network：先核对套餐，再配置客户端

打开 [Network](https://proxyservice.maximoraverse.org/login)，检查套餐、到期时间、剩余流量和设备限制。统一账户登录不等于拥有有效套餐；没有套餐时先阅读原服务的开通、价格和退款说明，再自行决定是否购买。

已有有效套餐后，按 [Network 指南](/docs/network-guide/)导入自己的订阅并检查连接。不要把订阅地址发给他人，也不要把 Console 的快照当作实时节点连通性证明。

### DNS：从账户页复制自己的配置

打开 [DNS 账户](https://dns.maximoraverse.org/login)，确认账户状态，按设备选择页面提供的 DoH、DoT 或 DoQ 地址。不要手工拼接令牌或使用他人的截图配置。

按 [DNS 配置入口与验证](/docs/dns-guide/)完成配置，再到原账户页核对请求统计。Console 尚未接入 DNS 账户快照，无法据此判断 DNS 是否开通；设备配置、个人过滤开通与账号登录是不同步骤。

### Mirrors：先浏览，再按项目确认授权

打开 [Mirrors](https://mirrors.maximoraverse.org/)，浏览公开项目、版本和校验信息。需要登录或授权时，进入[软件账户页](https://mirrors.maximoraverse.org/account)，按项目要求核对权限；浏览公开项目不等于创建订单或获得付费授权。

第一次下载先阅读 [Mirrors 用户指南](/docs/mirrors-user/)，下载后核对版本与 SHA-256。更新 Token 只在需要自动更新时按指南管理，不要公开分享。

## 3. 回到 Console，确认汇总时效

[打开 Console](https://console.maximoraverse.org/console)确认当前身份。已登录的统一账户和业务关联状态是两回事；服务数据通过只读快照同步，不保证立即更新。

- 未关联：当前有效快照中没有匹配账户，先在原服务确认登录与权限；
- 等待同步：尚无可用快照，不能判断是否关联；
- 同步异常：快照不可读或不完整，不等于业务服务故障；
- 数据过期：旧快照不代表当前状态；
- 汇总正常：仅表示读到了有效快照，不表示套餐有效或服务健康。

查看各服务的快照更新时间，等待下一次同步后再刷新。刷新 Console 不会触发同步任务。长期没有更新时，反馈发生时间和已打码提示，原服务的账户与用量信息优先。

这些细分状态需要相应 Console 版本部署后才会显示；旧版 Console 只显示总体同步时间时，也应进入原服务确认。

## 遇到中断时

- 登录页取消、返回或会话过期：从 [Console 登录](https://console.maximoraverse.org/login)重新开始，不重复提交旧回调页面；
- 注册未完成：回到邀请入口确认当前步骤，不假定账户已经创建；
- 某项服务打不开：先查看 [Status](https://status.maximoraverse.org/)，再按[常见问题排查](/docs/troubleshooting/)核对该服务；
- 状态页正常只说明其公开探测范围，不保证登录、上传、下载或所有设备线路都正常。

## 基本安全建议

- 不在聊天、工单或截图中暴露 Token、订阅地址和恢复代码；
- 公共设备使用后退出账户，不保存密码；
- 为重要分享设置密码和有效期；
- 收到异常登录提示时，从 Account 官方首页重新进入，不点击未知链接。

## 下一步

- [统一账户与安全](/docs/account-security/)
- [Drive 同步与分享指南](/docs/drive-guide/)
- [Network 客户端与线路选择](/docs/network-guide/)
- [DNS 配置入口与验证](/docs/dns-guide/)
- [常见问题排查](/docs/troubleshooting/)
