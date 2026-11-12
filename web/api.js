/**
 * Talking to the Solum Builder API. No DOM access, so it can be tested.
 * Every error the server sends has a plain-English `message`; that's what gets shown.
 */

export class ApiError extends Error {
  /** @param {string} message @param {number} status */
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/**
 * The message to show for a failed response.
 * @param {number} status
 * @param {unknown} body parsed JSON, or null if the body wasn't JSON
 * @returns {string}
 */
export function errorMessage(status, body) {
  if (body && typeof body === "object" && "message" in body && typeof body.message === "string") {
    return body.message;
  }
  if (status === 0) return "Can't reach the Solum Builder server. Is it running?";
  return `The server answered with an error (${status}). Try again; if it keeps happening, check the server log.`;
}

/**
 * @param {string} url
 * @param {RequestInit} [init]
 * @param {typeof fetch} [fetchFn]
 * @param {"json" | "blob"} [as] what the answer is read as (JSON: null if it isn't any)
 * @returns {Promise<any>}
 */
export async function request(url, init, fetchFn = fetch, as = "json") {
  let response;
  try {
    response = await fetchFn(url, init);
  } catch {
    throw new ApiError(errorMessage(0, null), 0);
  }
  if (response.ok && as === "blob") return response.blob();
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) throw new ApiError(errorMessage(response.status, body), response.status);
  return body;
}

/** @param {string} url @param {typeof fetch} [fetchFn] */
export const getJson = (url, fetchFn) => request(url, undefined, fetchFn);

/** @param {string} url @param {unknown} body @param {typeof fetch} [fetchFn] @param {"json" | "blob"} [as] */
export const postJson = (url, body, fetchFn, as) =>
  request(
    url,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    fetchFn,
    as,
  );

/**
 * POST a search and follow its progress (D-123): asked with `progress: true`, the server
 * answers one JSON line per step (`{done, of}`, each passed to `onStep`), then `{result}`
 * (what this resolves to) or `{message}` (an error on the way). An error before the first
 * step, or an answer that isn't a stream, comes as usual.
 * @param {string} url @param {Record<string, unknown>} body
 * @param {(done: number, of: number) => void} onStep @param {typeof fetch} [fetchFn]
 * @returns {Promise<any>}
 */
export async function postProgress(url, body, onStep, fetchFn = fetch) {
  let response;
  try {
    response = await fetchFn(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, progress: true }) });
  } catch {
    throw new ApiError(errorMessage(0, null), 0);
  }
  if (!response.ok || !response.body || !(response.headers.get("content-type") ?? "").includes("ndjson")) {
    let parsed = null;
    try {
      parsed = await response.json();
    } catch {
      parsed = null;
    }
    if (!response.ok) throw new ApiError(errorMessage(response.status, parsed), response.status);
    return parsed;
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    let chunk;
    try {
      chunk = await reader.read();
    } catch {
      throw new ApiError(errorMessage(0, null), 0);
    }
    buffer += chunk.value ?? "";
    const lines = buffer.split("\n");
    buffer = /** @type {string} */ (lines.pop());
    for (const line of lines.filter((l) => l.trim())) {
      const item = JSON.parse(line);
      if ("result" in item) return item.result;
      if ("message" in item) throw new ApiError(item.message, 422);
      onStep(item.done, item.of);
    }
    if (chunk.done) throw new ApiError("The search stopped before it finished. Try again.", 0);
  }
}

/** @param {string} url @param {unknown} body @param {typeof fetch} [fetchFn] */
export const putJson = (url, body, fetchFn) =>
  request(
    url,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    fetchFn,
  );

/** @param {string} url @param {typeof fetch} [fetchFn] */
export const deleteJson = (url, fetchFn) => request(url, { method: "DELETE" }, fetchFn);

/** @param {string} url @param {unknown} body @param {typeof fetch} [fetchFn] */
export const patchJson = (url, body, fetchFn) =>
  request(
    url,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    fetchFn,
  );

/**
 * Upload a file as the request body (no multipart, D-083).
 * @param {string} url @param {Blob} file @param {typeof fetch} [fetchFn]
 */
export const postFile = (url, file, fetchFn) => request(url, { method: "POST", body: file }, fetchFn);
