---
name: cortex-prompt
description: Audit all AI_COMPLETE prompts in quiz.py for JSON reliability, content completeness, and injection safety. Run when question generation returns wrong keys, shallow explanations, or parse errors.
tools:
  - Read
  - Grep
---

# When to Use

Use this skill when:
- `parse_cortex_json` raises a KeyError or returns None for expected fields
- Explanations are too short, generic, or missing per-option reasoning
- Question generation produces questions missing required fields (difficulty, domain, etc.)
- A prompt change was made and needs review before deploying
- Suspecting that a prompt is not dollar-quoted or lacks `$$` sanitization

Invoke with: `/cortex-prompt` or ask "audit the cortex prompts".

# Instructions

Read `quiz.py` in full. Find every string passed to `call_cortex()`. For each prompt, check all 7 items below. Report PASS or FAIL per item. On FAIL: show the function name, line number, and the offending text.

## Scan Items

**1. Explicit output instruction**
The prompt must contain `Return ONLY valid JSON` (or equivalent with "ONLY").
- PASS: phrase "ONLY" is present before or alongside "JSON"
- FAIL: says "return JSON" without "ONLY" - model may add explanation text before/after, breaking `parse_cortex_json`

**2. JSON shape shown as example**
The prompt must include the exact JSON shape expected, with key names and example values.
- PASS: full JSON example with all expected keys is present in the prompt
- FAIL: no example shape - model will invent key names, causing `.get("why_correct")` to return None

**3. No ambiguous key descriptions**
Each key description must be specific and actionable. Flag these patterns as FAIL:
- `"Brief explanation of..."` - "brief" causes the model to skip detail
- `"Explanation of why..."` - too generic; model produces one sentence
- `"URL to documentation"` - model may guess or hallucinate

Good patterns (PASS):
- `"2-3 sentences explaining exactly why X is correct, with Snowflake-specific technical detail"`
- `"for each wrong option (A, C, D), one sentence explaining why it is incorrect"`
- `"exact URL to the most relevant Snowflake documentation page"`

**4. Question generation prompt - required fields**
Applies to prompts that generate quiz questions. Must include all of: difficulty level, domain name, topic list, and a "do not repeat" block with already-asked question summaries.
- PASS: all four are present
- FAIL: any are missing - flag which ones
- N/A: prompt is not a question generation prompt

**5. Explanation prompt - required context**
Applies to prompts that generate explanations. Must include ALL of: full question text, all answer options with letter labels (e.g. `A) text  B) text`), correct answer letter(s), what the student selected, and explicit list of wrong option letters (e.g. `wrong options: A, B, D`).
- PASS: all items present
- FAIL: if `why_wrong` description does not mention specific option letters - model will write one generic sentence instead of per-option explanations
- N/A: prompt is not an explanation prompt

**6. Dollar-quoting**
Prompt must be passed via `$$...$$` quoting, not single-quote `'...'`.
- PASS: `$${safe_prompt}$$` pattern used
- FAIL: `'{prompt}'` pattern used - single quotes break on any apostrophe in question text

**7. `$$` sanitization**
Before interpolating the prompt into `$$...$$`, the code must call `.replace("$$", "$ $")`.
- PASS: `safe_prompt = prompt.replace("$$", "$ $")` (or equivalent) is present
- FAIL: missing - a `$$` in any question text will break the SQL query

---

## Reporting Format

For each prompt found, output a summary table:

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | Explicit output instruction | PASS/FAIL | |
| 2 | JSON shape example | PASS/FAIL | missing keys: ... |
| 3 | No ambiguous key descriptions | PASS/FAIL | line X: `"Brief explanation..."` |
| 4 | Question prompt required fields | PASS/FAIL/N/A | missing: ... |
| 5 | Explanation prompt required context | PASS/FAIL/N/A | missing: ... |
| 6 | Dollar-quoting | PASS/FAIL | |
| 7 | `$$` sanitization | PASS/FAIL | |

**Final verdict per prompt:**
- All 7 PASS → "Prompt is reliable and safe."
- Any FAIL → "Rewrite required." - show the corrected prompt in full.
