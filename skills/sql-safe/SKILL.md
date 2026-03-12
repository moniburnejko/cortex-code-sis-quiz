---
name: sql-safe
description: Audit quiz.py for SQL injection risks and unsafe Cortex query patterns. Reports PASS/FAIL per item with line numbers and severity. Run before every deploy and after any SQL or call_cortex change.
tools:
  - Read
  - Grep
---

# When to Use

Use this skill when:
- A new `session.sql(f"...")` call was added or modified
- A new `INSERT INTO` statement was added
- The `call_cortex` function was changed
- Reviewing a PR that touches any SQL query construction
- Running the pre-deploy checklist and want a focused SQL-only audit

Invoke with: `/sql-safe` or ask "run sql safety audit on quiz.py".

# Instructions

Read `quiz.py` in full. Check all 6 items below. For each item report PASS or FAIL. On FAIL: show the line number, offending code snippet, severity, and a one-line fix.

## Scan Items

**1. No user-derived values in f-string SQL**
Find every `session.sql(f"...")` call. Only `DATABASE`, `SCHEMA`, and `CORTEX_MODEL` constants (hardcoded at module top) are allowed in f-strings. Any runtime variable (`domain_id`, `difficulty`, dates, user input, `.collect()` results, session state) must use bind params `:1, :2, …`.
- PASS: no runtime variables in f-string SQL body
- FAIL: any runtime variable interpolated directly — severity HIGH

```python
# UNSAFE ❌
session.sql(f"SELECT * FROM {DATABASE}.{SCHEMA}.QUIZ_QUESTIONS WHERE domain_id = '{domain_id}'")

# SAFE ✅
session.sql(f"SELECT * FROM {DATABASE}.{SCHEMA}.QUIZ_QUESTIONS WHERE domain_id = :1", [domain_id])
```

**2. Parameterized INSERT**
Find all `INSERT INTO` statements. Values must be passed as bind params (`:1, :2, …`), not interpolated into the string.
- PASS: `VALUES (:1, :2, ...)` pattern with a params list
- FAIL: `VALUES ('{value}', ...)` f-string pattern — severity HIGH

**3. PARSE_JSON inside VALUES**
Check for `PARSE_JSON(` used inside a `VALUES (` clause.
- PASS: 0 occurrences
- FAIL: any occurrence — severity MEDIUM (use bind params instead)

**4. No dynamic table or schema names**
Table names and schema names must never come from user input or runtime variables. Only `DATABASE` and `SCHEMA` constants (set at module top from hardcoded strings) are acceptable in f-string SQL.
- PASS: no dynamic table/schema names
- FAIL: any runtime variable used as table or schema name — severity HIGH

**5. Dollar-quoting in `call_cortex`**
The `call_cortex(prompt)` function must use `$$...$$` quoting, not single-quote `'...'`. Single quotes break on any apostrophe in the prompt text and may enable injection.
- PASS: `f"SELECT AI_COMPLETE('{CORTEX_MODEL}', $${safe_prompt}$$)"` pattern used
- FAIL: `'` single-quote quoting used for prompt — severity HIGH

**6. `$$` sanitization**
Before interpolating a prompt into `$$...$$`, the code must call `.replace("$$", "$ $")` on the prompt string.
- PASS: `safe_prompt = prompt.replace("$$", "$ $")` (or equivalent) present before interpolation
- FAIL: missing — a `$$` in any question text will break the SQL query — severity MEDIUM

---

## Reporting Format

After checking all 6 items, output a summary table:

| # | Item | Status | Severity | Notes |
|---|------|--------|----------|-------|
| 1 | No user-derived values in f-string SQL | PASS/FAIL | HIGH | line X: `snippet` |
| 2 | Parameterized INSERT | PASS/FAIL | HIGH | |
| 3 | PARSE_JSON inside VALUES | PASS/FAIL | MEDIUM | |
| 4 | No dynamic table/schema names | PASS/FAIL | HIGH | |
| 5 | Dollar-quoting in call_cortex | PASS/FAIL | HIGH | |
| 6 | `$$` sanitization | PASS/FAIL | MEDIUM | |

**Final verdict:**
- All 6 PASS → "✅ All SQL calls are safe. Proceed to deploy."
- Any FAIL → "❌ Fix items [list] before deploying." — show the exact line number and a one-line fix for each FAIL.
