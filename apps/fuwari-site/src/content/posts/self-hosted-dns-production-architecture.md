---
title: 自建 DNS 正式上线：从加密入口到分地域递归与可回滚路由
published: 2026-09-30
description: "记录 MatchAll DNS 如何在保留 DoH/DoT/DoQ、过滤、Global 严格 DNSSEC 与最终回退的前提下，用 dnsdist 将中国域名和国际域名路由到经过实测的递归器。"
tags: ["DNS", "DoH", "DoT", "DoQ", "dnsdist", "Unbound", "DNSSEC", "可观测性"]
category: 运维
draft: false
---

DNS 服务“能返回地址”并不等于可以投入生产。真正困难的是同时处理加密入口、访问控制、广告与恶意域名过滤、缓存、DNSSEC、地域 CDN 调度、上游故障，以及随时可执行的回滚。

经过多轮 Shadow、故障演练和分阶段验证，MatchAll DNS 的新解析架构已经上线。本文记录这套系统的设计方法、实测结论和安全边界。文中的公网地址、Token、私网网段、管理接口和内部主机信息均已隐藏。

## 当前生产拓扑

客户端统一使用加密 DNS 接入：

```text
Client
  ↓ DoH / DoT / DoQ
MatchAll Gateway
  ↓ 身份与访问控制
modDNS
  ↓ 广告、恶意域名与自定义规则
dnsdist
  ├─ China domain-set → AliDNS / DNSPod
  ├─ force-global     → Global Unbound
  └─ International    → Google Public DNS

最终回退：Global Unbound
测量探针：Shanghai Unbound（不参与生产回退）
```

Gateway 负责加密协议终止和用户策略，modDNS 在请求进入递归层之前完成过滤，dnsdist 只负责可审计的路由、健康检查与故障切换。这样，无论后端选择哪个解析器，广告与恶意域名过滤都不会被绕过。

公网 TCP/UDP 53 始终关闭，递归器不直接暴露在互联网；ECS 也保持关闭，因为当前链路不能可信地把真实客户端地址传递到递归层。用 Gateway、localhost 或 WireGuard 地址伪装客户端 ECS，只会制造错误的地理信号和新的隐私问题。

## 为什么没有坚持“全部自递归”

最初的架构由两个 Unbound 分别在海外和上海执行完整递归：

```text
Unbound → Root → TLD → Authoritative DNS
```

它的优点是信任边界清晰、DNSSEC 可由自己的根信任锚验证，也不会让一个公共递归器集中看到所有查询。但完整 China domain-set 的 Shadow 测试暴露出明显问题：上海自递归在大量长尾域名上出现更高的超时率，冷缓存 P95/P99 经常撞到测试上限。

更重要的是，China domain-set 只能说明“这个域名大概率与中国网络有关”，不能证明“它一定应该交给某个中国递归器”。因此列表不再被视为绝对真理，而是候选分类依据；最终后端选择必须由成功率、长尾延迟和 CDN 实际访问质量共同决定。

## 国内域名：AliDNS 与 DNSPod

国内路径现在由 AliDNS 和 DNSPod 组成 `public-cn` 池。生产请求不会同时发给两家抢答，也不会每次随机选择，而是使用 dnsdist 的一致性哈希策略，让同一 QNAME 尽量稳定落到同一个 provider。

AliDNS 有两个服务端点。早期配置虽然在数学上给了 AliDNS 与 DNSPod 相同的 provider 总权重，但哈希环只有极少的节点，导致 1024 个不同 QNAME 中约 95% 都落到 DNSPod。问题不在域名，而在一致性哈希环的离散度。

隔离环境使用本地 mock DNS 重新验证后，将权重扩大并固定 backend UUID 与 hash perturbation：

- AliDNS A：500；
- AliDNS B：500；
- DNSPod：1000。

10,000 个确定性 QNAME 的结果为：

| Provider | QNAME 数 | 占比 |
| --- | ---: | ---: |
| AliDNS | 5357 | 53.57% |
| DNSPod | 4643 | 46.43% |

