# AGENTS.md
> snowpro core certification quiz - streamlit in snowflake
> cortex code in snowsight project

## what this is

this file gives cortex code the full context it needs to autonomously:

1. create EXAM_DOMAINS, QUIZ_QUESTIONS, and QUIZ_REVIEW_LOG tables
2. populate EXAM_DOMAINS from SnowProCoreStudyGuide.pdf; load QUIZ_QUESTIONS from quiz_questions.csv
3. build and deploy a certification quiz app in streamlit in snowflake
4. support runtime AI question generation and explanation via cortex AI functions

this is a scoped project. do not touch any database or schema other than the one configured below.

---

## snowflake environment

| setting   | value                |
|-----------|----------------------|
| database  | `CORTEX_DB`          |
| schema    | `CORTEX_DB.QUIZ_APP` |
| warehouse | `CORTEX_WH`          |
| role      | `CORTEXADMIN`        |
| stage     | `STAGE_QUIZ_DATA`    |
| app stage | `STAGE_SIS_APP`      |
| app_name  | `SNOWPRO_QUIZ`       |
| main_file | `quiz.py`            |

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

### stage requirements for STAGE_QUIZ_DATA

`STAGE_QUIZ_DATA` must have:
- `ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')` - required by `AI_PARSE_DOCUMENT` to read files from the stage. without server-side encryption, Cortex AI functions cannot access staged files.
- `DIRECTORY = (ENABLE = TRUE)` - required for Cortex AI functions to enumerate and reference files on the stage by path.

`STAGE_SIS_APP` does not require these settings.

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
    topics       VARIANT             -- JSON array of topic strings
);
```

extract from `SnowProCoreStudyGuide.pdf` using AI_PARSE_DOCUMENT + AI_COMPLETE. do NOT hardcode domain values.

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

### multi-answer questions

render each option as an independent `st.checkbox` with a stable key (e.g. `cb_A`). read selected options by checking session state after rendering. disable all checkboxes once answered. on "Next": delete all `cb_*` keys from session state manually.

### dates from `.collect()`

snowflake returns timestamps as snowflake datetime objects, not Python `datetime.date`. convert with `datetime.date(raw.year, raw.month, raw.day)` before passing to `st.date_input` or date arithmetic.

date range queries against `TIMESTAMP_LTZ` columns: pass start and end as formatted strings (`"%Y-%m-%d"`). add 1 day to end date and use `< end` (exclusive) to include the full last day.

### column names

snowflake returns UPPERCASE column names from `.collect()`. normalize with `{k.upper(): v for k, v in row.as_dict().items()}`.

---

## cortex llm

preferred model: `claude-4-sonnet`. store as constant `CORTEX_MODEL`.

account region `AWS_EU_CENTRAL_1` requires `CORTEX_ENABLED_CROSS_REGION = 'AWS_US'`.

### calling AI_COMPLETE

call via `session.sql()` with dollar-quoting: `SELECT AI_COMPLETE('{CORTEX_MODEL}', $${prompt}$$)`.

before interpolating the prompt, replace any `$$` occurrences with `$ $` to prevent dollar-quote breakout. `CORTEX_MODEL` is a constant - safe to interpolate. never interpolate user-derived values into the SQL string.

on exception: store the error string in `st.session_state["last_cortex_error"]`; return `None`. on empty result: return `None`.

### parsing AI_COMPLETE responses

AI_COMPLETE has two known encoding issues:
1. **markdown fences** - response wrapped in ` ```json ... ``` `
2. **double-encoded JSON** - `json.loads()` returns a `str` instead of `dict`; parse again

parsing function must: strip markdown fences >`json.loads()` >if result is `str`, `json.loads()` again >fallback: regex-extract first `{…}` block and parse >return `None` on all failures (never raise).

always call `isinstance(result, dict)` before calling `.get()` on the return value.

never call `json.loads()` directly on a Cortex response - always go through the parsing function.

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

after a successful generation and validation: INSERT the question into `QUIZ_QUESTIONS` using bind params (domain_id, domain_name, difficulty, question_text, is_multi, option_a through option_e, correct_answer, source='AI_GENERATED'). then query back the `question_id` (`SELECT question_id ... WHERE source='AI_GENERATED' AND domain_id=:1 AND question_text=:2 ORDER BY created_at DESC LIMIT 1`) and set it on the returned dict. if the INSERT fails: log the error to `last_cortex_error` and continue - return the question with `QUESTION_ID: None`.

### AI explanation generation

generate explanations **in the render phase** (`if answered:` block), not in the Submit handler. this keeps submit fast and the Cortex call lazy.

generate the explanation for **every answered question** - both correct and incorrect. the `doc_url` field is always needed regardless of correctness.

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

rendering (`st.expander("Explanation", expanded=True)`):
- `why_correct` >bold header + `st.write()`
- `why_wrong` >bold header + render each option separately if value is a dict; plain `st.write()` if string
- `mnemonic` >`st.info()`
- `doc_url` >markdown link

render the full expander (`why_correct`, `why_wrong`, `mnemonic`) only when `not is_correct and use_explanations` and the explanation dict has content.

render `doc_url` as a documentation link for **all answered questions** (correct and incorrect) whenever the explanation dict contains a non-empty `doc_url`. place the link directly below the ✅ / ❌ result line, outside the expander.

on "Next": reset `st.session_state["explanation"] = None`.

---

## app structure

quiz.py has these functions, in this order:

1. `init_session_state()` - set defaults for all session state keys
2. `load_domains()` - `@st.cache_data(ttl=300)`, calls `get_active_session()` inside
3. `call_cortex(prompt)` - wraps AI_COMPLETE with dollar-quoting and error handling
4. `parse_cortex_json(response)` - safe JSON parsing for Cortex responses
5. `generate_ai_question(domain, difficulty)` - builds prompt, calls Cortex, validates result
6. `get_question(domains, difficulty_filter, domain_filter, question_source)` - picks next question
7. `render_home(domains)` - home screen
8. `render_quiz(domains)` - quiz screen
9. `render_summary()` - results screen
10. `render_review()` - review log tab

entry point: call `init_session_state()` and `load_domains()` at module level, then render tabs.

`st.set_page_config(layout="centered")` must be the first `st.*` call in the file - before any other Streamlit call. no sidebar. no CSS injection. do NOT use `layout="wide"`.

---

## home screen

controls (in order):
- `st.select_slider`: number of questions - options: 5, 10, 25, 50, 100
- `st.selectbox`: difficulty - mixed / easy / medium / hard
- `st.selectbox`: domain focus - "All" + domain names from EXAM_DOMAINS
- `st.selectbox`: question source - "mix" (80% DB + 20% AI) / "db" (DB only) / "ai" (AI only)
- `st.toggle`: enable AI explanations

"Start Round" button: saves all settings to session state, loads the first question, sets screen to "quiz". no `st.rerun()`.

---

## quiz screen

### layout

- progress bar: question X of total
- domain + difficulty metadata (one line)
- question text as `### heading`

