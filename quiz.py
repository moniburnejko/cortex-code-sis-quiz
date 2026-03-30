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
FQS = f"{DATABASE}.{SCHEMA}"
CORTEX_MODEL = "claude-sonnet-4-5"
EXAM_CODE = "COF-C02"
OPTION_LETTERS = ["A", "B", "C", "D", "E"]
OPTION_KEYS = ["OPTION_A", "OPTION_B", "OPTION_C", "OPTION_D", "OPTION_E"]
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
    rows = s.sql(f"SELECT domain_id, domain_name, weight_pct, topics, key_facts FROM {FQS}.EXAM_DOMAINS ORDER BY domain_id").collect()
    result = []
    for r in rows:
        d = {k.upper(): v for k, v in r.as_dict().items()}
        result.append(d)
    return result


@st.cache_data(ttl=60)
def load_session_stats():
    s = get_active_session()
    rows = s.sql(f"SELECT COUNT(*) AS sessions, AVG(score_pct) AS avg_score, SUM(round_size) AS total_questions FROM {FQS}.QUIZ_SESSION_LOG").collect()
    d = {k.upper(): v for k, v in rows[0].as_dict().items()}
    return d


@st.cache_data(ttl=60)
def load_recent_sessions():
    s = get_active_session()
    rows = s.sql(f"""SELECT ROW_NUMBER() OVER (ORDER BY session_ts) AS session_num,
        session_ts, score_pct, round_size
        FROM {FQS}.QUIZ_SESSION_LOG ORDER BY session_ts ASC LIMIT 10""").collect()
    data = []
    for r in rows:
        d = {k.upper(): v for k, v in r.as_dict().items()}
        data.append(d)
    return data


@st.cache_data(ttl=60)
def load_domain_errors():
    s = get_active_session()
    rows = s.sql(f"SELECT domain_name, COUNT(*) AS error_count FROM {FQS}.QUIZ_REVIEW_LOG GROUP BY domain_name ORDER BY error_count DESC").collect()
    data = []
    for r in rows:
        d = {k.upper(): v for k, v in r.as_dict().items()}
        data.append(d)
    return data


def call_cortex(prompt):
    try:
        safe_prompt = prompt.replace("$$", "$ $")
        sql = f"SELECT AI_COMPLETE('{CORTEX_MODEL}', $${safe_prompt}$$) AS result"
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
    if not isinstance(text, str):
        return text
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def parse_cortex_json(response):
    if response is None:
        return None
    try:
        text = _strip_fences(str(response))
        result = json.loads(text)
        if isinstance(result, str):
            result = json.loads(_strip_fences(result))
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    try:
        m = re.search(r"\{.*\}", str(response), re.DOTALL)
        if m:
            result = json.loads(m.group(0))
            if isinstance(result, dict):
                return result
    except Exception:
        pass
    st.session_state["last_ai_parse_error"] = f"Failed to parse: {str(response)[:200]}"
    return None


