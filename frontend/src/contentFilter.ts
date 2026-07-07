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
const DEFAULT_OCR_LANGUAGE = "chi_sim+eng";

function normalize(value: string, caseSensitive: boolean) {
  let output = String(value ?? "");
  try {
    output = output.normalize("NFKC");
  } catch {}
  output = output.replace(/\p{Cf}/gu, "");
  return caseSensitive ? output : output.toLowerCase();
}

function splitKeywords(keywords: string[]) {
  return keywords.map(k => k.trim()).filter(Boolean);
}

function matchKeywords(
  text: string,
  keywordsInput: string[],
  caseSensitive: boolean,
  source: "text" | "ocr",
): FilterHit[] {
  const keywords = splitKeywords(keywordsInput || []);
  if (!text || keywords.length === 0) return [];

  const haystack = normalize(text, caseSensitive);
  return keywords.filter(keyword => {
    const needle = normalize(keyword, caseSensitive);
    return haystack.includes(needle);
  }).map(keyword => ({ keyword, source }));
}

async function getOcrWorker() {
  if (!ocrWorkerPromise) {
    ocrWorkerPromise = import("tesseract.js").then(async ({ createWorker }) => {
      return createWorker(DEFAULT_OCR_LANGUAGE);
    });
  }
  return ocrWorkerPromise;
}

async function recognizeImage(filePath: string): Promise<string> {
  const resolved = path.resolve(filePath);
  await fs.access(resolved);
  const worker = await getOcrWorker();
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
  const textKeywords = config.blockedKeywords || [];
  const ocrKeywords = config.ocrBlockedKeywords || [];
  const caseSensitive = config.caseSensitive === true;
  const textHits = matchKeywords(text, textKeywords, caseSensitive, "text");
  let ocrText = "";
  let ocrHits: FilterHit[] = [];

  if (ocrKeywords.length > 0 && mediaPaths.length > 0) {
    for (const mediaPath of mediaPaths.filter(isImagePath)) {
      try {
        ocrText += "\n" + await recognizeImage(mediaPath);
      } catch (e) {
        console.warn("[ContentFilter] OCR failed:", e);
      }
    }
    ocrHits = matchKeywords(ocrText, ocrKeywords, caseSensitive, "ocr");
  }

  const hits = textHits.concat(ocrHits);
  const blocked = textHits.length > 0 || (config.blockOnOcrHit !== false && ocrHits.length > 0);
  return { blocked, hits, ocrText: ocrText.trim() };
}
