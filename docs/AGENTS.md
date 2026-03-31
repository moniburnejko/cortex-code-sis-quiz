# AGENTS.md
> snowpro core certification quiz - streamlit in snowflake
> cortex code CLI project

## what this is

this file gives cortex code the full context it needs to autonomously:

1. create EXAM_DOMAINS, QUIZ_QUESTIONS, QUIZ_REVIEW_LOG, and QUIZ_SESSION_LOG tables
2. populate EXAM_DOMAINS from SnowProCoreStudyGuide.pdf; load QUIZ_QUESTIONS from quiz_questions.csv
3. build and deploy a certification quiz app in streamlit in snowflake
4. support runtime AI question generation and explanation via cortex AI functions
5. track learning progress across quiz sessions
6. provide AI-powered study recommendations based on performance data

> **why 4 tables?** QUIZ_REVIEW_LOG stores per-question wrong answers (Review tab + domain error analysis). QUIZ_SESSION_LOG stores per-round summaries (score, round size - needed for progress metrics). they can't be merged because rounds with 0 wrong answers have no QUIZ_REVIEW_LOG rows, so session data would be lost.

this is a scoped project. do not touch any database or schema other than the one configured below.

---

## snowflake environment

| setting   | value                          |
|-----------|--------------------------------|
| database  | `PL_MBURNEJK_DB`              |
| schema    | `PL_MBURNEJK_DB.QUIZ_COF_C02` |
| warehouse | `PL_MBURNEJK_WH`              |
| role      | `PL_MBURNEJK_ROLE`            |
| exam_code | `COF-C02`                      |
| stage     | `STAGE_QUIZ_DATA`              |
| app stage | `STAGE_SIS_APP`                |
| app_name  | `SNOWPRO_QUIZ`                 |
| main_file | `quiz.py`                      |

each exam uses a dedicated schema (`QUIZ_<EXAM_CODE>`). never share a schema between exams. to switch exams: use the `$switch-exam` skill.

all sections reference these values. never hardcode environment names elsewhere in this file.

---

## how to proceed

the role `PL_MBURNEJK_ROLE` has full permissions on `PL_MBURNEJK_DB` - it can create schemas, tables, stages, file formats, and streamlit apps without additional grants.

verify session context by running:
```sql
SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA();
```
confirm values match the environment table. if they do not match, run the appropriate USE statements.

before writing any streamlit code: read the "platform constraints" section of this file.

---

## source files

files uploaded to `{database}.{schema}.STAGE_QUIZ_DATA` via `snow stage copy` CLI command.

### stage DDL

both stages must be created before any file uploads.

```sql
CREATE STAGE IF NOT EXISTS {database}.{schema}.STAGE_QUIZ_DATA
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);

CREATE STAGE IF NOT EXISTS {database}.{schema}.STAGE_SIS_APP;
```

**why these settings matter:**
- `ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')` - required by `AI_PARSE_DOCUMENT`. without server-side encryption, Cortex AI functions cannot read staged files. this is the #1 cause of "file not accessible" errors after PDF upload.
- `DIRECTORY = (ENABLE = TRUE)` - required for Cortex AI functions to enumerate and reference files by path.

if `STAGE_QUIZ_DATA` already exists without these settings, recreate it:
```sql
DROP STAGE IF EXISTS {database}.{schema}.STAGE_QUIZ_DATA;
CREATE STAGE {database}.{schema}.STAGE_QUIZ_DATA
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);
```

### upload commands

```bash
snow stage copy data/<pdf_filename> @{database}.{schema}.STAGE_QUIZ_DATA --overwrite
snow stage copy data/<csv_filename> @{database}.{schema}.STAGE_QUIZ_DATA --overwrite
```

after upload: `ALTER STAGE {database}.{schema}.STAGE_QUIZ_DATA REFRESH;`

### source file table

| file | purpose |
|---|---|
| `SnowProCoreStudyGuide.pdf` | EXAM_DOMAINS - extract domains, weights, topics via AI_PARSE_DOCUMENT + AI_COMPLETE |
| `quiz_questions.csv` | QUIZ_QUESTIONS - complete questions (all domains) |

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
    key_facts    VARCHAR             -- plain text, one fact per line
);
```

extract from study guide PDF using AI_PARSE_DOCUMENT + AI_COMPLETE. do NOT hardcode domain values.

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
    created_at     TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
```

### QUIZ_REVIEW_LOG

