const { createWorker } = require("tesseract.js");

async function main() {
  const imagePath = process.argv[2];
  if (!imagePath) {
    console.error("Usage: node test_ocr.js <image-path> [language]");
    process.exit(1);
  }

  const language = process.argv[3] || "chi_sim+eng";
  const worker = await createWorker(language);
  try {
    const result = await worker.recognize(imagePath);
    console.log(result.data.text.trim());
  } finally {
    await worker.terminate();
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