def generate_ai_question(domain, difficulty):
    domain_id = domain["DOMAIN_ID"]
    domain_name = domain["DOMAIN_NAME"]
    key_facts = domain.get("KEY_FACTS") or ""
    topics = domain.get("TOPICS")
    topics_str = ""
    if topics:
        if isinstance(topics, str):
            try:
                topics_list = json.loads(topics)
            except Exception:
                topics_list = []
        elif isinstance(topics, list):
            topics_list = topics
        else:
            topics_list = []
        if topics_list:
            topics_str = "\nTopics for this domain: " + ", ".join(str(t) for t in topics_list)

    try:
        recent_rows = session.sql(
            f"SELECT question_text FROM {FQS}.QUIZ_QUESTIONS WHERE source = 'AI_GENERATED' AND domain_id = :1 ORDER BY created_at DESC LIMIT 20",
            [domain_id]
        ).collect()
        recent_texts = [str(r[0])[:80] for r in recent_rows]
    except Exception:
        recent_texts = []

    session_texts = [h["question_text"][:80] for h in st.session_state.get("round_history", [])]
    all_recent = list(set(recent_texts + session_texts))[:30]
    no_repeat_block = "\n".join(f"- {t}" for t in all_recent) if all_recent else "(none)"

    if key_facts and key_facts.strip():
        grounding = f"""Ground your question ONLY in the following verified facts from the official study guide:

{key_facts}

Based ONLY on the facts above, generate a {difficulty} multiple-choice question for domain: {domain_name}."""
    else:
        grounding = f"""Generate a {difficulty} multiple-choice question for domain: {domain_name}.{topics_str}"""

    prompt = f"""You are a SnowPro Core COF-C02 exam question writer.
{grounding}
{topics_str}
Rules:
- Every answer option must reflect actual Snowflake behavior documented in the facts above
- The correct answer must be explicitly supported by one of the facts above
- Wrong options should represent common misconceptions, not invented behaviors
- Do not include specific numbers, limits, or behaviors not mentioned in the facts above
- Vary the topic area - prioritize topics not covered recently
- Do NOT repeat these recent questions:
{no_repeat_block}
- question_text: max 150 characters
- each option: max 80 characters
- respond with ONLY the JSON object, no markdown fences, no extra text

Return ONLY a valid JSON object with these exact keys:
"question_text", "option_a", "option_b", "option_c", "option_d", "correct_answer", "is_multi"
correct_answer is a letter like "A" or "A,C" for multi-select. is_multi is true/false."""

    for attempt in range(3):
        st.session_state["last_cortex_error"] = None
        st.session_state["last_ai_response"] = None
        st.session_state["last_ai_parse_error"] = None

        raw = call_cortex(prompt)
        st.session_state["last_ai_response"] = raw
        if raw is None:
            continue

        parsed = parse_cortex_json(raw)
        if not isinstance(parsed, dict):
            continue

        if "why_correct" in parsed or "why_wrong" in parsed:
            continue

        qt = parsed.get("question_text", "")
        oa = parsed.get("option_a", "")
        ob = parsed.get("option_b", "")
        ca = parsed.get("correct_answer", "")
        if not all([qt, oa, ob, ca]):
            continue

        is_multi = parsed.get("is_multi", False)
        oc = parsed.get("option_c", "")
        od = parsed.get("option_d", "")
        oe = parsed.get("option_e")

        q = {
            "QUESTION_ID": None,
            "DOMAIN_ID": domain_id,
            "DOMAIN_NAME": domain_name,
            "DIFFICULTY": difficulty,
            "QUESTION_TEXT": qt,
            "IS_MULTI": bool(is_multi),
            "OPTION_A": oa,
            "OPTION_B": ob,
            "OPTION_C": oc if oc else None,
            "OPTION_D": od if od else None,
            "OPTION_E": oe if oe else None,
            "CORRECT_ANSWER": ca.upper().replace(" ", ""),
            "SOURCE": "AI_GENERATED",
        }

        try:
            session.sql(
                f"""INSERT INTO {FQS}.QUIZ_QUESTIONS
                (domain_id, domain_name, difficulty, question_text, is_multi, option_a, option_b, option_c, option_d, option_e, correct_answer, source)
                VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12)""",
                [domain_id, domain_name, difficulty, qt, bool(is_multi), oa, ob, oc or None, od or None, oe or None, q["CORRECT_ANSWER"], "AI_GENERATED"]
            ).collect()
            id_rows = session.sql(
                f"SELECT question_id FROM {FQS}.QUIZ_QUESTIONS WHERE source='AI_GENERATED' AND domain_id=:1 AND question_text=:2 ORDER BY created_at DESC LIMIT 1",
                [domain_id, qt]
            ).collect()
            if id_rows:
                q["QUESTION_ID"] = id_rows[0][0]
        except Exception as e:
            st.session_state["last_cortex_error"] = str(e)

        return q

    return None


def get_question(domains, difficulty_filter, domain_filter, question_source):
    if domain_filter == "All":
        weights = [d["WEIGHT_PCT"] for d in domains]
        domain = random.choices(domains, weights=weights, k=1)[0]
    else:
        domain = next((d for d in domains if d["DOMAIN_NAME"] == domain_filter), domains[0])

    if difficulty_filter == "mixed":
        r = random.random()
        if r < 0.3:
            diff = "easy"
        elif r < 0.8:
            diff = "medium"
        else:
            diff = "hard"
    else:
        diff = difficulty_filter

    if question_source == "ai":
        with st.spinner("Generating question..."):
            q = generate_ai_question(domain, diff)
        return q

    if question_source == "mix" and random.random() < 0.2:
        with st.spinner("Generating question..."):
            q = generate_ai_question(domain, diff)
        if q is not None:
            return q

    seen_ids = [h["question_id"] for h in st.session_state.get("round_history", []) if h.get("question_id") is not None]

    for fallback in range(3):
        if fallback == 0:
            rows = session.sql(
                f"SELECT * FROM {FQS}.QUIZ_QUESTIONS WHERE domain_id = :1 AND difficulty = :2",
                [domain["DOMAIN_ID"], diff]
            ).collect()
        elif fallback == 1:
            rows = session.sql(
                f"SELECT * FROM {FQS}.QUIZ_QUESTIONS WHERE domain_id = :1",
                [domain["DOMAIN_ID"]]
            ).collect()
        else:
            rows = session.sql(f"SELECT * FROM {FQS}.QUIZ_QUESTIONS").collect()

        if not rows:
            continue

        candidates = []
        for r in rows:
            d = {k.upper(): v for k, v in r.as_dict().items()}
            if d.get("QUESTION_ID") not in seen_ids:
                candidates.append(d)

        if not candidates:
            candidates = [{k.upper(): v for k, v in r.as_dict().items()} for r in rows]

        if candidates:
            return random.choice(candidates)

    return None


