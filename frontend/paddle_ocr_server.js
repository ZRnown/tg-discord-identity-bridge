const http = require("node:http");
const { createWorker } = require("tesseract.js");

const port = Number(process.env.OCR_PORT || 8765);
const language = process.env.OCR_LANG || "chi_sim+eng";
let workerPromise;

function getWorker() {
  if (!workerPromise) workerPromise = createWorker(language);
  return workerPromise;
}

const server = http.createServer(async (req, res) => {
  if (req.method !== "POST" || req.url !== "/ocr") {
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "POST /ocr with { imagePath }" }));
    return;
  }

  let body = "";
  req.on("data", chunk => { body += chunk; });
  req.on("end", async () => {
    try {
      const { imagePath } = JSON.parse(body || "{}");
      if (!imagePath) throw new Error("imagePath is required");
      const worker = await getWorker();
      const result = await worker.recognize(imagePath);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ text: result.data.text || "" }));
    } catch (err) {
      res.writeHead(400, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: String(err.message || err) }));
    }
  });
});

server.listen(port, () => {
  console.log(`OCR server listening on http://localhost:${port}/ocr`);
});
