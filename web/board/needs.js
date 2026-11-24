/**
 * A part's needs, leg by leg (D-377): a card over the board canvas, shown while a part is
 * carried or selected: each leg's hole and net, and the terminals it must reach, joined
 * (✓), placed but not joined yet, or not placed yet (a lug: not wired yet). The rows come from
 * `board-logic.js`'s `legNeeds`. Below them, the builder's decisions on the part's
 * overlaps, in words (P6h4).
 */

import { h } from "../panels.js";

const STATE_WORDS = { joined: "✓", apart: "not joined yet", unplaced: "not placed yet" };

/**
 * @param {HTMLElement} card the card's element (hidden while there's nothing to show)
 */
export function needsCard(card) {
  return {
    /**
     * Show a part's needs; a leg the circuit doesn't use is said so.
     * @param {string} ref @param {import("./board-logic.js").Need[]} needs
     * @param {string[]} [decisions] its overlaps' decisions, in words
     */
    show(ref, needs, decisions = []) {
      if (!needs.length) return this.hide();
      card.replaceChildren(
        h("h3", {}, [ref]),
        h("ul", {}, needs.map((n) => h("li", { class: "need" }, [
          h("span", { class: "leg" }, [n.leg]),
          " ",
          h("span", { class: "where" }, [n.hole ?? "not placed"]),
          ...(n.net ? [" ", h("span", { class: "net" }, [n.net])] : [" ", h("span", { class: "unused" }, ["not used by the circuit"])]),
          ...(n.reach.length
            ? [h("ul", { class: "reach" }, n.reach.map((r) => h("li", { class: `reach-${r.state}` }, [
              r.words, " ",
              h("span", { class: "state" }, [r.lug && r.state === "unplaced" ? "not wired yet" : STATE_WORDS[r.state]]),
            ])))]
            : []),
        ]))),
        ...(decisions.length ? [h("ul", { class: "decisions" }, decisions.map((t) => h("li", {}, [t])))] : []),
      );
      card.hidden = false;
    },
    hide() {
      card.hidden = true;
      card.replaceChildren();
    },
  };
}
