# AGENTS.md
> snowpro core certification quiz - streamlit in snowflake
> cortex code in snowsight project

## what this is

this file gives cortex code the full context it needs to autonomously:

1. create EXAM_DOMAINS, QUIZ_QUESTIONS, QUIZ_REVIEW_LOG, and QUIZ_SESSION_LOG tables
2. populate EXAM_DOMAINS from SnowProCoreStudyGuide.pdf; load QUIZ_QUESTIONS from quiz_questions.csv
3. build and deploy a certification quiz app in streamlit in snowflake
4. support runtime AI question generation and explanation via cortex AI functions
5. track learning progress across quiz sessions

> **why 4 tables?** QUIZ_REVIEW_LOG stores per-question wrong answers (Review tab + domain error analysis). QUIZ_SESSION_LOG stores per-round summaries (score, round size - needed for progress metrics). they can't be merged because rounds with 0 wrong answers have no QUIZ_REVIEW_LOG rows, so session data would be lost.

this is a scoped project. do not touch any database or schema other than the one configured below.

---

## snowflake environment

| setting   | value                    |
|-----------|--------------------------|
| database  | `CORTEX_DB`              |
| schema    | `CORTEX_DB.QUIZ_COF_C02` |
| warehouse | `CORTEX_WH`              |
| role      | `CORTEXADMIN`            |
| exam_code | `COF-C02`                |
| stage     | `STAGE_QUIZ_DATA`        |
| app stage | `STAGE_SIS_APP`          |
| app_name  | `SNOWPRO_QUIZ`           |
| main_file | `quiz.py`                |

each exam uses a dedicated schema (`QUIZ_<EXAM_CODE>`). never share a schema between exams. to switch exams: use the `/switch-exam` skill.

all sections reference these values. never hardcode environment names elsewhere in this file.

---

## how to proceed

the database, schema, warehouse, and role already exist. do NOT attempt to create them.

verify session context by running:
```sql
SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA();
```
confirm values match the environment table. if they do not match, run the appropriate USE statements. if the database or schema does not exist, stop and tell the user - do not create them.

before writing any streamlit code: read the "platform constraints" section of this file.

---

## source files

files uploaded to `{database}.{schema}.STAGE_QUIZ_DATA` via snowsight ui.

### stage DDL

both stages must be created in Phase 1 before any file uploads. `STAGE_QUIZ_DATA` requires encryption and directory for `AI_PARSE_DOCUMENT` to work.

```sql
CREATE STAGE IF NOT EXISTS {database}.{schema}.STAGE_QUIZ_DATA
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);

CREATE STAGE IF NOT EXISTS {database}.{schema}.STAGE_SIS_APP;
```

**why these settings matter:**
- `ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')` — required by `AI_PARSE_DOCUMENT`. without server-side encryption, Cortex AI functions cannot read staged files. this is the #1 cause of "file not accessible" errors after PDF upload.
- `DIRECTORY = (ENABLE = TRUE)` — required for Cortex AI functions to enumerate and reference files by path.

if `STAGE_QUIZ_DATA` already exists without these settings, recreate it:
```sql
DROP STAGE IF EXISTS {database}.{schema}.STAGE_QUIZ_DATA;
CREATE STAGE {database}.{schema}.STAGE_QUIZ_DATA
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);
```
then re-upload files via Snowsight UI.

| file | purpose |
|---|---|
| `SnowProCoreStudyGuide.pdf` | EXAM_DOMAINS - extract 6 domains, weights, topics via AI_PARSE_DOCUMENT + AI_COMPLETE |
| `quiz_questions.csv` | QUIZ_QUESTIONS - ~1.1K complete questions (all 6 domains) |

### CSV column order (quiz_questions.csv)

```
question_id, domain_id, difficulty, question_text,
is_multi, option_a, option_b, option_c, option_d, option_e,
correct_answer, source
```

load into `QUIZ_QUESTIONS` using:
- file format `FF_CSV`: type CSV, `FIELD_OPTIONALLY_ENCLOSED_BY = '"'`, `SKIP_HEADER = 1`, `NULL_IF = ('')`
- `COPY INTO` from `@{database}.{schema}.STAGE_QUIZ_DATA/quiz_questions.csv` with an explicit column list in CSV order and explicit type casts matching the schema above
- after load: `UPDATE QUIZ_QUESTIONS q SET q.domain_name = d.domain_name FROM EXAM_DOMAINS d WHERE q.domain_id = d.domain_id`

