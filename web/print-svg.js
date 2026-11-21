/**
 * A drawing made into a file to print (D-205, D-386): drawn off-screen on paper colours
 * (theme.css `.print`), the on-screen-only layers taken out, every element's computed
 * style written onto it so the file needs no stylesheet, cropped with a margin onto a
 * white sheet. The schematic's (`schematic/printed.js`) and the board's (`board/printed.js`).
 */

const SVG = "http://www.w3.org/2000/svg";
const STYLES = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "paint-order", "opacity", "fill-opacity", "stroke-opacity", "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline"];

/**
 * An off-screen SVG on paper colours, inside `classes` (the stylesheet's scope), to draw into.
 * @param {string} [classes] the host's classes besides `print` @returns {{host: HTMLElement, svg: SVGSVGElement}}
 */
export function paperSvg(classes = "") {
  const host = document.createElement("div");
  host.className = `print ${classes}`.trim();
  host.setAttribute("style", "position: fixed; left: -20000px; top: 0; width: 1200px; height: 900px;");
  const svg = /** @type {SVGSVGElement} */ (document.createElementNS(SVG, "svg"));
  svg.setAttribute("width", "1200");
  svg.setAttribute("height", "900");
  if (classes) svg.setAttribute("class", classes);
  host.append(svg);
  document.body.append(host);
  return { host, svg };
}

/**
 * The drawing in `svg` as a self-contained file: the `drop` layers gone, styles written
 * on, cropped to its content with `margin` round it (its own units) on white.
 * @param {SVGSVGElement} svg drawn inside `paperSvg`'s host @param {string[]} drop selectors
 * @param {number} margin @param {string} title the file's `<title>` @returns {string}
 */
export function paperText(svg, drop, margin, title) {
  const host = /** @type {HTMLElement} */ (svg.parentElement);
  for (const sel of drop) svg.querySelectorAll(sel).forEach((n) => n.remove());
  // every style read before any class goes: the rules match on the ancestors' classes
  const nodes = [...svg.querySelectorAll("*")];
  const styled = nodes.map((node) => {
    const cs = getComputedStyle(node);
    if (cs.display === "none" || cs.visibility === "hidden") return null;
    /** @type {Array<[string, string]>} */
    const found = STYLES.map((prop) => [prop, cs.getPropertyValue(prop)]);
    if (cs.getPropertyValue("vector-effect") === "non-scaling-stroke") found.push(["vector-effect", "non-scaling-stroke"]);
    return found.filter(([, v]) => v && v !== "normal" && v !== "auto");
  });
  nodes.forEach((node, i) => {
    const found = styled[i];
    if (!found) return node.remove();
    for (const [prop, v] of found) node.setAttribute(prop, v);
    node.removeAttribute("class");
    for (const a of [...node.attributes]) if (a.name.startsWith("data-")) node.removeAttribute(a.name);
  });
  // text edged behind (`paint-order: stroke`) twice, the edge behind the plain text: the
  // PDF's renderer (WeasyPrint) paints the stroke over the fill
  for (const text of svg.querySelectorAll('text[paint-order="stroke"]')) {
    text.before(text.cloneNode(true));
    for (const n of [text, ...text.querySelectorAll("*")]) {
      n.setAttribute("stroke", "none");
      n.removeAttribute("paint-order");
    }
  }
  // one group round everything, so the crop includes each group's own transform
  const all = document.createElementNS(SVG, "g");
  all.append(...svg.childNodes);
  svg.append(all);
  const box = all.getBBox();
  const [x, y, w, h] = [box.x - margin, box.y - margin, box.width + 2 * margin, box.height + 2 * margin];
  svg.removeAttribute("class");
  svg.setAttribute("xmlns", SVG);
  svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
  svg.setAttribute("width", String(Math.round(w)));
  svg.setAttribute("height", String(Math.round(h)));
  const name = document.createElementNS(SVG, "title");
  name.textContent = title;
  const paper = document.createElementNS(SVG, "rect");
  const white = getComputedStyle(host).getPropertyValue("--surface-0").trim();
  for (const [k, v] of Object.entries({ x, y, width: w, height: h, fill: white })) paper.setAttribute(k, String(v));
  svg.prepend(name, paper);
  return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(svg)}\n`;
}
