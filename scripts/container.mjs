// The package and notes are made here; SVG shapes remain native DrawingML.
import fs from 'node:fs/promises';
import { loadModule, runtimeInfo } from './runtime.mjs';
const [manifestPath, output] = process.argv.slice(2);
const runtime = runtimeInfo();
if (manifestPath === '--probe') {
  console.log(JSON.stringify(runtime));
  process.exit(0);
}
if (!manifestPath || !output) throw new Error('Usage: container.mjs MANIFEST OUTPUT');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
const notes = spec => [spec.claim || '', spec.notes || '',
  ...(spec.sources || []).map(source => 'Source: ' + (typeof source === 'string' ? source : JSON.stringify(source)))
].filter(Boolean).join('\n');
if (runtime.container.engine === 'artifact') {
  const { Presentation, PresentationFile } = loadModule('@oai/artifact-tool');
  const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  for (const spec of manifest.slides) {
    const slide = deck.slides.add();
    slide.background.fill = '#FFFFFF';
    slide.speakerNotes.text = notes(spec);
  }
  const file = await PresentationFile.exportPptx(deck);
  await file.save(output);
} else {
  const PptxGenJS = loadModule('pptxgenjs');
  const deck = new PptxGenJS();
  deck.defineLayout({ name: 'SVG_1280_720', width: 1280 / 96, height: 720 / 96 });
  deck.layout = 'SVG_1280_720';
  deck.title = manifest.title || '';
  deck.author = 'PPT Agent';
  for (const spec of manifest.slides) {
    const slide = deck.addSlide();
    slide.background = { color: 'FFFFFF' };
    slide.addNotes(notes(spec));
  }
  await deck.writeFile({ fileName: output, compression: true });
}
console.log(JSON.stringify({ slides: manifest.slides.length, engine: runtime.container.engine, output }));