---

## table schemas

### EXAM_DOMAINS

```sql
CREATE TABLE IF NOT EXISTS {database}.{schema}.EXAM_DOMAINS (
    domain_id    VARCHAR PRIMARY KEY,
    domain_name  VARCHAR NOT NULL,
    weight_pct   FLOAT NOT NULL,
    topics       VARIANT,            -- JSON array of topic strings
    key_facts    VARCHAR             -- numbered list of testable facts extracted from study guide
);
```

extract from `SnowProCoreStudyGuide.pdf` using AI_PARSE_DOCUMENT + AI_COMPLETE. do NOT hardcode domain values.

after inserting all 6 domains, populate `key_facts` for each domain. for each domain run:

```sql
UPDATE {database}.{schema}.EXAM_DOMAINS
SET key_facts = AI_COMPLETE(
    '{CORTEX_MODEL}',
    $$You are preparing a SnowPro Core COF-C02 exam study guide.
From the documentation below, extract the facts a student must know about the "{domain_name}" domain.
Focus on: exact limits and default values, specific behaviors and constraints, key differences between features, common misconceptions (what X does NOT do), correct Snowflake-specific terminology.
Return a numbered list of up to 40 precise testable facts. Each fact max 120 characters.
Do NOT include general conceptual descriptions - only specific verifiable facts.

Documentation:
{AI_PARSE_DOCUMENT content for this domain}$$
)
WHERE domain_id = '{domain_id}';
```

use AI_PARSE_DOCUMENT on `@{database}.{schema}.STAGE_QUIZ_DATA/SnowProCoreStudyGuide.pdf` to get the document content, then pass it as context for each domain's extraction. if `key_facts` is NULL after update (AI_COMPLETE failed), set it to an empty string — do not leave NULL.

### QUIZ_QUESTIONS