AliDNS 两个端点内部为 2691 / 2666；重复查询没有映射漂移，dnsdist 重启后的映射指纹也保持一致。这个结果不追求每个小样本严格 50/50，而是保证样本扩大后收敛、同名稳定，并避免一个 provider 长期承担几乎全部流量。

故障链保持简单：

```text
AliDNS 单端点故障 → AliDNS 另一端点仍可服务
AliDNS 整体故障   → DNSPod
DNSPod 故障        → AliDNS
两个 provider 故障 → Global Unbound
```

上海 Unbound 只保留为 CN-East 测量探针，用来测返回 CDN 地址在大陆网络中的 TCP、TLS、TTFB 和路由质量，不再加入生产 fallback 链。

## 国际域名：Google 主解析，Global 最终回退

Google Public DNS 上线前先完成了 1024 域名、每个域名 A/AAAA 与 first/repeat 的 Shadow 对比。Google 侧没有出现查询超时，hard mismatch 约 0.76%；Global 自递归的 P99 约为 Google 的两倍。

在真实国际出口测点，对 Google 与 Global 返回的 CDN 地址进行 TCP、TLS 和 HTTP TTFB 抽样时，Google 答案的 TTFB 从约 84 ms 降至约 35 ms。上海测点只作为辅助诊断，不参与国际路径的晋级否决，因为国际请求的真实生产出口本来就在 Global 节点。

当前策略为：

```text
force-global 域名 → Global Unbound
China domain-set  → public-cn
其他国际域名       → Google Public DNS
Google provider down → Global Unbound
```

Google 两个端点互备，不做并发 race。对于 Google 返回的 `SERVFAIL`，dnsdist 2.1.2 使用原生可重启查询能力，同步且最多重试一次到 Global；不会在后台异步复制一个生产请求，也不会形成无限重试。

这里有一个明确限制：如果单个 UDP 请求恰好遇到网络黑洞，而健康检查尚未把 Google 判为 down，该请求仍可能超时。dnsdist 不会凭空重放一个没有收到响应的 UDP 请求。只有后端被健康检查判定为不可用后，后续请求才直接进入 Global。

## DNSSEC：两条不同的信任模型

Global Unbound 始终保留自己的完整递归和严格 DNSSEC validation：有效签名正常返回，已知 bogus 域名返回 `SERVFAIL`，它也是全系统最终可信回退。

Google 的 DNSSEC 行为通过了上线门槛：

- valid signed：`NOERROR + AD`；
- bogus：`SERVFAIL`；
- unsigned：正常返回且无 AD；
- signed NXDOMAIN：`NXDOMAIN + AD`；
- TCP DNSKEY：正常。

AliDNS/DNSPod 路径则明确接受公共递归器自身的 DNSSEC policy，不再承诺所有 bogus 域名都由本地根信任锚验证为 `SERVFAIL`。我们曾测试“公共 DNS → 本地 Unbound validator”，但上游没有提供本地完整重建信任链所需的全部材料，结果不仅 bogus 失败，valid、unsigned 与 signed NXDOMAIN 也大量 `SERVFAIL`。因此该方案被停止，而不是通过关闭 hardening 来伪装成功。

这是主动改变信任模型后的权衡：国内 CDN 调度和长尾性能得到改善，但对应域名会暴露给选中的公共递归器。系统不会把所有查询无脑转发给同一家公共 DNS，Global 自递归也不会被删除。

## Shadow 不阻塞生产请求

生产响应和测量系统完全解耦：

```text
生产后端 → 立即响应客户端
Shadow worker → 低速异步比较多个 resolver
```

Shadow 使用全局锁、队列上限、每 provider QPS、并发限制、超时和 circuit breaker。后端不健康时停止向它发送 Shadow，请求积压超过上限则丢弃测量任务，而不是拖慢生产。

