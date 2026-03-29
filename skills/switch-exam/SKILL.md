---
name: switch-exam
description: Switch the quiz app to a different Snowflake certification exam. Creates a new schema, preserves the previous exam's data and app.
tools:
  - Read
  - SnowflakeSqlExecute
  - SnowflakeObjectSearch
---

# When to Use

Use this skill when switching from one certification exam to another (e.g. COF-C03 to DGES-C01). Each exam gets its own schema - nothing is overwritten.

# Instructions

## Step 1 - Confirm target exam

Ask the user for:
- exam name (e.g. "SnowPro Specialty: Gen AI")
- exam code (e.g. "GES-C01")

## Step 2 - Update AGENTS.md

Read `AGENTS.md` and update in this order:

1. **schema** in the environment table: `CORTEX_DB.QUIZ_<NEW_EXAM_CODE>` (e.g. `QUIZ_DSA_C01`)
2. **exam_code** in the environment table: new exam code
3. **title** (line 2): update to new exam name
4. **description prompts**: update any exam-specific text (study guide name, domain count, question count)

Do NOT change: database, warehouse, role, stage names, app structure, platform constraints, or skill references.

## Step 3 - Create new schema

```sql
CREATE SCHEMA IF NOT EXISTS {database}.QUIZ_{new_exam_code};
```

Then grant permissions (same as setup.sql):
```sql
GRANT USAGE ON SCHEMA {database}.QUIZ_{new_exam_code} TO ROLE CORTEXADMIN;
GRANT CREATE TABLE ON SCHEMA {database}.QUIZ_{new_exam_code} TO ROLE CORTEXADMIN;
GRANT CREATE STAGE ON SCHEMA {database}.QUIZ_{new_exam_code} TO ROLE CORTEXADMIN;
GRANT CREATE FILE FORMAT ON SCHEMA {database}.QUIZ_{new_exam_code} TO ROLE CORTEXADMIN;
GRANT CREATE STREAMLIT ON SCHEMA {database}.QUIZ_{new_exam_code} TO ROLE CORTEXADMIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON FUTURE TABLES IN SCHEMA {database}.QUIZ_{new_exam_code} TO ROLE CORTEXADMIN;
GRANT READ, WRITE ON FUTURE STAGES IN SCHEMA {database}.QUIZ_{new_exam_code} TO ROLE CORTEXADMIN;
```

DO NOT drop or truncate the previous schema. Both exams run in parallel.

## Step 4 - Upload and load data

Ask the user to upload:
1. New exam study guide PDF to STAGE_QUIZ_DATA
2. New exam questions CSV to STAGE_QUIZ_DATA

Then run Phase 1 (infrastructure) and Phase 2 (load questions) from `docs/prompts.md` in the new schema.

## Step 5 - Rebuild and deploy

Run Phase 3 (build and deploy) from `docs/prompts.md`. Cortex Code will generate a new quiz.py based on the updated AGENTS.md.

## Step 6 - Verify

Run Phase 4 (verification) from `docs/prompts.md`.

Confirm:
- new schema has all 4 tables populated
- previous schema and app are still intact
- new app loads with correct exam name and domains
