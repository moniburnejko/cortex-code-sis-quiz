---
name: streamlit-in-snowflake
description: Coding patterns and pre-deploy checks for Streamlit in Snowflake (SiS v1.52.*). Use when writing, reviewing, or debugging any SiS app - and before every deploy to catch known runtime failures.
tools:
  - Read
  - Grep
---

# When to Use

- Writing any Streamlit in Snowflake app (connection, caching, navigation, SQL)
- Reviewing generated code before deploying
- Debugging runtime errors specific to SiS
- Before every deploy: run `/streamlit-in-snowflake` and invoke the pre-deploy scan

# Coding Patterns

## Connection

Always use `get_active_session()` from `snowflake.snowpark.context`. Never use `st.connection("snowflake")`.

Inside `@st.cache_data` functions: call `get_active_session()` **inside** the function body - not at module level.
Module-level `session = get_active_session()` is fine for non-cached code (DML, AI_COMPLETE).

```python
from snowflake.snowpark.context import get_active_session

session = get_active_session()   # module-level - used for DML and AI_COMPLETE

@st.cache_data(ttl=300)
def load_domains():
    _session = get_active_session()   # inside cached function - required
    return _session.sql(...).collect()
```

## Screen Routing

Use `st.session_state` flags for navigation. No `st.rerun()` needed for screen switches.

```python
if st.button("Start Round"):
    st.session_state["screen"] = "quiz"   # flag only, no rerun

screen = st.session_state.get("screen", "home")
if screen == "home":
    render_home()
elif screen == "quiz":
    render_quiz()
else:
    render_summary()
```

## st.rerun() - exactly 2 occurrences allowed

`st.rerun()` is valid in exactly two places:
1. Submit Answer button handler - to hide submit and reveal answered state
2. Retry button in AI question error screen - to trigger a fresh generation attempt

Everywhere else: use session state flags. Extra reruns cause blank screens.

```python
if st.button("Submit Answer", disabled=submit_disabled):
    st.session_state["answered"] = True
    st.rerun()   # occurrence 1
```

## Multi-Answer Checkboxes

Do not use `@st.fragment`. Use manual checkbox state.

```python
for opt in options:
    st.checkbox(f"{opt}) {option_texts[opt]}", key=f"cb_{opt}", disabled=answered)
selected = [o for o in options if st.session_state.get(f"cb_{o}")]
```

On "Next": clear checkbox state manually:
```python
for opt in ["A", "B", "C", "D", "E"]:
    if f"cb_{opt}" in st.session_state:
        del st.session_state[f"cb_{opt}"]
```

## Date Values from .collect()

Cast to `datetime.date()` before passing to any Streamlit widget:

```python
raw = session.sql("SELECT MIN(logged_at), MAX(logged_at) FROM ...").collect()[0]
if raw[0] is None:
    st.info("No entries yet.")
    st.stop()
min_date = datetime.date(raw[0].year, raw[0].month, raw[0].day)
max_date = datetime.date(raw[1].year, raw[1].month, raw[1].day)
```

Date range queries: pass as formatted strings, use exclusive upper bound (`< end + 1 day`).

## Column Names after .collect()

Snowflake returns UPPERCASE column names. Normalize with:
```python
{k.upper(): v for k, v in row.as_dict().items()}
```

## Session State Reliability in SiS

SiS serializes session_state between reruns. Mutable objects (lists, sets, dicts) stored directly in session_state may not survive reliably — in-place mutations (`.append()`, `.add()`, `dict[key] = val`) are NOT detected by the serializer.

**Rules:**
1. **Never use separate tracking lists/sets in session_state** for deduplication or counters. They will silently reset.
2. **Use `round_history`** (which is built in the Submit handler + `st.rerun()`) as the single source of truth for "what has been shown."
3. **For DB dedup:** collect `question_text` values from `round_history` + current question, pass them as bind params to `NOT IN` in SQL.
4. **For AI dedup:** collect `question_text[:80]` from `round_history`, pass as "DO NOT repeat" block in the prompt.
5. **Never rely on state written in the "Next" button handler** (which does NOT call `st.rerun()`). Only state written before a `st.rerun()` is guaranteed to persist.

```python
# GOOD — dedup via round_history (survives reruns)
def _get_shown_texts():
    texts = [h["question_text"] for h in st.session_state.get("round_history", []) if h.get("question_text")]
    current_q = st.session_state.get("question")
    if current_q and current_q.get("QUESTION_TEXT"):
        texts.append(current_q["QUESTION_TEXT"])
    return texts

# BAD — mutable list in session_state (unreliable in SiS)
# st.session_state["shown_ids"].append(id)  # may be lost on rerun
# st.session_state["shown_ids"] = new_list   # still unreliable without rerun
```

## Styling

No `unsafe_allow_html=True`, no inline CSS. Use native Streamlit components:
- `st.markdown()` for result row — plain bold text only, no colored boxes for correct/incorrect feedback
- `st.info()` for mnemonic box (`💡 Remember: ...`)
- `st.success()` / `st.warning()` for pass/fail summary (one-line only)
- `st.caption()` for secondary/metadata text (domain, difficulty, dates)
- `st.container(border=True)` for card-style grouping (supported in SiS 1.52.*)
- `st.progress(value, text="...")` — `text` param supported in SiS 1.52.*
- `st.set_page_config(layout="centered")` must be the **first** `st.*` call in the file

## SQL Safety

Only `DATABASE`, `SCHEMA`, and `CORTEX_MODEL` constants in f-string SQL. All user-derived values via bind params:

```python
session.sql("SELECT * FROM ... WHERE domain_id = :1", [domain_id]).collect()
```

---

# Pre-Deploy Scan

Run before every deploy of quiz.py to STAGE_SIS_APP. Catches issues that cause silent failures or runtime errors in SiS v1.52.*.

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
- FAIL: single-quote quoting - breaks on apostrophes in question text

**6. `$$` sanitization**
Before interpolating a prompt into `$$...$$`, the code must call `.replace("$$", "$ $")`.
- PASS: `safe_prompt = prompt.replace("$$", "$ $")` present
- FAIL: missing - a `$$` in question text will break the SQL query

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
- PASS: exactly 2 occurrences - Submit Answer handler and Retry button handler (AI question error screen)
- FAIL: 0 or 1 occurrence (submit button stays active after click, or Retry button does nothing)
- FAIL: 3 or more occurrences (extra reruns cause blank screen)

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
- All 22 PASS → "Clean. Proceed to deploy."
- Any FAIL → "Fix items [list] before deploying."

For each FAIL item: show the exact line number and a 1-line fix suggestion.