实验级域名数据只短期保留，并自动过期，不关联客户端 IP、Token 或用户身份。长期只保留聚合指标、晋级/降级原因和当前路由集合。用户在网站中主动开启的短期查询记录属于 Gateway 的独立隐私功能，不等于递归器长期记录所有查询。

## 怎样证明故障切换真的可用

“写了 fallback 配置”不是验证。上线前在隔离环境中逐项停止后端，确认：

1. AliDNS A down 后由 B 和 DNSPod 承担；
2. AliDNS B down 后由 A 和 DNSPod 承担；
3. AliDNS provider 整体 down 后全部转到 DNSPod；
4. DNSPod down 后全部转到 AliDNS；
5. 两个中国 provider 同时 down 后进入 Global；
6. Google 整体 down 后国际域名进入 Global；
7. 连续健康检查达到恢复阈值后才重新上线；
8. 恢复后的 QNAME 映射回到原来的稳定指纹。

每个场景都要求 unknown=0、query failure=0、无 fallback loop。生产上线后又执行 5、15、30、60 分钟门禁，持续验证 provider health、drops、send errors、DNSSEC、过滤计数、服务重启与资源余量。

## 可观测性与回滚

长期监控至少覆盖：

- 每个 resolver/provider 的查询、响应和健康状态；
- timeout、SERVFAIL、NXDOMAIN、REFUSED；
- public-cn 与 Google 到 Global 的 fallback；
- p50、p95、p99 解析延迟；
- Shadow queue depth 与 dropped；
- dnsdist、Unbound 的 CPU、内存、队列、重启和 OOM；
- modDNS blocked queries；
- CDN 的 TCP、TLS、HTTP TTFB 与必要的 MTR。

所有生产模式都有独立回滚：国际 Google 可以单独恢复为 Global，不影响 China；China 也可以逐级从完整集合退回 cohort、canary 或全部 Global。回滚不要求重启 Gateway、modDNS 或整台服务器。

## 这次上线带来的经验

1. **域名列表只是候选来源。** 地域标签不能替代真实成功率与 CDN 质量。
2. **平均延迟会掩盖长尾。** P95/P99、timeout 和真实 TTFB 比单次 `dig` 更重要。
3. **缓存测试必须紧邻重复。** 同一 QNAME/QTYPE、同一 endpoint、同一 flags，并确保 repeat 间隔小于 TTL；把完整 first pass 跑完再整体 repeat，不能叫可靠 warm cache。
4. **一致性哈希的小权重可能严重偏斜。** provider 总权重相等，不代表只有几个 ring points 时分布就合理。
5. **正常 CDN 地址差异不是 hard mismatch。** 真正需要阻断的是 `SERVFAIL ↔ NOERROR`、`NXDOMAIN ↔ NOERROR` 和 DNSSEC validation disagreement。
6. **回退链越短越好。** 选定 provider → 另一 provider/Global；不把每个解析器串成长链。
7. **隐私、性能与验证能力必须显式权衡。** 公共递归更快不代表可以忽略它看到查询的事实。

## 总结

这套 DNS 的目标并不是“让所有国内域名都走国内 DNS”，也不是“找一个最快的公共 DNS 全部转发”。最终原则是：入口、过滤、策略和回滚掌握在自己手中；每类域名选择经过数据证明更适合的解析路径；任何公共 resolver 都不能取代 Global 自递归作为最终可信回退。

当前生产形态可以概括为：

```text
中国域名 → AliDNS / DNSPod（一致性哈希、互备）
国际域名 → Google Public DNS
强制可信域名与所有最终故障 → Global Unbound strict DNSSEC
上海节点 → CN-East 测量探针
```

上线不是终点。后续仍会依据失败率、长尾、CDN TTFB、provider flap 和用户侧异常持续降级或调整，而不是为了维持一张漂亮的架构图忽略真实数据。

相关入口：

- [MatchAll DNS](https://dns.maximoraverse.org/)
- [MatchAll 技术博客](https://blog.maximoraverse.org/)
