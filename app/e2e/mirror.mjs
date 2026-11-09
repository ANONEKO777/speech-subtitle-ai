// A local stand-in for the download hosts, so the wizard and the model page can download real bytes
// without the network. Models are served from an existing models folder, runtimes from a folder of
// the zips the registry names. Every file keeps its real size and SHA256, so the app's own checks run.
// Usage: const m = await startMirror({ modelsDir, zipDir }); writeMirrors(userData, m); ... m.close();
import { readFileSync, createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const REGISTRY = resolve(here, "../../backend/manager/registry.json");

/** `modelsDir` may be a list of folders, searched in order. */
export function localPath(entry, kind, { modelsDir, zipDir }) {
  if (kind !== "model") return join(zipDir, entry.file);
  const dirs = Array.isArray(modelsDir) ? modelsDir : [modelsDir];
  const found = dirs.map((d) => join(d, entry.id, entry.file)).find((f) => existsSync(f));
  return found ?? join(dirs[0], entry.id, entry.file);
}

export async function startMirror({ modelsDir, zipDir, bytesPerSec = 0 }) {
  const registry = JSON.parse(readFileSync(REGISTRY, "utf8"));
  const byId = new Map([
    ...registry.models.map((m) => [m.id, { entry: m, kind: "model" }]),
    ...registry.runtimes.map((r) => [r.id, { entry: r, kind: "runtime" }]),
  ]);
  const state = { bytesPerSec, served: 0, requests: [] };
  const server = createServer((req, res) => {
    const id = decodeURIComponent((req.url ?? "").split("?")[0].replace(/^\/files\//, ""));
    const found = byId.get(id);
    const file = found ? localPath(found.entry, found.kind, { modelsDir, zipDir }) : null;
    if (!file || !existsSync(file)) {
      res.writeHead(404).end("not served by the mirror");
      return;
    }
    const size = statSync(file).size;
    const range = /bytes=(\d+)-(\d*)/.exec(req.headers.range ?? "");
    const start = range ? Number(range[1]) : 0;
    const end = range && range[2] ? Number(range[2]) : size - 1;
    state.requests.push({ id, start });
    res.writeHead(range ? 206 : 200, {
      "content-length": end - start + 1,
      "accept-ranges": "bytes",
      ...(range ? { "content-range": `bytes ${start}-${end}/${size}` } : {}),
    });
    if (req.method === "HEAD") return res.end();
    const stream = createReadStream(file, { start, end, highWaterMark: 256 * 1024 });
    stream.on("data", (chunk) => {
      state.served += chunk.length;
      res.write(chunk);
      const resume = () => (res.writableNeedDrain ? res.once("drain", () => stream.resume()) : stream.resume());
      if (state.bytesPerSec > 0) {
        stream.pause();
        setTimeout(resume, (chunk.length / state.bytesPerSec) * 1000);
      } else if (res.writableNeedDrain) {
        stream.pause();
        res.once("drain", () => stream.resume());
      }
    });
    stream.on("end", () => res.end());
    res.on("close", () => stream.destroy());
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const port = server.address().port;
  const mirrors = Object.fromEntries(
    [...byId.values()].map(({ entry }) => [entry.url, `http://127.0.0.1:${port}/files/${encodeURIComponent(entry.id)}`]),
  );
  return {
    port,
    mirrors,
    state,
    setRate: (bps) => {
      state.bytesPerSec = bps;
    },
    close: () => new Promise((ok) => (server.closeAllConnections(), server.close(ok))),
  };
}

/** Points the app's downloads at the mirror by writing `storage.json` in the user data folder. */
export function writeMirrors(userData, mirror) {
  mkdirSync(userData, { recursive: true });
  writeFileSync(join(userData, "storage.json"), JSON.stringify({ models_dir: null, mirrors: mirror.mirrors }, null, 1));
}
