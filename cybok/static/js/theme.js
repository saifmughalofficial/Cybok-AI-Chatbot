/* Applies the saved theme before first paint (no flash). Loaded synchronously in <head>. */
(function () {
  var pref = "system";
  try { pref = localStorage.getItem("cybok-theme") || "system"; } catch (e) {}
  var dark = pref === "dark" || (pref === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.setAttribute("data-theme", dark ? "dark" : "light");
  try {
    var accent = localStorage.getItem("cybok-accent");
    if (accent) root.setAttribute("data-accent", accent);
    var font = localStorage.getItem("cybok-font");
    if (font) root.setAttribute("data-font", font);
  } catch (e) {}
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
      var p = "system";
      try { p = localStorage.getItem("cybok-theme") || "system"; } catch (err) {}
      if (p === "system") root.setAttribute("data-theme", e.matches ? "dark" : "light");
    });
  }
})();
