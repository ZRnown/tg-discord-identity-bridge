import fs from "node:fs/promises";
import path from "node:path";
import { ContentFilterConfig } from "./bridgeConfig";

type FilterHit = {
  keyword: string;
  source: "text" | "ocr";
};

type FilterResult = {
  blocked: boolean;
  hits: FilterHit[];
  ocrText: string;
};

let ocrWorkerPromise: Promise<any> | null = null;
let ocrWorkerLanguage = "";

function normalize(value: string, caseSensitive: boolean) {
  return caseSensitive ? value : value.toLowerCase();
}

function splitKeywords(keywords: string[]) {
  return keywords.map(k => k.trim()).filter(Boolean);
}

function matchKeywords(text: string, config: ContentFilterConfig, source: "text" | "ocr"): FilterHit[] {
  const keywords = splitKeywords(config.blockedKeywords || []);
  if (!text || keywords.length === 0) return [];

  const haystack = normalize(text, config.caseSensitive);
  return keywords.filter(keyword => {
    const needle = normalize(keyword, config.caseSensitive);
    if (config.matchMode === "exact") {
      return haystack.split(/\s+/).includes(needle);
    }
    return haystack.includes(needle);
  }).map(keyword => ({ keyword, source }));
}

async function getOcrWorker(language: string) {
  if (!ocrWorkerPromise || ocrWorkerLanguage !== language) {
    ocrWorkerLanguage = language;
    ocrWorkerPromise = import("tesseract.js").then(async ({ createWorker }) => {
      return createWorker(language);
    });
  }
  return ocrWorkerPromise;
}

async function recognizeImage(filePath: string, language: string): Promise<string> {
  const resolved = path.resolve(filePath);
  await fs.access(resolved);
  const worker = await getOcrWorker(language);
  const result = await worker.recognize(resolved);
  return result?.data?.text || "";
}

function isImagePath(filePath: string) {
  return /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i.test(filePath);
}

export async function evaluateContentFilter(
  text: string,
  mediaPaths: string[],
  config: ContentFilterConfig,
): Promise<FilterResult> {
  if (!config.enabled) return { blocked: false, hits: [], ocrText: "" };

  const textHits = matchKeywords(text, config, "text");
  let ocrText = "";
  let ocrHits: FilterHit[] = [];

  if (config.ocrEnabled && mediaPaths.length > 0) {
    for (const mediaPath of mediaPaths.filter(isImagePath)) {
      try {
        ocrText += "\n" + await recognizeImage(mediaPath, config.ocrLanguage || "chi_sim+eng");
      } catch (e) {
        console.warn("[ContentFilter] OCR failed:", e);
      }
    }
    ocrHits = matchKeywords(ocrText, config, "ocr");
  }

  const hits = textHits.concat(ocrHits);
  const blocked = textHits.length > 0 || (config.blockOnOcrHit !== false && ocrHits.length > 0);
  return { blocked, hits, ocrText: ocrText.trim() };
}
