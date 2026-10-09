// Source SVG preview; never used as presentation page content.
import { loadModule } from './runtime.mjs';
const sharp = loadModule('sharp');
const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: preview.mjs SVG PNG');
await sharp(input, { density: 96 }).resize(1280, 720).png().toFile(output);
