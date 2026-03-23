# known bugs and fixes

issues encountered during development with Cortex Code.
if a bug reappears, use the fix session prompt from `docs/prompts.md` and reference this file.

---

## AI question generation fails with parse error (truncated response)

symptom: "Unable to generate question" with `Parse error: Expecting value: line 1 column 1 (char 0)`. the raw response shows a valid-looking JSON that is cut off mid-string (e.g. `"option_c": "Virtual warehous`).

cause: Cortex returned a response that exceeded the output length and was truncated. after stripping markdown fences, the remaining string is incomplete and cannot be parsed.

fix: add explicit length constraints to the question generation prompt:
- `question_text`: max 150 characters
- each option: max 80 characters
- instruct the model to respond with ONLY the JSON object, no markdown fences, no extra text

these constraints are specified in `AGENTS.md` under `## cortex llm > ### AI question generation`.

---

## retry button does nothing after AI question generation fails

symptom: "Unable to generate question" screen appears; clicking Retry has no effect and the app is stuck. the only way out is to restart SiS.

cause 1: Retry button sets session state keys but does not call `st.rerun()`, so the UI never re-renders and no new generation is triggered.

cause 2: Cortex returned an explanation-shaped JSON (`why_correct`, `why_wrong`) instead of a question JSON. `parse_cortex_json` successfully parsed it as a dict, but `question_text` / `option_a` validation failed all 3 retries. the bad response is stored in `last_ai_response`, and Retry re-runs into the same state.

fix:
- Retry button must clear `question`, `last_cortex_error`, `last_ai_response`, `last_ai_parse_error` from session state, then call `st.rerun()`.
- in `generate_ai_question`: after parsing, check for `why_correct` or `why_wrong` keys in the result dict. if present, discard immediately and count as a failed attempt before reaching field validation.

---

## AI_PARSE_DOCUMENT fails on unencrypted stage

symptom: `AI_PARSE_DOCUMENT` returns an error or refuses to read the PDF.

cause: stage was created without the required settings. see AGENTS.md > "stage requirements for STAGE_QUIZ_DATA" for the correct configuration.

fix: recreate `STAGE_QUIZ_DATA` with the required encryption and directory settings, then re-upload the PDF via Snowsight UI.

---

## AI_COMPLETE returns double-encoded JSON

symptom: `'str' object has no attribute 'get'`

cause: AI_COMPLETE wraps the JSON in a string literal: `"{\"key\":\"val\"}"`.

fix: in `parse_cortex_json`, after first `json.loads`, check `isinstance(result, str)` and parse again.

---

## AI_COMPLETE not accessible

symptom: `This account is not allowed to access this endpoint.`

cause: account region is EU; claude models are US-only.

fix: `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'AWS_US';` (requires ACCOUNTADMIN).

verify: `SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;` value should be `AWS_US`.

---

## cortex returns JSON in markdown fences

symptom: `JSONDecodeError` when parsing response.

fix: strip ` ```json ... ``` ` before parsing. never call `json.loads()` directly on Cortex output.

---

## correct answer shows only letter, not full text

symptom: after answering shows "C" instead of "C) full option text".

fix: `history_item` must include `option_texts` dict. resolve letters to full text everywhere.

---

## explanations appear rarely or never

symptom: explanation expander missing after wrong answers.

cause: Cortex call was inside Submit handler and timed out before `st.rerun()`.

fix: generate explanation in `if answered:` render phase with `st.spinner`. use `explanation is None` guard. sentinel `{}` prevents retry loop on failure.

---

## questions repeat within a round

symptom: same question appears multiple times in one round.

cause: DB query returns full pool each time with no exclusion of already-shown questions.

fix: collect `QUESTION_ID` values from `round_history`; exclude them from the candidate pool before picking randomly. fall back to full pool only when all questions have been shown.

---

## review tab shows no entries (date filter)

symptom: review tab empty even after completing a round with wrong answers.

cause: Python `datetime.date` objects passed directly as bind params to a `TIMESTAMP_NTZ` comparison; `<= end_date` truncates to midnight and misses same-day entries.

fix: convert dates to formatted strings (`strftime("%Y-%m-%d")`); add 1 day to end date and use `< end` (exclusive upper bound).
