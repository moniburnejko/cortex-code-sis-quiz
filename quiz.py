import streamlit as st

st.set_page_config(layout="centered")

import json
import re
import random
import datetime
import pandas as pd
import altair as alt
from snowflake.snowpark.context import get_active_session

session = get_active_session()

DATABASE = "CORTEX_DB"
SCHEMA = "QUIZ_COF_C02"
FQN = f"{DATABASE}.{SCHEMA}"
EXAM_CODE = "COF-C02"
CORTEX_MODEL = "claude-sonnet-4-5"

DIFFICULTY_GUIDE = {
    "easy": (
        "EASY — single-concept recall. "
        "Ask 'What is X?', 'Which feature does Y?', or 'What happens when Z?'. "
        "One fact, one clearly correct answer. The wrong options should be obviously wrong "
        "to someone who studied the material."
    ),
    "medium": (
        "MEDIUM — applied scenario. "
        "Present a real-world use-case and ask which approach, feature, or configuration is best. "
        "Requires understanding trade-offs. All four options should be plausible Snowflake features "
        "but only one fits the scenario."
    ),
    "hard": (
        "HARD — tricky edge cases and gotchas. "
        "Ask about exceptions to general rules, counterintuitive behaviors, precise limits, "
        "or scenarios where the obvious answer is wrong. "
        "All options must look plausible — the correct answer should surprise someone "
        "who only has surface-level knowledge. "
        "Pick ANY topic from the domain — do not limit to a fixed set of topics."
    ),
}

SOURCE_LABELS = {"mix": "Mix (DB + AI)", "db": "DB only", "ai": "AI only"}


