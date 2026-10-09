// Prefer host-provided dependencies, then a normal local npm install.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const moduleRoot = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES || process.env.RUNTIME_NODE_MODULES;
const loaders = [moduleRoot && createRequire(path.join(moduleRoot, 'package.json')),
  createRequire(import.meta.url)].filter(Boolean);

export function resolveModule(name) {
  for (const loader of loaders) {
    try { return { loader, resolved: loader.resolve(name) }; }
    catch (error) { if (error.code !== 'MODULE_NOT_FOUND') throw error; }
  }
  return null;
}
export function loadModule(name) {
  const info = resolveModule(name);
  if (!info) throw new Error(`Missing Node package: ${name}. See references/runtime.md.`);
  return info.loader(name);
}
function version(name) {
  const info = resolveModule(name);
  if (!info) return null;
  let folder = path.dirname(info.resolved);
  while (true) {
    const candidate = path.join(folder, 'package.json');
    if (fs.existsSync(candidate)) {
      const metadata = JSON.parse(fs.readFileSync(candidate, 'utf8'));
      if (metadata.name === name) return metadata.version;
    }
    const parent = path.dirname(folder);
    if (parent === folder) return 'unknown';
    folder = parent;
  }
}
export function selectEngine() {
  const requested = process.env.PPT_AGENT_CONTAINER || 'auto';
  if (!['auto', 'artifact', 'pptxgenjs'].includes(requested))
    throw new Error('PPT_AGENT_CONTAINER must be auto, artifact, or pptxgenjs');
  const engine = requested === 'auto'
    ? (resolveModule('@oai/artifact-tool') ? 'artifact' : 'pptxgenjs') : requested;
  const packageName = engine === 'artifact' ? '@oai/artifact-tool' : 'pptxgenjs';
  if (!resolveModule(packageName)) throw new Error(`Missing ${packageName}. See references/runtime.md.`);
  return { engine, packageName, version: version(packageName) };
}
export function runtimeInfo() {
  const container = selectEngine();
  if (!resolveModule('sharp')) throw new Error('Missing sharp. Run npm install in the skill folder.');
  return { container, sharp: version('sharp'), node: process.versions.node };
}