```sql
CREATE TABLE IF NOT EXISTS {database}.{schema}.QUIZ_QUESTIONS (
    question_id    NUMBER AUTOINCREMENT PRIMARY KEY,
    domain_id      VARCHAR NOT NULL,
    domain_name    VARCHAR,
    difficulty     VARCHAR DEFAULT 'medium',    -- easy | medium | hard
    question_text  VARCHAR(2000) NOT NULL,
    is_multi       BOOLEAN DEFAULT FALSE,
    option_a       VARCHAR(500)  NOT NULL,
    option_b       VARCHAR(500)  NOT NULL,
    option_c       VARCHAR(500),
    option_d       VARCHAR(500),
    option_e       VARCHAR(500),
    correct_answer VARCHAR NOT NULL,            -- 'A' or 'A,C' for multi
    source         VARCHAR DEFAULT 'MANUAL',    -- MANUAL | AI_GENERATED
    created_at     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

### QUIZ_REVIEW_LOG

```sql
CREATE TABLE IF NOT EXISTS {database}.{schema}.QUIZ_REVIEW_LOG (
    log_id         NUMBER AUTOINCREMENT PRIMARY KEY,
    logged_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    domain_id      VARCHAR,
    domain_name    VARCHAR,
    difficulty     VARCHAR,
    question_text  VARCHAR,
    correct_answer VARCHAR,      -- full text e.g. "C) FLATTEN()" not just "C"
    mnemonic       VARCHAR(500),
    doc_url        VARCHAR(500)
);
```

### QUIZ_SESSION_LOG

```sql
CREATE TABLE IF NOT EXISTS {database}.{schema}.QUIZ_SESSION_LOG (
    session_id     NUMBER AUTOINCREMENT PRIMARY KEY,
    session_ts     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    exam_code      VARCHAR,
    round_size     INT,
    correct_count  INT,
    score_pct      FLOAT,
    domain_filter  VARCHAR,
    difficulty     VARCHAR
);
```

---

## platform constraints

these are Snowflake / Streamlit-in-Snowflake requirements. they are not style preferences - violating them causes runtime errors or security issues.

### session

- always `get_active_session()` from `snowflake.snowpark.context`. never `st.connection("snowflake")`.
- inside `@st.cache_data` functions: call `get_active_session()` **inside the function body** - the module-level session object is not available in cached context.
- module-level `session = get_active_session()` is valid for non-cached code (DML, AI_COMPLETE calls).

### re-rendering

- `st.rerun()` is allowed in exactly two places: the Submit Answer button handler (to hide submit and reveal answered state), and the Retry button in the AI question error screen (to trigger a fresh generation attempt after clearing error state).
- never call `st.rerun()` from screen transitions (home >quiz, quiz >summary). set `st.session_state["screen"]` and let the next interaction re-render.

### unsupported apis

- `@st.fragment` - not supported in SiS. do not use.
- `st.experimental_rerun()` - deprecated. use `st.rerun()`.
- `st.container(horizontal=True)` - not supported. use `st.columns()`.
- `.applymap()` - removed in pandas ≥ 2.1. use `.map()`.
- `from snowflake.cortex import complete` - do not import. use `AI_COMPLETE` via `session.sql()`.

### supported apis (confirmed in SiS 1.52.*)

- `st.container(border=True)` - supported. use for card-style grouping.
- `st.progress(value, text="...")` - `text` parameter supported. use for labeled progress bars.
- `st.segmented_control(label, options, format_func=..., default=...)` - supported. use for single-select pill-style controls (e.g. difficulty, question source). always guard against `None` return: `if value is None: value = default`.

### multi-answer questions

render each option as an independent `st.checkbox` with a stable key (e.g. `cb_A`). read selected options by checking session state after rendering. disable all checkboxes once answered. on "Next": delete all `cb_*` keys from session state manually.

### dates from `.collect()`

snowflake returns timestamps as snowflake datetime objects, not Python `datetime.date`. convert with `datetime.date(raw.year, raw.month, raw.day)` before passing to `st.date_input` or date arithmetic.

date range queries against `TIMESTAMP_LTZ` columns: pass start and end as formatted strings (`"%Y-%m-%d"`). add 1 day to end date and use `< end` (exclusive) to include the full last day.

### column names

snowflake returns UPPERCASE column names from `.collect()`. normalize with `{k.upper(): v for k, v in row.as_dict().items()}`.

---

## cortex llm

preferred model: `claude-sonnet-4-5`. store as constant `CORTEX_MODEL`.

account region `AWS_EU_CENTRAL_1` requires `CORTEX_ENABLED_CROSS_REGION = 'AWS_US'`.

### calling AI_COMPLETE

call via `session.sql()` with dollar-quoting: `SELECT AI_COMPLETE('{CORTEX_MODEL}', $${prompt}$$)`.

before interpolating the prompt, replace any `$$` occurrences with `$ $` to prevent dollar-quote breakout. `CORTEX_MODEL` is a constant - safe to interpolate. never interpolate user-derived values into the SQL string.

on exception: store the error string in `st.session_state["last_cortex_error"]`; return `None`. on empty result: return `None`.

### parsing AI_COMPLETE responses

AI_COMPLETE has three known encoding issues:
1. **markdown fences** - response wrapped in ` ```json ... ``` `
2. **double-encoded JSON** - `json.loads()` returns a `str` instead of `dict`; parse again
3. **JSON-encoded string containing markdown-fenced JSON** - response starts with `"`, `json.loads()` returns a string like `` ```json\n{...}\n``` ``; must strip fences from that string before the second parse

parsing function must: extract a helper `_strip_fences(text)` >apply it to initial text >
`json.loads()` >if result is `str`, apply `_strip_fences` again then `json.loads()` again >
fallback: regex-extract first `{…}` block and parse >return `None` on all failures (never raise).

always call `isinstance(result, dict)` before calling `.get()` on the return value.

never call `json.loads()` directly on a Cortex response - always go through the parsing function.

### difficulty guide

define `DIFFICULTY_GUIDE` dict at module level. descriptions define **how** to ask (depth, style, trickiness) — NOT **what** topics to ask about. the domain and topics list control the topic; difficulty controls the framing.

