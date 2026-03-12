# snowpro core quiz - cortex code upskilling task

a hands-on project for Snowflake upskilling. you will use **Cortex Code** - an AI coding agent built into Snowsight - to build and deploy a real certification quiz app from scratch.

---

## what you will learn

| technology | what you practice |
|---|---|
| **Cortex Code** | prompting an AI agent to write SQL and Python, reviewing generated code, iterating via chat |
| **Cortex AI functions** | AI_COMPLETE for LLM inference, AI_PARSE_DOCUMENT for PDF extraction |
| **Streamlit in Snowflake** | building and deploying an interactive Python app inside Snowflake, no infrastructure needed |
| **SnowPro Core prep** | the app you build runs 1.1K real COF-C02 exam questions to help you study |

---

## what you will build

a 4-screen quiz app deployed in Snowsight:

- **home** - configure your round (question count, difficulty, domain, AI explanations toggle)
- **quiz** - answer questions with instant feedback and AI-generated explanations
- **summary** - see your score vs the 75% pass threshold with a wrong-answer review
- **review** - browse your full history of wrong answers with domain and date filters

the question bank contains **1.1K real SnowPro Core COF-C02 questions** loaded from a CSV file, plus AI-generated questions on demand via Cortex.

---

## how it works

you do not write the code manually. instead, you direct **Cortex Code** (the AI agent in Snowsight) using structured prompts. the agent reads AGENTS.md as its context and builds the entire app across 4 phases:

1. **infrastructure** - tables, stages, exam domains extracted from the official study guide PDF
2. **data load** - 1.1K questions loaded from CSV into QUIZ_QUESTIONS
3. **app build** - Cortex Code generates quiz.py and deploys it as a Streamlit in Snowflake app
4. **verification** - SQL acceptance checks + manual UX testing

---

## getting started

**first time?** read [instructions/INSTRUCTIONS_DETAILED.md](instructions/INSTRUCTIONS_DETAILED.md)

**know your way around Snowflake?** read [instructions/INSTRUCTIONS.md](instructions/INSTRUCTIONS.md)

---

## repo structure

```
cortex-code-sis-quiz/
├── README.md                           
├── data/
│   ├── quiz_questions.csv              <- ~1.1K COF-C02 questions
│   └── SnowProCoreStudyGuide.pdf       <- the official Snowflake Study Guide for the SnowPro Core exam
├── instructions/
│   ├── INSTRUCTIONS.md                 <- concise step-by-step guide
│   └── INSTRUCTIONS_DETAILED.md        <- detailed guide with explanations and doc links
├── docs/
│   ├── AGENTS.md                       <- Cortex Code context (do not restructure)
│   ├── prompts.md                      <- Cortex Code phase prompts (paste into chat)
│   ├── checklists.md                   <- verification queries for each phase
│   └── known-bugs.md                   <- common issues and fixes
├── setup/
│   ├── setup.sql                       <- SQL bootstrap script
│   └── setup.md                        <- explains what setup.sql creates and why
└── skills/
    ├── pre-deploy-scan/SKILL.md        <- 22-item safety gate before every deploy
    ├── test-cortex/SKILL.md            <- smoke test for AI_COMPLETE and model access
    ├── sql-safe/SKILL.md               <- SQL injection audit
    └── cortex-prompt/SKILL.md          <- prompt quality audit
```