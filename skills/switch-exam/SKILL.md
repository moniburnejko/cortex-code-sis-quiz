---
name: switch-exam
description: >
  Automated exam switch for Cortex Code CLI. User provides study guide PDF filename.
  CLI extracts exam info from PDF, creates schema, uploads PDF, extracts domains,
  optionally loads questions from CSV, updates AGENTS.md, builds quiz.py, and deploys.
  Creates a new git branch per exam to preserve previous exam files.
tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# When to Use

Use this skill when switching from one Snowflake certification exam to another. Each exam gets its own git branch and its own Snowflake schema - nothing is overwritten.

Example prompt: "Mam nowy study guide - SnowProGenAIStudyGuide.pdf. Stworz quiz app na nowy egzamin."

---

# Exam Code Mapping

| Exam Name | Code |
|-----------|------|
| SnowPro Core | COF-C02 |
| SnowPro Advanced: Architect | ARA-C01 |
| SnowPro Advanced: Data Engineer | DAE-C01 |
| SnowPro Advanced: Data Scientist | DSA-C01 |
| SnowPro Specialty: Gen AI | GES-C01 |
| SnowPro Specialty: Data Lake | DEL-C01 |

If the exam is not in this table, ask the user for the exam code.

---

# Instructions

## Step 1 - Collect inputs

The user provides the study guide PDF filename in their prompt. The PDF is always in `data/`.

1. Verify the file exists: `ls data/<filename>`
2. Read the PDF content and **extract the exam name** from the document (look for the certification name on the cover/first pages)
3. **Map the exam code** using the table above
4. Confirm with the user: "I found exam: {exam_name} ({exam_code}). Is this correct?"
5. **Ask the user:**
   - "Do you also have a questions CSV file in the `data/` folder? If yes, what's the filename?"
   - "Do you have any additional requirements, notes, or customizations for this quiz? (e.g. AI study recommendations, different UI, extra features)"

Wait for the user's response before proceeding.

## Step 2 - Create git branch

Create a dedicated branch for this exam:

```bash
git checkout -b exam/<exam_code>
```

This ensures:
- Original exam files are preserved on the previous branch
- Each exam has its own complete file history
- Easy switching between exams via `git checkout`

## Step 3 - Create Snowflake schema

The environment uses a single role with full permissions - no grants needed.

```sql
CREATE SCHEMA IF NOT EXISTS PL_MBURNEJK_DB.QUIZ_<EXAM_CODE>;
USE SCHEMA PL_MBURNEJK_DB.QUIZ_<EXAM_CODE>;
```

Replace `<EXAM_CODE>` with the mapped code, hyphens replaced by underscores (e.g. `COF-C02` -> `QUIZ_COF_C02`).

## Step 4 - Create stages and tables

Execute DDL from the "stage DDL" and "table schemas" sections of `docs/AGENTS.md`, targeting the new schema.

**Stages** (STAGE_QUIZ_DATA MUST have encryption + directory for AI_PARSE_DOCUMENT):
```sql
CREATE STAGE IF NOT EXISTS PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_QUIZ_DATA
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);

CREATE STAGE IF NOT EXISTS PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_SIS_APP;
```

**Tables** - create all 4 from AGENTS.md "table schemas":
- EXAM_DOMAINS
- QUIZ_QUESTIONS
- QUIZ_REVIEW_LOG
- QUIZ_SESSION_LOG

Also create the file format:
```sql
CREATE FILE FORMAT IF NOT EXISTS PL_MBURNEJK_DB.QUIZ_<CODE>.FF_CSV
  TYPE = 'CSV' SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"';
```

## Step 5 - Upload PDF to stage

```bash
snow stage copy data/<pdf_filename> @PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_QUIZ_DATA --overwrite
```

Then refresh the directory table:
```sql
ALTER STAGE PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_QUIZ_DATA REFRESH;
```

**Fallback:** If `snow stage copy` fails (command not found, auth error), ask the user to upload the PDF manually via Snowsight to `@PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_QUIZ_DATA`. Wait for confirmation before proceeding.

## Step 6 - Extract domains from PDF

### 6a - Parse PDF content

```sql
SELECT AI_PARSE_DOCUMENT(
    BUILD_SCOPED_FILE_URL(@PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_QUIZ_DATA, '<pdf_filename>'),
    'LAYOUT'
):content::VARCHAR AS doc_content;
```

Save the result - you'll need it for domain extraction and key_facts.

### 6b - Extract exam domains

Use AI_COMPLETE to extract domains from the parsed PDF content. The prompt must ask for a JSON array:

```sql
SELECT AI_COMPLETE(
    'claude-sonnet-4-5',
    $$Extract ALL exam domains from this certification study guide.
Return ONLY a valid JSON array. Each object must have:
- domain_id (integer, starting from 1)
- domain_name (string, exact name from the guide)
- weight_pct (number, percentage weight - must sum to 100 across all domains)
- topics (JSON array of topic strings covered in this domain)

Study guide content:
{doc_content}$$
)::VARCHAR;
```

Parse the response and INSERT each domain into EXAM_DOMAINS.

### 6c - Extract key_facts per domain

For each domain, run a separate AI_COMPLETE call to extract testable facts:

```sql
UPDATE PL_MBURNEJK_DB.QUIZ_<CODE>.EXAM_DOMAINS
SET key_facts = (
    SELECT AI_COMPLETE(
        'claude-sonnet-4-5',
        $$Extract the key testable facts for the "{domain_name}" domain from this study guide.
Focus on facts that could appear as exam questions: definitions, limits, best practices, feature names, SQL syntax.
Return a plain text list, one fact per line. No JSON, no markdown.

Study guide content:
{doc_content}$$
    )::VARCHAR
)
WHERE domain_id = {id};
```

