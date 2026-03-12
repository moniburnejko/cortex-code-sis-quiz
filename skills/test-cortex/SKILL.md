---
name: test-cortex
description: Smoke test AI_COMPLETE availability, model access, and cross-region inference. Use when debugging Cortex errors or before deploying quiz.py.
tools:
  - SnowflakeSqlExecute
---

# When to Use

Use this skill when:
- AI question generation fails with "AI failed to generate a question"
- Explanation generation silently fails
- User sees `This account is not allowed to access this endpoint`
- After changing `CORTEX_MODEL` in quiz.py to verify the new model is accessible
- Before deploying a new version of the quiz app
- Diagnosing any `AI_COMPLETE` or cross-region inference issue

# Instructions

Run the following tests in order. Report pass/fail for each, plus the raw output for any failing test.

## Step 1 — Basic connectivity

```sql
SELECT AI_COMPLETE('claude-sonnet-4-5', $Tell me the current Snowflake region in one word.$);
```

Expected: returns a non-empty string (region name or short answer).
Fail signal: `This account is not allowed to access this endpoint` or NULL.

---

## Step 2 — Model used in quiz.py

```sql
SELECT AI_COMPLETE('claude-4-sonnet', $Say "ok" in JSON exactly: {"status":"ok"}$);
```

Expected: returns a string containing `{"status":"ok"}` (possibly with markdown fences).
Fail signal: `Model not found`, `not allowed`, or NULL.

---

## Step 3 — Cross-region parameter

```sql
SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;
```

Expected: value = `AWS_US` at ACCOUNT level.
If value = `DISABLED` or level = `DEFAULT`: cross-region inference is off — AI_COMPLETE will fail for EU accounts using US-only claude models.

Fix if needed (requires ACCOUNTADMIN):
```sql
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'AWS_US';
```

---

## Step 4 — JSON parsing smoke test

```sql
SELECT AI_COMPLETE('claude-4-sonnet', $Return only valid JSON with this exact structure, no markdown fences:
{"question_text": "What is a virtual warehouse?", "option_a": "A compute cluster", "option_b": "A storage unit", "option_c": "A database schema", "option_d": "A role", "correct_answer": "A"}$);
```

Expected: a JSON object (possibly wrapped in markdown fences — `parse_cortex_json` handles that).
Fail signal: empty response, NULL, or malformed non-JSON output.

---

## Step 5 — Available models

```sql
SELECT * FROM SNOWFLAKE.ML_FUNCTIONS.MODELS WHERE MODEL_NAME LIKE 'claude%' ORDER BY MODEL_NAME;
```

Expected: list of available claude models in this region.
If empty: no claude models available — check cross-region setting from Step 3.

---

## Reporting

After running all steps, report:

| Step | Status | Notes |
|------|--------|-------|
| 1 — Basic connectivity | PASS / FAIL | raw error if FAIL |
| 2 — claude-4-sonnet model | PASS / FAIL | raw error if FAIL |
| 3 — Cross-region parameter | PASS / FAIL | current value |
| 4 — JSON output | PASS / FAIL | raw output if unexpected |
| 5 — Available models | INFO | list of models |

If Step 3 fails: provide the ALTER ACCOUNT fix and ask user to confirm ACCOUNTADMIN role before running.

# Best Practices

- Run Step 3 first if account region is EU (AWS_EU_CENTRAL_1, AWS_EU_WEST_1, etc.) — this is the most common failure cause
- The model name in quiz.py (`CORTEX_MODEL = "claude-4-sonnet"`) must match an available model from Step 5
- `parse_cortex_json` in quiz.py handles markdown fences and double-encoded JSON — Step 4 tests this end-to-end path
