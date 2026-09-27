"""The DocuMind landing page, which is also the whole search workspace.

Idle: logo ring, greeting, search bar, settings. After a search or upload the same page
switches to a conversation, with the search bar and settings staying below it.
"""
import html

import streamlit as st

from ui.brand import LOGO_CSS, greeting, mark
from ui.workflow import ingest, refresh, summary

DASHBOARD_LINK = "?view=app"

# Note: st.html drops any <style> whose text contains tag-like "<x" sequences,
# so keep "<" out of the CSS entirely.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Inter+Tight:wght@400;500;600&display=swap');

:root {
    --bg: #E3D9CC;
    --ink: #3F2F1E;
    --soft: #7A6C5D;
    --line: rgba(63, 47, 30, 0.18);
    --orange: #FF4A1C;
    --ease: cubic-bezier(.2, .75, .2, 1);
}

/* strip Streamlit chrome so the page is full-bleed */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stAppViewContainer"], .stApp { background: var(--bg); }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 100% !important; padding: 0 0 40px !important; }

.lp, .lp * { box-sizing: border-box; }
.lp { font-family: 'Inter', system-ui, sans-serif; color: var(--ink); }
.lp a { color: inherit; text-decoration: none; }
.lp ::selection { background: var(--orange); color: var(--bg); }

.fade { animation: fade 1s var(--ease) both; animation-delay: var(--d, 0s); }
@keyframes fade { from { opacity: 0; transform: translateY(10px); } }

/* ---------- top bar ---------- */
.top { display: flex; flex-direction: column; align-items: center; padding: 18px 28px 0; }
.topbar { width: 100%; display: flex; justify-content: space-between; align-items: center; }
.brand { font-family: 'Inter Tight', sans-serif; font-weight: 600; font-size: 15px; letter-spacing: .22em; }
.links { display: flex; gap: 8px; }
.ghost {
    padding: 9px 16px; border-radius: 999px; font-size: 13.5px; font-weight: 500;
    border: 1px solid var(--line); transition: all .3s var(--ease);
}
.ghost:hover { border-color: var(--orange); color: var(--orange); }

/* ---------- idle hero ---------- */
.stage { width: 100%; height: 310px; display: grid; place-items: center; }
.hello {
    display: flex; align-items: center; justify-content: center; gap: 14px; text-align: center;
    font-family: 'Inter Tight', sans-serif; font-size: clamp(24px, 2.5vw, 32px); font-weight: 400;
    letter-spacing: -0.02em; margin: 4px 0 6px; padding: 0 16px; color: var(--ink);
}
.captions { display: flex; justify-content: space-between; padding: 40px 28px 0; font-size: 14px; line-height: 1.3; }
.captions .r { text-align: right; }

/* ---------- centred column shared by the thread, documents, input and settings ---------- */
.st-key-thread, .st-key-docs, .st-key-land_ask, .st-key-land_settings {
    max-width: 900px; width: calc(100% - 32px); margin-left: auto; margin-right: auto;
}
.st-key-thread { padding-top: 26px; }

.ask-q { display: flex; justify-content: flex-end; animation: fade .6s var(--ease) both; }
.ask-q span {
    max-width: 78%; background: #FFFFFF; border-radius: 22px; padding: 11px 18px; font-size: 16px; line-height: 1.5;
    box-shadow: 0 4px 18px rgba(63, 47, 30, .06); color: var(--ink); font-family: 'Inter', sans-serif;
}
.ask-q.file span { background: transparent; box-shadow: none; border: 1px dashed var(--line); color: var(--soft); font-size: 14px; }
.st-key-thread [data-testid="stChatMessage"] { background: transparent !important; padding: 10px 0 !important; animation: fade .6s var(--ease) both; }

