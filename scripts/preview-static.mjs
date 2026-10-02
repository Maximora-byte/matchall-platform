// Minimal loopback-only server for browser tests of built static applications.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";

const root = resolve(process.argv[2] || "dist");
const port = Number(process.argv[3] || 4173);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".webp": "image/webp", ".woff2": "font/woff2" };
createServer(async (request, response) => {
  try {
    const path = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    let file = resolve(root, `.${path}`);
    if (file !== root && !file.startsWith(root + sep)) throw new Error("Invalid path");
    if ((await stat(file)).isDirectory()) file = resolve(file, "index.html");
    const body = await readFile(file);
    response.writeHead(200, { "content-type": types[extname(file)] || "application/octet-stream" });
    response.end(body);
  } catch {
    response.writeHead(404);
    response.end("Not found");
  }
}).listen(port, "127.0.0.1", () => console.log(`Static test preview: http://127.0.0.1:${port}`));