def render_home(domains):
    st.title("SnowPro Core Quiz")
    round_size = st.select_slider("Number of questions", options=[5, 10, 25, 50, 100], value=10)

    domain_names = ["All"] + [d["DOMAIN_NAME"] for d in domains]
    default_idx = domain_names.index(st.session_state["domain_filter"]) if st.session_state["domain_filter"] in domain_names else 0
    domain_filter = st.selectbox("Domain focus", domain_names, index=default_idx)

    difficulty = st.segmented_control("Difficulty", options=["mixed", "easy", "medium", "hard"], format_func=lambda x: x.capitalize(), default="mixed")
    if difficulty is None:
        difficulty = "mixed"

    question_source = st.segmented_control("Question source", options=["mix", "db", "ai"], format_func=lambda x: SOURCE_LABELS.get(x, x), default="mix")
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
        st.session_state["round_history"] = []
        st.session_state["correct_count"] = 0
        st.session_state["total_count"] = 0
        st.session_state["answered"] = False
        st.session_state["selected"] = []
        st.session_state["explanation"] = None
        st.session_state["current_history_item"] = None
        q = get_question(domains, difficulty, domain_filter, question_source)
        st.session_state["question"] = q
        st.session_state["screen"] = "quiz"


def render_quiz(domains):
    q = st.session_state.get("question")
    if q is None:
        st.warning("Could not load a question.")
        err = st.session_state.get("last_cortex_error")
        raw = st.session_state.get("last_ai_response")
        parse_err = st.session_state.get("last_ai_parse_error")
        if err:
            st.code(f"Cortex error: {err}")
        if raw:
            st.code(f"Raw response: {str(raw)[:500]}")
        if parse_err:
            st.code(f"Parse error: {parse_err}")
        if st.button("Retry", type="primary"):
            st.session_state["question"] = None
            st.session_state["last_cortex_error"] = None
            st.session_state["last_ai_response"] = None
            st.session_state["last_ai_parse_error"] = None
            q = get_question(domains, st.session_state["difficulty"], st.session_state["domain_filter"], st.session_state["question_source"])
            st.session_state["question"] = q
            st.rerun()
        return

    q_index = st.session_state["q_index"]
    round_size = st.session_state["round_size"]
    answered = st.session_state["answered"]

    st.progress(value=(q_index + 1) / round_size, text=f"Question {q_index + 1} of {round_size}")

    domain_name = q.get("DOMAIN_NAME", "")
    difficulty = q.get("DIFFICULTY", "")
    question_text = q.get("QUESTION_TEXT", "")
    is_multi = q.get("IS_MULTI", False)
    correct_answer = q.get("CORRECT_ANSWER", "")
    correct_letters = [l.strip() for l in correct_answer.split(",")]

    options = {}
    for letter, key in zip(OPTION_LETTERS, OPTION_KEYS):
        val = q.get(key)
        if val:
            options[letter] = val

    st.caption(f"{domain_name} \u00b7 {difficulty}")
    st.subheader(question_text)

    if not is_multi:
        option_list = [f"{l}) {t}" for l, t in options.items()]
        radio_key = f"radio_{q_index}"
        selected_radio = st.radio("Select your answer", option_list, index=None, key=radio_key, disabled=answered)
        selected_letters = []
        if selected_radio:
            selected_letters = [selected_radio.split(")")[0]]
    else:
        selected_letters = []
        for letter, text in options.items():
            cb_key = f"cb_{letter}"
            checked = st.checkbox(f"{letter}) {text}", key=cb_key, disabled=answered)
            if checked:
                selected_letters.append(letter)

    if not answered:
        can_submit = len(selected_letters) > 0
        if is_multi:
            can_submit = len(selected_letters) == len(correct_letters)
        if st.button("Submit Answer", type="primary", use_container_width=True, disabled=not can_submit):
            is_correct = sorted(selected_letters) == sorted(correct_letters)
            st.session_state["answered"] = True
            st.session_state["selected"] = selected_letters
            if is_correct:
                st.session_state["correct_count"] += 1
            st.session_state["total_count"] += 1

            selected_labels = [f"{l}) {options.get(l, '')}" for l in selected_letters]
            history_item = {
                "question_id": q.get("QUESTION_ID"),
                "domain_id": q.get("DOMAIN_ID", ""),
                "domain_name": domain_name,
                "difficulty": difficulty,
                "question_text": question_text,
                "correct_answer": correct_answer,
                "option_texts": dict(options),
                "selected": ",".join(selected_letters),
                "selected_labels": selected_labels,
                "is_correct": is_correct,
                "mnemonic": "",
                "doc_url": "",
            }
            st.session_state["round_history"].append(history_item)
            st.session_state["current_history_item"] = history_item
            st.session_state["explanation"] = None
            st.rerun()

    if answered:
        sel = st.session_state["selected"]
        hist = st.session_state.get("current_history_item", {})
        is_correct = hist.get("is_correct", False)
        opt_texts = hist.get("option_texts", options)

        if is_correct:
            st.markdown("**Correct!**")
            sel_text = ", ".join(f"{l}) {opt_texts.get(l, '')}" for l in sel)
            st.markdown(f"Your answer: {sel_text}")
        else:
            correct_text = ", ".join(f"{l}) {opt_texts.get(l, '')}" for l in correct_letters)
            sel_text = ", ".join(f"{l}) {opt_texts.get(l, '')}" for l in sel)
            st.markdown("**Incorrect!**")
            st.markdown(f"Correct answer: {correct_text}")
            st.markdown(f"Your answer: {sel_text}")

        if st.session_state.get("use_explanations"):
            expl = st.session_state.get("explanation")

            if expl is None:
                with st.spinner("Generating explanation..."):
                    if is_correct:
                        expl_prompt = f"""You are a Snowflake certification tutor.
Question: {question_text}
Options: {', '.join(f'{l}) {opt_texts.get(l, "")}' for l in options)}
Correct answer: {correct_answer}
The student answered correctly.
Return ONLY valid JSON with this key:
"doc_url": exact URL to the most relevant Snowflake documentation page"""
                    else:
                        wrong_letters = [l for l in options if l not in correct_letters]
                        expl_prompt = f"""You are a Snowflake certification tutor.
Question: {question_text}
Options: {', '.join(f'{l}) {opt_texts.get(l, "")}' for l in options)}
Correct answer: {correct_answer}
Student selected: {','.join(sel)}
Wrong option letters: {','.join(wrong_letters)}
Return ONLY valid JSON with these keys:
"why_correct": 2-3 sentences on why the correct answer is right with Snowflake technical detail
"why_wrong": a dict where each key is a wrong option letter ({','.join(wrong_letters)}) and value is one sentence explaining why that option is incorrect
"mnemonic": a memorable phrase or acronym to remember the correct answer
"doc_url": exact URL to the most relevant Snowflake documentation page"""

                    raw = call_cortex(expl_prompt)
                    parsed = parse_cortex_json(raw)
                    if isinstance(parsed, dict) and parsed:
                        st.session_state["explanation"] = parsed
                        if hist and parsed.get("mnemonic"):
                            hist["mnemonic"] = parsed["mnemonic"]
                        if hist and parsed.get("doc_url"):
                            hist["doc_url"] = parsed["doc_url"]
                    else:
                        st.session_state["explanation"] = {}

            expl = st.session_state.get("explanation")
            if isinstance(expl, dict) and expl:
                if not is_correct and (expl.get("why_correct") or expl.get("why_wrong") or expl.get("mnemonic")):
                    with st.expander("\u2728 AI Explanation", expanded=True):
                        if expl.get("why_correct"):
                            st.markdown("**Why this is correct:**")
                            st.write(expl["why_correct"])
                        if expl.get("why_wrong"):
                            st.markdown("**Why other options are wrong:**")
                            ww = expl["why_wrong"]
                            if isinstance(ww, dict):
                                for wl, reason in ww.items():
                                    st.write(f"**{wl})** {reason}")
                            else:
                                st.write(ww)
                        if expl.get("mnemonic"):
                            st.info(f"\U0001f4a1 Remember: {expl['mnemonic']}")

                if expl.get("doc_url"):
                    st.markdown(f"[\U0001f4d6 Snowflake Documentation]({expl['doc_url']})")

        nav_l, nav_r = st.columns([3, 1])
        is_last = q_index >= round_size - 1

        if is_last:
            if nav_r.button("Finish", type="primary", use_container_width=True):
                for h in st.session_state["round_history"]:
                    if not h["is_correct"]:
                        cl = [l.strip() for l in h["correct_answer"].split(",")]
                        correct_full = ", ".join(f"{l}) {h['option_texts'].get(l, '')}" for l in cl)
                        session.sql(
                            f"INSERT INTO {FQS}.QUIZ_REVIEW_LOG (domain_id, domain_name, difficulty, question_text, correct_answer, mnemonic, doc_url) VALUES (:1, :2, :3, :4, :5, :6, :7)",
                            [h["domain_id"], h["domain_name"], h["difficulty"], h["question_text"], correct_full, h.get("mnemonic", ""), h.get("doc_url", "")]
                        ).collect()

                rc = st.session_state["correct_count"]
                rs = st.session_state["round_size"]
                pct = rc / rs * 100 if rs > 0 else 0
                session.sql(
                    f"INSERT INTO {FQS}.QUIZ_SESSION_LOG (exam_code, round_size, correct_count, score_pct, domain_filter, difficulty) VALUES (:1, :2, :3, :4, :5, :6)",
                    [EXAM_CODE, rs, rc, pct, st.session_state["domain_filter"], st.session_state["difficulty"]]
                ).collect()

                load_session_stats.clear()
                load_recent_sessions.clear()
                load_domain_errors.clear()
                st.session_state["screen"] = "summary"
        else:
            if nav_r.button("Next", use_container_width=True):
                for letter in OPTION_LETTERS:
                    cb_key = f"cb_{letter}"
                    if cb_key in st.session_state:
                        del st.session_state[cb_key]
                st.session_state["answered"] = False
                st.session_state["selected"] = []
                st.session_state["explanation"] = None
                st.session_state["current_history_item"] = None
                st.session_state["q_index"] += 1
                q = get_question(domains, st.session_state["difficulty"], st.session_state["domain_filter"], st.session_state["question_source"])
                st.session_state["question"] = q


