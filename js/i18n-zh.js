/* SafeR — Smart Home Security · Simplified Chinese (zh) dictionary */
(function () {
  "use strict";
  if (!window.SafeRI18n) return;

  window.SafeRI18n.register("zh", {
    "meta.pricing.title": "定价 — SafeR 智能家居安防",
    "meta.pricing.description":
      "SafeR 智能家居安防的定价简单透明。免费自托管，或由我们托管您的安防中枢——提供家庭、社区和企业方案。",

    /* Site chrome */
    "nav.home": "首页",
    "nav.features": "功能",
    "nav.pricing": "定价",
    "nav.docs": "文档",
    "nav.dashboard": "控制台",
    "nav.getStarted": "立即开始",
    "nav.menu": "菜单",
    "nav.language": "语言",

    "footer.tagline":
      "开源智能家居安防与应急响应平台——紧急按钮、火灾与水浸传感器、实时事件地图，以及网络中断时的短信备援。",
    "footer.product": "产品",
    "footer.resources": "资源",
    "footer.company": "公司",
    "footer.link.features": "功能",
    "footer.link.pricing": "定价",
    "footer.link.dashboard": "控制台",
    "footer.link.mobileApp": "移动应用",
    "footer.link.docs": "文档",
    "footer.link.api": "API 参考",
    "footer.link.github": "GitHub",
    "footer.link.deployment": "部署指南",
    "footer.link.about": "关于我们",
    "footer.link.contact": "联系我们",
    "footer.link.license": "许可证（Apache 2.0）",
    "footer.emergency": "遇到紧急情况时，请务必首先拨打当地紧急服务电话。",
    "footer.rights": "© 2026 SafeR。基于 Apache 2.0 开源。",

    /* Pricing hero */
    "pricing.eyebrow": "定价",
    "pricing.title": "守护每一个家，适合每一种预算。",
    "pricing.subtitle":
      "使用开源平台免费开始，或由我们托管您的安防中枢。所有方案均包含 SOS 移动应用、实时警报和社区事件地图。",

    /* Billing toggle */
    "billing.monthly": "按月",
    "billing.annual": "按年",
    "billing.save": "省 20%",
    "billing.perMonth": "/月",
    "billing.custom": "定制",
    "billing.free": "免费",
    "billing.note.annual": "按年计费",
    "billing.note.monthly": "按月计费",
    "billing.note.forever": "永久免费，无需信用卡。",
    "billing.note.contact": "按您的部署量身定制",

    /* Plans */
    "plan.oss.name": "开源版",
    "plan.oss.desc": "在您自己的硬件上自托管完整的 SafeR 平台。全部功能，永久免费。",
    "plan.oss.f1": "完整平台，传感器数量不限",
    "plan.oss.f2": "Home Assistant 集成",
    "plan.oss.f3": "SOS 移动应用（iOS + Android）",
    "plan.oss.f4": "GitHub 社区支持",
    "plan.oss.cta": "免费部署",

    "plan.home.name": "家庭版",
    "plan.home.desc": "面向单个家庭的云端托管中枢——托管、更新和备份全由我们负责。",
    "plan.home.f1": "托管中枢：1 个家庭，20 个传感器",
    "plan.home.f2": "推送 + 短信警报（每月 100 条短信）",
    "plan.home.f3": "30 天事件历史",
    "plan.home.f4": "自动更新与备份",
    "plan.home.f5": "邮件支持",
    "plan.home.cta": "开始 14 天免费试用",
    "plan.home.badge": "最受欢迎",

    "plan.community.name": "社区版",
    "plan.community.desc": "面向社区、合作社和住宅小区的共享安防中枢。",
    "plan.community.f1": "一个中枢最多接入 50 户",
    "plan.community.f2": "共享事件地图与响应者模式",
    "plan.community.f3": "每月 1,000 条短信警报",
    "plan.community.f4": "1 年事件历史与数据分析",
    "plan.community.f5": "优先支持",
    "plan.community.cta": "开始 14 天免费试用",

    "plan.enterprise.name": "企业版",
    "plan.enterprise.desc": "面向大规模运行 SafeR 的城市、园区和安防服务商。",
    "plan.enterprise.f1": "家庭数量不限，多节点中枢",
    "plan.enterprise.f2": "区域数据分析控制台",
    "plan.enterprise.f3": "LoRaWAN 与离线优先部署",
    "plan.enterprise.f4": "SLA、SSO 与专属上线服务",
    "plan.enterprise.f5": "24/7 电话支持",
    "plan.enterprise.cta": "联系销售",

    /* Included strip */
    "included.title": "所有方案均包含",
    "included.sos.title": "一键 SOS",
    "included.sos.desc": "即时紧急警报，附带实时 GPS 位置。",
    "included.sensors.title": "传感器覆盖",
    "included.sensors.desc": "紧急按钮、烟雾、火灾与水浸传感器。",
    "included.offline.title": "离线可用",
    "included.offline.desc": "本地中枢在断网时仍持续保护您。",
    "included.privacy.title": "隐私优先",
    "included.privacy.desc": "数据保存在您自己的中枢。开源，可审计。",

    /* FAQ */
    "faq.title": "常见问题",
    "faq.q1": "开源方案真的免费吗？",
    "faq.a1":
      "是的。SafeR 采用 Apache 2.0 许可证——完整平台可免费自托管，没有任何功能限制。付费方案仅覆盖托管服务、短信发送和技术支持。",
    "faq.q2": "可以在按月和按年计费之间切换吗？",
    "faq.a2":
      "随时可以。按年计费可节省 20%，您可以在控制台中更改计费周期或方案，差额会自动按比例结算。",
    "faq.q3": "如果家里断网了怎么办？",
    "faq.a3":
      "本地中枢会在离线状态下继续运行自动化和警报器，警报会通过 GSM 短信送达。网络恢复后，一切自动同步到云端。",
    "faq.q4": "是否为公益组织和社区团体提供折扣？",
    "faq.a4":
      "提供——注册的非营利组织和社区安全团体可享受社区版方案 5 折优惠。联系我们即可开通。",

    /* CTA banner */
    "cta.title": "准备好让您的家更安全了吗？",
    "cta.subtitle": "加入数千个守护挚爱的家庭——10 分钟内即可完成设置。",
    "cta.primary": "免费开始",
    "cta.secondary": "咨询销售"
  });
})();