```sql
CREATE TABLE IF NOT EXISTS {database}.{schema}.QUIZ_REVIEW_LOG (
    log_id         NUMBER AUTOINCREMENT PRIMARY KEY,
    logged_at      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
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
    session_ts     TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    exam_code      VARCHAR NOT NULL,
    round_size     NUMBER NOT NULL,
    correct_count  NUMBER NOT NULL,
    score_pct      FLOAT NOT NULL,
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

- `st.rerun()` is allowed in exactly 6 places:
  1. Start Round button handler (after loading first question)
  2. Lazy load at top of render_quiz (after question loaded successfully)
  3. Retry button (after clearing error state)
  4. Submit Answer button handler (after recording result)
  5. Finish button handler (after writing results)
  6. Next button handler (after clearing state for next question)
- never add additional `st.rerun()` calls. the count of 6 is a pre-deploy scan checkpoint.

### unsupported apis

- `@st.fragment` - not supported in SiS. do not use.
- `st.experimental_rerun()` - deprecated. use `st.rerun()`.
- `st.container(horizontal=True)` - not supported. use `st.columns()`.
- `.applymap()` - removed in pandas >= 2.1. use `.map()`.
- `from snowflake.cortex import complete` - do not import. use `AI_COMPLETE` via `session.sql()`.

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

AI_COMPLETE has two known encoding issues:
1. **markdown fences** - response wrapped in ` ```json ... ``` `
2. **double-encoded JSON** - `json.loads()` returns a `str` instead of `dict`; parse again

parsing function must: strip markdown fences > `json.loads()` > if result is `str`, `json.loads()` again > fallback: regex-extract first `{...}` block and parse > return `None` on all failures (never raise).

always call `isinstance(result, dict)` before calling `.get()` on the return value.

never call `json.loads()` directly on a Cortex response - always go through the parsing function.

### difficulty guide

store as a `DIFFICULTY_GUIDE` dict with full descriptions for each level. pass as primary constraint in AI question prompts, before any grounding/facts:

```python
DIFFICULTY_GUIDE = {
    "easy": "EASY - single-concept recall. Ask 'What is X?', 'Which feature does Y?'...",
    "medium": "MEDIUM - applied scenario. Present a real-world use-case...",
    "hard": "HARD - multi-step analysis. Combine 2-3 concepts..."
}
```

### AI question generation

ask Cortex to generate a `{difficulty}` question for the given domain and topics, returning ONLY valid JSON:

```json
{"question_text":"...","is_multi":false,"option_a":"...","option_b":"...","option_c":"...","option_d":"...","option_e":null,"correct_answer":"C"}
```

length constraints (include explicitly in the prompt to prevent truncation):
- `question_text`: max 150 characters
- each option: max 80 characters
- respond with ONLY the JSON object, no markdown fences, no extra text

to avoid repetition: pass already-asked question texts (up to 10, truncated to 80 chars each) as a "do not repeat" block in the prompt.

validate the parsed result: `question_text`, `option_a`, `option_b`, `correct_answer` must all be non-empty. retry up to 3 times on failure.

**UX**: wrap the generation loop in `with st.spinner("Generating question..."):`

after a successful generation and validation: INSERT the question into `QUIZ_QUESTIONS` using bind params (domain_id, domain_name, difficulty, question_text, is_multi, option_a through option_e, correct_answer, source='AI_GENERATED'). then query back the `question_id` and set it on the returned dict.

### AI explanation generation

generate explanations **in the render phase** (`if answered:` block), not in the Submit handler. this keeps submit fast and the Cortex call lazy.

generate the explanation for **every answered question** - both correct and incorrect. the `doc_url` field is always needed regardless of correctness.

explanation state in `st.session_state["explanation"]`:
- `None` > not yet attempted; call Cortex and store result
- `{}` > tried and failed (sentinel - do not retry)
- `{dict}` > success; render

**UX**: wrap the Cortex call in `with st.spinner("Generating explanation..."):`

the explanation prompt must produce **rich, exam-relevant content**. include:
- the full question text
- all answer options with their letter labels
- the correct answer letter(s)
- what the student selected
- the list of wrong option letters (all options not in correct_answer)

ask Cortex to return ONLY valid JSON with these keys:
- `why_correct`: 2-3 sentences explaining exactly why the correct answer is right, with Snowflake-specific technical detail
- `why_wrong`: for **each wrong option separately** (not a single generic sentence), one sentence explaining why it is incorrect
- `mnemonic`: a memorable phrase, acronym, or analogy to help remember the correct answer
- `doc_url`: exact URL to the most relevant Snowflake documentation page

rendering (`st.expander("Explanation", expanded=True)`):
- `why_correct` > bold header + `st.write()`
- `why_wrong` > bold header + render each option separately if value is a dict; plain `st.write()` if string
- `mnemonic` > `st.info()`
- `doc_url` > markdown link

render the full expander (`why_correct`, `why_wrong`, `mnemonic`) only when `not is_correct and use_explanations` and the explanation dict has content.

render `doc_url` as a documentation link for **all answered questions** (correct and incorrect) whenever the explanation dict contains a non-empty `doc_url`. place the link directly below the result line, outside the expander.

on "Next": reset `st.session_state["explanation"] = None`.

---

## app structure

quiz.py has these functions, in this order:

1. `init_session_state()` - set defaults for all session state keys
2. `load_domains()` - `@st.cache_data(ttl=300)`, calls `get_active_session()` inside
3. `load_session_stats()` - `@st.cache_data(ttl=60)`, aggregate stats from QUIZ_SESSION_LOG
4. `load_recent_sessions()` - `@st.cache_data(ttl=60)`, last 10 sessions with labels
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
tab_quiz, tab_review, tab_progress = st.tabs(["Quiz", "Review", "Progress"])
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
st.title("{exam_name} Quiz")
st.caption("{exam_code} · Certification Practice")
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

"Start Round" button: saves all settings to session state, loads the first question (wrapped in `st.spinner("Loading first question...")`), sets screen to "quiz", then `st.rerun()` for clean transition.

---

## quiz screen

### lazy load pattern

at the top of `render_quiz`, before rendering any widgets:

```python
q = st.session_state.get("question")
if q is None:
    with st.spinner("Loading question..."):
        q = get_question(...)
    if q is not None:
        st.session_state["question"] = q
        st.rerun()       # clean rerender with loaded question
    else:
        # show error UI (cortex error, raw response, parse error)
        # Retry button -> clear error state -> st.rerun()
        return
