/* ==========================================================================
   SafeR — Smart Home Security · i18n engine + English base dictionary
   Usage:
     - Mark elements with data-i18n="key" (text content) or
       data-i18n-attr="attrName:key" (attribute value).
     - Extra languages register themselves via SafeRI18n.register(code, dict).
     - SafeRI18n.setLang(code) re-applies strings, updates <html lang/dir>,
       and persists the choice in localStorage.
   ========================================================================== */

(function (global) {
  "use strict";

  var STORAGE_KEY = "safer-lang";
  var RTL_LANGS = ["ar"];

  var dictionaries = {
    en: {
      "meta.pricing.title": "Pricing — SafeR Smart Home Security",
      "meta.pricing.description":
        "Simple, transparent pricing for SafeR smart home security. Self-host for free, or let us run your safety hub — plans for homes, communities, and enterprises.",

      /* Site chrome */
      "nav.home": "Home",
      "nav.features": "Features",
      "nav.pricing": "Pricing",
      "nav.docs": "Docs",
      "nav.dashboard": "Dashboard",
      "nav.getStarted": "Get Started",
      "nav.menu": "Menu",
      "nav.language": "Language",

      "footer.tagline":
        "Open-source smart home security and emergency response — panic buttons, fire and flood sensors, live incident maps, and SMS fallback for when the network fails.",
      "footer.product": "Product",
      "footer.resources": "Resources",
      "footer.company": "Company",
      "footer.link.features": "Features",
      "footer.link.pricing": "Pricing",
      "footer.link.dashboard": "Dashboard",
      "footer.link.mobileApp": "Mobile App",
      "footer.link.docs": "Documentation",
      "footer.link.api": "API Reference",
      "footer.link.github": "GitHub",
      "footer.link.deployment": "Deployment Guide",
      "footer.link.about": "About",
      "footer.link.contact": "Contact",
      "footer.link.license": "License (Apache 2.0)",
      "footer.emergency":
        "In an emergency, always call your local emergency services first.",
      "footer.rights": "© 2026 SafeR. Open source under Apache 2.0.",

      /* Pricing hero */
      "pricing.eyebrow": "Pricing",
      "pricing.title": "Security for every home. Priced for every budget.",
      "pricing.subtitle":
        "Start free with the open-source platform, or let us host your safety hub. Every plan includes the SOS mobile app, real-time alerts, and community incident maps.",

      /* Billing toggle */
      "billing.monthly": "Monthly",
      "billing.annual": "Annual",
      "billing.save": "Save 20%",
      "billing.perMonth": "/month",
      "billing.custom": "Custom",
      "billing.free": "Free",
      "billing.note.annual": "Billed annually",
      "billing.note.monthly": "Billed monthly",
      "billing.note.forever": "Free forever. No card required.",
      "billing.note.contact": "Tailored to your deployment",

      /* Plans */
      "plan.oss.name": "Open Source",
      "plan.oss.desc":
        "Self-host the full SafeR platform on your own hardware. Everything, forever free.",
      "plan.oss.f1": "Full platform, unlimited sensors",
      "plan.oss.f2": "Home Assistant integration",
      "plan.oss.f3": "SOS mobile app (iOS + Android)",
      "plan.oss.f4": "Community support on GitHub",
      "plan.oss.cta": "Deploy for free",

      "plan.home.name": "Home",
      "plan.home.desc":
        "Managed cloud hub for one household — we handle hosting, updates, and backups.",
      "plan.home.f1": "Hosted hub for 1 home, 20 sensors",
      "plan.home.f2": "Push + SMS alerts (100 SMS/mo)",
      "plan.home.f3": "30-day incident history",
      "plan.home.f4": "Automatic updates & backups",
      "plan.home.f5": "Email support",
      "plan.home.cta": "Start 14-day free trial",
      "plan.home.badge": "Most popular",

      "plan.community.name": "Community",
      "plan.community.desc":
        "A shared safety hub for neighborhoods, co-ops, and residential compounds.",
      "plan.community.f1": "Up to 50 homes on one hub",
      "plan.community.f2": "Shared incident map & responder mode",
      "plan.community.f3": "1,000 SMS alerts per month",
      "plan.community.f4": "1-year incident history & analytics",
      "plan.community.f5": "Priority support",
      "plan.community.cta": "Start 14-day free trial",

      "plan.enterprise.name": "Enterprise",
      "plan.enterprise.desc":
        "For cities, campuses, and security providers running SafeR at scale.",
      "plan.enterprise.f1": "Unlimited homes & multi-node hubs",
      "plan.enterprise.f2": "Regional analytics dashboard",
      "plan.enterprise.f3": "LoRaWAN & offline-first deployments",
      "plan.enterprise.f4": "SLA, SSO & dedicated onboarding",
      "plan.enterprise.f5": "24/7 phone support",
      "plan.enterprise.cta": "Contact sales",

      /* Included strip */
      "included.title": "Every plan includes",
      "included.sos.title": "One-tap SOS",
      "included.sos.desc": "Instant panic alerts with live GPS location.",
      "included.sensors.title": "Sensor coverage",
      "included.sensors.desc": "Panic buttons, smoke, fire, and flood sensors.",
      "included.offline.title": "Works offline",
      "included.offline.desc": "Local hub keeps protecting you without internet.",
      "included.privacy.title": "Private by design",
      "included.privacy.desc": "Your data stays on your hub. Open source, auditable.",

      /* FAQ */
      "faq.title": "Frequently asked questions",
      "faq.q1": "Is the open-source plan really free?",
      "faq.a1":
        "Yes. SafeR is Apache 2.0 licensed — the complete platform is free to self-host with no feature gates. Paid plans simply cover managed hosting, SMS delivery, and support.",
      "faq.q2": "Can I switch between monthly and annual billing?",
      "faq.a2":
        "Anytime. Annual billing saves 20% and you can change your billing cycle or plan from your dashboard; changes are prorated automatically.",
      "faq.q3": "What happens if my internet goes down?",
      "faq.a3":
        "Your local hub keeps running automations and sirens offline, and alerts fall back to SMS over GSM. Everything syncs to the cloud once connectivity returns.",
      "faq.q4": "Do you offer discounts for NGOs and community groups?",
      "faq.a4":
        "Yes — registered non-profits and community safety groups get 50% off Community plans. Contact us and we'll set it up.",

      /* CTA banner */
      "cta.title": "Ready to make your home safer?",
      "cta.subtitle":
        "Join thousands of households protecting what matters most — starting in under 10 minutes.",
      "cta.primary": "Get started free",
      "cta.secondary": "Talk to sales"
    }
  };

  var current = "en";

  function normalize(code) {
    return (code || "").toLowerCase().split("-")[0];
  }

  function detectInitialLang() {
    try {
      var stored = global.localStorage.getItem(STORAGE_KEY);
      if (stored && dictionaries[stored]) return stored;
    } catch (e) {
      /* storage unavailable (private mode) — fall through */
    }
    var nav = normalize(global.navigator && global.navigator.language);
    return dictionaries[nav] ? nav : "en";
  }

  function t(key) {
    var dict = dictionaries[current] || {};
    if (Object.prototype.hasOwnProperty.call(dict, key)) return dict[key];
    return dictionaries.en[key] !== undefined ? dictionaries.en[key] : key;
  }

  function apply(root) {
    var scope = root || global.document;

    var nodes = scope.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = t(nodes[i].getAttribute("data-i18n"));
    }

    var attrNodes = scope.querySelectorAll("[data-i18n-attr]");
    for (var j = 0; j < attrNodes.length; j++) {
      // Format: "attr:key" or "attr:key;attr2:key2"
      var pairs = attrNodes[j].getAttribute("data-i18n-attr").split(";");
      for (var k = 0; k < pairs.length; k++) {
        var parts = pairs[k].split(":");
        if (parts.length === 2) {
          attrNodes[j].setAttribute(parts[0].trim(), t(parts[1].trim()));
        }
      }
    }

    var doc = global.document;
    doc.documentElement.lang = current;
    doc.documentElement.dir = RTL_LANGS.indexOf(current) !== -1 ? "rtl" : "ltr";

    var titleKey = doc.body && doc.body.getAttribute("data-i18n-title");
    if (titleKey) doc.title = t(titleKey);

    var metaDesc = doc.querySelector('meta[name="description"][data-i18n-meta]');
    if (metaDesc) {
      metaDesc.setAttribute("content", t(metaDesc.getAttribute("data-i18n-meta")));
    }

    doc.dispatchEvent(new CustomEvent("safer:langchange", { detail: { lang: current } }));
  }

  var SafeRI18n = {
    register: function (code, dict) {
      code = normalize(code);
      dictionaries[code] = dict;
    },
    setLang: function (code) {
      code = normalize(code);
      if (!dictionaries[code]) code = "en";
      current = code;
      try {
        global.localStorage.setItem(STORAGE_KEY, code);
      } catch (e) {
        /* ignore */
      }
      apply();
    },
    getLang: function () {
      return current;
    },
    languages: function () {
      return Object.keys(dictionaries);
    },
    t: t,
    apply: apply,
    init: function () {
      current = detectInitialLang();
      apply();
    }
  };

  global.SafeRI18n = SafeRI18n;
})(window);
