# skills

custom Cortex Code skills used in this project. upload the `skills/` folder to Cortex Code to enable them as slash commands.

---

## /streamlit-in-snowflake

**scope:** coding patterns and pre-deploy checks for Streamlit in Snowflake (SiS v1.52.*).

**when to use:**
- writing or reviewing any SiS app code
- before every deploy — run the 22-item pre-deploy scan to catch known runtime failures

**what it checks:**
- SQL injection risks and parameterized queries
- Cortex AI_COMPLETE dollar-quoting and response parsing
- st.rerun() count (exactly 6 locations)
- SiS-incompatible APIs (st.fragment, st.connection, unsafe_allow_html)
- session_state reliability (mutable objects, rerun timing)
- date handling, column name normalization, page config

---

## /cortex-ai

**scope:** Cortex AI function patterns (AI_COMPLETE, AI_PARSE_DOCUMENT) and diagnostics.

**when to use:**
- calling any Cortex AI function for the first time
- diagnosing errors from AI_COMPLETE or AI_PARSE_DOCUMENT
- setting up stages for PDF extraction (encryption, directory, file URL)

**what it covers:**
- AI_COMPLETE: dollar-quoting, `$$` sanitization, error handling
- AI_PARSE_DOCUMENT: no PARSE_JSON needed (returns VARIANT), BUILD_SCOPED_FILE_URL, stage requirements (SNOWFLAKE_SSE encryption, DIRECTORY=TRUE)
- 5-step diagnostic runbook for Cortex errors (cross-region inference, model availability, permissions)

---

## /cortex-prompt

**scope:** prompt quality audit for all AI_COMPLETE prompts in quiz.py.

**when to use:**
- question generation returns wrong JSON keys or shallow content
- AI explanations are incomplete or parse errors occur
- after modifying any prompt template in quiz.py

**what it checks:**
- JSON output reliability (key names, fences, double-encoding)
- content completeness (difficulty adherence, grounding from key_facts)
- deduplication block (uses `_get_shown_texts()` from round_history)
- injection safety

---

## /switch-exam

**scope:** switch the quiz app to a different Snowflake certification exam.

**when to use:**
- switching from one exam to another (e.g. COF-C02 to DGES-C01)

**what it does:**
- creates a new schema for the target exam
- preserves the previous exam's data and app
- guides through re-running phases 1-3 in the new schema
