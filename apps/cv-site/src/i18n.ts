export const locales = ["zh-cn", "zh-tw", "ja", "en", "fr"] as const;
export type Locale = (typeof locales)[number];

export const localeInfo: Record<Locale, {
  htmlLang: string;
  ogLocale: string;
  label: string;
  path: string;
}> = {
  "zh-cn": { htmlLang: "zh-CN", ogLocale: "zh_CN", label: "简体中文", path: "/" },
  "zh-tw": { htmlLang: "zh-TW", ogLocale: "zh_TW", label: "繁體中文", path: "/zh-tw/" },
  ja: { htmlLang: "ja", ogLocale: "ja_JP", label: "日本語", path: "/ja/" },
  en: { htmlLang: "en", ogLocale: "en_US", label: "English", path: "/en/" },
  fr: { htmlLang: "fr", ogLocale: "fr_FR", label: "Français", path: "/fr/" },
};

type Copy = {
  meta: { title: string; description: string };
  skip: string;
  nav: { about: string; work: string; approach: string; contact: string };
  controls: {
    command: string;
    theme: string;
    menuOpen: string;
    menuClose: string;
    language: string;
  };
  hero: {
    eyebrow: string;
    line1: string;
    line2: string;
    accent: string;
    end: string;
    lead: string;
    explore: string;
    print: string;
    role: string;
    profile: string;
    online: string;
    noteBuild: string;
    noteVerify: string;
  };
  about: {
    label: string;
    kicker: string;
    title: [string, string];
    paragraphs: [string, string];
  };
  work: {
    label: string;
    kicker: string;
    title: string;
    filters: { all: string; openSource: string; platform: string; lab: string };
    descriptions: [string, string, string, string];
  };
  approach: {
    label: string;
    kicker: string;
    title: [string, string];
    principles: [
      { title: string; text: string },
      { title: string; text: string },
      { title: string; text: string },
    ];
  };
  contact: {
    kicker: string;
    title: string;
    text: string;
  };
  command: {
    title: string;
    work: string;
    print: string;
    copy: string;
    copied: string;
    github: string;
    blog: string;
  };
  footer: string;
  attribution: string;
};

