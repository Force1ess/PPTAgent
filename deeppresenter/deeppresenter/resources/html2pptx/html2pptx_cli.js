const fs = require("node:fs");
const path = require("node:path");
const pptxgen = require("pptxgenjs");
const html2pptx = require("./html2pptx");

const LAYOUT_MAP = {
  widescreen: "LAYOUT_WIDE",
  normal: "LAYOUT_4x3",
};

const A1_LAYOUT = {
  name: "A1",
  width: 23.39,
  height: 33.11,
};

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) continue;
    const key = arg.slice(2);
    const value = argv[i + 1];
    args[key] = value;
    i += 1;
  }
  return args;
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

async function run() {
  const args = parseArgs(process.argv);
  const inputDir = args.input;
  const outputFile = args.output;
  const layout = args.layout || "widescreen";
  const tmpDir = args.tmpdir || process.env.TMPDIR;

  if (!inputDir || !outputFile) {
    console.error(
      "Usage: node html2pptx_cli.js --input <html_dir> --output <file.pptx> --layout <widescreen|normal|A1>"
    );
    process.exit(1);
  }

  if (!fs.existsSync(inputDir) || !fs.statSync(inputDir).isDirectory()) {
    console.error(`Input directory not found: ${inputDir}`);
    process.exit(1);
  }

  const htmlFiles = fs
    .readdirSync(inputDir)
    .filter((file) => file.endsWith(".html"))
    .sort()
    .map((file) => path.join(inputDir, file));

  if (htmlFiles.length === 0) {
    console.error(`No HTML files found in: ${inputDir}`);
    process.exit(1);
  }

  const pptx = new pptxgen();
  if (layout === "A1") {
    pptx.defineLayout(A1_LAYOUT);
    pptx.layout = "A1";
  } else if (LAYOUT_MAP[layout]) {
    pptx.layout = LAYOUT_MAP[layout];
  } else {
    console.error(`Unsupported layout: ${layout}`);
    process.exit(1);
  }

  const outputPath = path.resolve(outputFile);
  ensureDir(path.dirname(outputPath));

  for (const htmlFile of htmlFiles) {
    await html2pptx(htmlFile, pptx, tmpDir ? { tmpDir } : {});
  }

  await pptx.writeFile({ fileName: outputPath });
}

run().catch((err) => {
  console.error(err?.stack || err?.message || String(err));
  process.exit(1);
});
