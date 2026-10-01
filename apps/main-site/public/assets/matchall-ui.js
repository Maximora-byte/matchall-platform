(() => {
  "use strict";

  const VERSION = "20260930astro2";
  const COOKIE = "matchall_lang";
  const supported = new Set(["zh", "en", "ja"]);
  const hostname = location.hostname;
  const textRecords = [];
  const attrRecords = [];
  const seenText = new WeakSet();
  const seenAttrs = new WeakMap();

  const common = {
    en: {
      "总览": "Overview", "账户": "Account", "网盘": "Drive", "网络": "Network", "镜像": "Mirrors", "博客": "Blog", "控制台": "Console", "状态": "Status", "服务状态": "Service status", "用户中心 →": "Console →",
      "全部服务": "All services", "统一账户": "Account", "统一登录": "Sign in", "统一登录 →": "Sign in →", "注册账户": "Register", "使用邀请码注册": "Register with invite", "使用邀请码注册 →": "Register with invite →", "进入服务 →": "Open service →", "浏览项目 →": "Browse projects →",
      "联系方式": "Contact", "联系我们": "Contact", "隐私政策": "Privacy", "服务条款": "Terms", "退款政策": "Refunds", "定价说明": "Pricing", "账户中心": "Account center",
      "主要服务": "Primary services", "MatchAll 服务": "MatchAll services", "打开服务菜单": "Open service menu", "关闭菜单": "Close menu", "MatchAll Drive 首页": "MatchAll Drive home", "MatchAll Network 首页": "MatchAll Network home",
      "联系": "Contact", "隐私": "Privacy", "条款": "Terms", "定价": "Pricing", "关于": "About",
      "项目主页 ↗": "Project website ↗", "更新 API": "Update API", "下载": "Download", "搜索": "Search", "MatchAll 登录": "MatchAll sign in",
      "发布管理": "Publishing", "项目目录": "Project directory", "查看版本 →": "View releases →", "等待首个版本": "Awaiting first release",
      "累计下载": "Downloads", "发布项目": "Projects", "可用版本": "Releases", "平台": "Platform", "文件": "File", "大小": "Size", "外部文件": "External file",
      "返回项目目录": "Back to projects", "该项目尚未发布版本。": "No releases have been published yet.", "没有找到匹配项目。": "No matching projects found.", "跳到主要内容": "Skip to content",
      "价格": "Pricing", "我的授权": "My access", "收费与发布管理": "Billing & publishing", "退出": "Sign out", "免费": "Free", "付费": "Paid", "已解锁": "Unlocked"
    },
    ja: {
      "总览": "概要", "账户": "アカウント", "网盘": "ドライブ", "网络": "ネットワーク", "镜像": "ミラー", "博客": "ブログ", "控制台": "コンソール", "状态": "稼働状況", "服务状态": "サービス状態", "用户中心 →": "コンソール →",
      "全部服务": "すべてのサービス", "统一账户": "統合アカウント", "统一登录": "ログイン", "统一登录 →": "ログイン →", "注册账户": "登録", "使用邀请码注册": "招待コードで登録", "使用邀请码注册 →": "招待コードで登録 →", "进入服务 →": "サービスを開く →", "浏览项目 →": "プロジェクトを見る →",
      "联系方式": "お問い合わせ", "联系我们": "お問い合わせ", "隐私政策": "プライバシー", "服务条款": "利用規約", "退款政策": "返金ポリシー", "定价说明": "料金", "账户中心": "アカウントセンター",
      "主要服务": "主要サービス", "MatchAll 服务": "MatchAll サービス", "打开服务菜单": "サービスメニューを開く", "关闭菜单": "メニューを閉じる", "MatchAll Drive 首页": "MatchAll Drive ホーム", "MatchAll Network 首页": "MatchAll Network ホーム",
      "联系": "連絡先", "隐私": "プライバシー", "条款": "規約", "定价": "料金", "关于": "概要",
      "项目主页 ↗": "プロジェクトサイト ↗", "更新 API": "更新 API", "下载": "ダウンロード", "搜索": "検索", "MatchAll 登录": "MatchAll ログイン",
      "发布管理": "リリース管理", "项目目录": "プロジェクト一覧", "查看版本 →": "リリースを見る →", "等待首个版本": "初回リリース待ち",
      "累计下载": "ダウンロード", "发布项目": "プロジェクト", "可用版本": "リリース", "平台": "プラットフォーム", "文件": "ファイル", "大小": "サイズ", "外部文件": "外部ファイル",
      "返回项目目录": "一覧へ戻る", "该项目尚未发布版本。": "このプロジェクトにはまだリリースがありません。", "没有找到匹配项目。": "該当するプロジェクトはありません。", "跳到主要内容": "本文へ移動",
      "价格": "料金", "我的授权": "利用権", "收费与发布管理": "課金・リリース管理", "退出": "ログアウト", "免费": "無料", "付费": "有料", "已解锁": "利用可能"
    }
  };

  const hostText = {
    "www.maximoraverse.org": {
      en: {
        "连接每一种": "Connect every", "数字生活。": "digital life.",
        "MatchAll 将统一账户、私人云存储、全球网络、隐私 DNS、软件分发与技术内容连接在同一体验中。清晰、可靠，也更像一个整体。": "MatchAll brings identity, private cloud storage, global networking, privacy-focused DNS, software distribution and technical content into one clear, reliable experience.",
        "探索全部服务 ↓": "Explore all services ↓", "统一身份认证": "Unified identity", "隐私与政策公开": "Transparent policies", "多端访问": "Multi-device access", "持续维护": "Continuously maintained",
        "每项服务，各司其职": "One ecosystem, focused services", "统一的视觉与账户体验，背后仍由独立服务承担明确职责。": "A unified brand and account experience, backed by services with clear responsibilities.",
        "连接多个国家和地区，多线路与多设备支持，让跨区域访问更顺畅。": "Multi-region acceleration, flexible routes and support for all your devices.",
        "大容量私人云存储、多端同步与不限速下载，重要文件随时可取。": "Large private cloud storage, cross-device sync and unrestricted downloads.",
        "支持 DoH、DoT 与 DoQ 的加密 DNS，提供按账号过滤、自定义规则、统计与自建递归解析。": "Encrypted DNS over DoH, DoT and DoQ with per-account filtering, custom rules, statistics and recursive resolution.",
        "一个安全身份访问全部服务。": "One secure identity for every service.", "版本发布、更新 API 与下载分发。": "Releases, update APIs and download distribution.",
        "技术实践、产品动态与公告。": "Engineering notes, product updates and announcements.", "统一查看容量、套餐、授权与账户状态。": "View storage, plans, licenses and account status in one place.", "服务可用率、响应时间与事件记录。": "Service uptime, response time and incident history.", "定价、条款、隐私与退款说明。": "Pricing, terms, privacy and refund information."
      },
      ja: {
        "连接每一种": "あらゆる", "数字生活。": "デジタル体験をつなぐ。",
        "MatchAll 将统一账户、私人云存储、全球网络、隐私 DNS、软件分发与技术内容连接在同一体验中。清晰、可靠，也更像一个整体。": "MatchAll は統合アカウント、プライベートクラウド、グローバルネットワーク、プライバシー重視の DNS、ソフトウェア配信、技術コンテンツを一つの明快で信頼できる体験につなぎます。",
        "探索全部服务 ↓": "サービスを見る ↓", "统一身份认证": "統合認証", "隐私与政策公开": "透明なポリシー", "多端访问": "マルチデバイス", "持续维护": "継続的な運用",
        "每项服务，各司其职": "一つの体験、明確な役割", "统一的视觉与账户体验，背后仍由独立服务承担明确职责。": "統一されたブランドとアカウント体験を、役割の明確な各サービスが支えます。",
        "连接多个国家和地区，多线路与多设备支持，让跨区域访问更顺畅。": "複数地域・回線・デバイスに対応したネットワーク体験。",
        "大容量私人云存储、多端同步与不限速下载，重要文件随时可取。": "大容量のプライベートクラウド、同期、高速ダウンロード。",
        "支持 DoH、DoT 与 DoQ 的加密 DNS，提供按账号过滤、自定义规则、统计与自建递归解析。": "DoH、DoT、DoQ に対応した暗号化 DNS。アカウント別フィルタ、カスタムルール、統計、再帰解析を提供します。",
        "一个安全身份访问全部服务。": "一つの安全なIDですべてのサービスへ。", "版本发布、更新 API 与下载分发。": "リリース、更新 API、ダウンロード配信。",
        "技术实践、产品动态与公告。": "技術記事、製品アップデート、お知らせ。", "统一查看容量、套餐、授权与账户状态。": "容量、プラン、ライセンス、アカウント状態を一元確認。", "服务可用率、响应时间与事件记录。": "稼働率、応答時間、障害履歴を公開。", "定价、条款、隐私与退款说明。": "料金、規約、プライバシー、返金情報。"
      }
    },
    "auth.maximoraverse.org": {
      en: {
        "一个账户，": "One account,", "连接全部服务。": "every service.", "统一管理身份、登录与安全验证。一次登录，即可自然切换 MatchAll Network、Drive、Blog 与 Mirrors。": "Manage identity, sign-in and security in one place. Sign in once and move naturally between MatchAll Network, Drive, Blog and Mirrors.",
        "登录统一账户 →": "Sign in →", "打开账户中心": "Open account center", "单点登录": "Single sign-on", "双重人机验证": "Dual CAPTCHA", "邮箱验证": "Email verification",
        "一个身份": "One identity", "跨服务安全访问": "Secure service access", "一次登录": "Sign in once", "标准协议": "Open standard", "身份保护": "Identity protection",
        "一个入口，抵达每项服务": "One account for every service", "统一身份负责“你是谁”，每项业务继续专注自己的服务与权限。": "Identity answers who you are; each service keeps control of its own features and permissions.",
        "多个国家和地区的网络加速服务，多线路、多设备统一管理。": "Multi-region network acceleration with routes and devices managed in one place.", "大容量私人云存储，支持多端同步与不限速下载。": "Large private cloud storage with sync and unrestricted downloads.",
        "产品更新、技术实践与重要公告。": "Product updates, engineering notes and announcements.", "软件版本、更新 API 与高速下载分发。": "Software releases, update APIs and fast distribution.",
        "规则清晰，信息公开": "Clear rules, transparent information", "重要政策集中展示，减少信息差，让每次使用都有清楚边界。": "Important policies are kept together so every service has clear boundaries.",
        "工单、Telegram 与正式服务渠道。": "Tickets, Telegram and official support channels.", "账户与服务数据的处理方式。": "How account and service data are handled.", "统一账户及各项服务使用规则。": "Rules for the unified account and every service.", "网络服务订单的退款条件。": "Refund terms for network service orders.", "套餐、周期、节点与计费倍率。": "Plans, billing periods, nodes and usage rates.",
        "从一个安全账户开始。": "Start with one secure account.", "邀请码注册、邮箱验证与统一登录已经准备好。": "Invite-only registration, email verification and unified sign-in are ready."
      },
      ja: {
        "一个账户，": "一つのアカウントで、", "连接全部服务。": "すべてのサービスへ。", "统一管理身份、登录与安全验证。一次登录，即可自然切换 MatchAll Network、Drive、Blog 与 Mirrors。": "ID、ログイン、セキュリティを一元管理。一度のログインで Network、Drive、Blog、Mirrors を利用できます。",
        "登录统一账户 →": "ログイン →", "打开账户中心": "アカウントセンター", "单点登录": "シングルサインオン", "双重人机验证": "二重 CAPTCHA", "邮箱验证": "メール認証",
        "一个身份": "一つのID", "跨服务安全访问": "安全なサービスアクセス", "一次登录": "一度のログイン", "标准协议": "標準プロトコル", "身份保护": "ID保護",
        "一个入口，抵达每项服务": "一つの入口ですべてのサービスへ", "统一身份负责“你是谁”，每项业务继续专注自己的服务与权限。": "統合IDが本人確認を担い、各サービスが機能と権限を管理します。",
        "多个国家和地区的网络加速服务，多线路、多设备统一管理。": "複数地域のネットワーク、回線、デバイスを一元管理。", "大容量私人云存储，支持多端同步与不限速下载。": "大容量プライベートクラウド、同期、高速ダウンロード。",
        "产品更新、技术实践与重要公告。": "製品アップデート、技術記事、お知らせ。", "软件版本、更新 API 与高速下载分发。": "ソフトウェア配信、更新 API、高速ダウンロード。",
        "规则清晰，信息公开": "明確なルールと透明性", "重要政策集中展示，减少信息差，让每次使用都有清楚边界。": "重要なポリシーを一か所にまとめ、サービスの境界を明確にします。",
        "工单、Telegram 与正式服务渠道。": "チケット、Telegram、公式サポート。", "账户与服务数据的处理方式。": "アカウントとサービスデータの取扱い。", "统一账户及各项服务使用规则。": "統合アカウントと各サービスのルール。", "网络服务订单的退款条件。": "ネットワークサービスの返金条件。", "套餐、周期、节点与计费倍率。": "プラン、期間、ノード、課金倍率。",
        "从一个安全账户开始。": "安全なアカウントから始めましょう。", "邀请码注册、邮箱验证与统一登录已经准备好。": "招待登録、メール認証、統合ログインに対応しています。"
      }
    },
    "drive.maximoraverse.org": {
      en: {
        "大容量空间，": "More room for", "下载不设限。": "everything.", "为重要文件准备的私人云端空间。集中保存照片、视频与工作资料，在所有设备上自然同步，随时以当前网络的完整速度取回。": "Private cloud space for the files that matter. Keep photos, videos and work together, sync across devices and download at the full speed of your connection.",
        "进入我的网盘": "Open my Drive", "桌面与移动端": "Desktop and mobile", "私人文件空间": "Private file space", "空间够大，体验够快": "Room to grow, speed to move", "从浏览器到桌面与移动设备，用同一个 MatchAll 账户安全访问每一份文件。": "Access every file securely from the browser, desktop or mobile with one MatchAll account.",
        "大容量存储": "Large storage", "集中管理高清照片、大型视频、项目文件与个人资料。": "Keep photos, large videos, project files and personal data together.", "不限速下载": "Unrestricted downloads", "不人为限制下载速度，充分利用当前网络连接能力。": "No artificial download cap—use the full capacity of your connection.", "跨平台同步": "Cross-platform sync", "支持浏览器、桌面客户端、移动端与 WebDAV 访问。": "Use the browser, desktop and mobile clients, or WebDAV.", "统一安全账户": "Unified secure account", "注册、登录、找回与身份保护统一由 MatchAll Account 管理。": "Registration, sign-in, recovery and identity protection are managed by MatchAll Account.",
        "现在，把文件放回自己手中。": "Put your files back in your hands.", "一个账户，连接 MatchAll 的所有服务。": "One account connects every MatchAll service.", "登录并开始使用 →": "Sign in and get started →", "进入我的网盘 →": "Open my Drive →"
      },
      ja: {
        "大容量空间，": "もっと大きな容量、", "下载不设限。": "制限のないダウンロード。", "为重要文件准备的私人云端空间。集中保存照片、视频与工作资料，在所有设备上自然同步，随时以当前网络的完整速度取回。": "大切なファイルのためのプライベートクラウド。写真、動画、仕事の資料をまとめ、デバイス間で同期し、回線速度を活かしてダウンロードできます。",
        "进入我的网盘": "Drive を開く", "桌面与移动端": "デスクトップとモバイル", "私人文件空间": "プライベート領域", "空间够大，体验够快": "大容量で、快適に", "从浏览器到桌面与移动设备，用同一个 MatchAll 账户安全访问每一份文件。": "ブラウザ、デスクトップ、モバイルから一つの MatchAll アカウントで安全にアクセス。",
        "大容量存储": "大容量ストレージ", "集中管理高清照片、大型视频、项目文件与个人资料。": "写真、動画、プロジェクト、個人データをまとめて管理。", "不限速下载": "高速ダウンロード", "不人为限制下载速度，充分利用当前网络连接能力。": "人為的な速度制限を設けず、回線性能を活用します。", "跨平台同步": "クロスプラットフォーム同期", "支持浏览器、桌面客户端、移动端与 WebDAV 访问。": "ブラウザ、デスクトップ、モバイル、WebDAV に対応。", "统一安全账户": "安全な統合アカウント", "注册、登录、找回与身份保护统一由 MatchAll Account 管理。": "登録、ログイン、復旧、ID保護を MatchAll Account が管理します。",
        "现在，把文件放回自己手中。": "ファイルを自分の手に。", "一个账户，连接 MatchAll 的所有服务。": "一つのアカウントですべての MatchAll サービスへ。", "登录并开始使用 →": "ログインして始める →", "进入我的网盘 →": "Drive を開く →"
      }
    },
    "proxyservice.maximoraverse.org": {
      en: {
        "连接多个国家与地区，": "Connect across regions,", "让网络更顺畅。": "move with confidence.", "灵活线路与多端支持，为学习、工作和跨区域访问提供清晰、稳定的连接体验。订阅、节点与设备，都由一个账户管理。": "Flexible routes and multi-device support deliver a clear, stable experience for study, work and cross-region access. Manage subscriptions, nodes and devices from one account.",
        "进入服务中心": "Open service center", "多国家与地区": "Multiple regions", "多线路选择": "Flexible routes", "三台设备": "Three devices", "统一账户管理": "Unified account",
        "从本地，到更广阔的网络": "From local to global", "清晰的订阅管理、丰富的地区选择与跨平台客户端支持，统一收进一个账户。": "Clear subscription management, regional choice and cross-platform clients, all under one account.",
        "全球地区覆盖": "Global coverage", "提供多个国家与地区的线路选择，按实际需求灵活连接。": "Choose routes across multiple countries and regions to match your needs.", "稳定网络加速": "Stable acceleration", "面向跨区域访问优化链路，改善高延迟与不稳定体验。": "Optimized cross-region routes improve latency and stability.", "多设备支持": "Multi-device support", "便捷导入常用桌面与移动客户端，随时管理订阅。": "Import into popular desktop and mobile clients and manage subscriptions anywhere.", "统一账户中心": "Unified account center", "通过 MatchAll Account 完成注册、登录与安全验证。": "Registration, sign-in and security are handled by MatchAll Account.",
        "一个账户，连接更多可能。": "One account. More possibilities.", "登录后查看可用计划、线路与使用教程。": "Sign in to view plans, routes and setup guides.", "统一登录 →": "Sign in →", "进入服务中心 →": "Open service center →"
      },
      ja: {
        "连接多个国家与地区，": "複数の国と地域へ、", "让网络更顺畅。": "よりスムーズにつながる。", "灵活线路与多端支持，为学习、工作和跨区域访问提供清晰、稳定的连接体验。订阅、节点与设备，都由一个账户管理。": "柔軟な回線とマルチデバイス対応で、学習、仕事、地域をまたぐアクセスを安定化。サブスクリプション、ノード、デバイスを一元管理します。",
        "进入服务中心": "サービスセンター", "多国家与地区": "複数の国と地域", "多线路选择": "複数回線", "三台设备": "3台のデバイス", "统一账户管理": "統合アカウント",
        "从本地，到更广阔的网络": "ローカルから世界へ", "清晰的订阅管理、丰富的地区选择与跨平台客户端支持，统一收进一个账户。": "サブスクリプション、地域、各種クライアントを一つのアカウントで管理。",
        "全球地区覆盖": "グローバル対応", "提供多个国家与地区的线路选择，按实际需求灵活连接。": "複数の国と地域から用途に合う回線を選択。", "稳定网络加速": "安定した高速化", "面向跨区域访问优化链路，改善高延迟与不稳定体验。": "地域間アクセスを最適化し、遅延と不安定さを改善。", "多设备支持": "マルチデバイス", "便捷导入常用桌面与移动客户端，随时管理订阅。": "主要なデスクトップ・モバイルクライアントで利用可能。", "统一账户中心": "統合アカウントセンター", "通过 MatchAll Account 完成注册、登录与安全验证。": "登録、ログイン、セキュリティを MatchAll Account が管理。",
        "一个账户，连接更多可能。": "一つのアカウントで、もっと広く。", "登录后查看可用计划、线路与使用教程。": "ログインしてプラン、回線、ガイドを確認。", "统一登录 →": "ログイン →", "进入服务中心 →": "サービスセンター →"
      }
    },
    "mirrors.maximoraverse.org": {
      en: {
        "让软件更新": "Deliver software", "更快抵达。": "updates faster.", "面向开源项目和独立开发者的版本发布、更新检查与下载分发平台。稳定版、Beta、Alpha，多系统架构与 SHA-256 校验都在一个清晰目录中。": "Release, update-check and download distribution for open-source projects and independent developers. Stable, Beta and Alpha channels, multiple platforms and SHA-256 verification in one directory.",
        "SHA-256 校验": "SHA-256 verified", "选择项目，查看版本、平台与校验信息": "Choose a project to inspect releases, platforms and checksums", "搜索项目名称": "Search projects", "软件分发与更新基础设施": "Software distribution and update infrastructure",
        "选择访问方案": "Choose an access plan", "Mirrors 拥有独立订单与授权系统；购买记录不会与 Network 套餐混合。": "Mirrors has its own orders and licensing system. Purchases remain separate from Network plans.", "收费系统已经就绪，管理员尚未发布商品价格。": "Billing is ready. No products have been published yet.",
        "我的授权": "My access", "管理购买记录、CDK、有效授权与客户端更新 Token。": "Manage purchases, CDKs, active entitlements and updater tokens.", "兑换 CDK": "Redeem CDK", "输入管理员或合作方提供的兑换码。": "Enter a redemption code from an administrator or partner.", "兑换": "Redeem", "客户端 Token": "Client tokens", "用于更新 API 的 Bearer Token，仅在创建时显示一次。": "Bearer tokens for the update API. Each token is shown only once.", "创建": "Create", "有效授权": "Active entitlements", "购买新方案": "Buy a plan", "订单记录": "Order history", "更新 Token": "Updater tokens",
        "方案": "Plan", "来源": "Source", "开始": "Starts", "到期": "Expires", "状态": "Status", "订单号": "Order", "商品": "Product", "金额": "Amount", "时间": "Time", "名称": "Name", "创建时间": "Created", "最近使用": "Last used", "撤销": "Revoke", "暂无授权": "No entitlements", "暂无订单": "No orders", "暂无 Token": "No tokens", "永久": "Lifetime", "未使用": "Never used", "已撤销": "Revoked", "有效": "Active", "失效": "Inactive",
        "解锁全部付费项目": "Unlock all paid projects", "解锁指定项目": "Unlock selected projects", "网页下载与更新 API": "Web downloads and update API", "可撤销设备 Token": "Revocable device tokens", "安全结账": "Secure checkout", "提交订单": "Place order", "登录后购买": "Sign in to buy", "免费项目": "Free project", "账户已解锁": "Unlocked for your account", "需要购买": "Purchase required", "需要访问授权": "Access required", "请购买对应商品或在账户中心兑换 CDK。": "Buy the matching product or redeem a CDK in your account.", "购买访问权": "Buy access", "🔒 解锁": "🔒 Unlock",
        "独立管理商品、订单、CDK、项目访问策略与软件发布。": "Manage products, orders, CDKs, project access policies and software releases independently."
      },
      ja: {
        "让软件更新": "ソフトウェア更新を", "更快抵达。": "より速く届ける。", "面向开源项目和独立开发者的版本发布、更新检查与下载分发平台。稳定版、Beta、Alpha，多系统架构与 SHA-256 校验都在一个清晰目录中。": "オープンソースと個人開発者のためのリリース、更新確認、ダウンロード配信。Stable、Beta、Alpha、各種プラットフォーム、SHA-256 検証を一つの一覧に。",
        "SHA-256 校验": "SHA-256 検証", "选择项目，查看版本、平台与校验信息": "プロジェクトを選び、リリース、環境、チェックサムを確認", "搜索项目名称": "プロジェクトを検索", "软件分发与更新基础设施": "ソフトウェア配信・更新基盤",
        "选择访问方案": "利用プランを選ぶ", "Mirrors 拥有独立订单与授权系统；购买记录不会与 Network 套餐混合。": "Mirrors は独立した注文・ライセンスシステムを使用し、Network プランとは別に管理されます。", "收费系统已经就绪，管理员尚未发布商品价格。": "課金システムは準備済みです。商品はまだ公開されていません。",
        "我的授权": "利用権", "管理购买记录、CDK、有效授权与客户端更新 Token。": "購入履歴、CDK、有効な利用権、更新用トークンを管理します。", "兑换 CDK": "CDK を引き換える", "输入管理员或合作方提供的兑换码。": "管理者またはパートナーから受け取ったコードを入力してください。", "兑换": "引き換え", "客户端 Token": "クライアントトークン", "用于更新 API 的 Bearer Token，仅在创建时显示一次。": "更新 API 用の Bearer トークンです。作成時に一度だけ表示されます。", "创建": "作成", "有效授权": "有効な利用権", "购买新方案": "プランを購入", "订单记录": "注文履歴", "更新 Token": "更新トークン",
        "方案": "プラン", "来源": "取得元", "开始": "開始", "到期": "有効期限", "状态": "状態", "订单号": "注文番号", "商品": "商品", "金额": "金額", "时间": "日時", "名称": "名前", "创建时间": "作成日時", "最近使用": "最終使用", "撤销": "無効化", "暂无授权": "利用権はありません", "暂无订单": "注文はありません", "暂无 Token": "トークンはありません", "永久": "無期限", "未使用": "未使用", "已撤销": "無効化済み", "有效": "有効", "失效": "無効",
        "解锁全部付费项目": "すべての有料プロジェクトを利用", "解锁指定项目": "指定プロジェクトを利用", "网页下载与更新 API": "Web ダウンロードと更新 API", "可撤销设备 Token": "無効化可能なデバイストークン", "安全结账": "安全な決済", "提交订单": "注文する", "登录后购买": "ログインして購入", "免费项目": "無料プロジェクト", "账户已解锁": "利用可能", "需要购买": "購入が必要", "需要访问授权": "利用権が必要", "请购买对应商品或在账户中心兑换 CDK。": "対象商品を購入するか、アカウントで CDK を引き換えてください。", "购买访问权": "利用権を購入", "🔒 解锁": "🔒 ロック解除",
        "独立管理商品、订单、CDK、项目访问策略与软件发布。": "商品、注文、CDK、アクセス制御、リリースを独立して管理します。"
      }
    },
    "blog.maximoraverse.org": {
      en: {"主页": "Home", "归档": "Archive", "服务导航": "Services", "搜索": "Search", "技术博客与 MatchAll 服务动态": "Engineering notes and MatchAll service updates"},
      ja: {"主页": "ホーム", "归档": "アーカイブ", "服务导航": "サービス", "搜索": "検索", "技术博客与 MatchAll 服务动态": "技術ブログと MatchAll サービス情報"}
    }
  };

  const seo = {
    "www.maximoraverse.org": {
      zh: ["MatchAll｜连接每一种数字生活", "统一账户、私人云存储、全球网络、隐私 DNS、软件镜像与技术博客。"],
      en: ["MatchAll | One account. Every service.", "Unified identity, private cloud, global networking, privacy-focused DNS, software mirrors and engineering content."],
      ja: ["MatchAll｜一つのアカウントですべてのサービスへ", "統合アカウント、プライベートクラウド、グローバルネットワーク、プライバシー重視の DNS、ソフトウェアミラー、技術ブログ。"]
    },
    "auth.maximoraverse.org": {
      zh: ["MatchAll Account · 统一身份中心", "一个账户访问 MatchAll 的网络、云存储、博客与镜像服务。"],
      en: ["MatchAll Account | Unified identity", "One secure account for MatchAll Network, Drive, Blog and Mirrors."],
      ja: ["MatchAll Account｜統合ID", "一つの安全なアカウントで MatchAll のすべてのサービスへ。"]
    },
    "drive.maximoraverse.org": {
      zh: ["MatchAll Drive｜大容量私人云存储", "大容量、安全、跨设备的私人云存储与不限速下载体验。"],
      en: ["MatchAll Drive | Private cloud storage", "Large, secure private cloud storage with cross-device sync and unrestricted downloads."],
      ja: ["MatchAll Drive｜大容量プライベートクラウド", "大容量、安全、マルチデバイス対応のクラウドストレージ。"]
    },
    "proxyservice.maximoraverse.org": {
      zh: ["MatchAll Network｜全球网络加速", "覆盖多个国家和地区的稳定网络加速服务。"],
      en: ["MatchAll Network | Global acceleration", "Stable multi-region network acceleration with flexible routes and device support."],
      ja: ["MatchAll Network｜グローバルネットワーク", "複数の国と地域に対応した安定したネットワークサービス。"]
    },
    "mirrors.maximoraverse.org": {
      zh: ["MatchAll Mirrors｜软件版本与更新分发", "软件版本发布、更新检查、SHA-256 校验与高速下载。"],
      en: ["MatchAll Mirrors | Software distribution", "Software releases, update checks, SHA-256 verification and fast downloads."],
      ja: ["MatchAll Mirrors｜ソフトウェア配信", "リリース、更新確認、SHA-256 検証、高速ダウンロード。"]
    },
    "blog.maximoraverse.org": {
      zh: ["MatchAll - 技术博客与 MatchAll 服务动态", "MatchAll 技术实践、产品更新与服务公告。"],
      en: ["MatchAll Blog | Engineering and service updates", "Engineering notes, product updates and announcements from MatchAll."],
      ja: ["MatchAll Blog｜技術記事とサービス情報", "MatchAll の技術記事、製品アップデート、サービス情報。"]
    }
  };

  function normalize(value) {
    if (!value) return null;
    const v = value.toLowerCase();
    if (v.startsWith("ja")) return "ja";
    if (v.startsWith("en")) return "en";
    if (v.startsWith("zh")) return "zh";
    return null;
  }

  function readCookie() {
    const item = document.cookie.split("; ").find((v) => v.startsWith(`${COOKIE}=`));
    return item ? normalize(decodeURIComponent(item.split("=").slice(1).join("="))) : null;
  }

  function initialLocale() {
    const query = normalize(new URL(location.href).searchParams.get("lang"));
    return query || readCookie() || normalize(navigator.language) || "zh";
  }

  function remember(locale) {
    document.cookie = `${COOKIE}=${locale}; Max-Age=31536000; Path=/; Domain=.maximoraverse.org; SameSite=Lax; Secure`;
    const url = new URL(location.href);
    if (locale === "zh") url.searchParams.delete("lang"); else url.searchParams.set("lang", locale);
    history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function captureText() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        const parent = node.parentElement;
        if (!parent || ["SCRIPT", "STYLE", "CODE", "PRE", "TEXTAREA"].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    let node;
    while ((node = walker.nextNode())) {
      if (!seenText.has(node)) {
        seenText.add(node);
        textRecords.push([node, node.nodeValue]);
      }
    }
    document.querySelectorAll("[placeholder],[aria-label],[title]").forEach((el) => {
      const seen = seenAttrs.get(el) || new Set();
      ["placeholder", "aria-label", "title"].forEach((name) => {
        if (el.hasAttribute(name) && !seen.has(name)) {
          seen.add(name);
          attrRecords.push([el, name, el.getAttribute(name)]);
        }
      });
      seenAttrs.set(el, seen);
    });
  }

  function dictionary(locale) {
    if (locale === "zh") return {};
    return {...(common[locale] || {}), ...((hostText[hostname] || {})[locale] || {})};
  }

  function translateValue(value, dict) {
    const trimmed = value.trim();
    if (!trimmed || !dict[trimmed]) return value;
    return value.replace(trimmed, dict[trimmed]);
  }

  function updateSeo(locale) {
    if (location.pathname !== "/") return;
    const entry = seo[hostname]?.[locale];
    if (!entry) return;
    document.title = entry[0];
    const description = document.querySelector('meta[name="description"]');
    const ogTitle = document.querySelector('meta[property="og:title"]');
    const ogDescription = document.querySelector('meta[property="og:description"]');
    const twitterTitle = document.querySelector('meta[name="twitter:title"]');
    const twitterDescription = document.querySelector('meta[name="twitter:description"]');
    if (description) description.content = entry[1];
    if (ogTitle) ogTitle.content = entry[0];
    if (ogDescription) ogDescription.content = entry[1];
    if (twitterTitle) twitterTitle.content = entry[0];
    if (twitterDescription) twitterDescription.content = entry[1];
  }

  function applyLocale(locale) {
    if (!supported.has(locale)) locale = "zh";
    const dict = dictionary(locale);
    captureText();
    textRecords.forEach(([node, original]) => { if (node.isConnected) node.nodeValue = translateValue(original, dict); });
    attrRecords.forEach(([el, name, original]) => { if (el.isConnected) el.setAttribute(name, translateValue(original, dict)); });
    document.documentElement.lang = locale === "zh" ? "zh-CN" : locale;
    document.documentElement.dataset.matchallLocale = locale;
    document.querySelectorAll("[data-matchall-lang]").forEach((button) => {
      const active = button.dataset.matchallLang === locale;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    updateSeo(locale);
    window.dispatchEvent(new CustomEvent("matchall:language", {detail: {locale}}));
  }

  function languageButtons() {
    const group = document.createElement("div");
    group.className = "matchall-language";
    group.setAttribute("aria-label", "Language / 语言 / 言語");
    [["zh", "中"], ["en", "EN"], ["ja", "日"]].forEach(([locale, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.matchallLang = locale;
      button.textContent = label;
      button.addEventListener("click", () => { remember(locale); applyLocale(locale); });
      group.append(button);
    });
    return group;
  }

  function buildMenu() {
    if (hostname === "blog.maximoraverse.org") {
      const actions = document.querySelector("#navbar .flex:last-child");
      if (actions && !actions.querySelector(".matchall-language-compact")) {
        const compact = languageButtons();
        compact.classList.add("matchall-language-compact");
        compact.addEventListener("click", (event) => {
          if (innerWidth > 980 || !event.target.closest("button.active")) return;
          const current = initialLocale();
          const next = current === "zh" ? "en" : current === "en" ? "ja" : "zh";
          remember(next);
          applyLocale(next);
        });
        actions.prepend(compact);
      }
      return;
    }
    const header = document.querySelector("header");
    if (!header || document.querySelector(".matchall-menu-trigger")) return;
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "matchall-menu-trigger";
    trigger.setAttribute("aria-label", "打开服务菜单");
    trigger.setAttribute("aria-expanded", "false");
    trigger.innerHTML = '<span aria-hidden="true">☰</span><b>Menu</b>';
    const drawer = document.createElement("aside");
    drawer.className = "matchall-drawer";
    drawer.setAttribute("role", "dialog");
    drawer.setAttribute("aria-modal", "true");
    drawer.setAttribute("aria-label", "MatchAll 服务菜单");
    drawer.setAttribute("aria-hidden", "true");
    drawer.inert = true;
    drawer.innerHTML = `<div class="matchall-drawer-head"><strong>MatchAll</strong><button type="button" aria-label="关闭菜单">×</button></div>
      <nav aria-label="MatchAll 服务">
        <a href="https://www.maximoraverse.org/">总览</a><a href="https://auth.maximoraverse.org/">账户</a>
        <a href="https://drive.maximoraverse.org/">网盘</a><a href="https://proxyservice.maximoraverse.org/">网络</a>
        <a href="https://dns.maximoraverse.org/">DNS</a>
        <a href="https://mirrors.maximoraverse.org/">镜像</a><a href="https://blog.maximoraverse.org/">博客</a>
        <a href="https://console.maximoraverse.org/">控制台</a><a href="https://status.maximoraverse.org/">状态</a>
      </nav><div class="matchall-drawer-policy"><a href="https://www.maximoraverse.org/contact/">联系</a><a href="https://www.maximoraverse.org/privacy/policy/">隐私</a><a href="https://www.maximoraverse.org/terms/">条款</a><a href="https://www.maximoraverse.org/pricing/">定价</a></div>`;
    drawer.append(languageButtons());
    const overlay = document.createElement("button");
    overlay.type = "button";
    overlay.className = "matchall-overlay";
    overlay.setAttribute("aria-label", "关闭菜单");
    document.body.append(overlay, drawer);
    const background = () => [...document.body.children].filter((element) => element !== drawer && element !== overlay);
    let returnFocus = trigger;
    const open = () => {
      returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : trigger;
      background().forEach((element) => { element.inert = true; });
      drawer.inert = false;
      document.documentElement.classList.add("matchall-menu-open");
      trigger.setAttribute("aria-expanded", "true");
      drawer.setAttribute("aria-hidden", "false");
      drawer.querySelector("a")?.focus();
    };
    const close = ({restoreFocus = true} = {}) => {
      if (trigger.getAttribute("aria-expanded") !== "true") return;
      document.documentElement.classList.remove("matchall-menu-open");
      trigger.setAttribute("aria-expanded", "false");
      drawer.setAttribute("aria-hidden", "true");
      drawer.inert = true;
      background().forEach((element) => { element.inert = false; });
      if (restoreFocus) returnFocus?.focus();
    };
    trigger.addEventListener("click", () => trigger.getAttribute("aria-expanded") === "true" ? close() : open());
    overlay.addEventListener("click", () => close());
    drawer.querySelector("button")?.addEventListener("click", () => close());
    drawer.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => close({restoreFocus: false})));
    document.addEventListener("keydown", (event) => {
      if (trigger.getAttribute("aria-expanded") !== "true") return;
      if (event.key === "Escape") { event.preventDefault(); close(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...drawer.querySelectorAll('a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])')].filter((element) => !element.inert);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    const action = header.querySelector(".nav-actions, .nav, .account, .btn.primary");
    if (action) header.insertBefore(trigger, action); else header.append(trigger);
  }

  function injectStyles() {
    if (document.getElementById("matchall-ui-style")) return;
    const style = document.createElement("style");
    style.id = "matchall-ui-style";
    style.textContent = `
      .matchall-menu-open{overflow:hidden}.matchall-menu-trigger{display:none;min-width:42px;height:42px;align-items:center;justify-content:center;gap:7px;padding:0 12px;border:1px solid rgba(197,213,236,.18);border-radius:13px;background:rgba(255,255,255,.055);color:inherit;font:700 12px/1 system-ui;cursor:pointer}.matchall-menu-trigger span{font-size:18px}.matchall-menu-trigger b{display:none}.matchall-overlay{appearance:none;-webkit-appearance:none;position:fixed;inset:0;width:100vw;height:100dvh;margin:0;padding:0;z-index:9997;visibility:hidden;border:0;border-radius:0;background:rgba(2,5,12,.68);box-shadow:none;opacity:0;-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);transition:opacity .2s,visibility .2s}.matchall-drawer{position:fixed;top:12px;right:12px;z-index:9998;width:min(340px,calc(100vw - 24px));padding:18px;border:1px solid rgba(197,213,236,.18);border-radius:24px;background:linear-gradient(145deg,rgba(19,27,47,.98),rgba(7,11,23,.98));box-shadow:0 30px 100px rgba(0,0,0,.55);color:#f7faff;opacity:0;transform:translateY(-14px) scale(.98);pointer-events:none;transition:.22s}.matchall-menu-open .matchall-overlay{visibility:visible;opacity:1}.matchall-menu-open .matchall-drawer{opacity:1;transform:none;pointer-events:auto}.matchall-drawer-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:15px;padding:2px 2px 12px;border-bottom:1px solid rgba(197,213,236,.14)}.matchall-drawer-head strong{font:800 18px/1 system-ui}.matchall-drawer-head button{width:38px;height:38px;border:1px solid rgba(197,213,236,.14);border-radius:12px;background:rgba(255,255,255,.06);color:#fff;font-size:24px;cursor:pointer}.matchall-drawer nav{display:grid;grid-template-columns:1fr 1fr;gap:8px}.matchall-drawer a{display:flex;min-height:48px;align-items:center;padding:0 14px;border:1px solid rgba(197,213,236,.12);border-radius:13px;background:rgba(255,255,255,.045);color:#eef5ff;text-decoration:none;font:750 13px/1 system-ui}.matchall-drawer a:hover,.matchall-drawer a:focus-visible{border-color:rgba(103,220,255,.48);background:rgba(103,220,255,.1);outline:0}.matchall-drawer-policy{display:flex;flex-wrap:wrap;gap:4px;margin:13px 0}.matchall-drawer-policy a{min-height:36px;border:0;background:transparent;color:#9ba9bd;font-size:11px}.matchall-language{display:flex;gap:5px;padding:5px;border:1px solid rgba(197,213,236,.14);border-radius:13px;background:rgba(0,0,0,.18)}.matchall-language button{flex:1;min-width:42px;height:34px;border:0;border-radius:9px;background:transparent;color:#9ba9bd;font:800 11px/1 system-ui;cursor:pointer}.matchall-language button.active{background:linear-gradient(120deg,#67dcff,#9f8cff);color:#06101a}.matchall-language-compact{margin-right:4px;padding:3px}.matchall-language-compact button{min-width:32px;height:34px}.matchall-language-compact button:not(.active){display:none}@media(max-width:980px){.matchall-menu-trigger{display:inline-flex}.matchall-language-compact{display:flex}.matchall-language-compact button{display:none}.matchall-language-compact button.active{display:block}}@media(min-width:981px){.matchall-language-compact button{display:block!important}}@media(max-width:430px){.matchall-menu-trigger{padding:0 10px}.matchall-drawer{top:8px;right:8px;width:calc(100vw - 16px)}}@media(prefers-reduced-motion:reduce){.matchall-overlay,.matchall-drawer{transition:none}}`;
    style.textContent += `.matchall-skip{position:fixed;top:8px;left:8px;z-index:10000;padding:11px 15px;border-radius:12px;background:#f7faff;color:#06101a;font:800 13px/1 system-ui;text-decoration:none;transform:translateY(-160%);transition:.15s}.matchall-skip:focus{transform:none}@media(min-width:981px){.matchall-menu-trigger{display:inline-flex;width:42px;padding:0}.matchall-menu-trigger span{font-size:0}.matchall-menu-trigger span::after{content:"文";font-size:15px}}.matchall-motion-ready .matchall-reveal{opacity:0;transform:translateY(18px);transition:opacity .65s ease var(--matchall-reveal-delay,0ms),transform .65s cubic-bezier(.2,.75,.2,1) var(--matchall-reveal-delay,0ms)}.matchall-motion-ready .matchall-reveal.is-visible{opacity:1;transform:none}@media(prefers-reduced-motion:reduce){.matchall-motion-ready .matchall-reveal{opacity:1!important;transform:none!important;transition:none!important}}`;
    style.textContent += `.matchall-scroll-progress{position:fixed;inset:0 0 auto;z-index:10001;height:2px;pointer-events:none;transform:scaleX(var(--matchall-scroll,0));transform-origin:left;background:linear-gradient(90deg,#67dcff,#9f8cff 55%,#ffca73);box-shadow:0 0 14px rgba(103,220,255,.45)}.matchall-pointer-glow{position:fixed;top:0;left:0;z-index:0;width:360px;height:360px;border-radius:50%;pointer-events:none;opacity:0;transform:translate3d(calc(var(--matchall-pointer-x,-500px) - 50%),calc(var(--matchall-pointer-y,-500px) - 50%),0);background:radial-gradient(circle,rgba(103,220,255,.12),rgba(159,140,255,.055) 42%,transparent 70%);filter:blur(10px);transition:opacity .28s;will-change:transform}.matchall-pointer-glow.is-active{opacity:1}.matchall-spotlight{position:relative;--matchall-x:50%;--matchall-y:50%}.matchall-spotlight-layer{position:absolute!important;inset:0!important;z-index:3!important;width:auto!important;height:auto!important;margin:0!important;border:0!important;border-radius:inherit!important;pointer-events:none!important;opacity:0;background:radial-gradient(220px circle at var(--matchall-x) var(--matchall-y),rgba(103,220,255,.15),rgba(159,140,255,.055) 38%,transparent 70%)!important;mix-blend-mode:screen;transition:opacity .22s}.matchall-spotlight.is-pointer-over .matchall-spotlight-layer{opacity:1}.btn:active,.matchall-drawer a:active,.matchall-menu-trigger:active{transform:translateY(1px) scale(.985)}@media(hover:none),(pointer:coarse){.matchall-pointer-glow,.matchall-spotlight-layer{display:none!important}}@media(prefers-reduced-motion:reduce){.matchall-pointer-glow,.matchall-spotlight-layer{display:none!important}.matchall-scroll-progress{transition:none}}`;
    document.head.append(style);
  }

  function enhanceMotion() {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)");
    if (reduce.matches || !("IntersectionObserver" in window)) return;
    const candidates = document.querySelectorAll(".matchall-reveal, .hero-copy, .hero-panel, .section-head, .card, .cta, .journal-intro, .journal-section-label, .post-card");
    if (!candidates.length) return;
    document.documentElement.classList.add("matchall-motion-ready");
    candidates.forEach((element, index) => {
      if (element.dataset.matchallMotion === "ready") return;
      element.dataset.matchallMotion = "ready";
      element.classList.add("matchall-reveal");
      element.style.setProperty("--matchall-reveal-delay", `${Math.min(index % 4, 3) * 55}ms`);
    });
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, {rootMargin: "0px 0px -7%", threshold: .08});
    candidates.forEach((element) => observer.observe(element));
  }

  function enhanceLiveliness() {
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!document.querySelector(".matchall-scroll-progress")) {
      const progress = document.createElement("div");
      progress.className = "matchall-scroll-progress";
      progress.setAttribute("aria-hidden", "true");
      document.body.append(progress);
      let progressFrame = 0;
      const updateProgress = () => {
        progressFrame = 0;
        const range = Math.max(document.documentElement.scrollHeight - innerHeight, 1);
        progress.style.setProperty("--matchall-scroll", String(Math.min(Math.max(scrollY / range, 0), 1)));
      };
      addEventListener("scroll", () => { if (!progressFrame) progressFrame = requestAnimationFrame(updateProgress); }, {passive: true});
      addEventListener("resize", updateProgress, {passive: true});
      updateProgress();
    }

    if (!reduced && !document.querySelector(".matchall-pointer-glow")) {
      const glow = document.createElement("div");
      glow.className = "matchall-pointer-glow";
      glow.setAttribute("aria-hidden", "true");
      document.body.append(glow);
      let pointerFrame = 0;
      let pointerX = -500;
      let pointerY = -500;
      document.addEventListener("pointermove", (event) => {
        if (event.pointerType === "touch") return;
        pointerX = event.clientX;
        pointerY = event.clientY;
        glow.classList.add("is-active");
        if (!pointerFrame) pointerFrame = requestAnimationFrame(() => {
          pointerFrame = 0;
          glow.style.setProperty("--matchall-pointer-x", `${pointerX}px`);
          glow.style.setProperty("--matchall-pointer-y", `${pointerY}px`);
        });
      }, {passive: true});
      document.documentElement.addEventListener("mouseleave", () => glow.classList.remove("is-active"));
    }

    if (!reduced) {
      document.querySelectorAll(".card, .hero-panel, .journal-intro, .post-card").forEach((element) => {
        if (element.dataset.matchallSpotlight === "ready") return;
        element.dataset.matchallSpotlight = "ready";
        element.classList.add("matchall-spotlight");
        const layer = document.createElement("span");
        layer.className = "matchall-spotlight-layer";
        layer.setAttribute("aria-hidden", "true");
        element.append(layer);
        element.addEventListener("pointermove", (event) => {
          if (event.pointerType === "touch") return;
          const rect = element.getBoundingClientRect();
          layer.style.setProperty("--matchall-x", `${event.clientX - rect.left}px`);
          layer.style.setProperty("--matchall-y", `${event.clientY - rect.top}px`);
          element.classList.add("is-pointer-over");
        }, {passive: true});
        element.addEventListener("pointerleave", () => element.classList.remove("is-pointer-over"));
      });
    }

    if (!reduced && "IntersectionObserver" in window) {
      const numbers = [...document.querySelectorAll("strong, b, [data-count]")].filter((element) => /^\d+(?:[.,]\d+)?(?:%|\+|K|M|B)?$/i.test(element.textContent.trim()));
      const counterObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting || entry.target.dataset.matchallCounted === "true") return;
          const element = entry.target;
          const original = element.textContent.trim();
          const match = original.match(/^(\d+(?:[.,]\d+)?)(.*)$/);
          if (!match) return;
          const target = Number(match[1].replace(",", "."));
          if (!Number.isFinite(target) || target <= 1) return;
          const decimals = (match[1].split(/[.,]/)[1] || "").length;
          const suffix = match[2];
          const started = performance.now();
          element.setAttribute("aria-label", original);
          const tick = (now) => {
            const t = Math.min((now - started) / 720, 1);
            const eased = 1 - Math.pow(1 - t, 3);
            element.textContent = `${(target * eased).toFixed(decimals)}${suffix}`;
            if (t < 1) requestAnimationFrame(tick); else { element.textContent = original; element.dataset.matchallCounted = "true"; }
          };
          requestAnimationFrame(tick);
          counterObserver.unobserve(element);
        });
      }, {threshold: .65});
      numbers.forEach((element) => counterObserver.observe(element));
    }
  }

  function init() {
    injectStyles();
    if (!document.querySelector(".matchall-skip") && document.querySelector("main")) {
      const skip = document.createElement("a");
      const main = document.querySelector("main");
      skip.className = "matchall-skip";
      skip.href = "#matchall-main";
      skip.textContent = "跳到主要内容";
      if (!main.id) main.id = "matchall-main";
      document.body.prepend(skip);
    }
    document.querySelectorAll("a.active").forEach((link) => link.setAttribute("aria-current", "page"));
    buildMenu();
    captureText();
    applyLocale(initialLocale());
    enhanceMotion();
    enhanceLiveliness();
    document.documentElement.dataset.matchallUi = VERSION;
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {once: true}); else init();
  document.addEventListener("astro:page-load", init);
})();
