---
name: cortex-ai
description: Cortex AI function patterns and diagnostics - AI_COMPLETE, AI_PARSE_DOCUMENT, BUILD_SCOPED_FILE_URL, dollar-quoting, stage requirements. Use when calling any Cortex AI function or diagnosing Cortex errors.
tools:
  - Read
  - Grep
---

# When to Use

- Calling `AI_COMPLETE` (question generation, explanation generation, key_facts extraction)
- Calling `AI_PARSE_DOCUMENT` (PDF parsing in Phase 1)
- Debugging Cortex errors: "file not accessible", "model not found", NULL responses
- Setting up stages for Cortex AI functions
- Before deploying quiz.py - verify Cortex connectivity

---

# AI_COMPLETE

## Dollar-quoting

All prompts passed to AI_COMPLETE must use `$$...$$` quoting, not single quotes. Before interpolation, sanitize:

```python
safe_prompt = prompt.replace("$$", "$ $")
sql = f"SELECT AI_COMPLETE('{CORTEX_MODEL}', $${safe_prompt}$$)"
```

`CORTEX_MODEL` is a hardcoded constant - safe to interpolate. Never interpolate user-derived values.

## Error handling

```python
def call_cortex(prompt):
    try:
        safe_prompt = prompt.replace("$$", "$ $")
        rows = session.sql(f"SELECT AI_COMPLETE('{CORTEX_MODEL}', $${safe_prompt}$$)").collect()
        if not rows or rows[0][0] is None:
            return None
        return str(rows[0][0])
    except Exception as e:
        st.session_state["last_cortex_error"] = str(e)
        return None
```

## Response parsing

AI_COMPLETE responses may be:
1. Plain JSON
2. JSON wrapped in markdown fences (` ```json ... ``` `)
3. Double-encoded (first `json.loads` returns a string, needs second parse)

Always use `parse_cortex_json()` - never `json.loads()` directly.

---

# AI_PARSE_DOCUMENT

## Correct pattern

`AI_PARSE_DOCUMENT` returns a **VARIANT** directly. Common mistakes:

| Mistake | Fix |
|---------|-----|
| Wrapping in `PARSE_JSON()` | Do NOT - result is already VARIANT |
| Paginating manually (page by page) | Do NOT - one call returns the full document |
| Using raw stage path `@stage/file.pdf` | Use `BUILD_SCOPED_FILE_URL(@stage, 'file.pdf')` |

```sql
-- get full document content in one call
SELECT AI_PARSE_DOCUMENT(
    BUILD_SCOPED_FILE_URL(@{database}.{schema}.STAGE_QUIZ_DATA, 'SnowProCoreStudyGuide.pdf'),
    'LAYOUT'
) AS result;

-- extract text from VARIANT result
SELECT result:content::VARCHAR
FROM (
    SELECT AI_PARSE_DOCUMENT(
        BUILD_SCOPED_FILE_URL(@{database}.{schema}.STAGE_QUIZ_DATA, 'SnowProCoreStudyGuide.pdf'),
        'LAYOUT'
    ) AS result
);
```

## Stage requirements

`AI_PARSE_DOCUMENT` requires server-side encryption and directory enabled on the stage:

```sql
CREATE STAGE IF NOT EXISTS {database}.{schema}.STAGE_QUIZ_DATA
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);
```

- `SNOWFLAKE_SSE` - required for Cortex to read files. #1 cause of "file not accessible" errors after PDF upload.
- `DIRECTORY = TRUE` - required for file path enumeration.

If stage exists without these settings, recreate it:
```sql
DROP STAGE IF EXISTS {database}.{schema}.STAGE_QUIZ_DATA;
CREATE STAGE {database}.{schema}.STAGE_QUIZ_DATA
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);
```
Then re-upload files via Snowsight UI.

---

# Diagnostics

Run these tests when AI functions fail. Report pass/fail for each.

## Step 1 - Basic connectivity

```sql
SELECT AI_COMPLETE('claude-sonnet-4-5', $Tell me the current Snowflake region in one word.$);
```

Expected: non-empty string. Fail: `not allowed to access this endpoint` or NULL.

## Step 2 - Model access

```sql
SELECT AI_COMPLETE('claude-sonnet-4-5', $Say "ok" in JSON exactly: {"status":"ok"}$);
```

Expected: string containing `{"status":"ok"}`. Fail: `Model not found` or NULL.

## Step 3 - Cross-region parameter

```sql
SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;
```

Expected: value = `AWS_US`. If `DISABLED`: AI_COMPLETE will fail for EU accounts.

Fix (requires ACCOUNTADMIN):
```sql
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'AWS_US';
```

## Step 4 - JSON parsing

```sql
SELECT AI_COMPLETE('claude-sonnet-4-5', $Return only valid JSON with this exact structure, no markdown fences:
{"question_text": "What is a virtual warehouse?", "option_a": "A compute cluster", "option_b": "A storage unit", "option_c": "A database schema", "option_d": "A role", "correct_answer": "A"}$);
```

Expected: JSON object (possibly with markdown fences - `parse_cortex_json` handles that).

## Step 5 - Available models

```sql
SELECT * FROM SNOWFLAKE.ML_FUNCTIONS.MODELS WHERE MODEL_NAME LIKE 'claude%' ORDER BY MODEL_NAME;
```

Expected: list of available claude models in this region.

## Reporting

| Step | Status | Notes |
|------|--------|-------|
| 1 - Basic connectivity | PASS / FAIL | |
| 2 - Model access | PASS / FAIL | |
| 3 - Cross-region | PASS / FAIL | current value |
| 4 - JSON output | PASS / FAIL | |
| 5 - Models list | INFO | |

If Step 3 fails: provide the ALTER ACCOUNT fix and ask user to confirm ACCOUNTADMIN role before running.
