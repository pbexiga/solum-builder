/**
 * The user guide's pages (D-290): the search box. The server searches (`/api/manual/search`,
 * results by section); while there's a query the results take the page list's place.
 * A link to another page of the guide fetches it and swaps only the page and the page list,
 * so nothing else redraws (D-300). Escape tells the app's window (when the page is inside
 * it) to close.
 */

import { getJson } from "./api.js";
import { h } from "./panels.js";
import { debounce, latestOnly } from "./state.js";

const search = /** @type {HTMLInputElement} */ (document.getElementById("manual-search"));
const results = /** @type {HTMLElement} */ (document.getElementById("manual-results"));
const pages = /** @type {HTMLElement} */ (document.getElementById("manual-pages"));
const page = /** @type {HTMLElement} */ (document.querySelector("main.manual-page"));
const nav = /** @type {HTMLElement} */ (document.querySelector(".manual-nav"));
const requests = latestOnly();
const loads = latestOnly();
const guideRoot = new URL("./", location.href).pathname;
let shown = location.pathname;

/**
 * The address a click should load in place, or null to leave it to the browser: a plain
 * left click on a link to a page of the guide. A heading on this page is left to the browser
 * (it just scrolls); this page's own link comes back too, or the browser would reload it.
 * @param {MouseEvent} e
 * @returns {URL | null}
 */
function inPlace(e) {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return null;
  const link = e.target instanceof Element ? e.target.closest("a[href]") : null;
  if (!link || link.hasAttribute("target") || link.hasAttribute("download")) return null;
  const url = new URL(/** @type {HTMLAnchorElement} */ (link).href);
  if (url.origin !== location.origin || !url.pathname.startsWith(guideRoot)) return null;
  return url.pathname === location.pathname && url.hash ? null : url;
}

/**
 * Show another page of the guide: its body and page list replace this one's.
 * @param {URL} url
 * @param {boolean} push add it to the history (not when going back or forward)
 * @param {Element | null} [from] the page list's link clicked: the list scrolls so the page's
 *   link stays where it was on screen, though the sections under the old page fold away
 */
async function load(url, push, from = null) {
  const token = loads.next();
  const reply = await fetch(url.href);
  if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
  const next = new DOMParser().parseFromString(await reply.text(), "text/html");
  if (!loads.isCurrent(token)) return;
  const body = next.querySelector("main.manual-page");
  const list = next.getElementById("manual-pages");
  if (!body || !list) throw new Error("not a guide page");
  const before = from && pages.contains(from) ? from.getBoundingClientRect().top : null;
  page.replaceChildren(...Array.from(body.childNodes)); // copied first: moving empties the live list
  pages.replaceChildren(...Array.from(list.childNodes));
  const current = pages.querySelector("a[aria-current='page']");
  if (current && before !== null) nav.scrollTop += current.getBoundingClientRect().top - before;
  else current?.scrollIntoView({ block: "nearest" });
  document.title = next.title;
  if (push) history.pushState(null, "", url.href);
  shown = url.pathname;
  const target = url.hash && document.getElementById(decodeURIComponent(url.hash.slice(1)));
  if (target) target.scrollIntoView();
  else window.scrollTo(0, 0);
}

/** @param {Array<{slug: string, title: string, heading: string, anchor: string, snippet: string}>} found */
function show(found) {
  results.replaceChildren(
    ...found.map((r) =>
      h("a", { href: `./${r.slug}${r.anchor ? `#${r.anchor}` : ""}` }, [
        h("span", { class: "where" }, [r.heading === r.title ? r.title : `${r.title} › ${r.heading}`]),
        h("span", { class: "snippet" }, [r.snippet]),
      ]),
    ),
  );
  if (!found.length) results.append(h("p", { class: "empty" }, ["Nothing in the guide matches that."]));
}

async function run() {
  const query = search.value.trim();
  results.hidden = !query;
  pages.hidden = Boolean(query);
  if (!query) return;
  const token = requests.next();
  const found = await getJson(`../api/manual/search?q=${encodeURIComponent(query)}`);
  if (requests.isCurrent(token)) show(found);
}

search.addEventListener("input", debounce(() => run().catch(() => show([])), 150));
// a result on this page: the address changes but the page stays, so put the page list back
results.addEventListener("click", () => {
  search.value = "";
  results.hidden = true;
  pages.hidden = false;
});
document.addEventListener("click", (e) => {
  const url = inPlace(e);
  if (!url) return;
  e.preventDefault();
  if (url.pathname === location.pathname) {
    if (url.href !== location.href) history.pushState(null, "", url.href);
    window.scrollTo(0, 0);
    return;
  }
  const link = e.target instanceof Element ? e.target.closest("a") : null;
  load(url, true, link).catch(() => location.assign(url.href));
});
window.addEventListener("popstate", () => {
  if (location.pathname !== shown) load(new URL(location.href), false).catch(() => location.reload());
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && window.parent !== window) window.parent.postMessage("manual-close", location.origin);
});
