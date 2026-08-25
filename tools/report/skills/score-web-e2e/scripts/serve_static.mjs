#!/usr/bin/env node
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MIME_TYPES = new Map([
  [".css", "text/css; charset=utf-8"],
  [".gif", "image/gif"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml; charset=utf-8"],
  [".txt", "text/plain; charset=utf-8"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
  [".xml", "application/xml; charset=utf-8"],
]);

function parseArgs(argv) {
  const result = { host: "127.0.0.1", port: "4173", "spa-fallback": false };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (key === "--spa-fallback") {
      result["spa-fallback"] = true;
      continue;
    }
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`参数格式错误: ${key ?? ""}`);
    result[key.slice(2)] = value;
    index += 1;
  }
  return result;
}

function safeFile(root, requestPath) {
  let decoded;
  try {
    decoded = decodeURIComponent(requestPath);
  } catch {
    return null;
  }
  const relative = decoded.replace(/^\/+/, "");
  const resolved = path.resolve(root, relative || "index.html");
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) return null;
  if (!fs.existsSync(resolved)) return null;
  const real = fs.realpathSync(resolved);
  if (real !== root && !real.startsWith(`${root}${path.sep}`)) return null;
  const stat = fs.statSync(real);
  if (stat.isDirectory()) {
    const indexFile = path.join(real, "index.html");
    if (!fs.existsSync(indexFile)) return null;
    const realIndex = fs.realpathSync(indexFile);
    return realIndex.startsWith(`${root}${path.sep}`) && fs.statSync(realIndex).isFile() ? realIndex : null;
  }
  return stat.isFile() ? real : null;
}

function sendFile(response, filename, method) {
  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Type": MIME_TYPES.get(path.extname(filename).toLowerCase()) ?? "application/octet-stream",
  });
  if (method === "HEAD") response.end();
  else fs.createReadStream(filename).pipe(response);
}

export function startStaticServer(options) {
  const requestedRoot = path.resolve(options.root);
  if (!fs.existsSync(requestedRoot) || !fs.statSync(requestedRoot).isDirectory()) {
    throw new Error(`静态站点根目录不存在: ${requestedRoot}`);
  }
  const root = fs.realpathSync(requestedRoot);
  if (options.host !== "127.0.0.1") throw new Error("静态评分服务只允许监听 127.0.0.1");
  const port = Number(options.port);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error(`非法端口: ${options.port}`);
  const spaFallback = Boolean(options.spaFallback);
  const server = http.createServer((request, response) => {
    if (!new Set(["GET", "HEAD"]).has(request.method)) {
      response.writeHead(405, { Allow: "GET, HEAD" });
      response.end("Method Not Allowed");
      return;
    }
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    let filename = safeFile(root, url.pathname);
    if (!filename && spaFallback && !path.extname(url.pathname)) filename = safeFile(root, "/index.html");
    if (!filename) {
      response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      response.end("Not Found");
      return;
    }
    sendFile(response, filename, request.method);
  });
  return { root, server, port };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.root) throw new Error("必须提供 --root");
  const { root, server, port } = startStaticServer({
    root: args.root,
    host: args.host,
    port: args.port,
    spaFallback: args["spa-fallback"],
  });
  server.listen(port, args.host, () => {
    const address = server.address();
    process.stdout.write(`PASS: http://${args.host}:${address.port}/ root=${root}\n`);
  });
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => server.close(() => process.exit(0)));
  }
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`FAIL: ${error.message}\n`);
    process.exitCode = 2;
  }
}