def render_summary():
    correct = st.session_state["correct_count"]
    total = st.session_state["round_size"]
    pct = correct / total * 100 if total > 0 else 0

    st.metric(label="Score", value=f"{correct}/{total}", delta=f"{pct:.0f}%")

    if pct >= 75:
        st.success("Passed \u2713 \u2014 above 75% threshold")
    else:
        st.warning(f"Not yet \u2014 {75 - pct:.1f}% to go")

    wrong = [h for h in st.session_state["round_history"] if not h["is_correct"]]
    for h in wrong:
        with st.expander(h["question_text"][:60] + "\u2026", expanded=False):
            cl = [l.strip() for l in h["correct_answer"].split(",")]
            correct_full = ", ".join(f"{l}) {h['option_texts'].get(l, '')}" for l in cl)
            st.markdown(f"**Correct answer:** {correct_full}")
            if h.get("mnemonic"):
                st.markdown(f"\U0001f4a1 {h['mnemonic']}")

    col_a, col_b = st.columns(2)
    if col_a.button("Play Again"):
        st.session_state["q_index"] = 0
        st.session_state["round_history"] = []
        st.session_state["correct_count"] = 0
        st.session_state["total_count"] = 0
        st.session_state["answered"] = False
        st.session_state["selected"] = []
        st.session_state["explanation"] = None
        st.session_state["current_history_item"] = None
        q = get_question(domains, st.session_state["difficulty"], st.session_state["domain_filter"], st.session_state["question_source"])
        st.session_state["question"] = q
        st.session_state["screen"] = "quiz"
    if col_b.button("New Round", type="primary"):
        st.session_state["screen"] = "home"
        st.session_state["answered"] = False
        st.session_state["selected"] = []
        st.session_state["explanation"] = None
        st.session_state["current_history_item"] = None


