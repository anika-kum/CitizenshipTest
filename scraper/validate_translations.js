#!/usr/bin/env node
// Validates every translation pack in translations/ against questions.js.
// Hard failures (exit 1): missing question ids, missing/empty question text,
// answer array length mismatches, missing _ui keys, malformed files.
// Warnings: translated text identical to English (legitimate for proper
// nouns, worth eyeballing everywhere else).
//
// Usage: node scraper/validate_translations.js

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const QUESTIONS = eval(fs.readFileSync(path.join(root, 'questions.js'), 'utf8') + '; QUESTIONS');
const DYNAMIC_IDS = new Set(QUESTIONS.filter(q => q.dynamic).map(q => q.id));
const UI_KEYS = ['offline', 'repsNote', 'dcNoSenators', 'dcNoGovernor', 'dcMayor', 'dcCapital'];

const dir = path.join(root, 'translations');
const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort() : [];
if (files.length === 0) {
  console.error('No translation packs found in translations/');
  process.exit(1);
}

let hardFailures = 0;

for (const file of files) {
  const lang = file.replace('.js', '');
  const errors = [];
  const warnings = [];
  let pack;

  try {
    const src = fs.readFileSync(path.join(dir, file), 'utf8');
    const registerTranslations = (l, p) => {
      if (l !== lang) errors.push(`registers language "${l}" but file is named ${file}`);
      pack = p;
    };
    eval(src);
    if (!pack) throw new Error('registerTranslations was never called');
  } catch (e) {
    console.error(`${lang}: FAILED TO LOAD — ${e.message}`);
    hardFailures++;
    continue;
  }

  const ui = pack._ui || {};
  for (const key of UI_KEYS) {
    if (!ui[key] || !ui[key].trim()) errors.push(`_ui.${key} missing or empty`);
  }
  if (ui.dcMayor && !ui.dcMayor.includes('{name}')) errors.push('_ui.dcMayor is missing the {name} placeholder');

  let identical = 0;
  for (const q of QUESTIONS) {
    const entry = pack[q.id];
    if (!entry) { errors.push(`question ${q.id} missing`); continue; }
    if (!entry.q || !entry.q.trim()) errors.push(`question ${q.id} has empty q`);
    else if (entry.q === q.question) { identical++; warnings.push(`question ${q.id} text identical to English`); }

    if (DYNAMIC_IDS.has(q.id)) {
      if (entry.a !== null) errors.push(`question ${q.id} is dynamic — a must be null`);
    } else {
      if (!Array.isArray(entry.a)) { errors.push(`question ${q.id} answers not an array`); continue; }
      if (entry.a.length !== q.answers.length)
        errors.push(`question ${q.id} has ${entry.a.length} answers, English has ${q.answers.length}`);
      entry.a.forEach((a, i) => { if (!a || !a.trim()) errors.push(`question ${q.id} answer ${i} empty`); });
    }
  }

  const extraneous = Object.keys(pack).filter(k => k !== '_ui' && !QUESTIONS.some(q => String(q.id) === k));
  if (extraneous.length) errors.push(`unknown keys: ${extraneous.join(', ')}`);

  if (errors.length) {
    hardFailures++;
    console.error(`${lang}: ${errors.length} ERROR(S)`);
    errors.slice(0, 15).forEach(e => console.error(`   - ${e}`));
    if (errors.length > 15) console.error(`   … and ${errors.length - 15} more`);
  } else {
    console.log(`${lang}: OK (128 questions, ${warnings.length} identical-to-English warnings)`);
  }
}

process.exit(hardFailures ? 1 : 0);
