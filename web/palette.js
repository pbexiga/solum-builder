/**
 * The palette on the left (DOM, D-057): the Wiring tiles (Wire, Ground, the supplies V+ and
 * V-, Net label), a tile for each part in `PALETTE` by group, and Text. Pressing a tile
 * starts placing it; dragging it onto the canvas drops it there. What placing does is the
 * app root's.
 */

import { PALETTE, SUPPLIES } from "./editor/edit.js";
import { h } from "./panels.js";
import { drawShapes } from "./schematic/render.js";
import { supplySymbol, symbol } from "./schematic/symbols.js";

/**
 * @typedef {object} PaletteApp what the palette asks of the app root
 * @property {() => any} circuit the open circuit (none yet: tiles don't place)
 * @property {(type: string) => void} startPlacing a palette part type, "label:<net>", "supply:<net>" or "text"
 * @property {() => void} stopPlacing
 * @property {(pos: number[], wire?: number) => unknown} place drop what is being placed
 * @property {(on: boolean) => void} setWireMode
 * @property {() => void} askLabel the Net label tile's form
 */

/**
 * Fill the palette. @param {HTMLElement} el
 * @param {import("./schematic/render.js").Schematic} schematic the sheet (wire mode, where the pointer is over it)
 * @param {PaletteApp} app
 * @returns {{showSupplyTiles: () => void}} `showSupplyTiles`: the V+ and V- tiles again, after the circuit's rails changed
 */
export function palette(el, schematic, app) {
  /**
   * A palette tile: the symbol drawn small above its name. Its hotkey shows only in the
   * tooltip (D-057).
   * @param {string} name @param {string} key @param {import("./schematic/symbols.js").Shape[]} shapes
   * @param {number[]} box @param {Record<string, string>} attrs
   */
  function tile(name, key, shapes, box, attrs) {
    const SVG = "http://www.w3.org/2000/svg";
    const icon = document.createElementNS(SVG, "svg");
    const [x, y, w, hgt] = box;
    const pad = 4;
    icon.setAttribute("viewBox", `${x - pad} ${y - pad} ${w + 2 * pad} ${hgt + 2 * pad}`);
    icon.setAttribute("aria-hidden", "true");
    drawShapes(shapes, icon);
    const b = h("button", { type: "button", class: "tile", title: key ? `${name} (${key})` : name, ...attrs }, [h("span", {}, [name])]);
    b.prepend(icon);
    return b;
  }

  /**
   * Pressing a part tile starts placing it. Dragging onto the canvas and letting go drops
   * it there; a plain click leaves the ghost on the pointer for a click on the canvas.
   * @param {PointerEvent} e @param {string} type a palette part type or "label:GND"
   */
  function dragFromPalette(e, type) {
    if (e.button !== 0 || !app.circuit()) return;
    e.preventDefault();
    app.startPlacing(type);
    const [x0, y0] = [e.clientX, e.clientY];
    let moved = false;
    const onMove = (/** @type {PointerEvent} */ ev) => {
      if (!moved && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 4) return;
      moved = true;
      document.body.classList.add("dragging-part");
      schematic.hover(ev.clientX, ev.clientY);
    };
    const onUp = (/** @type {PointerEvent} */ ev) => {
      window.removeEventListener("pointermove", onMove);
      document.body.classList.remove("dragging-part");
      if (!moved) return;
      if (!schematic.hover(ev.clientX, ev.clientY)) return app.stopPlacing();
      const spot = schematic.spot ?? { pos: schematic.pointer };
      app.place(spot.pos, spot.wire);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  }

  /**
   * Supply tiles between Ground and Net label: V+ and V- (dropping one the circuit hasn't
   * got adds that rail, D-069).
   */
  function showSupplyTiles() {
    const rails = app.circuit()?.power?.rails ?? {};
    const bar = supplySymbol("rail");
    const tiles = Object.keys(SUPPLIES).map((net) => {
      const t = tile(net, "", bar.shapes, bar.box, { "data-tool": "supply", "data-net": net });
      t.title = net in rails
        ? `Supply ${net} (${String(rails[net]).replace("-", "\u2212")} V): every ${net} bar is the same net`
        : `Supply ${net}: not used yet; placing it adds a ${net === "V-" ? "negative" : "positive"} supply (set its voltage in Power \u2192 Custom\u2026)`;
      t.addEventListener("pointerdown", (e) => dragFromPalette(e, `supply:${net}`));
      return t;
    });
    wiring.replaceChildren(wire, gnd, ...tiles, label);
  }

  const groups = [...new Set(PALETTE.map((e) => e.group))];
  const wire = tile("Wire", "W", [{ line: [-20, 0, 20, 0] }, { circle: [-20, 0, 2.2], fill: true }, { circle: [20, 0, 2.2], fill: true }], [-22, -10, 44, 20], { "data-tool": "wire", "aria-pressed": "false" });
  wire.addEventListener("click", () => app.setWireMode(!schematic.wireMode));
  const label = tile("Net label", "L", [{ circle: [-14, 6, 2.2], fill: true }, { text: "OUT", at: [2, 2], size: 11 }], [-20, -10, 40, 20], { "data-tool": "label" });
  label.addEventListener("click", app.askLabel);
  const ground = supplySymbol("ground");
  const gnd = tile("Ground", "G", ground.shapes, ground.box, { "data-tool": "ground" });
  gnd.addEventListener("pointerdown", (e) => dragFromPalette(e, "label:GND"));
  // a note on the sheet (D-091): click where it goes, then write it
  const text = tile("Text", "X", [{ text: "Aa", at: [0, 4], size: 13 }, { line: [-16, 9, 16, 9] }], [-20, -10, 40, 22], { "data-tool": "text" });
  text.addEventListener("pointerdown", (e) => dragFromPalette(e, "text"));
  const wiring = h("div", { class: "tiles", id: "wiring-tiles" });
  el.replaceChildren(
    h("h2", {}, ["Wiring"]),
    wiring,
    ...groups.flatMap((group) => [
      h("h2", {}, [group]),
      h("div", { class: "tiles" }, PALETTE.filter((e) => e.group === group).map((e) => {
        const sym = symbol({ type: e.type, pins: [], draw: {} });
        const tool = e.tool ?? e.type;
        const b = tile(e.name, (e.key ?? "").toUpperCase(), sym.shapes, sym.box, { "data-place": tool });
        b.addEventListener("pointerdown", (ev) => dragFromPalette(ev, tool));
        return b;
      })),
    ]),
    h("h2", {}, ["Misc"]),
    h("div", { class: "tiles" }, [text]),
  );
  // the supply tiles are there from the start: added only once a circuit had loaded, they
  // pushed every tile below them down a row after a refresh (the user, 2026-11-11, D-281)
  showSupplyTiles();
  return { showSupplyTiles };
}