def render_review():
    s = get_active_session()

    date_rows = s.sql(f"SELECT MIN(logged_at) AS mn, MAX(logged_at) AS mx FROM {FQS}.QUIZ_REVIEW_LOG").collect()
    d0 = {k.upper(): v for k, v in date_rows[0].as_dict().items()}
    if d0["MN"] is None:
        st.info("No review entries yet. Complete a quiz round with wrong answers to see them here.")
        return

    min_raw = d0["MN"]
    max_raw = d0["MX"]
    min_date = datetime.date(min_raw.year, min_raw.month, min_raw.day)
    max_date = datetime.date(max_raw.year, max_raw.month, max_raw.day)

    domain_rows = s.sql(f"SELECT DISTINCT domain_name FROM {FQS}.QUIZ_REVIEW_LOG WHERE domain_name IS NOT NULL ORDER BY domain_name").collect()
    domain_list = ["All"] + [str(r[0]) for r in domain_rows]

    fcol1, fcol2 = st.columns([2, 2])
    with fcol1:
        rev_domain = st.selectbox("Domain", domain_list, key="review_domain")
    with fcol2:
        date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date, key="review_dates")

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_str = date_range[0].strftime("%Y-%m-%d")
        end_date = date_range[1] + datetime.timedelta(days=1)
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        start_str = min_date.strftime("%Y-%m-%d")
        end_str = (max_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    if rev_domain == "All":
        rows = s.sql(
            f"SELECT * FROM {FQS}.QUIZ_REVIEW_LOG WHERE logged_at >= :1 AND logged_at < :2 ORDER BY logged_at DESC",
            [start_str, end_str]
        ).collect()
    else:
        rows = s.sql(
            f"SELECT * FROM {FQS}.QUIZ_REVIEW_LOG WHERE domain_name = :1 AND logged_at >= :2 AND logged_at < :3 ORDER BY logged_at DESC",
            [rev_domain, start_str, end_str]
        ).collect()

    if not rows:
        st.info("No entries match the selected filters.")
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
            mnemonic = d.get("MNEMONIC", "")
            if mnemonic and str(mnemonic).strip():
                st.markdown(f"\U0001f4a1 {mnemonic}")
            doc_url = d.get("DOC_URL", "")
            if doc_url and str(doc_url).strip():
                st.markdown(f"[\U0001f4d6 Documentation]({doc_url})")


def render_dashboard(domains):
    stats = load_session_stats()
    sessions = stats.get("SESSIONS", 0) or 0
    if sessions == 0:
        st.info("Complete a quiz round to see your progress here.")
        return

    avg_score = float(stats.get("AVG_SCORE", 0) or 0)
    total_questions = int(stats.get("TOTAL_QUESTIONS", 0) or 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions", sessions)
    c2.metric("Avg Score", f"{avg_score:.1f}%", delta=f"{avg_score - 75:+.1f}% vs pass")
    c3.metric("Questions Practiced", total_questions)

    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**Readiness Score**")
        st.progress(avg_score / 100)
        st.caption(f"{avg_score:.1f}% \u2014 need 75% to pass ({avg_score - 75:+.1f}%)")

    with col_right:
        recent = load_recent_sessions()
        if recent:
            df = pd.DataFrame(recent)
            df.columns = [c.lower() for c in df.columns]
            bars = alt.Chart(df).mark_bar().encode(
                x=alt.X("session_num:O", title="Session", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("score_pct:Q", scale=alt.Scale(domain=[0, 100]), title="Score %"),
                color=alt.condition(
                    alt.datum.score_pct >= 75,
                    alt.value("#4CAF50"),
                    alt.value("#2196F3")
                )
            )
            rule = alt.Chart(pd.DataFrame({"y": [75]})).mark_rule(
                color="red", strokeDash=[4, 4]
            ).encode(y="y:Q")
            st.altair_chart(bars + rule, use_container_width=True)
        else:
            st.caption("No sessions yet.")

    st.divider()

    err_col, weak_col = st.columns(2)
    error_data = load_domain_errors()

    with err_col:
        if error_data:
            df_err = pd.DataFrame(error_data)
            df_err.columns = [c.lower() for c in df_err.columns]
            chart = alt.Chart(df_err).mark_bar().encode(
                x=alt.X("error_count:Q", title="Errors"),
                y=alt.Y("domain_name:N", sort="-x", title=None),
                color=alt.value("#EF5350")
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No errors recorded yet.")

    with weak_col:
        st.markdown("**Weak Spots**")
        if error_data:
            top3 = error_data[:3]
            for item in top3:
                dn = item["DOMAIN_NAME"]
                cnt = item["ERROR_COUNT"]
                st.markdown(f"**{dn}** \u2014 {cnt} errors")
                if st.button("Practice", key=f"practice_{dn}"):
                    st.session_state["domain_filter"] = dn
                    st.session_state["screen"] = "home"
        else:
            st.caption("No weak spots identified yet.")


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