```python
DIFFICULTY_GUIDE = {
    "easy": (
        "EASY — single-concept recall. "
        "Ask 'What is X?', 'Which feature does Y?', or 'What happens when Z?'. "
        "One fact, one clearly correct answer. The wrong options should be obviously wrong "
        "to someone who studied the material."
    ),
    "medium": (
        "MEDIUM — applied scenario. "
        "Present a real-world use-case and ask which approach, feature, or configuration is best. "
        "Requires understanding trade-offs. All four options should be plausible Snowflake features "
        "but only one fits the scenario."
    ),
    "hard": (
        "HARD — tricky edge cases and gotchas. "
        "Ask about exceptions to general rules, counterintuitive behaviors, precise limits, "
        "or scenarios where the obvious answer is wrong. "
        "All options must look plausible — the correct answer should surprise someone "
        "who only has surface-level knowledge. "
        "Pick ANY topic from the domain — do not limit to a fixed set of topics."
    ),
}
```

### AI question generation

the prompt must put **difficulty as the primary constraint** (before any grounding/facts). structure:

```
=== DIFFICULTY: {difficulty.upper()} ===
{DIFFICULTY_GUIDE[difficulty]}

This difficulty level is your PRIMARY constraint. ...
Self-check: "Would someone who only memorized definitions get this right?" — if YES, make it harder.

Reference material (use for factual accuracy only): {key_facts or domain+topics}

DO NOT generate any of these questions: {no_repeat_block}
```

if `key_facts` is empty for a domain, use domain + topics as reference material instead.

length constraints (include explicitly in the prompt):
- `question_text`: max 150 characters
- each option: max 80 characters

to avoid repetition: use `_get_shown_texts()` (same helper as DB dedup) to collect question texts from `round_history` + current question. truncate each to 80 chars, take last 10, and include as a "DO NOT generate any of these questions" block in the prompt.

validate the parsed result: `question_text`, `option_a`, `option_b`, `correct_answer` must all be non-empty. retry up to 3 times on failure.

**UX**: wrap the generation loop in `with st.spinner("Generating question..."):`

after a successful generation and validation: INSERT the question into `QUIZ_QUESTIONS` using bind params (domain_id, domain_name, difficulty, question_text, is_multi, option_a through option_e, correct_answer, source='AI_GENERATED'). then query back the `question_id` (`SELECT question_id ... WHERE source='AI_GENERATED' AND domain_id=:1 AND question_text=:2 ORDER BY created_at DESC LIMIT 1`) and set it on the returned dict. if the INSERT fails: log the error to `last_cortex_error` and continue - return the question with `QUESTION_ID: None`.

### AI explanation generation

generate explanations **in the render phase** (`if answered:` block), not in the Submit handler. this keeps submit fast and the Cortex call lazy.

**correct answer:** fetch `doc_url` only — minimal Cortex call returning `{"doc_url": "https://..."}`. render as a plain markdown link below the result row. no expander.

**wrong answer:** full explanation — `why_correct`, `why_wrong`, `mnemonic`, `doc_url`. render inside expander.

explanation state in `st.session_state["explanation"]`:
- `None` >not yet attempted; call Cortex and store result
- `{}` >tried and failed (sentinel - do not retry)
- `{dict}` >success; render

**UX**: wrap the Cortex call in `with st.spinner("Generating explanation..."):`

the explanation prompt must produce **rich, exam-relevant content**. include:
- the full question text
- all answer options with their letter labels
- the correct answer letter(s)
- what the student selected
- the list of wrong option letters (all options not in correct_answer)

ask Cortex to return ONLY valid JSON with these keys:
- `why_correct`: 2-3 sentences explaining exactly why the correct answer is right, with Snowflake-specific technical detail
- `why_wrong`: for **each wrong option separately** (not a single generic sentence), one sentence explaining why it is incorrect - pass the wrong option letters explicitly so the AI knows which ones to cover
- `mnemonic`: a memorable phrase, acronym, or analogy to help remember the correct answer
- `doc_url`: exact URL to the most relevant Snowflake documentation page

