# session prompts - snowpro core quiz SiS

**BEFORE START**
- read instructions, `setup/setup.md` and this file carefully before starting. 
- make sure to setup your environment and add `AGENTS.md` and skills in the cortex code workspace.
- paste one phase prompt at a time. wait for the done criteria before moving to the next phase.
- verify results using `docs/checklists.md` after each phase.

---

## phase 1: infrastructure

```
verify the session context matches AGENTS.md, then proceed.

create only what is listed in AGENTS.md under "table schemas": EXAM_DOMAINS, QUIZ_QUESTIONS,
QUIZ_REVIEW_LOG, and both stages.

then ask me to upload SnowProCoreStudyGuide.pdf to STAGE_QUIZ_DATA. wait for my confirmation.

after i confirm: extract exam domains from the pdf and insert them into EXAM_DOMAINS.

run these verification queries and report results:
1. SELECT COUNT(*) FROM EXAM_DOMAINS;
2. SELECT SUM(weight_pct) FROM EXAM_DOMAINS;
3. SHOW STAGES;
```

---

## phase 2: load questions

```
ask me to upload quiz_questions.csv to STAGE_QUIZ_DATA. wait for my confirmation.

after i confirm: load questions per the "source files" section of AGENTS.md (COPY INTO with FF_CSV).
then backfill domain_name from EXAM_DOMAINS.

run these verification queries and report results:
1. SELECT COUNT(*) FROM QUIZ_QUESTIONS;
2. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE domain_name IS NULL;
3. SELECT COUNT(DISTINCT domain_id) FROM QUIZ_QUESTIONS;
4. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE correct_answer IS NULL OR correct_answer = '';
5. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE question_text IS NULL OR LENGTH(TRIM(question_text)) = 0;
6. SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE option_a IS NULL OR option_b IS NULL;
```

---

## phase 3: build and deploy

```
build quiz.py as specified in AGENTS.md. the app is fully specified there. build the complete,
working implementation without showing me intermediate steps or asking for my approval on the code.

when the implementation is complete:
- run /pre-deploy-scan
- fix all issues found
- re-scan until clean
- then ask me to upload quiz.py and environment.yml to STAGE_SIS_APP

after i confirm the upload: deploy per the "deploy sql" section of AGENTS.md.
```

---

## phase 4: verification

```
please confirm each of the following by testing the app:

1. home screen: 5 controls visible (round size, difficulty, domain, question source, explanations toggle)
2. DB only mode: questions appear immediately; within a 10-question round no question repeats
3. AI only mode: spinner appears while generating; question appears or retry button with cortex error details.
   after a successful AI question: verify it was saved to QUIZ_QUESTIONS
   with SELECT COUNT(*) FROM {database}.{schema}.QUIZ_QUESTIONS WHERE source = 'AI_GENERATED'
4. Mix mode: round completes with no repeated questions
5. wrong answer + explanations ON:
   - spinner appears while generating
   - expander shows: why the correct answer is right (2-3 sentences, Snowflake-specific detail)
   - expander shows: per-option explanation for each wrong option
   - expander shows: mnemonic
   - documentation link appears below the result line (outside the expander)
6. correct answer: checkmark + documentation link below it; no explanation expander
7. incorrect answer: X + "Correct answer: C) full option text"; no "Your answer" line
8. summary: score %, pass/fail indicator, wrong answer cards with full correct answer text
9. review tab: domain and date filters work; entries appear after completing a round with wrong answers

also run:
SELECT COUNT(*) FROM {database}.{schema}.QUIZ_REVIEW_LOG;
expected: > 0 after a round with at least one wrong answer
```

---

## fix session

```
read AGENTS.md before making any changes.

the issue is: [describe the error or wrong behavior]

if the issue involves AI_COMPLETE, model access, or cross-region inference: run /test-cortex first
and report the results.

run /pre-deploy-scan. do not redeploy until the scan is clean.
after fixing: ask me to re-upload quiz.py to STAGE_SIS_APP, then redeploy.
```
