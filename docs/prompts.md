# session prompts - snowpro core quiz SiS (snowsight)

---

## phase 1: infrastructure

```
verify the session context matches AGENTS.md, then proceed.

create the stages FIRST — per the "stage DDL" section of AGENTS.md. STAGE_QUIZ_DATA must have
ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') and DIRECTORY = (ENABLE = TRUE). without these,
AI_PARSE_DOCUMENT will fail after PDF upload.

then create the tables listed in AGENTS.md under "table schemas": EXAM_DOMAINS, QUIZ_QUESTIONS,
QUIZ_REVIEW_LOG, QUIZ_SESSION_LOG.

then ask me to upload SnowProCoreStudyGuide.pdf to STAGE_QUIZ_DATA. wait for my confirmation.

after i confirm:
1. extract exam domains from the pdf and insert them into EXAM_DOMAINS (domain_id, domain_name, weight_pct, topics).
2. for each of the 6 domains: extract key_facts from the pdf and UPDATE EXAM_DOMAINS SET key_facts = ... per the spec in AGENTS.md. do this domain by domain — run one UPDATE per domain, verify it set a non-null value before moving to the next.

when done, run these verification queries and report the results:
1. SELECT COUNT(*) FROM EXAM_DOMAINS;
2. SELECT SUM(weight_pct) FROM EXAM_DOMAINS;
3. SELECT COUNT(*) FROM QUIZ_SESSION_LOG;
4. SELECT domain_name, LENGTH(key_facts) AS facts_len FROM EXAM_DOMAINS ORDER BY domain_id;
5. SHOW STAGES;

done criteria:
- EXAM_DOMAINS: 6 rows, weights sum to 100.0
- key_facts: all 6 domains have facts_len > 0
- QUIZ_SESSION_LOG: 0 rows (empty, table exists)
- STAGE_QUIZ_DATA and STAGE_SIS_APP exist
- STAGE_QUIZ_DATA has ENCRYPTION=SNOWFLAKE_SSE and DIRECTORY=TRUE
```

---

## phase 2: load questions

```
ask me to upload quiz_questions.csv to STAGE_QUIZ_DATA. wait for my confirmation.

after i confirm: load questions per the "source files" section of AGENTS.md (COPY INTO with FF_CSV).
then backfill domain_name from EXAM_DOMAINS.

when done, run these verification queries and report the results:
1. SELECT COUNT(*) FROM QUIZ_QUESTIONS;
2. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE domain_name IS NULL;
3. SELECT COUNT(DISTINCT domain_id) FROM QUIZ_QUESTIONS;
4. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE correct_answer IS NULL OR correct_answer = '';
5. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE question_text IS NULL OR LENGTH(TRIM(question_text)) = 0;
6. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE option_a IS NULL OR option_b IS NULL;

done criteria:
- query 1: ~1160 rows
- queries 2-6: 0
```

---

## phase 3: build and deploy

```
read AGENTS.md fully before writing any code — especially "platform constraints", "cortex llm", and "app structure".

build quiz.py per the specification in AGENTS.md.

key requirements:
- use AI_COMPLETE with dollar-quoting for all Cortex calls (see "cortex llm")
- use parse_cortex_json for all Cortex response parsing — never json.loads() directly
- explanation generated on-demand in render phase, not in Submit handler
- st.rerun() exactly twice — Submit Answer handler and Retry button handler
- history_item must include option_texts dict
- question_source selectbox: mix / db / ai
- implement render_dashboard() per the "progress dashboard" section of AGENTS.md
- implement QUIZ_SESSION_LOG write-back per the "write-back on round end" section
- result display: plain st.markdown() — "Correct!" / "Incorrect!" + correct answer + your answer (no colored boxes)
- explanation UI: why_correct, why_wrong (per-option), mnemonic, doc_url
- deduplication: use `_get_shown_texts()` helper (reads round_history + current question) — pass to SQL NOT IN for DB questions and to "DO NOT repeat" block for AI questions. do NOT use separate shown_question_ids/shown_question_texts keys in session_state — they are unreliable in SiS
- difficulty: use DIFFICULTY_GUIDE dict with full descriptions for each level (easy/medium/hard) — pass as primary constraint in AI question prompt, before any grounding/facts

when done, run the pre-deploy scan from the /streamlit-in-snowflake skill. fix all issues. re-scan until clean.

then ask me to upload quiz.py and environment.yml to STAGE_SIS_APP. wait for my confirmation.

after i confirm: deploy per the "deploy sql" section of AGENTS.md.

done criteria:
- pre-deploy scan: all 22 items pass
- SHOW STREAMLITS returns 1 row for SNOWPRO_QUIZ
- home screen loads in the browser (i will confirm)
```

---

## phase 4: verification

```
please confirm each of the following:

1. home screen loads with all 5 controls: round size, difficulty, domain, question source, explanations toggle
2. DB only mode: questions appear immediately, correct answer shown with full text after submitting
3. AI only mode: questions generate (may take a few seconds), or retry button appears with error details
4. Mix mode: mix of DB and AI questions
5. result display: plain text — "Correct!" or "Incorrect!" followed by correct answer and your answer (no green/red boxes)
6. wrong answer + explanations ON:
   - spinner appears while generating
   - "✨ AI Explanation" shows: why_correct (2-3 sentences), why_wrong (per-option), mnemonic (💡 Remember: ...), doc_url
7. SHORT_REASON shown via st.info() after every answer (correct and incorrect)
8. summary screen: score %, pass/fail indicator, wrong answer cards with full correct answer text
9. review tab: domain and date filters work, correct_answer column shows full text
10. "📊 Progress" tab: empty state message before first round; after completing a round shows sessions, avg score, questions practiced, readiness score, recent sessions chart, errors by domain chart, weak spots

also run:
SELECT COUNT(*) FROM {database}.{schema}.QUIZ_REVIEW_LOG;
SELECT COUNT(*) FROM {database}.{schema}.QUIZ_SESSION_LOG;
expected: both > 0 after completing a round with at least one wrong answer.
```

---

## fix session

```
read AGENTS.md before making any changes.

the issue is: [describe the error]

if the issue involves AI_COMPLETE, model access, or cross-region inference: run /cortex-ai first
and report the results.

run the pre-deploy scan from the /streamlit-in-snowflake skill. do not redeploy until the scan is clean.
after fixing: ask me to re-upload quiz.py to STAGE_SIS_APP, then redeploy.
```