**result row** (always shown, for all answers) — plain markdown, no colored boxes:
```python
if is_correct:
    st.markdown("**Correct!**")
    st.markdown(f"Your answer: {letter}) {full_text}")
else:
    st.markdown("**Incorrect!**")
    st.markdown(f"Correct answer: {correct_letter}) {correct_text}")
    st.markdown(f"Your answer: {selected_letter}) {selected_text}")
```

rendering (`st.expander("✨ AI Explanation", expanded=True)`):
- `why_correct` >bold header + `st.write()`
- `why_wrong` >bold header + render each option separately if value is a dict; plain `st.write()` if string
- `mnemonic` >`st.info("💡 Remember: ...")` - prominent box
- `doc_url` >markdown link

render the full expander (`why_correct`, `why_wrong`, `mnemonic`) when `use_explanations` and the explanation dict has content.

render `doc_url` as a documentation link for **all answered questions** (correct and incorrect) whenever the explanation dict contains a non-empty `doc_url`. place the link below the explanation expander.

on "Next": reset `st.session_state["explanation"] = None`.

---

## app structure

quiz.py has these functions, in this order:

1. `init_session_state()` - set defaults for all session state keys
2. `load_domains()` - `@st.cache_data(ttl=300)`, calls `get_active_session()` inside. query includes `key_facts` column
3. `load_session_stats()` - `@st.cache_data(ttl=60)`, aggregate stats from QUIZ_SESSION_LOG
4. `load_recent_sessions()` - `@st.cache_data(ttl=60)`, last 10 sessions for trend chart
5. `load_domain_errors()` - `@st.cache_data(ttl=60)`, error counts per domain from QUIZ_REVIEW_LOG
6. `call_cortex(prompt)` - wraps AI_COMPLETE with dollar-quoting and error handling
7. `parse_cortex_json(response)` - safe JSON parsing for Cortex responses
8. `generate_ai_question(domain, difficulty)` - builds prompt, calls Cortex, validates result
9. `get_question(domains, difficulty_filter, domain_filter, question_source)` - picks next question
10. `render_home(domains)` - home screen
11. `render_quiz(domains)` - quiz screen
12. `render_summary()` - results screen
13. `render_review()` - review log tab
14. `render_dashboard(domains)` - progress dashboard tab

entry point: call `init_session_state()` and `load_domains()` at module level, then render tabs:

```python
tab_quiz, tab_review, tab_progress = st.tabs(["Quiz", "Review", "📊 Progress"])
with tab_quiz:
    # screen routing (home / quiz / summary)
with tab_review:
    render_review()
with tab_progress:
    render_dashboard(domains)
```

`st.set_page_config(layout="centered")` must be the first `st.*` call in the file - before any other Streamlit call. no sidebar. no CSS injection. do NOT use `layout="wide"`.

---

## home screen

```python
st.title("SnowPro Core Quiz")
st.caption("COF-C02 · Certification Practice")
```

controls (in order):
- `st.select_slider`: number of questions - options: 5, 10, 25, 50, 100
- `st.selectbox`: domain focus - "All" + domain names from EXAM_DOMAINS
- `st.segmented_control`: difficulty - options `["mixed", "easy", "medium", "hard"]`, `format_func=lambda x: x.capitalize()`. guard: `if difficulty is None: difficulty = "mixed"`
- `st.segmented_control`: question source - options `["mix", "db", "ai"]`, `format_func` maps to `"Mix (DB + AI)" / "DB only" / "AI only"`. guard: `if question_source is None: question_source = "mix"`
- `st.toggle`: enable AI explanations

```python
st.divider()
st.button("Start Round", type="primary", use_container_width=True)
```

"Start Round" button: saves all settings to session state, loads the first question, sets screen to "quiz". no `st.rerun()`.

---

## quiz screen

### layout

- progress bar with inline label: `st.progress(value=(q_index+1)/round_size, text=f"Question {q_index+1} of {round_size}")`
- domain + difficulty: single caption line: `st.caption(f"{domain_name} · {difficulty}")`
- question text: `st.subheader(question_text)`

### answer input

single-answer: `st.radio` with `index=None`, keyed by question index, disabled once answered.

multi-answer: one `st.checkbox` per option, disabled once answered. submit enabled only when exactly the right number of answers are selected (match `len(correct_letters)`).