export const translations: Record<Locale, Copy> = {
  "zh-cn": {
    meta: {
      title: "CHANGAO MA — 独立开发者 · 系统构建者",
      description: "CHANGAO MA 的个人简历与作品集，专注自动化、云端基础设施、开发者工具与可靠的软件交付。",
    },
    skip: "跳到主要内容",
    nav: { about: "关于", work: "作品", approach: "方法", contact: "联系" },
    controls: {
      command: "打开快捷命令面板",
      theme: "切换颜色主题",
      menuOpen: "打开导航菜单",
      menuClose: "关闭导航菜单",
      language: "选择语言",
    },
    hero: {
      eyebrow: "构建可靠、清晰、可长期维护的数字产品",
      line1: "把复杂系统，",
      line2: "做成",
      accent: "简单体验",
      end: "。",
      lead: "我是 CHANGAO MA，一名独立开发者与系统构建者。关注自动化、云端基础设施、开发者工具，以及每一次可验证的软件交付。",
      explore: "查看作品",
      print: "打印 / PDF",
      role: "独立开发者 · 系统构建者",
      profile: "档案",
      online: "在线",
      noteBuild: "带着目标构建",
      noteVerify: "验证最终结果",
    },
    about: {
      label: "关于与能力",
      kicker: "系统 / 产品 / 运维",
      title: ["从想法到稳定运行，", "把每一层都做扎实。"],
      paragraphs: [
        "我喜欢解决边界清晰但工程链路完整的问题：从接口与交互设计，到测试、发布、监控和故障恢复。目标不只是“能运行”，而是让系统可理解、可验证、可回滚。",
        "我的公开工作主要集中在 Python / TypeScript 自动化、自托管服务、身份认证，以及面向真实运维环境的工具。",
      ],
    },
    work: {
      label: "精选作品",
      kicker: "公开作品 / 开源项目",
      title: "做真实可用的东西。",
      filters: { all: "全部", openSource: "开源", platform: "平台", lab: "实验" },
      descriptions: [
        "面向真实生产环境的自动签到工具：具备只读探测、严格状态码、单次提交安全语义、systemd 定时与跨平台 CI。",
        "围绕统一身份、文件服务、软件分发、状态监测与文档构建的一组自托管云端服务。",
        "服务校园出行场景的校车导航小程序，以轻量交互组织线路与站点信息。",
        "持续维护的算法与竞赛练习空间，用于验证解法、复杂度与实现细节。",
      ],
    },
    approach: {
      label: "工作方法",
      kicker: "思考 / 构建 / 验证",
      title: ["工程质量来自", "可重复的过程。"],
      principles: [
        { title: "先把边界说清楚", text: "明确目标、风险和不做什么，让实现始终可审查。" },
        { title: "安全默认，失败可见", text: "谨慎处理凭据与外部写操作，为异常设计清晰状态和恢复路径。" },
        { title: "交付后再验证", text: "从测试、产物到线上回读，确认用户实际得到预期结果。" },
      ],
    },
    contact: {
      kicker: "保持联系",
      title: "有一个值得做好的想法？",
      text: "欢迎从公开项目、博客或联系页面开始交流。",
    },
    command: {
      title: "快速导航",
      work: "查看精选作品",
      print: "打印 / 保存 PDF",
      copy: "复制页面链接",
      copied: "已复制",
      github: "打开 GitHub",
      blog: "阅读博客",
    },
    footer: "设计与构建于 MaximoraVerse",
    attribution: "Astro 基础",
  },
  "zh-tw": {
    meta: {
      title: "CHANGAO MA — 獨立開發者 · 系統建構者",
      description: "CHANGAO MA 的個人履歷與作品集，專注自動化、雲端基礎設施、開發者工具與可靠的軟體交付。",
    },
    skip: "跳到主要內容",
    nav: { about: "關於", work: "作品", approach: "方法", contact: "聯絡" },
    controls: {
      command: "開啟快速命令面板",
      theme: "切換色彩主題",
      menuOpen: "開啟導覽選單",
      menuClose: "關閉導覽選單",
      language: "選擇語言",
    },
    hero: {
      eyebrow: "打造可靠、清晰、可長期維護的數位產品",
      line1: "把複雜系統，",
      line2: "化為",
      accent: "簡單體驗",
      end: "。",
      lead: "我是 CHANGAO MA，一名獨立開發者與系統建構者。專注自動化、雲端基礎設施、開發者工具，以及每一次可驗證的軟體交付。",
      explore: "查看作品",
      print: "列印 / PDF",
      role: "獨立開發者 · 系統建構者",
      profile: "檔案",
      online: "線上",
      noteBuild: "帶著目標建構",
      noteVerify: "驗證最終結果",
    },
    about: {
      label: "關於與能力",
      kicker: "系統 / 產品 / 維運",
      title: ["從想法到穩定運行，", "把每一層都做紮實。"],
      paragraphs: [
        "我喜歡處理邊界清楚、工程鏈路完整的問題：從介面與互動設計，到測試、發布、監控與故障復原。目標不只是「能運行」，更要讓系統可理解、可驗證、可回復。",
        "我的公開工作主要聚焦 Python / TypeScript 自動化、自託管服務、身分驗證，以及面向真實維運環境的工具。",
      ],
    },
    work: {
      label: "精選作品",
      kicker: "公開作品 / 開源專案",
      title: "打造真正可用的產品。",
      filters: { all: "全部", openSource: "開源", platform: "平台", lab: "實驗" },
      descriptions: [
        "面向真實生產環境的自動簽到工具：具備唯讀探測、嚴格狀態碼、單次提交安全語意、systemd 排程與跨平台 CI。",
        "涵蓋統一身分、檔案服務、軟體發佈、狀態監測與文件的一組自託管雲端服務。",
        "服務校園交通情境的校車導航小程式，以輕量互動整理路線與站點資訊。",
        "持續維護的演算法與競賽練習空間，用於驗證解法、複雜度與實作細節。",
      ],
    },
    approach: {
      label: "工作方法",
      kicker: "思考 / 建構 / 驗證",
      title: ["工程品質來自", "可重複的流程。"],
      principles: [
        { title: "先釐清邊界", text: "明確目標、風險與不做什麼，讓實作始終可審查。" },
        { title: "安全預設，失敗可見", text: "審慎處理憑證與外部寫入，為異常設計清楚狀態與復原路徑。" },
        { title: "交付後再驗證", text: "從測試、產物到線上回讀，確認使用者真正得到預期結果。" },
      ],
    },
    contact: {
      kicker: "保持聯絡",
      title: "有一個值得做好的想法？",
      text: "歡迎從公開專案、部落格或聯絡頁面開始交流。",
    },
    command: {
      title: "快速導覽",
      work: "查看精選作品",
      print: "列印 / 儲存 PDF",
      copy: "複製頁面連結",
      copied: "已複製",
      github: "開啟 GitHub",
      blog: "閱讀部落格",
    },
    footer: "設計與建構於 MaximoraVerse",
    attribution: "Astro 基礎",
  },
  ja: {
    meta: {
      title: "CHANGAO MA — インディペンデント開発者 · システムビルダー",
      description: "CHANGAO MA の履歴書・ポートフォリオ。自動化、クラウド基盤、開発者ツール、信頼できるソフトウェアデリバリーに取り組んでいます。",
    },
    skip: "メインコンテンツへ移動",
    nav: { about: "自己紹介", work: "実績", approach: "進め方", contact: "連絡" },
    controls: {
      command: "コマンドパレットを開く",
      theme: "カラーテーマを切り替える",
      menuOpen: "ナビゲーションを開く",
      menuClose: "ナビゲーションを閉じる",
      language: "言語を選択",
    },
    hero: {
      eyebrow: "信頼でき、明快で、長く保守できるデジタルプロダクトをつくる",
      line1: "複雑なシステムを、",
      line2: "",
      accent: "シンプルな体験",
      end: "へ。",
      lead: "CHANGAO MAです。自動化、クラウド基盤、開発者ツール、そして検証可能なソフトウェアデリバリーに注力するインディペンデント開発者・システムビルダーです。",
      explore: "実績を見る",
      print: "印刷 / PDF",
      role: "インディペンデント開発者 · システムビルダー",
      profile: "プロフィール",
      online: "オンライン",
      noteBuild: "意図を持ってつくる",
      noteVerify: "結果を検証する",
    },
    about: {
      label: "自己紹介とスキル",
      kicker: "システム / プロダクト / 運用",
      title: ["アイデアから安定運用まで、", "すべての層を丁寧につくる。"],
      paragraphs: [
        "境界が明確で、工程全体を見渡せる課題に取り組むことが好きです。インターフェースと操作設計から、テスト、リリース、監視、障害復旧まで。「動く」だけでなく、理解・検証・ロールバックできるシステムを目指します。",
        "公開している成果は、Python / TypeScript による自動化、セルフホスト型サービス、アイデンティティ、実運用を前提としたツールが中心です。",
      ],
    },
    work: {
      label: "主な実績",
      kicker: "公開プロジェクト / オープンソース",
      title: "実際に使えるものを届ける。",
      filters: { all: "すべて", openSource: "オープンソース", platform: "プラットフォーム", lab: "ラボ" },
      descriptions: [
        "読み取り専用プローブ、厳密なステータスコード、単一送信の安全性、systemd スケジュール、クロスプラットフォーム CI を備えた実運用向け自動チェックインツール。",
        "統合アイデンティティ、ファイルサービス、ソフトウェア配布、稼働監視、ドキュメントをまとめたセルフホスト型クラウドサービス群。",
        "路線と停留所の情報を軽快な操作で整理する、キャンパス向けシャトルバス案内ミニプログラム。",
        "解法、計算量、実装の細部を検証するために継続更新しているアルゴリズム・競技プログラミング演習環境。",
      ],
    },
    approach: {
      label: "仕事の進め方",
      kicker: "考える / つくる / 検証する",
      title: ["品質は、", "再現可能なプロセスから。"],
      principles: [
        { title: "境界を先に定義する", text: "目標、リスク、対象外を明確にし、実装を常にレビュー可能にします。" },
        { title: "安全を標準に、失敗を可視化", text: "認証情報と外部書き込みを慎重に扱い、明確な状態と復旧経路を設計します。" },
        { title: "届けた後に検証する", text: "テスト、成果物、本番環境を確認し、期待した結果が利用者に届いたことを確かめます。" },
      ],
    },
    contact: {
      kicker: "つながる",
      title: "丁寧につくる価値のあるアイデアはありますか？",
      text: "公開プロジェクト、ブログ、または連絡ページからお気軽にどうぞ。",
    },
    command: {
      title: "クイックナビゲーション",
      work: "主な実績を見る",
      print: "印刷 / PDF に保存",
      copy: "ページのURLをコピー",
      copied: "コピーしました",
      github: "GitHub を開く",
      blog: "ブログを読む",
    },
    footer: "MaximoraVerse でデザイン・開発",
    attribution: "Astro 基盤",
  },
  en: {
    meta: {
      title: "CHANGAO MA — Independent Developer · Systems Builder",
      description: "The résumé and portfolio of CHANGAO MA, focused on automation, cloud infrastructure, developer tools, and reliable software delivery.",
    },
    skip: "Skip to main content",
    nav: { about: "About", work: "Work", approach: "Approach", contact: "Contact" },
    controls: {
      command: "Open command palette",
      theme: "Switch color theme",
      menuOpen: "Open navigation menu",
      menuClose: "Close navigation menu",
      language: "Select language",
    },
    hero: {
      eyebrow: "Building reliable, legible, long-lived digital products",
      line1: "Turning complex systems",
      line2: "into ",
      accent: "simple experiences",
      end: ".",
      lead: "I'm CHANGAO MA, an independent developer and systems builder focused on automation, cloud infrastructure, developer tools, and verifiable software delivery.",
      explore: "Explore work",
      print: "Print / PDF",
      role: "Independent Developer · Systems Builder",
      profile: "Profile",
      online: "Online",
      noteBuild: "Build with intent",
      noteVerify: "Verify the result",
    },
    about: {
      label: "About & capabilities",
      kicker: "Systems / Product / Operations",
      title: ["From idea to reliable operation,", "make every layer count."],
      paragraphs: [
        "I enjoy bounded problems with complete engineering journeys—from interfaces and interaction design to testing, release, observability, and recovery. The goal is not merely to run, but to remain understandable, verifiable, and reversible.",
        "My public work centers on Python and TypeScript automation, self-hosted services, identity, and tools designed for real operational environments.",
      ],
    },
    work: {
      label: "Selected work",
      kicker: "Public work / Open source",
      title: "Work that ships.",
      filters: { all: "All", openSource: "Open source", platform: "Platform", lab: "Lab" },
      descriptions: [
        "A production-minded check-in utility with read-only probes, strict status codes, single-submit safety, systemd scheduling, and cross-platform CI.",
        "A self-hosted service suite spanning identity, file services, software distribution, status monitoring, and documentation.",
        "A lightweight campus shuttle navigation mini program that organizes routes and stop information for everyday travel.",
        "An evolving algorithms practice space for validating solutions, complexity, and implementation details.",
      ],
    },
    approach: {
      label: "Working approach",
      kicker: "Think / Build / Verify",
      title: ["Quality comes from", "repeatable process."],
      principles: [
        { title: "Define the boundary", text: "Clarify goals, risks, and non-goals so the implementation stays reviewable." },
        { title: "Safe defaults, visible failure", text: "Treat credentials and external writes carefully, with explicit states and recovery paths." },
        { title: "Verify after delivery", text: "Validate tests, artifacts, and live behavior to confirm the intended outcome reaches users." },
      ],
    },
    contact: {
      kicker: "Let's connect",
      title: "Have an idea worth building well?",
      text: "Start a conversation through my public work, blog, or contact page.",
    },
    command: {
      title: "Quick navigation",
      work: "View selected work",
      print: "Print / save PDF",
      copy: "Copy page URL",
      copied: "Copied",
      github: "Open GitHub",
      blog: "Read the blog",
    },
    footer: "Designed & built in MaximoraVerse",
    attribution: "Astro foundation",
  },
  fr: {
    meta: {
      title: "CHANGAO MA — Développeur indépendant · Concepteur de systèmes",
      description: "CV et portfolio de CHANGAO MA, spécialisé dans l’automatisation, l’infrastructure cloud, les outils de développement et la livraison logicielle fiable.",
    },
    skip: "Aller au contenu principal",
    nav: { about: "À propos", work: "Projets", approach: "Méthode", contact: "Contact" },
    controls: {
      command: "Ouvrir la palette de commandes",
      theme: "Changer le thème de couleurs",
      menuOpen: "Ouvrir le menu de navigation",
      menuClose: "Fermer le menu de navigation",
      language: "Choisir la langue",
    },
    hero: {
      eyebrow: "Créer des produits numériques fiables, lisibles et durables",
      line1: "Transformer des systèmes complexes",
      line2: "en ",
      accent: "expériences simples",
      end: ".",
      lead: "Je suis CHANGAO MA, développeur indépendant et concepteur de systèmes, spécialisé dans l’automatisation, l’infrastructure cloud, les outils de développement et la livraison logicielle vérifiable.",
      explore: "Voir les projets",
      print: "Imprimer / PDF",
      role: "Développeur indépendant · Concepteur de systèmes",
      profile: "Profil",
      online: "En ligne",
      noteBuild: "Construire avec intention",
      noteVerify: "Vérifier le résultat",
    },
    about: {
      label: "Profil et compétences",
      kicker: "Systèmes / Produit / Opérations",
      title: ["De l’idée à l’exploitation fiable,", "soigner chaque couche."],
      paragraphs: [
        "J’aime résoudre des problèmes bien délimités tout au long de leur parcours d’ingénierie : interfaces, expérience, tests, publication, observabilité et reprise. L’objectif n’est pas seulement de fonctionner, mais de rester compréhensible, vérifiable et réversible.",
        "Mes travaux publics portent principalement sur l’automatisation en Python et TypeScript, les services auto-hébergés, l’identité et les outils conçus pour des environnements d’exploitation réels.",
      ],
    },
    work: {
      label: "Projets sélectionnés",
      kicker: "Travaux publics / Open source",
      title: "Des projets réellement livrés.",
      filters: { all: "Tous", openSource: "Open source", platform: "Plateforme", lab: "Laboratoire" },
      descriptions: [
        "Un outil de pointage pensé pour la production, avec sondes en lecture seule, codes d’état stricts, envoi unique sécurisé, planification systemd et CI multiplateforme.",
        "Une suite de services cloud auto-hébergés couvrant l’identité, les fichiers, la distribution logicielle, la supervision et la documentation.",
        "Un mini-programme léger de navigation pour les navettes du campus, structurant les itinéraires et les arrêts.",
        "Un espace évolutif d’entraînement aux algorithmes et à la programmation compétitive, pour valider solutions, complexité et détails d’implémentation.",
      ],
    },
    approach: {
      label: "Méthode de travail",
      kicker: "Réfléchir / Construire / Vérifier",
      title: ["La qualité vient d’un", "processus reproductible."],
      principles: [
        { title: "Définir les limites", text: "Clarifier objectifs, risques et hors-périmètre afin que l’implémentation reste vérifiable." },
        { title: "Sécurité par défaut, échecs visibles", text: "Traiter prudemment les identifiants et écritures externes, avec des états et chemins de reprise explicites." },
        { title: "Vérifier après livraison", text: "Contrôler tests, artefacts et comportement en production pour confirmer le résultat attendu." },
      ],
    },
    contact: {
      kicker: "Échangeons",
      title: "Une idée qui mérite d’être bien construite ?",
      text: "Échangeons à partir de mes projets publics, de mon blog ou de la page de contact.",
    },
    command: {
      title: "Navigation rapide",
      work: "Voir les projets sélectionnés",
      print: "Imprimer / enregistrer en PDF",
      copy: "Copier l’adresse de la page",
      copied: "Copié",
      github: "Ouvrir GitHub",
      blog: "Lire le blog",
    },
    footer: "Conçu et développé dans MaximoraVerse",
    attribution: "Base Astro",
  },
};

export function isLocale(value: string): value is Locale {
  return locales.includes(value as Locale);
}
