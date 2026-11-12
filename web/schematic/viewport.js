/**
 * Pan and zoom as pure viewBox arithmetic (schematic units). No DOM.
 * @typedef {{x: number, y: number, w: number, h: number}} ViewBox
 * @typedef {{minX: number, minY: number, maxX: number, maxY: number}} Bounds
 */

export const MIN_ZOOM_W = 80; // narrowest view, schematic units
export const MAX_ZOOM_W = 20000;

/**
 * Bounds of every point, grown by `margin`.
 * @param {Array<[number, number]>} points
 * @param {number} margin
 * @returns {Bounds}
 */
export function boundsOf(points, margin = 40) {
  if (!points.length) return { minX: -100, minY: -100, maxX: 100, maxY: 100 };
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return {
    minX: Math.min(...xs) - margin,
    minY: Math.min(...ys) - margin,
    maxX: Math.max(...xs) + margin,
    maxY: Math.max(...ys) + margin,
  };
}

/**
 * The viewBox that shows `bounds` whole and centred in a `width` × `height` pixel area.
 * @param {Bounds} bounds @param {number} width @param {number} height
 * @returns {ViewBox}
 */
export function fitView(bounds, width, height) {
  const bw = bounds.maxX - bounds.minX;
  const bh = bounds.maxY - bounds.minY;
  const aspect = width / height;
  const w = Math.max(bw, bh * aspect);
  const h = w / aspect;
  return {
    x: bounds.minX - (w - bw) / 2,
    y: bounds.minY - (h - bh) / 2,
    w,
    h,
  };
}

/**
 * Zoom by `factor` (> 1 zooms in) keeping schematic point (px, py) fixed on screen.
 * @param {ViewBox} vb @param {number} px @param {number} py @param {number} factor
 * @returns {ViewBox}
 */
export function zoomAt(vb, px, py, factor) {
  const w = Math.min(Math.max(vb.w / factor, MIN_ZOOM_W), MAX_ZOOM_W);
  const scale = w / vb.w;
  const h = vb.h * scale;
  return { x: px - (px - vb.x) * scale, y: py - (py - vb.y) * scale, w, h };
}

/**
 * Move the view by a drag of (dx, dy) screen pixels on an element `widthPx` wide.
 * @param {ViewBox} vb @param {number} dx @param {number} dy @param {number} widthPx
 * @returns {ViewBox}
 */
export function panBy(vb, dx, dy, widthPx) {
  const unitsPerPx = vb.w / widthPx;
  return { ...vb, x: vb.x - dx * unitsPerPx, y: vb.y - dy * unitsPerPx };
}

/**
 * The view moved so schematic point (x, y) is in it: unchanged if the point is already
 * inside and at least `margin` (a fraction of the view) from its edges, otherwise centred
 * on the point at the same zoom (Find part).
 * @param {ViewBox} vb @param {number} x @param {number} y @param {number} [margin]
 * @returns {ViewBox}
 */
export function revealPoint(vb, x, y, margin = 0.1) {
  const inX = x >= vb.x + vb.w * margin && x <= vb.x + vb.w * (1 - margin);
  const inY = y >= vb.y + vb.h * margin && y <= vb.y + vb.h * (1 - margin);
  return inX && inY ? vb : { ...vb, x: x - vb.w / 2, y: y - vb.h / 2 };
}

/**
 * The view after its element is resized from `from` to `to` pixels: the same zoom (units
 * per pixel) and the same point in the middle, so a window resize never re-fits (D-164).
 * @param {ViewBox} vb @param {{width: number, height: number}} from
 * @param {{width: number, height: number}} to
 * @returns {ViewBox}
 */
export function resizeView(vb, from, to) {
  const unitsPerPx = vb.w / from.width;
  const [cx, cy] = [vb.x + vb.w / 2, vb.y + vb.h / 2];
  const [w, h] = [to.width * unitsPerPx, to.height * unitsPerPx];
  return { x: cx - w / 2, y: cy - h / 2, w, h };
}

/** @param {ViewBox} vb */
export const viewBoxText = (vb) => `${vb.x} ${vb.y} ${vb.w} ${vb.h}`;