Submit Answer button: `type="primary"`, `use_container_width=True`, disabled when no answer selected.

### on submit

- record result in session state and append to `round_history`
- do NOT call Cortex in the submit handler
- call `st.rerun()` at the end (exactly here, nowhere else)

### after submission

**result row** (always shown) — plain markdown, no colored boxes. see "AI explanation generation" for exact implementation.

**explanation** (when `use_explanations` is ON):
- generate and render AI explanation below result row (see "AI explanation generation")
- `doc_url` link shown for all answers (correct and incorrect)

result row uses `st.markdown()` only — no `st.success()` / `st.error()` for the result row. `st.info()` stays for the mnemonic box.

### navigation

last question: "Finish" button >write wrong answers to QUIZ_REVIEW_LOG >go to summary screen.
other questions: "Next" button >clear checkbox state >load next question >increment index.

navigation buttons: right-aligned — `nav_l, nav_r = st.columns([3, 1])` → place Next / Finish in `nav_r`.

---

## question selection

```
get_question(domains, difficulty_filter, domain_filter, question_source)
```

**domain**: if "All", pick weighted random using `WEIGHT_PCT`. otherwise use the specified domain.

**difficulty** (mixed mode): 30% easy, 50% medium, 20% hard.

**source logic**:
- `"db"`: query DB only
- `"ai"`: call `generate_ai_question`, retry up to 3×; return `None` if all fail
- `"mix"`: 20% chance AI first; if AI fails, fall through to DB

**deduplication (DB questions)**: use a helper `_get_shown_texts()` that collects `question_text` from `round_history` + the current question in `st.session_state["question"]`. pass these as bind params to a `NOT IN` clause in the SQL query. this is more reliable than tracking IDs in session_state lists — `round_history` is proven to survive SiS reruns (the summary screen renders it). do NOT use separate `shown_question_ids` or `shown_question_texts` keys in session_state — mutable objects stored directly in session_state are unreliable in SiS.

**fallback chain** (DB path): domain + difficulty (excluding shown) → domain only (excluding shown) → domain only (full pool, no exclusion).

when `question_source == "ai"` and all retries fail: return `None`. `render_quiz` handles `q is None` with retry UI showing debug info from `last_cortex_error`, `last_ai_response`, `last_ai_parse_error`.

the Retry button must: clear `st.session_state["question"]`, `last_cortex_error`, `last_ai_response`, `last_ai_parse_error` - then call `st.rerun()`. without the rerun the button appears to do nothing.

in `generate_ai_question`: after parsing the Cortex response, immediately check if the returned dict contains `why_correct` or `why_wrong` keys - if so, discard it and count as a failed attempt (Cortex returned an explanation instead of a question). do not let it reach the `question_text` / `option_a` validation step.

---

## history_item

each submitted answer appended to `round_history`:

| field | value |
|---|---|
| `question_id` | from `QUESTION_ID` field - used for deduplication |
| `domain_id` | |
| `domain_name` | |
| `difficulty` | |
| `question_text` | |
| `correct_answer` | letter(s) only - e.g. `"C"` or `"A,D"` |
| `option_texts` | `{"A": "...", "B": "...", ...}` - required for correct answer display |
| `selected` | comma-joined selected letters |
| `selected_labels` | list of `"A) full text"` strings |
| `is_correct` | bool |
| `mnemonic` | empty string initially; filled after explanation generation |
| `doc_url` | empty string initially; filled after explanation generation |

`option_texts` is critical - without it, correct answer display shows only letters.

---

## summary screen

```python
st.metric(label="Score", value=f"{correct}/{total}", delta=f"{pct:.0f}%")
```

pass/fail (one line):
- passed: `st.success("Passed ✓ — above 75% threshold")`
- failed: `st.warning(f"Not yet — {75-pct:.1f}% to go")`

wrong answers: one `st.expander(question_text[:60] + "…", expanded=False)` per wrong answer containing correct answer with full option text and mnemonic (if any). collapsed by default.

buttons side by side:
```python
col_a, col_b = st.columns(2)
col_a.button("Play Again")           # same settings
col_b.button("New Round", type="primary")  # back to home
```

---

## review tab