Run one UPDATE per domain. Verify each sets a non-null value before moving to the next.

### 6d - Verify

```sql
SELECT COUNT(*) FROM PL_MBURNEJK_DB.QUIZ_<CODE>.EXAM_DOMAINS;
SELECT SUM(weight_pct) FROM PL_MBURNEJK_DB.QUIZ_<CODE>.EXAM_DOMAINS;
SELECT domain_name, LENGTH(key_facts) AS facts_len FROM PL_MBURNEJK_DB.QUIZ_<CODE>.EXAM_DOMAINS ORDER BY domain_id;
```

Expected: N domains (varies per exam), weights sum to 100, all facts_len > 0.

## Step 7 - Load or generate questions

### If user provided a CSV:

Upload it first:
```bash
snow stage copy data/<csv_filename> @PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_QUIZ_DATA --overwrite
```

Then load:
```sql
COPY INTO PL_MBURNEJK_DB.QUIZ_<CODE>.QUIZ_QUESTIONS
FROM @PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_QUIZ_DATA/<csv_filename>
FILE_FORMAT = PL_MBURNEJK_DB.QUIZ_<CODE>.FF_CSV;
```

Backfill domain_name:
```sql
UPDATE PL_MBURNEJK_DB.QUIZ_<CODE>.QUIZ_QUESTIONS q
SET q.domain_name = d.domain_name
FROM PL_MBURNEJK_DB.QUIZ_<CODE>.EXAM_DOMAINS d
WHERE q.domain_id = d.domain_id AND q.domain_name IS NULL;
```

### If no CSV - generate via AI:

For each domain and each difficulty level (easy, medium, hard), generate a batch of questions using AI_COMPLETE. Target: ~10-15 questions per domain per difficulty.

The prompt must produce JSON array of objects with: question_text, is_multi (TRUE/FALSE), option_a through option_e, correct_answer (letter(s)), difficulty. Include the domain's key_facts as grounding material.

INSERT each question with `source = 'AI_GENERATED'`.

### Verify:

```sql
SELECT COUNT(*) FROM PL_MBURNEJK_DB.QUIZ_<CODE>.QUIZ_QUESTIONS;
SELECT COUNT(DISTINCT domain_id) FROM PL_MBURNEJK_DB.QUIZ_<CODE>.QUIZ_QUESTIONS;
SELECT COUNT(*) FROM PL_MBURNEJK_DB.QUIZ_<CODE>.QUIZ_QUESTIONS WHERE domain_name IS NULL;
```

## Step 8 - Update AGENTS.md

Use the Edit tool on `docs/AGENTS.md`. Update these fields:

1. **environment table:**
   - database: `PL_MBURNEJK_DB`
   - schema: `PL_MBURNEJK_DB.QUIZ_<CODE>`
   - warehouse: `PL_MBURNEJK_WH`
   - role: `PL_MBURNEJK_ROLE`
   - exam_code: new exam code

2. **title** (line 2): update to new exam name

3. **source files**: update PDF filename

4. **"how to proceed" section**: the role has full permissions on the database - no need for SYSADMIN/SECURITYADMIN/CORTEXADMIN. Simplify accordingly.

5. **If user provided additional requirements:** add new specification sections in the appropriate place in AGENTS.md. For example, if user requested "AI study recommendations on Progress page", add a new subsection under "progress dashboard" with the full spec.

Do NOT change: table schemas, app structure, platform constraints, cortex llm patterns, security rules, skill references.

## Step 9 - Build and deploy

Execute Phase 3 from `docs/prompts.md`:

1. Read the updated AGENTS.md fully
2. Generate `quiz.py` per the complete specification
3. Run the pre-deploy scan from the `$streamlit-in-snowflake` skill - all 22 items must pass. Fix any issues and re-scan until clean.
4. Upload quiz.py to app stage:
   ```bash
   snow stage copy quiz.py @PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_SIS_APP --overwrite
   ```
5. Deploy:
   ```sql
   CREATE OR REPLACE STREAMLIT PL_MBURNEJK_DB.QUIZ_<CODE>.SNOWPRO_QUIZ
     ROOT_LOCATION = '@PL_MBURNEJK_DB.QUIZ_<CODE>.STAGE_SIS_APP'
     MAIN_FILE = '/quiz.py'
     QUERY_WAREHOUSE = PL_MBURNEJK_WH;
   ```

## Step 10 - Verify and report

1. Verify deployment:
   ```sql
   SHOW STREAMLITS LIKE 'SNOWPRO_QUIZ' IN SCHEMA PL_MBURNEJK_DB.QUIZ_<CODE>;
   ```
   Must return 1 row.

2. Confirm previous exam schema is untouched (if applicable).

3. Git commit all changes on the exam branch:
   ```bash
   git add -A
   git commit -m "feat: add {exam_name} ({exam_code}) quiz app"
   ```

4. Report to the user:
   - New exam: {exam_name} ({exam_code})
   - Schema: PL_MBURNEJK_DB.QUIZ_<CODE>
   - Branch: exam/<exam_code>
   - Domains extracted: N
   - Questions loaded: N
   - Streamlit app deployed: SNOWPRO_QUIZ
   - Any additional features implemented

---

# Important Notes

- **Never drop or modify the previous exam's schema.** Both exams coexist in separate schemas.
- **All SQL uses the new schema.** Double-check every query references `PL_MBURNEJK_DB.QUIZ_<CODE>`.
- **Dollar-quoting for AI_COMPLETE prompts.** Sanitize any `$$` in interpolated content to `$ $`.
- **If any step fails**, diagnose the issue, fix it, and retry. Do not skip steps.
- **The git branch isolates all file changes.** quiz.py, AGENTS.md, and any other modified files exist only on this branch.
