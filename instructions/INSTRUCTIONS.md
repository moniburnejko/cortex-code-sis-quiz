# instructions - snowpro core quiz

> first time with Snowflake or Cortex? use [INSTRUCTIONS_DETAILED.md](INSTRUCTIONS_DETAILED.md) instead.

> **disclaimer:** AI-generated questions and explanations (produced via Cortex AI functions) may be inaccurate - LLM models can hallucinate, and Snowflake exposes older models through AI functions that are less reliable than the latest ones. the CSV question bank is community-sourced from examprepper, not official Snowflake material, so answers there may also be incorrect. always verify against the Snowflake docs when in doubt.

> **performance:** enabling AI-generated questions or AI explanations in the quiz config makes the app noticeably slower - each question requires a live LLM call via Cortex. you can switch to a faster model in `docs/AGENTS.md` (see `docs/custom_config.md`), but faster models tend to hallucinate more. your call.

---

## step 1 - run environment setup

run `setup/setup.sql` as ACCOUNTADMIN / SECURITYADMIN / SYSADMIN. this creates the role, warehouse, database, schema and all required grants.

> **critical:** `setup/setup.sql` starts with `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'AWS_US';`
> this must be run as ACCOUNTADMIN **before anything else**. without it, all AI functions (AI_COMPLETE, AI_PARSE_DOCUMENT) will fail with a region access error and the app cannot be built.

see `setup/setup.md` for explanations of what each step does.

---

## step 2 - clone the repo

clone the repo locally:
```bash
git clone https://github.com/moniburnejko/cortex-code-sis-quiz.git
cd cortex-code-sis-quiz
```

you will need the files in `data/`, `docs/`, `skills/`, and `setup/` throughout the project.

---

## step 3 - enable prerequisites in Snowsight

1. **web search:** AI & ML > Agents > Settings > Tools and connectors > Web search > enable
2. **Cortex Code:** open a workspace > click the white star icon (bottom-right corner) to open the Cortex Code chat panel

---

## step 4 - load context into Cortex Code

open a Cortex Code workspace in Snowsight. load the project files manually:

1. add `AGENTS.md` to the session: attachment icon (or drag & drop the file into the chat)
2. upload skills: click the **+** icon in the chat input > **Upload skill folder(s)** > select the `skills/` folder from your local clone

---
## step 5 - run phase 1: infrastructure

paste the **phase 1** prompt from `docs/prompts.md` into the chat.
upload `SnowProCoreStudyGuide.pdf` to STAGE_QUIZ_DATA when asked.
verify with the done criteria at the end of the phase 1 prompt.

---

## step 6 - run phase 2: load questions

paste the **phase 2** prompt from `docs/prompts.md`.
upload `quiz_questions.csv` (from `data/`) to STAGE_QUIZ_DATA when asked.
verify with the done criteria at the end of the phase 2 prompt.

---

## step 7 - run phase 3: build and deploy

paste the **phase 3** prompt from `docs/prompts.md`.
when Cortex Code finishes, upload `quiz.py` (from the editor) and `environment.yml` to STAGE_SIS_APP.
verify with the done criteria at the end of the phase 3 prompt.

---

## step 8 - run phase 4: verification

open the app: Snowsight > Streamlit > SNOWPRO_QUIZ.
paste the **phase 4** prompt and walk through the verification items.

---

## customisation

want to change the AI model, quiz topic, round sizes, or explanation format?
see `docs/custom_config.md` for a list of things you can tweak in `AGENTS.md` and `docs/prompts.md`.

---

## troubleshooting

if the app breaks after deployment, use the **fix session** prompt from `docs/prompts.md`.
describe the error, let Cortex Code diagnose and fix, then re-upload `quiz.py` and redeploy.
see `docs/known-bugs.md` for common issues and fixes.