/* documents strip */
.docs { display: flex; flex-wrap: wrap; gap: 8px; }
.doc {
    position: relative; overflow: hidden; display: inline-flex; align-items: center; gap: 8px;
    font-size: 12.5px; padding: 7px 12px; border-radius: 999px; border: 1px solid var(--line);
    background: rgba(255, 255, 255, .35); color: var(--ink); font-family: 'Inter', sans-serif; max-width: 100%;
}
.doc b { font-weight: 500; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc small { color: var(--soft); font-size: 12px; white-space: nowrap; }
.doc i { width: 7px; height: 7px; border-radius: 50%; flex: none; background: #7BAA6B; }
.doc.indexing i { background: var(--orange); animation: blink 1.2s ease-in-out infinite; }
.doc.failed i { background: #B3261E; }
.doc .bar { position: absolute; left: 0; bottom: 0; height: 2px; background: var(--orange); transition: width .6s var(--ease); }
@keyframes blink { 50% { opacity: .25; } }

/* the search bar: the real Streamlit chat input, styled as a pill (question or PDF upload) */
.st-key-land_ask { margin-top: 6px; }
.st-key-land_ask [data-testid="stChatInput"] > div {
    background: #FFFFFF !important; border-radius: 36px !important; padding: 14px 14px 14px 18px !important;
    border: 1px solid rgba(63, 47, 30, .08) !important; box-shadow: 0 10px 40px rgba(63, 47, 30, .10);
    transition: box-shadow .35s var(--ease), transform .35s var(--ease);
}
.st-key-land_ask [data-testid="stChatInput"] > div:focus-within { box-shadow: 0 16px 50px rgba(255, 74, 28, .20); transform: translateY(-2px); }
.st-key-land_ask textarea { background: transparent !important; font-size: 18px !important; line-height: 1.5 !important; }
.st-key-land_ask [data-testid="stChatInputSubmitButton"] {
    background: var(--ink) !important; color: #FFFFFF !important; border-radius: 50% !important;
    width: 46px !important; height: 46px !important;
}
.st-key-land_ask [data-testid="stChatInputSubmitButton"]:hover { background: var(--orange) !important; }
.st-key-land_ask [data-testid="stChatInputSubmitButton"] svg,
.st-key-land_ask [data-testid="stChatInputFileUploadButton"] svg { width: 22px !important; height: 22px !important; }
.st-key-land_ask [data-testid="stChatInputFileUploadButton"] button:hover { color: var(--orange) !important; }

/* settings row under the search bar */
.st-key-land_settings { padding: 4px 18px 0; }
.st-key-land_settings [data-testid="stWidgetLabel"] p {
    font-size: 11px !important; letter-spacing: .08em; text-transform: uppercase; color: var(--soft) !important;
}
.st-key-land_settings [data-testid="stSlider"] { padding-top: 0; }

@media (prefers-reduced-motion: reduce) {
    .lp *, .lp *::before, .lp *::after, .ask-q, .st-key-thread [data-testid="stChatMessage"] { animation: none !important; }
}
@media (max-width: 760px) {
    .stage { height: 250px; transform: scale(.8); }
    .captions { display: none; }
    .doc b { max-width: 180px; }
}
</style>
"""

ASSISTANT_AVATAR = ":material/blur_circular:"


def _topbar(active: bool) -> str:
    new = '<a class="ghost" href="?">New search</a>' if active else ""
    return f"""
  <div class="topbar">
    <a class="dm-logo brand fade" href="?">{mark(26)}DOCUMIND</a>
    <div class="links fade" style="--d:.1s">{new}<a class="ghost" href="{DASHBOARD_LINK}">Dashboard</a></div>
  </div>"""


def _bubble(text: str, file: bool = False) -> None:
    cls = "ask-q file" if file else "ask-q"
    st.html(f'<div class="{cls}"><span>{html.escape(text)}</span></div>')


def _sources(sources) -> None:
    if not sources:
        st.caption("No matching passages. Upload a PDF with the + button first.")
        return
    with st.expander(f"Sources · {len(sources)} passages"):
        for i, c in enumerate(sources, 1):
            st.caption(f"#{i} · {c['doc_name']} · p.{c['page_num']} · {int(c['score'] * 100)}% match")
            st.markdown(c["text"][:400] + ("..." if len(c["text"]) > 400 else ""))


def _answer(question: str, top_k: int):
    """Stream an answer into the current container; returns (text, sources)."""
    from core.pipeline import query_document
    try:
        with st.spinner("Searching your documents..."):
            gen, sources = query_document(question=question, top_k=top_k, stream=True)
        text = st.write_stream(gen)
        _sources(sources)
        return text, sources
    except Exception as e:
        st.error(e)
        return f"Something went wrong: {e}", []


def _docs_html(docs) -> str:
    chips = []
    for d in docs:
        bar = f'<span class="bar" style="width:{int(d["pct"] * 100)}%"></span>' if d["status"] == "indexing" else ""
        chips.append(f'<span class="doc {d["status"]}"><i></i><b>{html.escape(d["name"])}</b>'
                     f'<small>{html.escape(d["detail"])}</small>{bar}</span>')
    return f'<div class="docs">{"".join(chips)}</div>'


def _docs_strip() -> None:
    docs = st.session_state.ws_docs
    if any(refresh(d) for d in list(docs)):
        st.rerun()  # a document finished: re-render the page and answer any waiting questions
    if docs:
        st.html(_docs_html(docs))


def render_landing():
    ss = st.session_state
    ss.setdefault("ws_chat", [])   # turns: {"kind": "q"|"file", "q", "a", "sources", "waiting", "doc"}
    ss.setdefault("ws_docs", [])
    ss.setdefault("cfg_chunk", 400)
    ss.setdefault("cfg_overlap", 50)
    ss.setdefault("cfg_topk", 5)
    chat, docs = ss.ws_chat, ss.ws_docs
    active = bool(chat or docs or ss.get("pending"))

    if active:
        st.html(CSS + LOGO_CSS + f'<div class="lp top">{_topbar(True)}</div>')
    else:
        st.html(CSS + LOGO_CSS + f"""
<div class="lp top">
  {_topbar(False)}
  <div class="stage">{mark(300)}</div>
  <h2 class="hello fade" style="--d:.5s">{mark(30)}{greeting()}</h2>
</div>
""")

    # ---- conversation (search mode only) ----
    thread = st.container(key="thread") if active else None
    slots = {}
    if active:
        with thread:
            for i, turn in enumerate(chat):
                if turn["kind"] == "file":
                    _bubble(f"Added {turn['q']}", file=True)
                    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                        st.markdown(summary(docs[turn["doc"]]))
                    continue
                _bubble(turn["q"])
                slots[i] = st.empty()
                with slots[i].container():
                    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                        if turn.get("waiting"):
                            st.caption("Waiting for your document to finish indexing, then I'll answer.")
                        else:
                            st.markdown(turn["a"])
                            _sources(turn.get("sources"))

    strip = st.container(key="docs")

    # ---- search bar: type a question, or use the upload button to add PDFs ----
    with st.container(key="land_ask"):
        prompt = st.chat_input("Ask anything, or upload a PDF", accept_file="multiple",
                               file_type=["pdf"], key="land_input")

    # ---- settings, directly under the search bar ----
    with st.container(key="land_settings"):
        c1, c2, c3 = st.columns(3, gap="large")
        c1.slider("Chunk size", 100, 800, step=50, key="cfg_chunk",
                  help="Tokens per chunk when a PDF is indexed. Applies to new uploads.")
        c2.slider("Chunk overlap", 0, 150, step=10, key="cfg_overlap",
                  help="Tokens shared between neighbouring chunks. Applies to new uploads.")
        c3.slider("Top-k retrieval", 1, 15, step=1, key="cfg_topk",
                  help="How many passages are retrieved to answer each question.")

    if not active:
        st.html('<div class="lp captions"><div>Document Q&amp;A,<br>grounded in source</div>'
                '<div class="r">Every answer,<br>cited to the page</div></div>')

    if prompt:
        # switch to search mode first, then handle the request on the next run
        ss.pending = {"q": (prompt.text or "").strip(), "files": list(prompt.files)}
        st.rerun()

    # ---- handle a new request ----
    pending = ss.pop("pending", None)
    if pending:
        with thread:
            for f in pending["files"]:
                _bubble(f"Added {f.name}", file=True)
                with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                    pb, cap = st.progress(0), st.empty()
                    doc = ingest(f, ss.cfg_chunk, ss.cfg_overlap,
                                 lambda step, pct=None: (pb.progress(pct) if pct is not None else None,
                                                         cap.caption(step)))
                    pb.empty(), cap.empty()
                    docs.append(doc)
                    st.markdown(summary(doc))
                chat.append({"kind": "file", "q": f.name, "doc": len(docs) - 1})

            q = pending["q"]
            if q:
                _bubble(q)
                with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                    if any(d["status"] == "indexing" for d in docs):
                        st.caption("Waiting for your document to finish indexing, then I'll answer.")
                        chat.append({"kind": "q", "q": q, "waiting": True})
                    else:
                        a, sources = _answer(q, ss.cfg_topk)
                        chat.append({"kind": "q", "q": q, "a": a, "sources": sources})

    # ---- answer questions that were waiting for indexing to finish ----
    if active and not any(d["status"] == "indexing" for d in docs):
        for i, turn in enumerate(chat):
            if turn.get("waiting") and i in slots:
                with slots[i].container():
                    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                        a, sources = _answer(turn["q"], ss.cfg_topk)
                turn.update(waiting=False, a=a, sources=sources)

    # ---- documents strip: polls background indexing until every document is ready ----
    with strip:
        polling = any(d["status"] == "indexing" for d in docs)
        st.fragment(run_every=2 if polling else None)(_docs_strip)()
