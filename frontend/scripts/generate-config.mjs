// Vercel 빌드 단계에서 실행: 환경변수 API_BASE_URL → config.js
// (바닐라 정적 사이트는 브라우저에서 환경변수를 읽을 수 없으므로 빌드 시 파일로 주입)
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const apiBaseUrl = (process.env.API_BASE_URL || "").trim().replace(/\/+$/, "");
if (!apiBaseUrl) {
  console.error("❌ API_BASE_URL 환경변수가 없습니다. Vercel 프로젝트 설정 → Environment Variables에 추가하세요.");
  process.exit(1);
}

const target = fileURLToPath(new URL("../config.js", import.meta.url));
writeFileSync(target, `window.APP_CONFIG = ${JSON.stringify({ API_BASE_URL: apiBaseUrl })};\n`);
console.log(`✅ config.js 생성: API_BASE_URL=${apiBaseUrl}`);
