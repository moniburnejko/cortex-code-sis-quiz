---
name: pre-deploy-scan
description: Scan quiz.py for all 22 known deployment blockers before uploading to STAGE_SIS_APP. Reports PASS/FAIL per item with line numbers. Run before every deploy.
tools:
  - Read
  - Grep
---

# When to Use

Run before every deploy of quiz.py to STAGE_SIS_APP. Catches issues that cause silent failures or runtime errors in Streamlit in Snowflake (SiS v1.52.*).

Invoke with: `/pre-deploy-scan` or ask "run pre-deploy scan on quiz.py".

# Instructions

Read `quiz.py` in full. Then check each of the 22 items below. For each item report PASS or FAIL. On FAIL: show the line number and the offending code snippet.

## Scan Items

### SQL and data safety

**1. SQL injection risk**
Find every `session.sql(f"...")` call. Only `DATABASE`, `SCHEMA`, and `CORTEX_MODEL` constants are allowed in f-strings. Any runtime variable (`domain_id`, `difficulty`, dates, user input) must use bind params `:1, :2, …`.
- PASS: user-derived values use bind params
- FAIL: any runtime variable interpolated directly into f-string SQL

**2. Parameterized INSERT**
All `INSERT INTO` statements must use `VALUES (:1, :2, …)` with a params list.
- PASS: bind params used
- FAIL: f-string interpolation of values inside `VALUES (`

**3. PARSE_JSON inside VALUES**
`PARSE_JSON(` must not appear inside a `VALUES (` clause.
- PASS: 0 occurrences
- FAIL: any occurrence (use bind params instead)

**4. SELECT DISTINCT without IS NOT NULL**
Every `SELECT DISTINCT` query must also filter `WHERE column IS NOT NULL`.
- PASS: IS NOT NULL filter present on every SELECT DISTINCT
- FAIL: SELECT DISTINCT without NULL exclusion

### Cortex / AI_COMPLETE

**5. AI_COMPLETE dollar-quoting**
The `call_cortex` function must use `$$...$$` quoting, not single-quote `'...'`.
- PASS: `$${safe_prompt}$$` pattern used
- FAIL: single-quote quoting — breaks on apostrophes in question text

**6. `$$` sanitization**
Before interpolating a prompt into `$$...$$`, the code must call `.replace("$$", "$ $")`.
- PASS: `safe_prompt = prompt.replace("$$", "$ $")` present
- FAIL: missing — a `$$` in question text will break the SQL query

**7. json.loads() on Cortex output**
`json.loads(response)` must never be called directly on a Cortex response. All parsing must go through `parse_cortex_json()`.
- PASS: 0 direct json.loads on Cortex output
- FAIL: any such occurrence (Cortex may return markdown fences or double-encoded JSON)

**8. `from snowflake.cortex import complete`**
Must not appear. Use `AI_COMPLETE` via `session.sql()` only.
- PASS: 0 occurrences
- FAIL: any occurrence

### Streamlit in Snowflake compatibility

**9. `st.rerun()` count**
Count all occurrences.
- PASS: exactly 1 occurrence, in the Submit Answer handler only
- FAIL: 0 occurrences (submit button stays active after click)
- FAIL: 2 or more occurrences (double-rerun causes blank screen)

**10. `st.experimental_rerun()`**
Must not appear.
- PASS: 0 occurrences
- FAIL: any occurrence (deprecated, crashes SiS)

**11. `@st.fragment` / `st.fragment(`**
Must not appear. Not supported in SiS.
- PASS: 0 occurrences
- FAIL: any occurrence

**12. `st.container(horizontal=True)`**
Must not appear. Use `st.columns()`.
- PASS: 0 occurrences
- FAIL: any occurrence (not available in SiS v1.52.*)

**13. `.applymap(`**
Must not appear.
- PASS: 0 occurrences
- FAIL: any occurrence (removed in pandas ≥ 2.1, use `.map(` instead)