- wrong answers from QUIZ_REVIEW_LOG, ordered by `logged_at DESC`
- filters side by side: `fcol1, fcol2 = st.columns([2, 2])` → domain selectbox in `fcol1`, date range in `fcol2`
- date range: cast dates from `.collect()` to `datetime.date`; use `< end+1day` query pattern
- if no entries: show info message and return early
- each card: `st.container(border=True)` containing:
  - `st.caption(f"{domain} · {difficulty} · {date}")` — one metadata line
  - `st.markdown(question_text)`
  - `st.markdown(f"**Correct answer:** {answer}")`
  - `st.markdown(f"💡 {mnemonic}")` — only if mnemonic is non-empty
  - markdown link to doc_url — only if doc_url is non-empty

---

## progress dashboard

the "📊 Progress" tab. shows learning analytics from QUIZ_SESSION_LOG and QUIZ_REVIEW_LOG.

**empty state:** if QUIZ_SESSION_LOG has 0 rows, show: "Complete a quiz round to see your progress here." and return early.

**cached queries** (all use `@st.cache_data(ttl=60)` with `get_active_session()` inside):
- `load_session_stats()`: `SELECT COUNT(*) as sessions, AVG(score_pct) as avg_score, SUM(round_size) as total_questions FROM QUIZ_SESSION_LOG`
- `load_recent_sessions()`: adds a session number for the x-axis:
  ```sql
  SELECT ROW_NUMBER() OVER (ORDER BY session_ts) AS session_num,
         session_ts, score_pct, round_size
  FROM QUIZ_SESSION_LOG ORDER BY session_ts ASC LIMIT 10
  ```
- `load_domain_errors()`: `SELECT domain_name, COUNT(*) as error_count FROM QUIZ_REVIEW_LOG GROUP BY domain_name ORDER BY error_count DESC`

**layout:**

Row 1 — 3 metric cards (`st.columns(3)`):
- `st.metric("Sessions", sessions)`
- `st.metric("Avg Score", f"{avg_score:.1f}%", delta=f"{avg_score-75:+.1f}% vs pass")`
- `st.metric("Questions Practiced", total_questions)`

`st.divider()`

Row 2 — 2 panels (`st.columns(2)`):
- Left: **Readiness Score**
  ```python
  st.markdown("**Readiness Score**")
  st.progress(avg_score / 100)
  st.caption(f"{avg_score:.1f}% — need 75% to pass ({avg_score-75:+.1f}%)")
  ```
- Right: **Recent Sessions** — Altair bar chart:
  ```python
  import altair as alt
  bars = alt.Chart(df).mark_bar().encode(
      x=alt.X("session_num:O", title="Session", axis=alt.Axis(labelAngle=0)),
      y=alt.Y("score_pct:Q", scale=alt.Scale(domain=[0, 100]), title="Score %"),
      color=alt.condition(
          alt.datum.score_pct >= 75,
          alt.value("#4CAF50"),
          alt.value("#2196F3")
      )
  )
  rule = alt.Chart(pd.DataFrame({"y": [75]})).mark_rule(
      color="red", strokeDash=[4, 4]
  ).encode(y="y:Q")
  st.altair_chart(bars + rule, use_container_width=True)
  ```

`st.divider()`

Row 3 — 2 panels (`st.columns(2)`):
- Left: **Errors by Domain** — Altair horizontal bar chart:
  ```python
  chart = alt.Chart(df).mark_bar().encode(
      x=alt.X("error_count:Q", title="Errors"),
      y=alt.Y("domain_name:N", sort="-x", title=None),
      color=alt.value("#EF5350")
  )
  st.altair_chart(chart, use_container_width=True)
  ```
- Right: **Weak Spots** — top 3 domains by error count. for each:
  ```python
  st.markdown(f"**{domain_name}** — {count} errors")
  st.button("Practice", key=f"practice_{domain_name}")  # sets domain_filter + screen="home"
  ```
  "Practice" button: sets `st.session_state["domain_filter"] = domain_name` and `st.session_state["screen"] = "home"` (no st.rerun needed)

---

## write-back on round end

