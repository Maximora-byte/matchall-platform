---
title: Mirrors 下载与授权
description: 查找版本、选择 Release Channel、校验 SHA-256、使用 CDK 和更新 Token。
lastUpdated: 2026-09-30
---

[MatchAll Mirrors](https://mirrors.maximoraverse.org/) 提供软件项目、版本和多平台制品。公开项目可以直接浏览；私有或付费项目需要相应授权。

## 找到正确制品

进入项目页后依次确认：

1. 项目名称和发布者；
2. 版本号与发布时间；
3. 操作系统；
4. CPU 架构，例如 x86_64、arm64；
5. 文件类型、大小和 SHA-256。

不要只凭文件名判断架构。下载错误架构通常会表现为无法启动或“格式不正确”。

## Release Channel

- **stable**：经过稳定性验证，适合生产和日常使用；
- **beta**：即将发布的功能，可能仍有兼容性问题；
- **alpha**：早期测试，仅用于评估，不建议承载重要数据。

从 alpha 或 beta 切回 stable 前先确认数据格式是否向后兼容。重要环境升级前应保留配置和数据备份。

## 校验下载

项目页显示的 SHA-256 用于确认文件未损坏或被替换。下载完成后使用系统工具计算哈希，并与页面逐字符比较。

Linux：

```bash
sha256sum <文件名>
```

macOS：

```bash
shasum -a 256 <文件名>
```

Windows PowerShell：

```powershell
Get-FileHash <文件名> -Algorithm SHA256
```

哈希不一致时不要运行文件，应删除并重新下载；再次失败时记录项目、版本、文件名和时间。

## 授权、CDK 与更新 Token

付费项目可通过订单或 CDK 获得访问权。CDK 通常只能兑换一次，请在已登录正确账户后操作。自动更新程序应使用专用、可撤销的更新 Token，而不是账户密码。

- 不把 Token 写进公开仓库、镜像或日志；
- 每个环境使用独立 Token，便于撤销；
- 设备淘汰或 CI 停用后立即撤销；
- 收到 401/403 时先检查授权和到期状态，不要高频重试。

## 下载失败排查

确认项目授权、版本是否仍发布、浏览器是否拦截下载，并查看 Status。提交问题时提供项目名、版本、平台、架构、HTTP 状态码和时间，不要发送 Token 或带签名的下载 URL。

---

<form class="docs-feedback" method="post" action="/docs/mirrors-user/feedback">
  <strong>这篇文档有帮助吗？</strong>
  <button name="helpful" value="1">有帮助</button>
  <button name="helpful" value="0">需要改进</button>
</form>
