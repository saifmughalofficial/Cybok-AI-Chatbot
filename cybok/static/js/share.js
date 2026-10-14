import { enhance, renderMarkdown } from "./markdown.js";
import { lightbox } from "./core.js";

const token = location.pathname.split("/")[2];
document.querySelectorAll("[data-md]").forEach((el) => {
  el.innerHTML = renderMarkdown(el.textContent);
  el.querySelectorAll('img[src^="/media/file/"]').forEach((img) => {
    img.src = img.getAttribute("src").replace("/media/file/", `/share/${token}/file/`);
  });
  enhance(el);
});
document.addEventListener("click", (e) => {
  const img = e.target.closest(".md img");
  if (img) lightbox(img.src, img.alt);
});