### answer input

single-answer: `st.radio` with `index=None`, keyed by question index, disabled once answered.

multi-answer: one `st.checkbox` per option, disabled once answered. submit enabled only when exactly the right number of answers are selected (match `len(correct_letters)`).

Submit Answer button: disabled when no answer selected.

### on submit

- record result in session state and append to `round_history`
- do NOT call Cortex in the submit handler
- call `st.rerun()` at the end (exactly here, nowhere else)

### after submission

**correct answer:**
- show `✅ Correct!`
- show `doc_url` link below result (see "AI explanation generation" - render `doc_url` for all answers)

**incorrect answer:**
- show `❌ Incorrect`
- show `**Correct answer:** C) full option text` (resolve letters to full text via `option_texts`)
- if `use_explanations`: generate and show AI explanation in expander (see "AI explanation generation")

no "Your answer" line. no inline colors or CSS.

### navigation

last question: "Finish" button >write wrong answers to QUIZ_REVIEW_LOG >go to summary screen.
other questions: "Next" button >clear checkbox state >load next question >increment index.

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

**deduplication (DB questions)**: before picking from the DB result set, collect `QUESTION_ID` values from `round_history` and exclude them. only fall back to the full pool if all matching questions have already been shown this round.

**fallback chain** (DB path): domain + difficulty >domain only >all questions.

when `question_source == "ai"` and all retries fail: return `None`. `render_quiz` handles `q is None` with retry UI showing debug info from `last_cortex_error`, `last_ai_response`, `last_ai_parse_error`.

the Retry button must: clear `st.session_state["question"]`, `last_cortex_error`, `last_ai_response`, `last_ai_parse_error` — then call `st.rerun()`. without the rerun the button appears to do nothing.

in `generate_ai_question`: after parsing the Cortex response, immediately check if the returned dict contains `why_correct` or `why_wrong` keys — if so, discard it and count as a failed attempt (Cortex returned an explanation instead of a question). do not let it reach the `question_text` / `option_a` validation step.

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

- title + score: `correct_count / total_count` as "7/10 correct - 70%"
- pass/fail vs 75% threshold
- wrong answer review (expandable): question text, correct answer with full option text, mnemonic (if any)
- "Play Again" (same settings) and "New Round" (back to home) buttons

---

## review tab

- wrong answers from QUIZ_REVIEW_LOG, ordered by `logged_at DESC`
- filter by domain (`st.selectbox`)
- filter by date range (`st.date_input`) - cast dates from `.collect()` to `datetime.date`; use `< end+1day` query pattern
- if no entries: show info message and return early
- cards: domain, difficulty, question text, correct answer (full text), mnemonic, doc_url link

---

## write-back on round end

for each wrong answer in `round_history`:
- build `correct_full`: `"{letter}) {full_text}"` for each letter in `correct_answer`, resolved via `option_texts`
- `INSERT INTO QUIZ_REVIEW_LOG (domain_id, domain_name, difficulty, question_text, correct_answer, mnemonic, doc_url)` using bind params (`:1, :2, …`) - never f-string interpolation of values

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
| `round_history` | list | list of history_item dicts |
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
| `/pre-deploy-scan` | before every deploy - 22-item safety gate (SQL, SiS APIs, Cortex, dates) |
| `/test-cortex` | when AI_COMPLETE fails or returns unexpected output |
| `/sql-safe` | during development - detailed SQL injection audit with suggested fixes |
| `/cortex-prompt` | when explanations or question generation produce poor output |

---

## pre-deploy scan

**MANDATORY before every deploy. run `/pre-deploy-scan`. all 22 items must pass.**

the full checklist is in `skills/pre-deploy-scan.md`. categories:
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
```