def init_session_state():
    defaults = {
        "screen": "home",
        "question": None,
        "answered": False,
        "selected": [],
        "explanation": None,
        "q_index": 0,
        "round_size": 10,
        "round_history": [],
        "difficulty": "mixed",
        "domain_filter": "All",
        "question_source": "mix",
        "use_explanations": True,
        "correct_count": 0,
        "total_count": 0,
        "current_history_item": None,
        "last_cortex_error": None,
        "last_ai_response": None,
        "last_ai_parse_error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


@st.cache_data(ttl=300)
def load_domains():
    s = get_active_session()
    rows = s.sql(f"SELECT domain_id, domain_name, weight_pct, topics, key_facts FROM {FQN}.EXAM_DOMAINS ORDER BY domain_id").collect()
    return [{k.upper(): v for k, v in r.as_dict().items()} for r in rows]


@st.cache_data(ttl=60)
def load_session_stats():
    s = get_active_session()
    rows = s.sql(f"SELECT COUNT(*) AS sessions, AVG(score_pct) AS avg_score, SUM(round_size) AS total_questions FROM {FQN}.QUIZ_SESSION_LOG").collect()
    r = {k.upper(): v for k, v in rows[0].as_dict().items()}
    return int(r["SESSIONS"] or 0), float(r["AVG_SCORE"] or 0), int(r["TOTAL_QUESTIONS"] or 0)


@st.cache_data(ttl=60)
def load_recent_sessions():
    s = get_active_session()
    rows = s.sql(
        f"SELECT ROW_NUMBER() OVER (ORDER BY session_ts) AS session_num, "
        f"session_ts, score_pct, round_size "
        f"FROM {FQN}.QUIZ_SESSION_LOG ORDER BY session_ts ASC LIMIT 10"
    ).collect()
    return [{k.upper(): v for k, v in r.as_dict().items()} for r in rows]


@st.cache_data(ttl=60)
def load_domain_errors():
    s = get_active_session()
    rows = s.sql(
        f"SELECT domain_name, COUNT(*) AS error_count "
        f"FROM {FQN}.QUIZ_REVIEW_LOG GROUP BY domain_name ORDER BY error_count DESC"
    ).collect()
    return [{k.upper(): v for k, v in r.as_dict().items()} for r in rows]


def call_cortex(prompt):
    safe_prompt = prompt.replace("$$", "$ $")
    sql = f"SELECT AI_COMPLETE('{CORTEX_MODEL}', $${safe_prompt}$$)"
    try:
        rows = session.sql(sql).collect()
        if not rows:
            return None
        val = rows[0][0]
        if val is None or str(val).strip() == "":
            return None
        return str(val)
    except Exception as e:
        st.session_state["last_cortex_error"] = str(e)
        return None


def _strip_fences(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_cortex_json(response):
    if response is None:
        return None
    try:
        cleaned = _strip_fences(response)
        result = json.loads(cleaned)
        if isinstance(result, str):
            cleaned2 = _strip_fences(result)
            result = json.loads(cleaned2)
        if isinstance(result, dict):
            return result
        return None
    except Exception:
        pass
    try:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
    except Exception:
        pass
    return None


def _get_shown_texts():
    texts = []
    for item in st.session_state.get("round_history", []):
        t = item.get("question_text", "")
        if t:
            texts.append(t)
    q = st.session_state.get("question")
    if q and q.get("QUESTION_TEXT"):
        texts.append(q["QUESTION_TEXT"])
    return texts


def generate_ai_question(domain, difficulty):
    domain_id = domain["DOMAIN_ID"]
    domain_name = domain["DOMAIN_NAME"]
    key_facts = domain.get("KEY_FACTS") or ""
    topics = domain.get("TOPICS")

    if not key_facts and topics:
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except Exception:
                topics = [topics]
        reference = f"Domain: {domain_name}\nTopics: {', '.join(topics) if isinstance(topics, list) else str(topics)}"
    else:
        reference = key_facts

    shown = _get_shown_texts()
    no_repeat_block = ""
    if shown:
        recent = [t[:80] for t in shown[-10:]]
        no_repeat_block = "\n".join(f"- {t}" for t in recent)

    prompt = (
        f"=== DIFFICULTY: {difficulty.upper()} ===\n"
        f"{DIFFICULTY_GUIDE[difficulty]}\n\n"
        "This difficulty level is your PRIMARY constraint. The question MUST match this difficulty.\n"
        "Self-check: \"Would someone who only memorized definitions get this right?\" — if YES, make it harder.\n\n"
        f"Generate ONE SnowPro Core (COF-C02) multiple-choice question for the domain: {domain_name}\n\n"
        f"Reference material (use for factual accuracy only):\n{reference}\n\n"
    )
    if no_repeat_block:
        prompt += f"DO NOT generate any of these questions:\n{no_repeat_block}\n\n"

    prompt += (
        "Constraints:\n"
        "- question_text: max 150 characters\n"
        "- each option: max 80 characters\n"
        "- exactly 4 options (A, B, C, D)\n"
        "- single correct answer\n\n"
        "Return ONLY valid JSON with these keys:\n"
        "question_text, option_a, option_b, option_c, option_d, correct_answer (letter only, e.g. \"B\")\n"
        "No markdown fences. No extra text."
    )

    st.session_state["last_cortex_error"] = None
    st.session_state["last_ai_response"] = None
    st.session_state["last_ai_parse_error"] = None

    for attempt in range(3):
        raw = call_cortex(prompt)
        st.session_state["last_ai_response"] = raw
        if raw is None:
            continue
        parsed = parse_cortex_json(raw)
        if parsed is None:
            st.session_state["last_ai_parse_error"] = "JSON parse failed"
            continue
        if "why_correct" in parsed or "why_wrong" in parsed:
            st.session_state["last_ai_parse_error"] = "Got explanation instead of question"
            continue
        qt = parsed.get("question_text", "")
        oa = parsed.get("option_a", "")
        ob = parsed.get("option_b", "")
        ca = parsed.get("correct_answer", "")
        if not qt or not oa or not ob or not ca:
            st.session_state["last_ai_parse_error"] = "Missing required fields"
            continue

        q_dict = {
            "QUESTION_ID": None,
            "DOMAIN_ID": domain_id,
            "DOMAIN_NAME": domain_name,
            "DIFFICULTY": difficulty,
            "QUESTION_TEXT": qt,
            "IS_MULTI": False,
            "OPTION_A": oa,
            "OPTION_B": ob,
            "OPTION_C": parsed.get("option_c", ""),
            "OPTION_D": parsed.get("option_d", ""),
            "OPTION_E": parsed.get("option_e", ""),
            "CORRECT_ANSWER": ca.upper().strip(),
            "SOURCE": "AI_GENERATED",
        }

        try:
            session.sql(
                f"INSERT INTO {FQN}.QUIZ_QUESTIONS "
                "(domain_id, domain_name, difficulty, question_text, is_multi, "
                "option_a, option_b, option_c, option_d, option_e, correct_answer, source) "
                "VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12)",
                [
                    domain_id, domain_name, difficulty, qt, False,
                    oa, ob,
                    parsed.get("option_c", ""),
                    parsed.get("option_d", ""),
                    parsed.get("option_e", ""),
                    ca.upper().strip(), "AI_GENERATED",
                ],
            ).collect()
            rows = session.sql(
                f"SELECT question_id FROM {FQN}.QUIZ_QUESTIONS "
                "WHERE source='AI_GENERATED' AND domain_id=:1 AND question_text=:2 "
                "ORDER BY created_at DESC LIMIT 1",
                [domain_id, qt],
            ).collect()
            if rows:
                q_dict["QUESTION_ID"] = rows[0][0]
        except Exception as e:
            st.session_state["last_cortex_error"] = str(e)

        return q_dict

    return None


def get_question(domains, difficulty_filter, domain_filter, question_source):
    if domain_filter == "All":
        weights = [d["WEIGHT_PCT"] for d in domains]
        domain = random.choices(domains, weights=weights, k=1)[0]
    else:
        domain = next((d for d in domains if d["DOMAIN_NAME"] == domain_filter), domains[0])

    if difficulty_filter == "mixed":
        difficulty = random.choices(["easy", "medium", "hard"], weights=[30, 50, 20], k=1)[0]
    else:
        difficulty = difficulty_filter

    if question_source == "ai":
        q = generate_ai_question(domain, difficulty)
        return q

    if question_source == "mix" and random.random() < 0.2:
        q = generate_ai_question(domain, difficulty)
        if q is not None:
            return q

    return _query_db_question(domain, difficulty)


def _query_db_question(domain, difficulty):
    domain_id = domain["DOMAIN_ID"]
    shown_texts = _get_shown_texts()

    if shown_texts:
        placeholders = ", ".join(f":{i+2}" for i in range(len(shown_texts)))
        params = [domain_id] + shown_texts

        rows = session.sql(
            f"SELECT * FROM {FQN}.QUIZ_QUESTIONS "
            f"WHERE domain_id = :1 AND difficulty = :{len(params)+1} "
            f"AND question_text NOT IN ({placeholders}) "
            "ORDER BY RANDOM() LIMIT 1",
            params + [difficulty],
        ).collect()
        if rows:
            return {k.upper(): v for k, v in rows[0].as_dict().items()}

        rows = session.sql(
            f"SELECT * FROM {FQN}.QUIZ_QUESTIONS "
            f"WHERE domain_id = :1 "
            f"AND question_text NOT IN ({placeholders}) "
            "ORDER BY RANDOM() LIMIT 1",
            params,
        ).collect()
        if rows:
            return {k.upper(): v for k, v in rows[0].as_dict().items()}

    rows = session.sql(
        f"SELECT * FROM {FQN}.QUIZ_QUESTIONS WHERE domain_id = :1 ORDER BY RANDOM() LIMIT 1",
        [domain_id],
    ).collect()
    if rows:
        return {k.upper(): v for k, v in rows[0].as_dict().items()}
    return None


def render_home(domains):
    st.title("SnowPro Core Quiz")

    round_size = st.select_slider("Number of questions", options=[5, 10, 25, 50, 100], value=10)
    domain_names = ["All"] + [d["DOMAIN_NAME"] for d in domains]
    default_idx = domain_names.index(st.session_state["domain_filter"]) if st.session_state["domain_filter"] in domain_names else 0
    domain_filter = st.selectbox("Domain focus", domain_names, index=default_idx)

    difficulty = st.segmented_control(
        "Difficulty", ["mixed", "easy", "medium", "hard"],
        format_func=lambda x: x.capitalize(), default="mixed",
    )
    if difficulty is None:
        difficulty = "mixed"

    question_source = st.segmented_control(
        "Question source", ["mix", "db", "ai"],
        format_func=lambda x: SOURCE_LABELS.get(x, x), default="mix",
    )
    if question_source is None:
        question_source = "mix"

    use_explanations = st.toggle("Enable AI explanations", value=True)

    st.divider()
    if st.button("Start Round", type="primary", use_container_width=True):
        st.session_state["round_size"] = round_size
        st.session_state["domain_filter"] = domain_filter
        st.session_state["difficulty"] = difficulty
        st.session_state["question_source"] = question_source
        st.session_state["use_explanations"] = use_explanations
        st.session_state["q_index"] = 0
        st.session_state["correct_count"] = 0
        st.session_state["total_count"] = 0
        st.session_state["round_history"] = []
        st.session_state["answered"] = False
        st.session_state["selected"] = []
        st.session_state["explanation"] = None
        st.session_state["current_history_item"] = None
        q = get_question(domains, difficulty, domain_filter, question_source)
        st.session_state["question"] = q
        st.session_state["screen"] = "quiz"


def _build_option_texts(q):
    opts = {}
    for letter in ["A", "B", "C", "D", "E"]:
        val = q.get(f"OPTION_{letter}", "")
        if val:
            opts[letter] = val
    return opts


def render_quiz(domains):
    q = st.session_state.get("question")

    # Lazy load: Next handler sets question=None + rerun; we load here on the fresh cycle
    if q is None:
        with st.spinner("Loading question..."):
            q = get_question(
                domains,
                st.session_state["difficulty"],
                st.session_state["domain_filter"],
                st.session_state["question_source"],
            )
        if q is not None:
            st.session_state["question"] = q
            st.rerun()
        else:
            st.warning("Could not load a question.")
            if st.session_state.get("last_cortex_error"):
                st.code(st.session_state["last_cortex_error"])
            if st.session_state.get("last_ai_response"):
                st.code(st.session_state["last_ai_response"][:500])
            if st.session_state.get("last_ai_parse_error"):
                st.code(st.session_state["last_ai_parse_error"])
            if st.button("Retry", type="primary"):
                st.session_state["question"] = None
                st.session_state["last_cortex_error"] = None
                st.session_state["last_ai_response"] = None
                st.session_state["last_ai_parse_error"] = None
                st.rerun()
            return

    round_size = st.session_state["round_size"]
    q_index = st.session_state["q_index"]
    answered = st.session_state["answered"]

    st.progress(value=(q_index + 1) / round_size, text=f"Question {q_index + 1} of {round_size}")
    st.caption(f"{q.get('DOMAIN_NAME', '')} \u00b7 {q.get('DIFFICULTY', '')}")
    st.subheader(q.get("QUESTION_TEXT", ""))

    option_texts = _build_option_texts(q)
    options_list = [f"{letter}) {text}" for letter, text in option_texts.items()]
    correct_answer = q.get("CORRECT_ANSWER", "")
    correct_letters = [l.strip() for l in correct_answer.split(",")]
    is_multi = q.get("IS_MULTI", False) or len(correct_letters) > 1

    if is_multi:
        num_correct = len(correct_letters)
        st.caption(f"Select {num_correct} answers")
        for letter, text in option_texts.items():
            st.checkbox(f"{letter}) {text}", key=f"cb_{letter}", disabled=answered)
        selected = [letter for letter in option_texts if st.session_state.get(f"cb_{letter}", False)]
        can_submit = len(selected) == num_correct
    else:
        choice = st.radio("Select your answer", options_list, index=None, key=f"radio_{q_index}", disabled=answered)
        selected = []
        if choice:
            selected = [choice[0]]
        can_submit = len(selected) > 0

    if not answered:
        if st.button("Submit Answer", type="primary", use_container_width=True, disabled=not can_submit):
            st.session_state["selected"] = selected
            st.session_state["answered"] = True
            is_correct = sorted(selected) == sorted(correct_letters)
            if is_correct:
                st.session_state["correct_count"] += 1
            st.session_state["total_count"] += 1

            selected_labels = []
            for letter in selected:
                txt = option_texts.get(letter, "")
                selected_labels.append(f"{letter}) {txt}")

            history_item = {
                "question_id": q.get("QUESTION_ID"),
                "domain_id": q.get("DOMAIN_ID", ""),
                "domain_name": q.get("DOMAIN_NAME", ""),
                "difficulty": q.get("DIFFICULTY", ""),
                "question_text": q.get("QUESTION_TEXT", ""),
                "correct_answer": correct_answer,
                "option_texts": option_texts,
                "selected": ",".join(selected),
                "selected_labels": selected_labels,
                "is_correct": is_correct,
                "mnemonic": "",
                "doc_url": "",
            }
            st.session_state["round_history"] = st.session_state["round_history"] + [history_item]
            st.session_state["current_history_item"] = history_item
            st.session_state["explanation"] = None
            st.rerun()

    if answered:
        selected = st.session_state["selected"]
        is_correct = sorted(selected) == sorted(correct_letters)

        if is_correct:
            st.markdown("**Correct!**")
            sel_text = ", ".join(f"{l}) {option_texts.get(l, '')}" for l in selected)
            st.markdown(f"Your answer: {sel_text}")
        else:
            st.markdown("**Incorrect!**")
            corr_text = ", ".join(f"{l}) {option_texts.get(l, '')}" for l in correct_letters)
            st.markdown(f"Correct answer: {corr_text}")
            sel_text = ", ".join(f"{l}) {option_texts.get(l, '')}" for l in selected)
            st.markdown(f"Your answer: {sel_text}")

        if st.session_state["use_explanations"]:
            explanation = st.session_state.get("explanation")
            if explanation is None:
                with st.spinner("Generating explanation..."):
                    if is_correct:
                        exp_prompt = _build_doc_url_prompt(q, option_texts, correct_letters)
                    else:
                        exp_prompt = _build_explanation_prompt(q, option_texts, correct_letters, selected)
                    raw = call_cortex(exp_prompt)
                    parsed = parse_cortex_json(raw)
                    if parsed and isinstance(parsed, dict):
                        explanation = parsed
                        h = st.session_state.get("current_history_item")
                        if h:
                            h["mnemonic"] = parsed.get("mnemonic", "")
                            h["doc_url"] = parsed.get("doc_url", "")
                    else:
                        explanation = {}
                    st.session_state["explanation"] = explanation

            if isinstance(explanation, dict) and explanation:
                if not is_correct:
                    with st.expander("\u2728 AI Explanation", expanded=True):
                        wc = explanation.get("why_correct", "")
                        if wc:
                            st.markdown("**Why the correct answer is right:**")
                            st.write(wc)
                        ww = explanation.get("why_wrong", "")
                        if ww:
                            st.markdown("**Why the other options are wrong:**")
                            if isinstance(ww, dict):
                                for opt_letter, reason in ww.items():
                                    st.write(f"**{opt_letter})** {reason}")
                            else:
                                st.write(ww)
                        mn = explanation.get("mnemonic", "")
                        if mn:
                            st.info(f"\U0001f4a1 Remember: {mn}")

                doc_url = explanation.get("doc_url", "")
                if doc_url:
                    st.markdown(f"[\U0001f4d6 Snowflake Documentation]({doc_url})")

        nav_l, nav_r = st.columns([3, 1])
        is_last = q_index >= round_size - 1
        if is_last:
            with nav_r:
                if st.button("Finish", type="primary", use_container_width=True):
                    _write_back_results()
                    st.session_state["screen"] = "summary"
        else:
            with nav_r:
                if st.button("Next", use_container_width=True):
                    st.session_state["q_index"] += 1
                    st.session_state["answered"] = False
                    st.session_state["selected"] = []
                    st.session_state["explanation"] = None
                    st.session_state["current_history_item"] = None
                    st.session_state["question"] = None  # triggers lazy load on next rerun
                    for letter in ["A", "B", "C", "D", "E"]:
                        cb_key = f"cb_{letter}"
                        if cb_key in st.session_state:
                            del st.session_state[cb_key]
                    st.rerun()


def _build_doc_url_prompt(q, option_texts, correct_letters):
    options_block = "\n".join(f"{l}) {t}" for l, t in option_texts.items())
    return (
        f"Question: {q.get('QUESTION_TEXT', '')}\n"
        f"Options:\n{options_block}\n"
        f"Correct answer: {','.join(correct_letters)}\n\n"
        "Return ONLY valid JSON with one key:\n"
        "doc_url: exact URL to the most relevant Snowflake documentation page\n"
        "No markdown fences."
    )


def _build_explanation_prompt(q, option_texts, correct_letters, selected):
    options_block = "\n".join(f"{l}) {t}" for l, t in option_texts.items())
    all_letters = list(option_texts.keys())
    wrong_letters = [l for l in all_letters if l not in correct_letters]
    return (
        f"Question: {q.get('QUESTION_TEXT', '')}\n"
        f"Options:\n{options_block}\n"
        f"Correct answer: {','.join(correct_letters)}\n"
        f"Student selected: {','.join(selected)}\n"
        f"Wrong option letters: {','.join(wrong_letters)}\n\n"
        "Return ONLY valid JSON with these keys:\n"
        "- why_correct: 2-3 sentences explaining why the correct answer is right with Snowflake-specific detail\n"
        "- why_wrong: a JSON object where each key is a wrong option letter and value is one sentence why it is wrong\n"
        "- mnemonic: a memorable phrase or analogy to remember the correct answer\n"
        "- doc_url: exact URL to the most relevant Snowflake documentation page\n"
        "No markdown fences."
    )


def _write_back_results():
    history = st.session_state.get("round_history", [])
    for item in history:
        if not item["is_correct"]:
            correct_letters = [l.strip() for l in item["correct_answer"].split(",")]
            correct_full_parts = []
            for l in correct_letters:
                txt = item.get("option_texts", {}).get(l, "")
                correct_full_parts.append(f"{l}) {txt}")
            correct_full = ", ".join(correct_full_parts)
            session.sql(
                f"INSERT INTO {FQN}.QUIZ_REVIEW_LOG "
                "(domain_id, domain_name, difficulty, question_text, correct_answer, mnemonic, doc_url) "
                "VALUES (:1, :2, :3, :4, :5, :6, :7)",
                [
                    item["domain_id"],
                    item["domain_name"],
                    item["difficulty"],
                    item["question_text"],
                    correct_full,
                    item.get("mnemonic", ""),
                    item.get("doc_url", ""),
                ],
            ).collect()

    round_size = st.session_state["round_size"]
    correct_count = st.session_state["correct_count"]
    score_pct = (correct_count / round_size * 100) if round_size > 0 else 0
    session.sql(
        f"INSERT INTO {FQN}.QUIZ_SESSION_LOG "
        "(exam_code, round_size, correct_count, score_pct, domain_filter, difficulty) "
        "VALUES (:1, :2, :3, :4, :5, :6)",
        [EXAM_CODE, round_size, correct_count, score_pct, st.session_state["domain_filter"], st.session_state["difficulty"]],
    ).collect()


def render_summary():
    history = st.session_state.get("round_history", [])
    total = len(history)
    correct = sum(1 for h in history if h["is_correct"])
    pct = (correct / total * 100) if total > 0 else 0

    st.metric(label="Score", value=f"{correct}/{total}", delta=f"{pct:.0f}%")
    if pct >= 75:
        st.success("Passed \u2713 \u2014 above 75% threshold")
    else:
        st.warning(f"Not yet \u2014 {75 - pct:.1f}% to go")

    wrong = [h for h in history if not h["is_correct"]]
    for h in wrong:
        with st.expander(h["question_text"][:60] + "\u2026", expanded=False):
            correct_letters = [l.strip() for l in h["correct_answer"].split(",")]
            corr_text = ", ".join(f"{l}) {h.get('option_texts', {}).get(l, '')}" for l in correct_letters)
            st.markdown(f"**Correct answer:** {corr_text}")
            if h.get("mnemonic"):
                st.markdown(f"\U0001f4a1 {h['mnemonic']}")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Play Again"):
            st.session_state["q_index"] = 0
            st.session_state["correct_count"] = 0
            st.session_state["total_count"] = 0
            st.session_state["round_history"] = []
            st.session_state["answered"] = False
            st.session_state["selected"] = []
            st.session_state["explanation"] = None
            st.session_state["current_history_item"] = None
            q = get_question(
                load_domains(),
                st.session_state["difficulty"],
                st.session_state["domain_filter"],
                st.session_state["question_source"],
            )
            st.session_state["question"] = q
            st.session_state["screen"] = "quiz"
    with col_b:
        if st.button("New Round", type="primary"):
            st.session_state["screen"] = "home"


def render_review():
    s = get_active_session()

    date_rows = s.sql(f"SELECT MIN(logged_at) AS mn, MAX(logged_at) AS mx FROM {FQN}.QUIZ_REVIEW_LOG").collect()
    dr = {k.upper(): v for k, v in date_rows[0].as_dict().items()}
    if dr["MN"] is None:
        st.info("No review entries yet. Complete a quiz round to see wrong answers here.")
        return

    mn_raw = dr["MN"]
    mx_raw = dr["MX"]
    min_date = datetime.date(mn_raw.year, mn_raw.month, mn_raw.day)
    max_date = datetime.date(mx_raw.year, mx_raw.month, mx_raw.day)

    domain_rows = s.sql(f"SELECT DISTINCT domain_name FROM {FQN}.QUIZ_REVIEW_LOG WHERE domain_name IS NOT NULL ORDER BY domain_name").collect()
    domain_options = ["All"] + [r[0] for r in domain_rows]

    fcol1, fcol2 = st.columns([2, 2])
    with fcol1:
        domain_choice = st.selectbox("Domain", domain_options, key="review_domain")
    with fcol2:
        date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date, key="review_dates")

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_str = date_range[0].strftime("%Y-%m-%d")
        end_date = date_range[1] + datetime.timedelta(days=1)
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        start_str = min_date.strftime("%Y-%m-%d")
        end_str = (max_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    if domain_choice == "All":
        rows = s.sql(
            f"SELECT * FROM {FQN}.QUIZ_REVIEW_LOG "
            "WHERE logged_at >= :1 AND logged_at < :2 ORDER BY logged_at DESC",
            [start_str, end_str],
        ).collect()
    else:
        rows = s.sql(
            f"SELECT * FROM {FQN}.QUIZ_REVIEW_LOG "
            "WHERE domain_name = :1 AND logged_at >= :2 AND logged_at < :3 ORDER BY logged_at DESC",
            [domain_choice, start_str, end_str],
        ).collect()

    if not rows:
        st.info("No entries match the current filters.")
        return

    for r in rows:
        d = {k.upper(): v for k, v in r.as_dict().items()}
        logged = d.get("LOGGED_AT")
        date_str = ""
        if logged:
            date_str = f"{logged.year}-{logged.month:02d}-{logged.day:02d}"
        with st.container(border=True):
            st.caption(f"{d.get('DOMAIN_NAME', '')} \u00b7 {d.get('DIFFICULTY', '')} \u00b7 {date_str}")
            st.markdown(d.get("QUESTION_TEXT", ""))
            st.markdown(f"**Correct answer:** {d.get('CORRECT_ANSWER', '')}")
            mn = d.get("MNEMONIC", "")
            if mn:
                st.markdown(f"\U0001f4a1 {mn}")
            doc = d.get("DOC_URL", "")
            if doc:
                st.markdown(f"[\U0001f4d6 Documentation]({doc})")


def render_dashboard(domains):
    sessions, avg_score, total_questions = load_session_stats()
    if sessions == 0:
        st.info("Complete a quiz round to see your progress here.")
        return

    # Row 1 — key metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions", sessions)
    c2.metric("Avg Score", f"{avg_score:.1f}%", delta=f"{avg_score - 75:+.1f}% vs pass threshold")
    c3.metric("Questions Practiced", total_questions)

    st.divider()

    # Row 2 — score trend line chart, full width
    recent = load_recent_sessions()
    if recent:
        df = pd.DataFrame(recent)
        df.columns = [c.lower() for c in df.columns]
        line = alt.Chart(df).mark_line(point=True, color="#29b5e8").encode(
            x=alt.X("session_num:O", title="Session", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("score_pct:Q", scale=alt.Scale(domain=[0, 100]), title="Score %"),
        )
        rule = alt.Chart(pd.DataFrame({"y": [75]})).mark_rule(
            color="red", strokeDash=[4, 4]
        ).encode(y="y:Q")
        st.altair_chart((line + rule).properties(title="Score per Session"), use_container_width=True)

    st.divider()

    # Row 3 — readiness + errors side by side
    col_left, col_right = st.columns(2)

    with col_left:
        st.metric("Readiness Score", f"{avg_score:.1f}%", delta=f"{avg_score - 75:+.1f}% vs pass threshold")
        st.progress(min(avg_score / 100, 1.0))

    with col_right:
        error_data = load_domain_errors()
        if error_data:
            df_err = pd.DataFrame(error_data)
            df_err.columns = [c.lower() for c in df_err.columns]
            df_err["error_count"] = df_err["error_count"].astype(int)
            chart = alt.Chart(df_err).mark_bar().encode(
                x=alt.X("error_count:Q", title="Errors", axis=alt.Axis(format="d")),
                y=alt.Y("domain_name:N", sort="-x", title=None),
                color=alt.value("#EF5350"),
            )
            st.altair_chart(chart.properties(title="Errors by Domain"), use_container_width=True)
        else:
            st.caption("No errors recorded yet.")


init_session_state()
domains = load_domains()

tab_quiz, tab_review, tab_progress = st.tabs(["Quiz", "Review", "Progress"])
with tab_quiz:
    screen = st.session_state["screen"]
    if screen == "home":
        render_home(domains)
    elif screen == "quiz":
        render_quiz(domains)
    elif screen == "summary":
        render_summary()
with tab_review:
    render_review()
with tab_progress:
    render_dashboard(domains)
