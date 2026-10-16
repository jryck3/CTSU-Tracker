(function (root) {
  function escHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[c];
    });
  }
  function normalize(labels) {
    var out = [];
    var seen = {};
    (labels || []).forEach(function (label) {
      var text = String(label == null ? "" : label).replace(/\s+/g, " ").trim();
      if (!text) return;
      var key = text.toLowerCase();
      if (key === "variety" || seen[key]) return;
      seen[key] = 1;
      out.push(text);
    });
    return out;
  }
  var phoneQuery = "(max-width: 1100px)";
  function isPhone() {
    return window.matchMedia(phoneQuery).matches;
  }
  function html(labels, id) {
    var clean = normalize(labels);
    var safe = String(id || "type").replace(/[^A-Za-z0-9_-]/g, "");
    if (!clean.length) return "Not classified";
    if (clean.length === 1) return escHtml(clean[0]);
    var pop = "type-pop-" + safe;
    return '<span class="type-anchor"><button type="button" class="type-btn" aria-expanded="false" aria-controls="' + pop + '">Multiple cancer types (' + clean.length + ')</button><div class="type-popover" id="' + pop + '" hidden><ul>' + clean.map(function (label) { return "<li>" + escHtml(label) + "</li>"; }).join("") + "</ul></div></span>";
  }
  function buttonFor(pop) {
    return document.querySelector('.type-btn[aria-controls="' + pop.id + '"]');
  }
  function clearFloat(panel) {
    if (!panel) return;
    ["position", "left", "top", "right", "bottom", "width", "minWidth", "maxWidth", "maxHeight"].forEach(function (key) {
      panel.style[key] = "";
    });
  }
  function closeAll(exceptBtn) {
    document.querySelectorAll(".type-popover").forEach(function (pop) {
      var btn = buttonFor(pop);
      if (exceptBtn && btn === exceptBtn) return;
      pop.hidden = true;
      clearFloat(pop);
      if (btn) btn.setAttribute("aria-expanded", "false");
    });
  }
  function visualBox() {
    var vv = window.visualViewport;
    return {
      left: vv ? vv.offsetLeft : 0,
      top: vv ? vv.offsetTop : 0,
      width: vv ? vv.width : document.documentElement.clientWidth,
      height: vv ? vv.height : window.innerHeight
    };
  }
  function place(anchor, panel) {
    if (!anchor || !panel || panel.hidden || isPhone()) return;
    var rect = anchor.getBoundingClientRect();
    var box = visualBox();
    if (rect.bottom < box.top + 4 || rect.top > box.top + box.height - 4) {
      closeAll(null);
      return;
    }
    panel.style.position = "fixed";
    panel.style.right = "auto";
    panel.style.bottom = "auto";
    panel.style.minWidth = "0";
    var margin = 8;
    var maxW = Math.max(160, box.width - margin * 2);
    panel.style.maxWidth = maxW + "px";
    panel.style.maxHeight = Math.max(120, Math.min(box.height * 0.5, box.height - margin * 2)) + "px";
    panel.style.width = Math.min(Math.max(panel.scrollWidth, 180), maxW) + "px";
    var width = panel.offsetWidth;
    var left = rect.left;
    if (left + width > box.left + box.width - margin) left = box.left + box.width - margin - width;
    if (left < box.left + margin) left = box.left + margin;
    var top = rect.bottom + 4;
    var height = panel.offsetHeight;
    if (top + height > box.top + box.height - margin) {
      var above = rect.top - 4 - height;
      if (above < box.top + margin) {
        closeAll(null);
        return;
      }
      top = above;
    }
    panel.style.left = Math.round(left) + "px";
    panel.style.top = Math.round(top) + "px";
  }
  function open(btn, hooks) {
    var pop = document.getElementById(btn.getAttribute("aria-controls"));
    if (!pop) return;
    var opening = pop.hidden;
    closeAll(null);
    if (hooks && hooks.closeMenus) hooks.closeMenus();
    if (!opening) {
      btn.focus();
      return;
    }
    pop.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    if (!isPhone()) place(btn, pop);
  }
  function scrollCloses(ev) {
    if (isPhone()) return;
    var openPop = document.querySelector(".type-popover:not([hidden])");
    if (!openPop) return;
    var target = ev && ev.target;
    if (target && target.nodeType === 1 && (target === openPop || openPop.contains(target))) return;
    closeAll(null);
  }
  var MENU = {
    Prostate: ["GU"], Bladder: ["GU"], Kidney: ["GU"], Testis: ["GU"], Penile: ["GU"],
    GU: ["GU"], "Genitourinary Cancers": ["GU"], "Male Reproductive System Cancer": ["GU"],
    Liver: ["GI"], Pancreas: ["GI"], Colorectal: ["GI"], Colon: ["GI"], Rectal: ["GI"],
    Esophagus: ["GI"], Gastric: ["GI"], Biliary: ["GI"], Anal: ["GI"], GI: ["GI"],
    "Gastrointestinal Cancer": ["GI"],
    Breast: ["Breast"], "Breast Cancer": ["Breast"],
    NSCLC: ["NSCLC"], SCLC: ["SCLC"], "Lung, other": ["Lung, other"],
    Lung: ["NSCLC", "SCLC", "Lung, other"], "Lung Cancer": ["NSCLC", "SCLC", "Lung, other"],
    "Lung, Mediastinal, and Pleural Cancer": ["NSCLC", "SCLC", "Lung, other"],
    "Head and neck": ["Head and neck"], "Head and Neck Cancer": ["Head and neck"],
    CNS: ["CNS"], Glioma: ["CNS"], Meningioma: ["CNS"], Medulloblastoma: ["CNS"], Ependymoma: ["CNS"],
    Gynecologic: ["Gynecologic"], Gyn: ["Gynecologic"], Cervix: ["Gynecologic"],
    Endometrial: ["Gynecologic"], Ovary: ["Gynecologic"], Vulva: ["Gynecologic"],
    "Female Reproductive System Cancer": ["Gynecologic"],
    Lymphoma: ["Lymphoma"], Hematologic: ["Hematologic"], Leukemia: ["Hematologic"],
    Myeloma: ["Hematologic"], Myelofibrosis: ["Hematologic"], "Hematologic Cancer": ["Hematologic"],
    Sarcoma: ["Sarcoma"], Skin: ["Skin"], Melanoma: ["Skin"], Merkel: ["Skin"], "Skin Cancer": ["Skin"],
    NET: ["other-mixed"], "Not classified": ["other-mixed"], Biorepository: ["other-mixed"], Other: ["other-mixed"]
  };
  function menuKeys(labels) {
    var keys = [];
    var seen = {};
    normalize(labels).forEach(function (label) {
      (MENU[label] || [label]).forEach(function (key) {
        if (seen[key]) return;
        seen[key] = 1;
        keys.push(key);
      });
    });
    return keys;
  }
  if (typeof document !== "undefined") {
    document.addEventListener("click", function (ev) {
      var pop = ev.target && ev.target.closest && ev.target.closest(".type-popover");
      if (pop) ev.stopPropagation();
    }, true);
  }
  root.CancerType = {
    normalize: normalize,
    html: html,
    closeAll: closeAll,
    place: place,
    open: open,
    scrollCloses: scrollCloses,
    isPhone: isPhone,
    menuKeys: menuKeys,
    setPhoneQuery: function (q) { phoneQuery = q; }
  };
})(typeof window !== "undefined" ? window : globalThis);
