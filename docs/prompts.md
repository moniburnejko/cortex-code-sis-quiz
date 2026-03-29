# session prompts - snowpro core quiz SiS (snowsight)

---

## phase 1: infrastructure

```
verify the session context matches AGENTS.md, then proceed.

create only what is listed in AGENTS.md under "table schemas": EXAM_DOMAINS, QUIZ_QUESTIONS,
QUIZ_REVIEW_LOG, QUIZ_SESSION_LOG, and both stages.

then ask me to upload SnowProCoreStudyGuide.pdf to STAGE_QUIZ_DATA. wait for my confirmation.

after i confirm: extract exam domains from the pdf and insert them into EXAM_DOMAINS.

when done, run these verification queries and report the results:
1. SELECT COUNT(*) FROM EXAM_DOMAINS;
2. SELECT SUM(weight_pct) FROM EXAM_DOMAINS;
3. SELECT COUNT(*) FROM QUIZ_SESSION_LOG;
4. SHOW STAGES;

done criteria:
- EXAM_DOMAINS: 6 rows, weights sum to 100.0
- QUIZ_SESSION_LOG: 0 rows (empty, table exists)
- STAGE_QUIZ_DATA and STAGE_SIS_APP exist
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
- result display: two-column st.success/st.error for correct/user answer
- explanation UI: why_correct, why_wrong (per-option), mnemonic, doc_url

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
5. result display: two-column row — green box (correct answer) and red box (your answer)
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

if the issue involves AI_COMPLETE, model access, or cross-region inference: run /test-cortex first
and report the results.

run the pre-deploy scan from the /streamlit-in-snowflake skill. do not redeploy until the scan is clean.
after fixing: ask me to re-upload quiz.py to STAGE_SIS_APP, then redeploy.
```