for each wrong answer in `round_history`:
- build `correct_full`: `"{letter}) {full_text}"` for each letter in `correct_answer`, resolved via `option_texts`
- `INSERT INTO QUIZ_REVIEW_LOG (domain_id, domain_name, difficulty, question_text, correct_answer, mnemonic, doc_url)` using bind params (`:1, :2, …`) - never f-string interpolation of values

after all wrong-answer inserts, write one session summary row:
- `INSERT INTO QUIZ_SESSION_LOG (exam_code, round_size, correct_count, score_pct, domain_filter, difficulty) VALUES (:1, :2, :3, :4, :5, :6)`
- `exam_code` from `EXAM_CODE` constant, `score_pct = correct_count / round_size * 100`

---

## session state

| key | type | description |
|---|---|---|
| `screen` | str | `home` / `quiz` / `summary` |
| `question` | dict \| None | current question (UPPERCASE keys) |
| `answered` | bool | |
| `selected` | list | selected option letters |
| `explanation` | None / {} / dict | None=not tried, {}=failed, dict=success |
| `q_index` | int | 0-based |
| `round_size` | int | |
| `round_history` | list | list of history_item dicts — also used as dedup source via `_get_shown_texts()` |
| `difficulty` | str | mixed / easy / medium / hard |
| `domain_filter` | str | "All" or domain name |
| `question_source` | str | mix / db / ai |
| `use_explanations` | bool | |
| `correct_count` | int | |
| `total_count` | int | |
| `current_history_item` | dict \| None | ref to last appended history_item |
| `last_cortex_error` | str \| None | debug |
| `last_ai_response` | str \| None | debug |
| `last_ai_parse_error` | str \| None | debug |

---

## available skills

| skill | when to use |
|---|---|
| `/streamlit-in-snowflake` | SiS coding patterns + pre-deploy scan (22-item safety gate) |
| `/test-cortex` | when AI_COMPLETE fails or returns unexpected output |
| `/cortex-prompt` | when explanations or question generation produce poor output |
| `/switch-exam` | switch to a different certification exam (creates new schema) |

---

## pre-deploy scan

**MANDATORY before every deploy. run `/streamlit-in-snowflake`. all 22 items must pass.**

categories:
- SQL and data safety (injection, parameterized INSERT, PARSE_JSON, SELECT DISTINCT)
- Cortex / AI_COMPLETE (dollar-quoting, `$$` sanitization, parse function, import)
- Streamlit in Snowflake compatibility (rerun count, unsupported APIs, session, page config)
- Date handling (cast from `.collect()`, range query pattern, slider)
- Column name normalization

all pass >proceed to deploy. any fail >fix and re-scan.

---

## deploy sql

```sql
CREATE OR REPLACE STREAMLIT {database}.{schema}.SNOWPRO_QUIZ
  ROOT_LOCATION = '@{database}.{schema}.STAGE_SIS_APP'
  MAIN_FILE = '/quiz.py'
  QUERY_WAREHOUSE = {warehouse};
```

verify:
```sql
SHOW STREAMLITS LIKE 'SNOWPRO_QUIZ' IN SCHEMA {database}.{schema};
```
must return 1 row.

---

## security and governance rules

1. isolation: all DDL/DML in `{database}.{schema}` only
2. no DROP: never DROP SCHEMA, DROP DATABASE, or DROP TABLE on existing objects
3. no CREATE OR REPLACE on tables/stages - use `CREATE TABLE IF NOT EXISTS`. for STREAMLIT and FILE FORMAT: `CREATE OR REPLACE` is allowed
4. parameterized SQL for all user-derived values: `session.sql("... WHERE domain_id = :1", [domain_id]).collect()`
5. AI_COMPLETE: dollar-quote the prompt. `CORTEX_MODEL` is a hardcoded constant
6. never interpolate user widget values into f-string SQL

---

## file edit protocol

after every EDIT:
1. immediately verify the changed section is correct
2. only after confirmation: proceed to the next EDIT

pattern: EDIT >VERIFY >EDIT >VERIFY >deploy
NOT: EDIT × N >deploy

---

## environment.yml

```yaml
name: snowpro_quiz
channels:
  - snowflake
dependencies:
  - streamlit=1.52.*
  - pandas
  - altair
```