// Observe a clone of this attempt's fetch response. Never alter request args,
// headers, the original response, tool inputs, or native completion decisions.
export async function installRuntimeStreamObserver(page, { attemptId, prompt, workspace }) {
  return page.evaluate(({ attemptId, prompt, workspace }) => {
    const key = "__wcbDoubaoResponseObserver";
    if (window[key]) throw new Error("DOUBAOWORK_STREAM_OBSERVER_ALREADY_EXISTS");
    const chunks = window["@flow-web/desktop:stable"];
    if (!Array.isArray(chunks)) throw new Error("DOUBAOWORK_RUNTIME_LOADER_UNAVAILABLE");
    let require;
    const item = [[`wcb-observer-${crypto.randomUUID()}`], {}, r => { require = r; }];
    chunks.push(item);
    if (chunks.at(-1) === item) chunks.pop();
    const module = String(require?.m?.[190005] || "");
    if (!module.includes("baseURL") || !module.includes("fetch")) throw new Error("DOUBAOWORK_SSE_FETCH_PROFILE_UNSUPPORTED");
    const sdk = require(190005);
    if (typeof sdk.le !== "function" || typeof sdk.iv !== "function") throw new Error("DOUBAOWORK_SSE_FETCH_PROFILE_UNSUPPORTED");
    const sdkFetch = sdk.le();
    const getter = sdkFetch === undefined ? () => window.fetch : () => sdk.le();
    const setter = sdkFetch === undefined ? value => { window.fetch = value; } : value => sdk.iv({ fetch: value });
    const original = getter();
    if (typeof original !== "function") throw new Error("DOUBAOWORK_RUNTIME_FETCH_UNAVAILABLE");
    const expected = prompt.replace(/\r\n/g, "\n").replace(/\n+$/u, "");
    const matchBody = body => {
      let promptFound = false, workspaceFound = false, nodes = 0;
      const queue = [[body, 0]];
      while (queue.length && nodes++ < 50000) {
        const [v, depth] = queue.pop();
        if (depth > 20) continue;
        if (typeof v === "string") {
          promptFound ||= v.replace(/\r\n/g, "\n").replace(/\n+$/u, "") === expected;
          workspaceFound ||= v === workspace;
          if (v.length <= 4 * 1024 * 1024 && /^[\[{]/u.test(v)) {
            try { queue.push([JSON.parse(v), depth + 1]); } catch { /* Non-JSON strings are not interpreted. */ }
          }
        } else if (v && typeof v === "object") for (const child of Object.values(v)) queue.push([child, depth + 1]);
      }
      return { promptFound, workspaceFound };
    };
    const observer = { attempt_id: attemptId, installed_at: new Date().toISOString(), requests: [], active: 0, errors: [], diagnostics: [],
      restore: () => { if (getter() !== wrapper) throw new Error("DOUBAOWORK_STREAM_OBSERVER_REPLACED"); setter(original); delete window[key]; } };
    const wrapper = async function (...args) {
      const body = args[1]?.body;
      const match = matchBody(body);
      const matched = match.promptFound && match.workspaceFound;
      if (observer.diagnostics.length < 16) observer.diagnostics.push({ body_type: typeof body, ...match });
      const response = await Reflect.apply(original, this, args);
      if (!matched) return response;
      const row = { sequence: observer.requests.length, started_at: new Date().toISOString(), finished_at: null,
        status: response.status ?? null, complete: false, chunks: [], bytes: 0, error: null };
      observer.requests.push(row);
      if (typeof response.clone !== "function") { row.error = "RESPONSE_CLONE_UNAVAILABLE"; return response; }
      try {
        const copy = response.clone(), reader = copy.body?.getReader();
        if (!reader) { row.error = "RESPONSE_STREAM_UNAVAILABLE"; return response; }
        observer.active += 1;
        void (async () => {
          const decoder = new TextDecoder();
          try {
            while (true) {
              const { value, done } = await reader.read();
              if (done) { const tail = decoder.decode(); if (tail) row.chunks.push(tail); row.complete = true; break; }
              row.bytes += value.byteLength;
              if (row.bytes > 16 * 1024 * 1024) { row.error = "RESPONSE_CAPTURE_LIMIT"; void reader.cancel(); break; }
              row.chunks.push(decoder.decode(value, { stream: true }));
            }
          } catch (e) { row.error = String(e.message || e); }
          finally { row.finished_at = new Date().toISOString(); observer.active -= 1; }
        })();
      } catch (e) { row.error = String(e.message || e); }
      return response;
    };
    setter(wrapper);
    window[key] = observer;
    return { installed: true, attempt_id: attemptId, policy: "matching-prompt-and-workspace-response-clone/v2",
      fetch_binding: sdkFetch === undefined ? "global-fetch-fallback" : "sdk-fetch" };
  }, { attemptId, prompt, workspace });
}

export async function collectRuntimeStream(page, attemptId, { restore = false } = {}) {
  return page.evaluate(({ attemptId, restore }) => {
    const o = window.__wcbDoubaoResponseObserver;
    if (!o) return { status: "unavailable", reason: "observer-not-installed", attempt_id: attemptId };
    if (o.attempt_id !== attemptId) throw new Error("DOUBAOWORK_STREAM_ATTEMPT_MISMATCH");
    const value = { schema: "wildclawbench.doubaowork-response-stream/v1", attempt_id: o.attempt_id,
      installed_at: o.installed_at, collected_at: new Date().toISOString(), active: o.active,
      requests: o.requests.map(r => ({ ...r, text: r.chunks.join(""), chunks: undefined })),
      diagnostics: o.diagnostics,
      status: o.requests.length && !o.active && o.requests.every(r => r.complete && !r.error) ? "captured" : "partial" };
    if (restore && o.active === 0) { o.restore(); value.observer_restored = true; }
    return value;
  }, { attemptId, restore });
}
