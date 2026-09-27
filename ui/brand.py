"""DocuMind logo mark and the time-aware greeting, shared by the landing page and the app."""
import datetime
import html
import math
import random

import streamlit as st

# The mark: a ring of thin loops fanned around a circle, orange fading to warm grey.
# It scales in on load, turns slowly while a twist wave runs through the loops,
# and lifts slightly when the logo is hovered. The same mark is used large in the hero.
# Keep "<" out of this CSS: st.html drops <style> blocks containing tag-like text.
LOGO_CSS = """
<style>
.dm-logo { display: inline-flex; align-items: center; gap: 12px; }
.dm-mark {
    display: inline-block; flex: none; line-height: 0;
    animation: dm-in 1.3s cubic-bezier(.2, .75, .2, 1) both;
    transition: scale .45s cubic-bezier(.2, .75, .2, 1);
}
.dm-logo:hover .dm-mark { scale: 1.12; }
.dm-ring { position: relative; display: block; width: var(--s); height: var(--s); animation: dm-spin var(--spin, 40s) linear infinite; }
.dm-ring .sp { position: absolute; left: 50%; top: 50%; width: 0; height: 0; }
.dm-ring .lo {
    position: absolute; left: calc(var(--s) * -0.2); top: calc(var(--s) * -0.07);
    width: calc(var(--s) * .4); height: calc(var(--s) * .14);
    border: var(--bw, 1px) solid var(--c); border-radius: 50%; opacity: .8;
    transform: translateY(calc(var(--s) * -0.28));
    animation: dm-twist 5s ease-in-out infinite; animation-delay: calc(var(--i) * var(--step));
}
@keyframes dm-in { from { transform: scale(.6) rotate(-120deg); opacity: 0; } }
@keyframes dm-spin { to { transform: rotate(360deg); } }
@keyframes dm-twist {
    0%, 100% { transform: translateY(calc(var(--s) * -0.28)) scale(1, 1); }
    50% { transform: translateY(calc(var(--s) * -0.3)) scale(.8, 1.35); }
}
@media (prefers-reduced-motion: reduce) {
    .dm-mark, .dm-ring, .dm-ring .lo { animation: none !important; }
}
</style>
"""


def mark(size: int = 18, loops: int = 0, spin: int = 0) -> str:
    """The ring logo at `size` px. Small marks use fewer loops so they stay crisp."""
    n = loops or (64 if size >= 120 else 28)
    orange, grey = (255, 74, 28), (142, 132, 122)
    parts = []
    for i in range(n):
        a = i * 360 / n  # 0 = top, 90 = right: orange sits on the upper right
        w = (1 + math.cos(math.radians(a - 60))) / 2
        r, g, b = (round(o * w + gr * (1 - w)) for o, gr in zip(orange, grey))
        parts.append(f'<span class="sp" style="transform:rotate({a:.1f}deg)">'
                     f'<span class="lo" style="--i:{i};--c:rgb({r},{g},{b})"></span></span>')
    bw = "1px" if size >= 60 else "0.75px"
    spin_s = spin or (40 if size >= 120 else 24)
    return (f'<span class="dm-mark"><span class="dm-ring" style="--s:{size}px;--bw:{bw};'
            f'--spin:{spin_s}s;--step:{-5 / n:.4f}s">{"".join(parts)}</span></span>')


# ---- greeting ---------------------------------------------------------------

GREETINGS = {
    "morning": [
        "Good morning. What are we working on today?",
        "Morning. What should we dig into first?",
        "Fresh start. Which document are we opening?",
        "Good morning. What do you want to find out?",
        "Morning. Where should we begin?",
    ],
    "afternoon": [
        "Where should we begin?",
        "Good afternoon. What can I find for you?",
        "What are we looking into this afternoon?",
        "Afternoon. Which page holds the answer?",
        "Ready when you are. What's the question?",
    ],
    "evening": [
        "Evening thoughts?",
        "Good evening. What's on the reading list?",
        "Winding down, or just getting started?",
        "What should we look into tonight?",
        "Evening. What would you like to understand?",
    ],
    "night": [
        "Still working? What's on your mind?",
        "Burning the midnight oil?",
        "Late one. What can I help you find?",
        "Quiet hours. What are we reading?",
        "Up late? Let's find that answer.",
    ],
}

# extra lines that only make sense on certain days
CONTEXTUAL = {
    ("morning", 0): ["New week. What's first?"],
    ("afternoon", 4): ["Almost the weekend. What's left to figure out?"],
    ("morning", 5): ["Weekend reading?"],
    ("afternoon", 5): ["A little weekend research?"],
    ("morning", 6): ["Slow Sunday? What are we reading?"],
}


def _now() -> datetime.datetime:
    # Use the visitor's browser timezone when Streamlit knows it; otherwise the server clock.
    try:
        from zoneinfo import ZoneInfo
        tz = st.context.timezone
        if tz:
            return datetime.datetime.now(ZoneInfo(tz))
    except Exception:
        pass
    return datetime.datetime.now()


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def greeting() -> str:
    """A time-appropriate greeting, picked once per visit so it stays put across reruns
    but changes when the page is refreshed."""
    if "greeting" not in st.session_state:
        now = _now()
        part = _part_of_day(now.hour)
        options = GREETINGS[part] + CONTEXTUAL.get((part, now.weekday()), [])
        st.session_state.greeting = random.choice(options)
    return html.escape(st.session_state.greeting)