```

**why:** the "Next" button handler only sets `question = None` and calls `st.rerun()`. it does NOT call `get_question()` inside the handler. the lazy load pattern ensures a clean page: only the spinner is visible during loading, then a full rerender shows the new question.

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
- call `st.rerun()` at the end

### after submission

**result row** (always shown) - plain markdown, no colored boxes.

**explanation** (when `use_explanations` is ON):
- generate and render AI explanation below result row (see "AI explanation generation")
- `doc_url` link shown for all answers (correct and incorrect)

result row uses `st.markdown()` only - no `st.success()` / `st.error()` for the result row. `st.info()` stays for the mnemonic box.

### navigation

last question: "Finish" button > wrap `_write_back_results()` in `st.spinner("Saving results...")` > set screen to summary > `st.rerun()` for clean transition.
other questions: "Next" button > set `question = None`, clear checkbox/explanation state, increment index > `st.rerun()`. the actual question loading happens on the next rerun cycle at the top of `render_quiz` (lazy load pattern).

navigation buttons: right-aligned - `nav_l, nav_r = st.columns([3, 1])` -> place Next / Finish in `nav_r`.

---

## question selection

```
get_question(domains, difficulty_filter, domain_filter, question_source)
```

**domain**: if "All", pick weighted random using `WEIGHT_PCT`. otherwise use the specified domain.

**difficulty** (mixed mode): 30% easy, 50% medium, 20% hard.

**source logic**:
- `"db"`: query DB only
- `"ai"`: call `generate_ai_question`, retry up to 3x; return `None` if all fail
- `"mix"`: 20% chance AI first; if AI fails, fall through to DB

**deduplication (DB questions)**: use a helper `_get_shown_texts()` that collects `question_text` from `round_history` + the current question in `st.session_state["question"]`. pass these as bind params to a `NOT IN` clause in the SQL query. do NOT use separate `shown_question_ids` or `shown_question_texts` keys in session_state - mutable objects stored directly in session_state are unreliable in SiS.

**fallback chain** (DB path): domain + difficulty (excluding shown) -> domain only (excluding shown) -> domain only (full pool, no exclusion).

when `question_source == "ai"` and all retries fail: return `None`. `render_quiz` handles `q is None` with retry UI showing debug info from `last_cortex_error`, `last_ai_response`, `last_ai_parse_error`.

the Retry button must: clear `st.session_state["question"]`, `last_cortex_error`, `last_ai_response`, `last_ai_parse_error` - then call `st.rerun()`. without the rerun the button appears to do nothing.

in `generate_ai_question`: after parsing the Cortex response, immediately check if the returned dict contains `why_correct` or `why_wrong` keys - if so, discard it and count as a failed attempt (Cortex returned an explanation instead of a question).

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
- passed: `st.success("Passed - above 75% threshold")`
- failed: `st.warning(f"Not yet - {75-pct:.1f}% to go")`

wrong answers: one `st.expander(question_text[:60] + "...", expanded=False)` per wrong answer containing correct answer with full option text and mnemonic (if any). collapsed by default.

buttons side by side:
```python
col_a, col_b = st.columns(2)
col_a.button("Play Again")           # same settings
col_b.button("New Round", type="primary")  # back to home
```

---

## review tab

- wrong answers from QUIZ_REVIEW_LOG, ordered by `logged_at DESC`
- filters side by side: `fcol1, fcol2 = st.columns([2, 2])` -> domain selectbox in `fcol1`, date range in `fcol2`
- date range: cast dates from `.collect()` to `datetime.date`; use `< end+1day` query pattern
- if no entries: show info message and return early
- each card: `st.container(border=True)` containing:
  - `st.caption(f"{domain} · {difficulty} · {date}")` - one metadata line
  - `st.markdown(question_text)`
  - `st.markdown(f"**Correct answer:** {answer}")`
  - `st.markdown(f"mnemonic")` - only if mnemonic is non-empty
  - markdown link to doc_url - only if doc_url is non-empty

---

## progress dashboard

the "Progress" tab. shows learning analytics from QUIZ_SESSION_LOG and QUIZ_REVIEW_LOG.

**empty state:** if QUIZ_SESSION_LOG has 0 rows, show: "Complete a quiz round to see your progress here." and return early.

**cached queries** (all use `@st.cache_data(ttl=60)` with `get_active_session()` inside):
- `load_session_stats()`: `SELECT COUNT(*) as sessions, AVG(score_pct) as avg_score, SUM(round_size) as total_questions FROM QUIZ_SESSION_LOG`
- `load_recent_sessions()`: adds session number + human-readable label for x-axis:
  ```sql
  SELECT ROW_NUMBER() OVER (ORDER BY session_ts) AS session_num,
         session_ts, score_pct, round_size,
         '#' || ROW_NUMBER() OVER (ORDER BY session_ts) || ' · ' || TO_CHAR(session_ts, 'DD/MM') AS session_label
  FROM QUIZ_SESSION_LOG ORDER BY session_ts ASC LIMIT 10
  ```
- `load_domain_errors()`: `SELECT domain_name, COUNT(*) as error_count FROM QUIZ_REVIEW_LOG GROUP BY domain_name ORDER BY error_count DESC`

**layout:**

Row 1 - 3 metric cards (`st.columns(3)`):
- `st.metric("Sessions", sessions)`
- `st.metric("Avg Score", f"{avg_score:.1f}%", delta=f"{avg_score-75:+.1f}% vs pass threshold")`
- `st.metric("Questions Practiced", total_questions)`

`st.divider()`

Row 2 - **Score per Session** line chart, full width (not in a column). x-axis uses `session_label` (e.g. "#1 · 31/03") sorted by `session_num`:
```python
line = alt.Chart(df).mark_line(point=True, color="#29b5e8").encode(
    x=alt.X("session_label:N", title=None, sort=alt.SortField("session_num"), axis=alt.Axis(labelAngle=0)),
    y=alt.Y("score_pct:Q", scale=alt.Scale(domain=[0, 100]), title="Score %"),
)
rule = alt.Chart(pd.DataFrame({"y": [75]})).mark_rule(
    color="red", strokeDash=[4, 4]
).encode(y="y:Q")
st.altair_chart((line + rule).properties(title="Score per Session"), use_container_width=True)
```

`st.divider()`

Row 3 - 2 panels (`st.columns(2)`):
- Left: **Readiness Score** - metric with delta + progress bar:
  ```python
  st.metric("Readiness Score", f"{avg_score:.1f}%", delta=f"{avg_score-75:+.1f}% vs pass threshold")
  st.progress(min(avg_score / 100, 1.0))
  ```
- Right: **Errors by Domain** - Altair horizontal bar chart with title, integer axis, no x-axis label:
  ```python
  df_err["error_count"] = df_err["error_count"].astype(int)
  chart = alt.Chart(df_err).mark_bar().encode(
      x=alt.X("error_count:Q", title=None, axis=alt.Axis(format="d")),
      y=alt.Y("domain_name:N", sort="-x", title=None),
      color=alt.value("#EF5350")
  )
  st.altair_chart(chart.properties(title="Errors by Domain"), use_container_width=True)
  ```

no Weak Spots section.

### AI study recommendations (Row 4)

`st.divider()` then `st.subheader("AI Study Recommendations")`

**condition:** show only when `sessions >= 2` AND `error_data` is non-empty. otherwise show caption: "Complete at least 2 quiz sessions to see personalized recommendations."

build a cortex AI prompt with exam coach persona. include in the prompt:
- exam code (`EXAM_CODE` constant), session count, avg score, total questions practiced
- domain error breakdown from `load_domain_errors()` result
- pass threshold: 75%

prompt must ask AI_COMPLETE to return ONLY valid JSON with these keys:
- `overall_assessment`: string, 1-2 sentences on current readiness
- `weak_domains`: array of objects `{domain_name: str, recommendation: str}`
- `study_plan`: array of 3-5 string bullet points for what to focus on next
- `recommended_difficulty`: "easy" | "medium" | "hard"
- `recommended_domain`: string, the single domain name to focus on next

use `call_cortex()` and `parse_cortex_json()` for the AI call and response parsing.

**caching:** store recommendations in `st.session_state["_ai_recommendations"]`. use `st.session_state["_rec_cache_key"]` set to `f"rec_{sessions}"`. only re-call AI_COMPLETE when cache key changes (i.e. new session completed). show `st.spinner("Analyzing your performance...")` during the call.

**display:**
- `st.info(overall_assessment)`
- `st.markdown("**Focus Areas:**")` + bullet list: `- **{domain_name}**: {recommendation}` per weak domain
- `st.markdown("**Next Steps:**")` + bullet list of study_plan items
- `st.button(f"Start Focused Session: {recommended_domain} ({recommended_difficulty})", type="primary")`
  - on click: set `domain_filter = recommended_domain`, `difficulty = recommended_difficulty`, `round_size = 10`, `question_source = "mix"`, `screen = "home"`
  - this button does NOT call `st.rerun()`. it only sets session_state. the `st.rerun()` count must remain exactly 6.

---

## write-back on round end

for each wrong answer in `round_history`:
- build `correct_full`: `"{letter}) {full_text}"` for each letter in `correct_answer`, resolved via `option_texts`
- `INSERT INTO QUIZ_REVIEW_LOG (domain_id, domain_name, difficulty, question_text, correct_answer, mnemonic, doc_url)` using bind params (`:1, :2, ...`) - never f-string interpolation of values

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
| `round_history` | list | list of history_item dicts - also used as dedup source via `_get_shown_texts()` |
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
| `_ai_recommendations` | dict \| None | cached AI study recommendations JSON |
| `_rec_cache_key` | str \| None | cache key = f"rec_{sessions}" |

---

## available skills

| skill | when to use |
|---|---|
| `$streamlit-in-snowflake` | SiS coding patterns + pre-deploy scan (22-item safety gate) |
| `$cortex-ai` | Cortex AI function patterns (AI_COMPLETE, AI_PARSE_DOCUMENT, stages) and diagnostics |
| `$cortex-prompt` | when explanations or question generation produce poor output |
| `$switch-exam` | switch to a different certification exam (automated pipeline: new branch, new schema, full rebuild) |

---

## pre-deploy scan

**MANDATORY before every deploy. run `$streamlit-in-snowflake`. all 22 items must pass.**

categories:
- SQL and data safety (injection, parameterized INSERT, PARSE_JSON, SELECT DISTINCT)
- Cortex / AI_COMPLETE (dollar-quoting, `$$` sanitization, parse function, import)
- Streamlit in Snowflake compatibility (rerun count = 6, unsupported APIs, session, page config)
- Date handling (cast from `.collect()`, range query pattern, slider)
- Column name normalization

all pass > proceed to deploy. any fail > fix and re-scan.

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

pattern: EDIT > VERIFY > EDIT > VERIFY > deploy
NOT: EDIT x N > deploy

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
