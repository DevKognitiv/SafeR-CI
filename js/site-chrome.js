/* ==========================================================================
   SafeR — Smart Home Security · Shared site chrome
   Injects the site header (nav + language switcher) and footer into any
   page containing #site-header / #site-footer mount points, initializes
   i18n, and wires up the mobile menu.
   ========================================================================== */

(function () {
  "use strict";

  var LANGS = [
    { code: "en", label: "English" },
    { code: "es", label: "Español" },
    { code: "zh", label: "中文" },
    { code: "ar", label: "العربية" }
  ];

  var LOGO_SVG =
    '<svg class="site-logo__mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<path d="M12 2l8 3.5v5.7c0 5-3.4 9.3-8 10.8-4.6-1.5-8-5.8-8-10.8V5.5L12 2z" ' +
    'fill="url(#safer-logo-grad)"/>' +
    '<path d="M8.5 12l2.4 2.4 4.6-4.8" stroke="#fff" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" fill="none"/>' +
    "<defs>" +
    '<linearGradient id="safer-logo-grad" x1="4" y1="2" x2="20" y2="22">' +
    '<stop stop-color="#DC2626"/><stop offset="1" stop-color="#EA580C"/>' +
    "</linearGradient></defs></svg>";

  function langOptions() {
    return LANGS.map(function (l) {
      return '<option value="' + l.code + '">' + l.label + "</option>";
    }).join("");
  }

  function headerHTML() {
    return (
      '<div class="container site-header__inner">' +
      '<a class="site-logo" href="index.html">' +
      LOGO_SVG +
      '<span>Safe<span class="site-logo__accent">R</span></span>' +
      "</a>" +
      '<nav class="site-nav" id="site-nav" aria-label="Main">' +
      '<a href="index.html" data-i18n="nav.home"></a>' +
      '<a href="index.html#features" data-i18n="nav.features"></a>' +
      '<a href="pricing.html" data-i18n="nav.pricing"></a>' +
      '<a href="https://github.com/DevKognitiv/SafeR-CI/tree/main/docs" data-i18n="nav.docs"></a>' +
      '<a href="dashboard.html" data-i18n="nav.dashboard"></a>' +
      "</nav>" +
      '<div class="site-header__actions">' +
      '<select class="lang-select" id="lang-select" data-i18n-attr="aria-label:nav.language">' +
      langOptions() +
      "</select>" +
      '<a class="btn btn-primary" href="signup.html" data-i18n="nav.getStarted"></a>' +
      '<button class="nav-toggle" id="nav-toggle" aria-expanded="false" ' +
      'aria-controls="site-nav" data-i18n-attr="aria-label:nav.menu">' +
      '<span class="nav-toggle__bar"></span><span class="nav-toggle__bar"></span>' +
      '<span class="nav-toggle__bar"></span></button>' +
      "</div></div>"
    );
  }

  function footerHTML() {
    var year = new Date().getFullYear();
    return (
      '<div class="container">' +
      '<div class="site-footer__grid">' +
      '<div class="site-footer__brand">' +
      '<a class="site-logo" href="index.html">' +
      LOGO_SVG.replace(/safer-logo-grad/g, "safer-logo-grad-f") +
      '<span>Safe<span class="site-logo__accent">R</span></span>' +
      "</a>" +
      '<p data-i18n="footer.tagline"></p>' +
      "</div>" +
      "<div>" +
      '<h3 data-i18n="footer.product"></h3>' +
      "<ul>" +
      '<li><a href="index.html#features" data-i18n="footer.link.features"></a></li>' +
      '<li><a href="pricing.html" data-i18n="footer.link.pricing"></a></li>' +
      '<li><a href="dashboard.html" data-i18n="footer.link.dashboard"></a></li>' +
      '<li><a href="index.html#app" data-i18n="footer.link.mobileApp"></a></li>' +
      "</ul></div>" +
      "<div>" +
      '<h3 data-i18n="footer.resources"></h3>' +
      "<ul>" +
      '<li><a href="https://github.com/DevKognitiv/SafeR-CI/tree/main/docs" data-i18n="footer.link.docs"></a></li>' +
      '<li><a href="https://github.com/DevKognitiv/SafeR-CI/blob/main/docs/deployment.md" data-i18n="footer.link.deployment"></a></li>' +
      '<li><a href="https://github.com/DevKognitiv/SafeR-CI" data-i18n="footer.link.github"></a></li>' +
      "</ul></div>" +
      "<div>" +
      '<h3 data-i18n="footer.company"></h3>' +
      "<ul>" +
      '<li><a href="index.html#about" data-i18n="footer.link.about"></a></li>' +
      '<li><a href="mailto:hello@safer.example" data-i18n="footer.link.contact"></a></li>' +
      '<li><a href="https://github.com/DevKognitiv/SafeR-CI/blob/main/LICENSE" data-i18n="footer.link.license"></a></li>' +
      "</ul></div>" +
      "</div>" +
      '<div class="site-footer__bottom">' +
      '<span data-i18n="footer.rights">© ' + year + " SafeR.</span>" +
      '<span data-i18n="footer.emergency"></span>' +
      "</div></div>"
    );
  }

  function markActiveNav() {
    var path = window.location.pathname.split("/").pop() || "index.html";
    var links = document.querySelectorAll("#site-nav a");
    for (var i = 0; i < links.length; i++) {
      var href = links[i].getAttribute("href") || "";
      if (href.split("#")[0] === path && href.indexOf("#") === -1) {
        links[i].classList.add("is-active");
        links[i].setAttribute("aria-current", "page");
      }
    }
  }

  function wireMobileNav() {
    var toggle = document.getElementById("nav-toggle");
    var nav = document.getElementById("site-nav");
    if (!toggle || !nav) return;
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function wireLangSelect() {
    var select = document.getElementById("lang-select");
    if (!select || !window.SafeRI18n) return;
    select.value = window.SafeRI18n.getLang();
    select.addEventListener("change", function () {
      window.SafeRI18n.setLang(select.value);
    });
    document.addEventListener("safer:langchange", function (e) {
      if (select.value !== e.detail.lang) select.value = e.detail.lang;
    });
  }

  function init() {
    var headerMount = document.getElementById("site-header");
    var footerMount = document.getElementById("site-footer");
    if (headerMount) headerMount.innerHTML = headerHTML();
    if (footerMount) footerMount.innerHTML = footerHTML();

    markActiveNav();
    wireMobileNav();

    if (window.SafeRI18n) {
      window.SafeRI18n.init();
    }
    wireLangSelect();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
