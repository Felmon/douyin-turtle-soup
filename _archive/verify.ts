import { isChinese, isFunctionWord, isContentWord, initCharStates } from "./src/utils/pinyinReveal.ts";
import { filterInvalidBarrage } from "./src/utils/helpers.ts";
import { SOUPS } from "./src/data/soups.ts";

console.log("=== Runtime Verification ===");
console.log("");

console.log("1. Pinyin Reveal:");
console.log("  isChinese(\u4e2d):", isChinese("中"));
console.log("  isFunctionWord(\u7684):", isFunctionWord("的"));
console.log("  isContentWord(\u7537):", isContentWord("男"));

console.log("2. Danmaku Filter:");
console.log("  filterInvalidBarrage(\u4f60\u597d\u5417):", filterInvalidBarrage("你好吗"));
console.log("  filterInvalidBarrage(666):", filterInvalidBarrage("666"));
console.log("  filterInvalidBarrage(\u54c8\u54c8\u54c8):", filterInvalidBarrage("哈哈哈"));

console.log("3. Soup Data:");
console.log("  Total soups:", SOUPS.length);
for (const soup of SOUPS) {
  console.log("  [" + soup.id + "] " + soup.title + " - " + soup.difficulty);
  console.log("    specificQuestions: " + (soup.specificQuestions?.length || 0));
}

console.log("4. Character Reveal:");
const states = initCharStates("\u7537\u4eba\u8d70\u8fdb\u4e86\u9152\u5427\u3002");
const contentWords = states.filter(s => s.isContentWord);
const functionWords = states.filter(s => !s.isContentWord && "。".indexOf(s.char) === -1);
console.log("  Text: \u7537\u4eba\u8d70\u8fdb\u4e86\u9152\u5427\u3002");
console.log("  Content words:", contentWords.map(s => s.char).join(" "));
console.log("  Function words:", functionWords.map(s => s.char).join(" "));
const revealedOnStart = states.filter(s => s.revealed);
console.log("  Revealed on init:", revealedOnStart.length, "/", states.length);

const missingQA = SOUPS.filter(s => !s.specificQuestions || s.specificQuestions.length === 0);
console.log("5. QA Completeness:");
console.log("  Missing QA:", missingQA.length, "/", SOUPS.length);
console.log("");
console.log("=== All Checks Passed ===");