**14. `st.connection("snowflake")`**
Must not appear. Use `get_active_session()` only.
- PASS: 0 occurrences
- FAIL: any occurrence

**15. `unsafe_allow_html=True` or `<style>` injection**
Must not appear. No inline CSS.
- PASS: 0 occurrences
- FAIL: any occurrence

### Session and rendering

**16. `get_active_session()` inside `@st.cache_data`**
Every `@st.cache_data` function must call `get_active_session()` inside its own body. Reusing the module-level session in a cached context causes a runtime error.
- PASS: each cached function calls get_active_session() internally
- FAIL: any cached function uses a module-level session variable

**17. `st.set_page_config` position and layout**
`st.set_page_config(layout="centered")` must be the very first `st.*` call in the file.
- PASS: it is the first `st.` call (ignoring imports and comments) and `layout="centered"`
- FAIL: any `st.` call appears before it
- FAIL: `layout="wide"` is used

**18. Screen transitions**
Setting `st.session_state["screen"]` and returning is the correct pattern. Calling `st.rerun()` on a screen transition is a bug (counts against item 9).
- PASS: screen transitions use session_state assignment only
- FAIL: st.rerun() called in a screen transition handler

### Date handling

**19. Date from `.collect()` without cast**
Any timestamp value from `.collect()` passed to `st.date_input` or date arithmetic must be cast: `datetime.date(raw.year, raw.month, raw.day)`.
- PASS: all collect() dates are cast before use
- FAIL: raw Snowflake datetime object passed directly to a widget

**20. Date range query pattern**
Comparisons against `TIMESTAMP_NTZ`: dates must be passed as formatted strings (`strftime("%Y-%m-%d")`); end date must use exclusive upper bound (`< end + 1 day`).
- PASS: pattern followed
- FAIL: date object passed directly or inclusive end bound used

**21. `st.slider` with date variable**
Must not receive a `datetime.date` as `min_value` / `max_value`. Use `st.date_input` for date ranges.
- PASS: 0 violations
- FAIL: any st.slider call with a date-typed min/max

### Column names

**22. Column name normalization**
All `.as_dict()` results must be normalized: `{k.upper(): v for k, v in row.as_dict().items()}`. Snowflake returns uppercase column names; accessing them with lowercase keys returns `None`.
- PASS: normalization applied to every as_dict() call
- FAIL: any as_dict() result accessed without uppercasing keys

---

## Reporting Format

After checking all 22 items, output a summary table:

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | SQL injection | PASS/FAIL | line X: `snippet` |
| 2 | Parameterized INSERT | PASS/FAIL | |
| 3 | PARSE_JSON in VALUES | PASS/FAIL | |
| 4 | SELECT DISTINCT NULL | PASS/FAIL | |
| 5 | Dollar-quoting | PASS/FAIL | |
| 6 | `$$` sanitization | PASS/FAIL | |
| 7 | json.loads direct | PASS/FAIL | |
| 8 | cortex import | PASS/FAIL | |
| 9 | st.rerun() count | PASS/FAIL | found N occurrences |
| 10 | experimental_rerun | PASS/FAIL | |
| 11 | st.fragment | PASS/FAIL | |
| 12 | container horizontal | PASS/FAIL | |
| 13 | applymap | PASS/FAIL | |
| 14 | st.connection snowflake | PASS/FAIL | |
| 15 | unsafe_allow_html | PASS/FAIL | |
| 16 | get_active_session in cache | PASS/FAIL | |
| 17 | set_page_config first | PASS/FAIL | |
| 18 | screen transitions | PASS/FAIL | |
| 19 | date cast from collect() | PASS/FAIL | |
| 20 | date range query pattern | PASS/FAIL | |
| 21 | slider date | PASS/FAIL | |
| 22 | column name normalization | PASS/FAIL | |

**Final verdict:**
- All 22 PASS → "✅ Clean. Proceed to deploy."
- Any FAIL → "❌ Fix items [list] before deploying."

For each FAIL item: show the exact line number and a 1-line fix suggestion.
