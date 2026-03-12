# verification checklists

use these after each phase to confirm Cortex Code completed the work correctly.
run the SQL queries in Snowsight and compare with expected values.

---

## phase 1: infrastructure

| # | query | expected |
|---|---|---|
| 1 | `SELECT COUNT(*) FROM EXAM_DOMAINS` | 6 |
| 2 | `SELECT SUM(weight_pct) FROM EXAM_DOMAINS` | 100.0 |
| 3 | `SHOW STAGES` | contains STAGE_QUIZ_DATA and STAGE_SIS_APP |

---

## phase 2: load questions

| # | query | expected |
|---|---|---|
| 1 | `SELECT COUNT(*) FROM QUIZ_QUESTIONS` | ~1160 |
| 2 | `SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE domain_name IS NULL` | 0 |
| 3 | `SELECT COUNT(DISTINCT domain_id) FROM QUIZ_QUESTIONS` | 6 |
| 4 | `SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE correct_answer IS NULL OR correct_answer = ''` | 0 |
| 5 | `SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE question_text IS NULL OR LENGTH(TRIM(question_text)) = 0` | 0 |
| 6 | `SELECT COUNT(*) FROM QUIZ_QUESTIONS WHERE option_a IS NULL OR option_b IS NULL` | 0 |

---

## phase 3: build and deploy

| # | check | expected |
|---|---|---|
| 1 | `/pre-deploy-scan` | all 22 items pass |
| 2 | `SHOW STREAMLITS LIKE 'SNOWPRO_QUIZ' IN SCHEMA {database}.{schema}` | 1 row |
| 3 | quiz.py and environment.yml visible in STAGE_SIS_APP | confirmed via Snowsight UI |
| 4 | home screen loads in the browser | confirmed manually |

---

## phase 4: verification

| # | check | expected |
|---|---|---|
| 1 | home screen: 5 controls visible (round size, difficulty, domain, question source, explanations toggle) | all present |
| 2 | DB only mode: questions appear immediately; no repeats within a 10-question round | confirmed |
| 3 | AI only mode: spinner appears while generating; question appears or retry button with error details | confirmed |
| 4 | AI only mode: `SELECT COUNT(*) FROM {database}.{schema}.QUIZ_QUESTIONS WHERE source = 'AI_GENERATED'` | > 0 after a successful AI question |
| 5 | Mix mode: round completes with no repeated questions | confirmed |
| 6 | wrong answer + explanations ON: spinner, then expander with why_correct, why_wrong, mnemonic | confirmed |
| 7 | documentation link appears below the result line (outside the expander) for all answers | confirmed |
| 8 | correct answer: shows checkmark + documentation link, no explanation expander | confirmed |
| 9 | incorrect answer: shows X + "Correct answer: C) full option text", no "Your answer" line | confirmed |
| 10 | summary: score %, pass/fail indicator, wrong answer cards with full correct answer text | confirmed |
| 11 | review tab: domain and date filters work; entries appear after completing a round with wrong answers | confirmed |
| 12 | `SELECT COUNT(*) FROM {database}.{schema}.QUIZ_REVIEW_LOG` | > 0 after a round with at least one wrong answer |
