# setup - snowflake environment


## step 1: cross-region inference

claude-sonnet-4-5 (the model used by the quiz app) is natively available in AWS US regions only.
accounts in other regions (e.g. AWS_EU_CENTRAL_1) need cross-region inference enabled,
otherwise AI_COMPLETE will return This account is not allowed to access this endpoint.

the setting CORTEX_ENABLED_CROSS_REGION = 'AWS_US' routes LLM calls to AWS US transparently.


## step 2: role

CORTEXADMIN is the working role for the entire project: Cortex Code sessions, table ownership,
stage access, and Streamlit deployment. keeping everything under one role simplifies access control.

two Snowflake database roles are granted:

1. SNOWFLAKE.COPILOT_USER - access to Cortex Code UI in Snowsight
2. SNOWFLAKE.CORTEX_USER - all Cortex AI functions (AI_COMPLETE, AI_PARSE_DOCUMENT, etc.)

SNOWFLAKE.CORTEX_USER is granted to PUBLIC by default 
the explicit grant is a safety net in case the account has restricted Cortex access.

there are other roles like CORTEX_AGENT_USER or CORTEX_EMBED_USER that are not needed for this project, 
but may be relevant for more complex use cases involving agents or embeddings.


## step 3: warehouse

XSMALL is sufficient for the quiz app and Cortex Code.


## step 4: database and schema

a dedicated database and schema isolate the project from other workloads.
each exam uses a dedicated schema: `QUIZ_<EXAM_CODE>` (e.g. `QUIZ_COF_C03`, `GES-C01`).
all DDL/DML in the project is scoped to this schema (enforced by AGENTS.md).
to switch exams: use the `/switch-exam` skill — it creates a new schema without touching the previous one.


## step 5: grants

### warehouse

- USAGE - running queries
- OPERATE - start/suspend (required with auto-suspend)

### database and schema

- USAGE on both - required to access objects inside the schema

### object creation

four CREATE privileges allow Cortex Code to create the objects it needs:

- CREATE TABLE (EXAM_DOMAINS, QUIZ_QUESTIONS, QUIZ_REVIEW_LOG, QUIZ_SESSION_LOG)
- CREATE STAGE (STAGE_QUIZ_DATA, STAGE_SIS_APP)
- CREATE FILE FORMAT (FF_CSV)
- CREATE STREAMLIT (SNOWPRO_QUIZ)

### future grants

FUTURE TABLES and FUTURE STAGES grants ensure that any new tables or stages created by 
other roles in the schema are automatically accessible to CORTEXADMIN, which is important for development agility.

### stage access (if created by another role)

if stages are created by CORTEXADMIN itself (which is the normal flow), the role owns them and
no separate grant is needed. if the stages were created by another role, explicit READ and WRITE
grants are required.

important: for internal named stages the grants are READ and WRITE (not USAGE).
USAGE applies to external stages only. WRITE requires READ to be granted first.

## step 6: verify

after running the script, switch to CORTEXADMIN and confirm that CURRENT_ROLE(),
CURRENT_WAREHOUSE(), CURRENT_DATABASE(), and CURRENT_SCHEMA() all return the expected values.


## post-setup: enable web search and Cortex Code

these steps are done in the Snowsight UI, not in SQL.

1. **web search:** AI & ML > Agents > Settings > Tools and connectors > Web search > enable.
   allows Cortex Code to search current Snowflake documentation and other web resources while building the app.

2. **Cortex Code:** open a workspace > click the white star icon (bottom-right corner).
   the Cortex Code chat panel opens on the right side of the editor.

3. **context:** 
   - add AGENTS.md to the session (to the Workspace files)
   - add skills to the session (plus button in the chat input box) 


## what Cortex Code creates (do not do this manually)

after running the phase prompts from docs/prompts.md, Cortex Code creates:

- table EXAM_DOMAINS - phase 1
- table QUIZ_QUESTIONS - phase 1
- table QUIZ_REVIEW_LOG - phase 1
- table QUIZ_SESSION_LOG - phase 1
- stage STAGE_QUIZ_DATA - phase 1
- stage STAGE_SIS_APP - phase 1
- file format FF_CSV - phase 2
- quiz.py + environment.yml - phase 3
- streamlit SNOWPRO_QUIZ - phase 3


## sources

- [Cortex AI Functions - access control](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql)
- [Cortex Code in Snowsight](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-snowsight)
- [Streamlit in Snowflake - privileges](https://docs.snowflake.com/en/developer-guide/streamlit/object-management/privileges)