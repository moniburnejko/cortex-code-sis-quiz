# custom configuration guide

this file describes what you can change in `AGENTS.md` and `docs/prompts.md` to personalise the quiz app without breaking anything.

changes are grouped into two levels: **easy** (swap a value, no side effects) and **advanced** (requires editing a larger block of text and understanding what it affects).

after any change: re-add `AGENTS.md` to the Cortex Code session before running the next prompt.

---

## easy changes

### change the AI model

**where:** `AGENTS.md` > `## cortex llm`

```
preferred model: `claude-sonnet-4-5`
```

swap to any model available in your region. examples: `mistral-large2`, `llama3.1-70b`, `snowflake-arctic`.

note: if your account is in `AWS_EU_CENTRAL_1`, cross-region inference must be enabled for Claude models (`CORTEX_ENABLED_CROSS_REGION = 'AWS_US'`). other models may be available locally without this setting.

---

### change the round size options

**where:** `AGENTS.md` > `## home screen`

```
`st.select_slider`: number of questions - options: 5, 10, 25, 50, 100
```

add, remove, or replace values.

---

### change the app name

**where:** `AGENTS.md` > `## snowflake environment`

```
app_name  | `SNOWPRO_QUIZ`
main_file | `quiz.py`
```

rename to anything. also update the deploy SQL at the bottom of `AGENTS.md` to match.

---

### change the AI/DB mix ratio

**where:** `AGENTS.md` > `## question selection`

```
`"mix"`: 20% chance AI first; if AI fails, fall through to DB
```

change `20%` to any value. higher = more AI-generated questions per round, slower but more variety. lower = mostly DB questions with occasional AI.

---

## advanced changes

### change the quiz topic entirely

this is the biggest customisation. the app is not hardcoded to SnowPro Core - it is driven by whatever is in `EXAM_DOMAINS` and `QUIZ_QUESTIONS`.

**what to change:**

1. `AGENTS.md` > `## source files` - replace `SnowProCoreStudyGuide.pdf` with a PDF relevant to your topic. Cortex will extract domains, weights, and topics from it automatically via `AI_PARSE_DOCUMENT + AI_COMPLETE`.
2. `AGENTS.md` > `## source files` - replace `quiz_questions.csv` with your own question bank in the same column format.
3. `docs/prompts.md` > `## phase 1` - the prompt references the PDF extraction; it works generically, no changes needed unless your PDF has a different structure.
4. `docs/prompts.md` > `## phase 4` - update the verification steps to reflect your domain count and expected question count.

the rest of `AGENTS.md` (table schemas, app structure, platform constraints) stays the same.

---

### change what the AI explanation includes

**where:** `AGENTS.md` > `## cortex llm` > `### AI explanation generation`

the explanation prompt currently asks for four fields: `why_correct`, `why_wrong`, `mnemonic`, `doc_url`.

you can:
- remove `mnemonic` if you don't want memory aids
- remove `doc_url` if your topic has no official documentation
- add a field like `example` (a practical usage example) or `exam_tip` (a test-taking hint)

after changing the field list in the prompt spec, also update the rendering block in the same section and the `history_item` section (which stores `mnemonic` and `doc_url`).

---

### change the difficulty distribution in mixed mode

**where:** `AGENTS.md` > `## question selection`

```
**difficulty** (mixed mode): 30% easy, 50% medium, 20% hard.
```

adjust the three percentages (must sum to 100%). example: `10% easy, 40% medium, 50% hard` for a harder default experience.

---

### add a new screen or tab

**where:** `AGENTS.md` > `## app structure`

the app currently has four functions rendered as tabs: home, quiz, summary, review. to add a new tab (e.g. a statistics dashboard or a flashcard mode), add a new entry to the function list and describe its layout and data source in a new section at the bottom of `AGENTS.md`.

then update `docs/prompts.md` > `## phase 3` to mention the new screen, and add verification steps for it in `## phase 4`.

---

### write the phase 3 prompt in your own language

**where:** `docs/prompts.md` > `## phase 3`

the build prompt is intentionally terse. if you want Cortex Code to produce a specific code style, add explicit instructions:
- "add a docstring to every function"
- "use Polish labels in the UI"
- "add an `st.info()` banner on the home screen describing the exam"

keep the structural requirements (function order, `st.set_page_config` first, no CSS injection) - those are constraints, not style preferences.
