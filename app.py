"""
🐾 Котик-навигатор 2.0 — маленький сайт, чтобы позвать её на свидание.
Запуск:  streamlit run app.py
Ответы:  data/answers.csv  (+ уведомление в Telegram, если настроено)
Админка: https://<твой-адрес>/?admin=<ADMIN_PASSWORD>
"""

import csv
import inspect
from html import escape
import json
import os
import random
import threading
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

st.set_page_config(page_title="Куда идём? 🐾", page_icon="🐱", layout="centered")

# ═══════════════════════════════════════════════════════════════════
# 1. НАСТРОЙКИ — всё, что обычно хочется поменять
# ═══════════════════════════════════════════════════════════════════

HER_NAME = ""                       # например "Аня" — тогда на старте будет «Привет, Аня 👋»
TIMEZONE = "Europe/Chisinau"        # от этой зоны считаются «сегодня» и «завтра»
DAYS_AHEAD = 14                     # сколько дней показывать в выборе
TIME_SLOTS = ["12:00", "13:00", "14:00", "15:00", "16:00", "17:00",
              "18:00", "18:30", "19:00", "19:30", "20:00", "21:00"]
DATA_FILE = Path(os.environ.get("DATA_DIR", "data")) / "answers.csv"

COLORS = {
    "bg_top": "#FFF5F8", "bg_bottom": "#F6EEFF", "card": "#FFFFFF", "cream": "#FFF9F1",
    "pink": "#F7B6CB", "pink_soft": "#FDE4EC", "lilac": "#C9B6F2", "lilac_soft": "#EFE8FD",
    "text": "#4A3B52", "muted": "#9C8CA6", "accent": "#E78AAB",
}
FUR = {"cream": "#FFF9F1", "ginger": "#FBD9B4", "gray": "#E6E1EC", "peach": "#FDE1DA"}

# ── Вопрос 1: формат ────────────────────────────────────────────────
# (ключ, эмодзи, текст, реакция котика)
Q1_OPTIONS = [
    ("coffee_dessert", "☕", "Кофе с десертом",                  "Сладкоежка обнаружена 😼"),
    ("food",           "🍝", "Нормально поесть",                 "Котик тоже всегда за еду 🐟"),
    ("coffee_walk",    "🚶‍♀️", "Кофе с собой и прогулка",       "Котик уже разминает лапки 🐾"),
    ("desserts",       "🍰", "Только десерты. Много десертов",   "Котик уважает такой подход 🍰"),
    ("brunch",         "🥐", "Завтрак / бранч",                  "Ранние пташки… то есть котики 🌤️"),
    ("drinks",         "🍷", "Бокал чего-нибудь и атмосфера",    "Котик надел бабочку 🎀"),
]
DESSERT_FORMATS = {"coffee_dessert", "desserts"}

# ── Вопрос 2: любимое блюдо (список зависит от ответа на вопрос 1) ──
DISHES = ["🍕 Пицца", "🍣 Суши / роллы", "🍝 Паста", "🍔 Бургер",
          "🥩 Стейк", "🍜 Рамен / вок", "🥟 Хинкали", "🥗 Что-то лёгкое"]
DESSERTS = ["🍰 Чизкейк", "☕ Тирамису", "🥐 Круассан", "🍪 Макарон",
            "🍦 Мороженое", "🍫 Шоколадный торт", "🥞 Панкейки", "🍯 Медовик"]
CUSTOM = "✍️ Своё"

# Пасхалки на текст, который она введёт сама (ищется подстрока, без учёта регистра)
TEXT_EGGS = [
    (("рыб", "лосос", "тунец", "сёмг", "семг", "fish"), "Рыба?! Котик в восторге 🐟🐟🐟"),
    (("кот", "кош", "cat"),                            "Эй! Котиков не едят 🙀"),
    (("шаурм", "шаверм"),                              "Котик уважает классику 🌯"),
    (("всё", "все", "любое", "без разниц"),            "Котик записал: «всё». Это смело 😼"),
]

# ── Вопрос 3: место мечты ──────────────────────────────────────────
Q3_OPTIONS = [
    ("yes",    "📍", "Да, есть! Сейчас напишу", "Котик весь во внимании 👂"),
    ("no",     "😼", "Нет, удиви меня",          "Котик принял вызов. Готовься 😼"),
    ("secret", "🤫", "Есть, но это секрет",      "Котик всё равно выведает. Позже 🕵️"),
]

# ── Вопрос 4: доверие (кнопка «Нет» убегает) ───────────────────────
Q4_OPTIONS = [
    ("yes",  "😌", "Да, доверяю",            "Ответственность принята. Котик нервничает 😅"),
    ("veto", "😼", "Да, но с правом вето",   "Справедливо. Котик уважает договорённости 🤝"),
]

# ── Вопрос 5: оценка сайта ────────────────────────────────────────
Q5_OPTIONS = [
    ("cute",      "🥹", "Мило",                                "Котик покраснел 🥹"),
    ("very_cute", "😻", "Очень мило",                          "Котик сейчас замурчит от гордости 😻"),
    ("cat_did",   "😼", "Это котик сделал всю работу, а не ты", "Котик: «наконец-то кто-то заметил» 😼"),
    ("counted",   "✅", "Засчитано",                           "Котик ставит себе лапку ✅"),
    ("too_many",  "🙀", "Слишком много котиков",               "Неправильный ответ. Котиков не бывает слишком много 🐈🐈🐈"),
]

# ── Экран и котик на каждом шаге ──────────────────────────────────
# step: 0 старт, 1–5 вопросы, 6 день/время, 7 проверка и отправка, 8 спасибо
CATS = {   # (настроение, окрас, аксессуар, подпись)
    0: ("smile",      "cream",  None,      ""),
    1: ("thinking",   "ginger", None,      "котик думает…"),
    2: ("looking",    "gray",   None,      "котик уже голодный"),
    3: ("suspicious", "peach",  "glasses", "котик-детектив на связи"),
    4: ("smile",      "cream",  "bow",     "котик максимально серьёзен"),
    5: ("almost",     "ginger", "glasses", "котик ждёт оценку"),
    6: ("looking",    "gray",   None,      "котик открыл календарь"),
    7: ("almost",     "peach",  None,      "котик проверяет всё дважды"),
    8: ("happy",      "cream",  "hat",     ""),
}
TOTAL_Q = 5
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WEEKDAYS_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


# ═══════════════════════════════════════════════════════════════════
# 2. СЕКРЕТЫ, CSV, TELEGRAM
# ═══════════════════════════════════════════════════════════════════

def get_secret(name: str) -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:          # нет secrets.toml — это нормально при локальном запуске
        pass
    return os.environ.get(name, "")


CSV_FIELDS = ["submitted_at", "format", "dish", "dream_place", "trust",
              "site_rating", "date", "weekday", "time", "comment"]
_csv_lock = threading.Lock()


def save_to_csv(row: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _csv_lock:
        new_file = not DATA_FILE.exists() or DATA_FILE.stat().st_size == 0
        # utf-8-sig: Excel корректно откроет кириллицу; BOM пишется только в начало файла
        with DATA_FILE.open("a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if new_file:
                w.writeheader()
            w.writerow(row)


def send_telegram(text: str) -> bool:
    token, chat_id = get_secret("TELEGRAM_BOT_TOKEN"), get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 200
    except Exception:
        return False   # уведомление — бонус; ответ всё равно сохранён в CSV


# ═══════════════════════════════════════════════════════════════════
# 3. СОСТОЯНИЕ
# ═══════════════════════════════════════════════════════════════════

if "step" not in st.session_state:
    st.session_state.step = 0
    st.session_state.ans = {}            # все ответы
    st.session_state.submitted = False
    st.session_state.saved_ok = None

S = st.session_state


def go(step: int):
    S.step = step
    S.nudge = None


# «Дальше»: если шаг не заполнен (например, поле ввода пустое) — не идём дальше, а мягко подсказываем
def go_next(step: int):
    if step_ready(step):
        go(step + 1)
    else:
        S.nudge = step


# Аргумент live=True есть только в новых версиях Streamlit. В старых — просто не передаём его,
# тогда значение фиксируется при Enter / уходе из поля / нажатии «Дальше».
_TEXT_INPUT_HAS_LIVE = "live" in inspect.signature(st.text_input).parameters


def text_input_compat(*args, **kwargs):
    if _TEXT_INPUT_HAS_LIVE:
        kwargs["live"] = True
    return st.text_input(*args, **kwargs)


def set_ans(key: str, value):
    S.ans[key] = value


def restart():
    S.step, S.ans, S.submitted, S.saved_ok, S.nudge = 0, {}, False, None, None


def label_of(options, key):
    for k, e, text, *_ in options:
        if k == key:
            return f"{e} {text}"
    return ""


def reaction_of(options, key):
    for k, _, _, reaction in options:
        if k == key:
            return reaction
    return ""


def text_egg(text: str) -> str:
    t = (text or "").lower()
    for needles, reply in TEXT_EGGS:
        if any(n in t for n in needles):
            return reply
    return ""


def today_local() -> date:
    try:
        return datetime.now(ZoneInfo(TIMEZONE)).date()
    except Exception:
        return date.today()


def day_label(d: date, short=True) -> str:
    delta = (d - today_local()).days
    if delta == 0:
        return "Сегодня" if short else f"сегодня, {d.day} {MONTHS[d.month - 1]}"
    if delta == 1:
        return "Завтра" if short else f"завтра, {d.day} {MONTHS[d.month - 1]}"
    if short:
        return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1][:3]}"
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def chosen_dish() -> str:
    d = S.ans.get("dish", "")
    return S.ans.get("dish_custom", "").strip() if d == CUSTOM else d


def chosen_time() -> str:
    t = S.ans.get("time", "")
    return S.ans.get("time_custom", "") if t == "other" else t


# Выбран ли вариант на шаге (включает кнопку «Дальше»; текст проверяется при нажатии)
def choice_made(step: int) -> bool:
    a = S.ans
    return {2: "dish" in a, 3: "dream" in a}.get(step, step_ready(step))


# Полностью ли заполнен шаг
def step_ready(step: int) -> bool:
    a = S.ans
    if step == 1:
        return "format" in a
    if step == 2:
        return bool(chosen_dish())
    if step == 3:
        return a.get("dream") in ("no", "secret") or (a.get("dream") == "yes" and a.get("dream_text", "").strip() != "")
    if step == 4:
        return "trust" in a
    if step == 5:
        return "vibe" in a
    if step == 6:
        return bool(a.get("day")) and bool(chosen_time())
    return True


def submit():
    if S.submitted:                       # защита от двойного клика
        return
    a = S.ans
    d = date.fromisoformat(a["day"])
    dream = a.get("dream")
    row = {
        "submitted_at": datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S"),
        "format": label_of(Q1_OPTIONS, a.get("format")),
        "dish": chosen_dish(),
        "dream_place": a.get("dream_text", "").strip() if dream == "yes"
                       else ("секрет 🤫" if dream == "secret" else "нет, удиви меня"),
        "trust": label_of(Q4_OPTIONS, a.get("trust")),
        "site_rating": label_of(Q5_OPTIONS, a.get("vibe")),
        "date": d.isoformat(),
        "weekday": WEEKDAYS_FULL[d.weekday()],
        "time": chosen_time(),
        "comment": a.get("comment", "").strip(),
    }
    try:
        save_to_csv(row)
        S.saved_ok = True
    except Exception:
        S.saved_ok = False
    send_telegram(
        "🐾 Котик принёс ответ!\n\n"
        f"🗓 {day_label(d, short=False)} в {row['time']}\n"
        f"☕ Формат: {row['format']}\n"
        f"🍽 Любимое: {row['dish']}\n"
        f"📍 Место мечты: {row['dream_place']}\n"
        f"🤝 Доверие: {row['trust']}\n"
        f"⭐ Сайт: {row['site_rating']}\n"
        + (f"💬 {row['comment']}" if row["comment"] else "")
    )
    S.submitted = True
    S.step = 8


# ═══════════════════════════════════════════════════════════════════
# 4. КОТИК (SVG): настроение × окрас × аксессуар
# ═══════════════════════════════════════════════════════════════════

def cat_svg(mood="smile", fur="cream", acc=None, size=150, cls="") -> str:
    c, f = COLORS, FUR.get(fur, fur)
    ink = c["text"]
    L, R = (78, 100), (122, 100)

    def round_eyes(dx=0, dy=0, r=9):
        return "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{ink}"/>'
                       f'<circle cx="{x+dx+3}" cy="{y+dy-3}" r="3" fill="#fff"/>' for x, y in (L, R))

    def arc_eyes(up=True):
        d = -8 if up else 7
        o = 4 if up else -3
        return "".join(f'<path d="M{x-9} {y+o} Q{x} {y+d} {x+9} {y+o}" stroke="{ink}" stroke-width="4" '
                       f'fill="none" stroke-linecap="round"/>' for x, y in (L, R))

    mouth_w = (f'<path d="M92 120 Q96 126 100 120 Q104 126 108 120" stroke="{ink}" stroke-width="3" '
               f'fill="none" stroke-linecap="round"/>')
    extra, blush = "", 0.55

    if mood == "smile":
        eyes, mouth = round_eyes(), mouth_w
    elif mood == "thinking":
        eyes = round_eyes(dx=3, dy=-3, r=8)
        mouth = f'<path d="M94 122 L106 121" stroke="{ink}" stroke-width="3" stroke-linecap="round"/>'
        extra = (f'<circle cx="160" cy="48" r="5" fill="{c["lilac"]}"/><circle cx="172" cy="32" r="7" fill="{c["lilac"]}"/>'
                 f'<text x="176" y="20" font-size="18" fill="{c["lilac"]}" font-weight="700">?</text>')
    elif mood == "looking":
        eyes = round_eyes(r=11) + "".join(f'<circle cx="{x-3}" cy="{y+4}" r="2" fill="#fff"/>' for x, y in (L, R))
        mouth = f'<ellipse cx="100" cy="122" rx="4" ry="3.5" fill="{ink}"/>'
    elif mood == "suspicious":
        eyes = "".join(f'<circle cx="{x}" cy="{y+2}" r="8" fill="{ink}"/>'
                       f'<rect x="{x-11}" y="{y-10}" width="22" height="10" fill="{f}"/>'
                       f'<path d="M{x-11} {y} L{x+11} {y}" stroke="{ink}" stroke-width="3" stroke-linecap="round"/>'
                       for x, y in (L, R))
        mouth = f'<path d="M92 121 Q100 126 110 117" stroke="{ink}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    elif mood == "almost":
        eyes, mouth = arc_eyes(up=False), mouth_w
    else:  # happy
        eyes = arc_eyes(up=True)
        mouth = (f'<path d="M90 118 Q100 134 110 118 Z" fill="{c["accent"]}" stroke="{ink}" '
                 f'stroke-width="2.5" stroke-linejoin="round"/>')
        blush = 0.85

    accessory = ""
    if acc == "bow":        # бабочка
        accessory = (f'<path d="M100 166 L80 156 L80 176 Z" fill="{c["accent"]}" stroke="{ink}" stroke-width="2.5" stroke-linejoin="round"/>'
                     f'<path d="M100 166 L120 156 L120 176 Z" fill="{c["accent"]}" stroke="{ink}" stroke-width="2.5" stroke-linejoin="round"/>'
                     f'<circle cx="100" cy="166" r="5" fill="{c["pink"]}" stroke="{ink}" stroke-width="2.5"/>')
    elif acc == "glasses":  # очки
        accessory = "".join(f'<circle cx="{x}" cy="{y}" r="15" fill="rgba(255,255,255,.25)" stroke="{ink}" stroke-width="3"/>'
                            for x, y in (L, R)) + f'<path d="M93 99 Q100 94 107 99" stroke="{ink}" stroke-width="3" fill="none"/>'
    elif acc == "hat":      # праздничный колпак
        accessory = (f'<path d="M100 2 L80 52 L120 52 Z" fill="{c["lilac"]}" stroke="{ink}" stroke-width="3" stroke-linejoin="round"/>'
                     f'<circle cx="100" cy="4" r="6" fill="{c["accent"]}"/>'
                     f'<circle cx="94" cy="34" r="3" fill="#fff"/><circle cx="106" cy="44" r="3" fill="#fff"/>')

    return (
        f'<svg class="cat {cls}" width="{size}" height="{size}" viewBox="0 0 200 182" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="M45 70 L52 18 L92 52 Z" fill="{f}" stroke="{ink}" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M155 70 L148 18 L108 52 Z" fill="{f}" stroke="{ink}" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M56 56 L59 32 L80 50 Z" fill="{c["pink"]}"/><path d="M144 56 L141 32 L120 50 Z" fill="{c["pink"]}"/>'
        f'<ellipse cx="100" cy="105" rx="68" ry="58" fill="{f}" stroke="{ink}" stroke-width="3"/>'
        f'<ellipse cx="62" cy="120" rx="11" ry="7" fill="{c["pink"]}" opacity="{blush}"/>'
        f'<ellipse cx="138" cy="120" rx="11" ry="7" fill="{c["pink"]}" opacity="{blush}"/>'
        f'{eyes}<path d="M95 111 L105 111 L100 117 Z" fill="{c["accent"]}"/>{mouth}'
        f'<g stroke="{c["muted"]}" stroke-width="2" stroke-linecap="round">'
        f'<path d="M48 112 L22 106"/><path d="M48 120 L22 122"/><path d="M152 112 L178 106"/><path d="M152 120 L178 122"/></g>'
        f'{accessory}{extra}</svg>'
    )


# ═══════════════════════════════════════════════════════════════════
# 5. СТИЛИ
# ═══════════════════════════════════════════════════════════════════

def inject_css():
    c = COLORS
    st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Comfortaa:wght@500;700&family=Nunito:wght@400;600;700;800&display=swap');
#MainMenu, header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="InputInstructions"] {{ display:none !important; }}
html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: linear-gradient(180deg, {c["bg_top"]} 0%, {c["bg_bottom"]} 100%) !important; background-attachment: fixed !important;
  color:{c["text"]}; font-family:'Nunito', system-ui, sans-serif;
}}
.block-container {{ max-width:680px !important; padding:2rem 1rem 4rem !important; }}
.stApp::before {{ content:"🐾"; position:fixed; top:8%; left:6%; font-size:42px; opacity:.12; transform:rotate(-20deg); pointer-events:none; }}
.stApp::after  {{ content:"🐾"; position:fixed; bottom:12%; right:6%; font-size:52px; opacity:.12; transform:rotate(25deg); pointer-events:none; }}
[data-testid="stElementContainer"]:has(> .stHtml), [data-testid="stElementContainer"]:has(iframe[height="0"]) {{ display:none; }}

@keyframes fadeUp  {{ from {{opacity:0; transform:translateY(14px);}} to {{opacity:1; transform:none;}} }}
@keyframes float   {{ 0%,100% {{transform:translateY(0);}} 50% {{transform:translateY(-8px);}} }}
@keyframes pop     {{ 0% {{transform:scale(.3); opacity:0;}} 70% {{transform:scale(1.08); opacity:1;}} 100% {{transform:scale(1);}} }}
@keyframes sparkle {{ 0%,100% {{opacity:0; transform:scale(.4);}} 50% {{opacity:1; transform:scale(1.1) rotate(20deg);}} }}
@keyframes wiggle  {{ 0%,100% {{transform:translateX(-50%) rotate(0);}} 25% {{transform:translateX(-50%) rotate(-8deg);}} 75% {{transform:translateX(-50%) rotate(8deg);}} }}
@keyframes jump    {{ 0%,100% {{transform:translateY(0);}} 40% {{transform:translateY(-22px);}} }}
@keyframes fall    {{ from {{transform:translateY(-12vh) rotate(0);}} to {{transform:translateY(112vh) rotate(360deg);}} }}

.fade {{ animation:fadeUp .55s ease both; }}
.cat-wrap {{ display:flex; flex-direction:column; align-items:center; margin:.1rem 0 .3rem; }}
.cat-wrap svg {{ animation:float 3.2s ease-in-out infinite; filter:drop-shadow(0 10px 14px rgba(200,150,190,.25)); max-width:100%; cursor:pointer; }}
.cat-wrap.pop svg {{ animation:pop .8s cubic-bezier(.2,.9,.3,1.3) both, float 3.2s ease-in-out .8s infinite; }}
.cat-caption {{ font-size:.85rem; color:{c["muted"]}; font-style:italic; margin-top:.1rem; }}
.cat-hint {{ font-size:.75rem; color:{c["muted"]}; opacity:.7; margin-top:.15rem; }}
.cat-row {{ display:flex; justify-content:center; align-items:flex-end; gap:.2rem; }}
.cat-row svg {{ animation:jump 1.1s ease-in-out infinite; cursor:pointer; }}
.cat-row svg:nth-child(2) {{ animation-delay:.18s; }} .cat-row svg:nth-child(3) {{ animation-delay:.36s; }}

.h1 {{ font-family:'Comfortaa','Nunito',system-ui,sans-serif; font-weight:700; font-size:2.05rem; text-align:center; line-height:1.25; margin:.3rem 0 .6rem; }}
.h2 {{ font-family:'Comfortaa','Nunito',system-ui,sans-serif; font-weight:700; font-size:1.42rem; text-align:center; line-height:1.35; margin:.2rem 0 .3rem; }}
.sub {{ text-align:center; font-size:1.06rem; opacity:.85; margin:.15rem 0; }}
.muted {{ text-align:center; font-size:.97rem; color:{c["muted"]}; margin:.15rem 0 1rem; }}
.section {{ text-align:center; font-weight:800; font-size:.82rem; letter-spacing:.12em; text-transform:uppercase; color:{c["muted"]}; margin:1rem 0 .35rem; }}

.progress-label {{ text-align:center; font-weight:700; font-size:.88rem; letter-spacing:.04em; color:{c["muted"]}; margin-bottom:.4rem; }}
.progress {{ display:flex; align-items:center; gap:.5rem; margin:0 auto .9rem; max-width:520px; padding-top:20px; }}
.progress .paw {{ font-size:1.05rem; opacity:.75; }}
.track {{ position:relative; flex:1; height:10px; border-radius:99px; background:{c["lilac_soft"]}; }}
.fill {{ position:absolute; inset:0 auto 0 0; border-radius:99px; background:linear-gradient(90deg,{c["pink"]},{c["lilac"]}); }}
.runner {{ position:absolute; top:-23px; line-height:1; font-size:1.55rem; animation:wiggle 1.4s ease-in-out infinite; }}

.reaction {{ text-align:center; margin:.9rem auto .2rem; padding:.55rem 1.1rem; width:fit-content; max-width:100%;
  background:{c["cream"]}; border:1px dashed {c["pink"]}; border-radius:999px; font-weight:600; font-size:.95rem; animation:fadeUp .4s ease both; }}

/* кнопки */
.stButton > button {{ font-family:'Nunito',sans-serif !important; border-radius:22px !important;
  transition:transform .15s ease, box-shadow .2s ease, background .2s ease !important; box-shadow:none !important; }}
.stButton > button p {{ font-size:1rem !important; font-weight:700 !important; }}
div[class*="st-key-opt_"] button {{ min-height:60px; width:100%; padding:.7rem 1.1rem !important; background:{c["card"]} !important;
  color:{c["text"]} !important; border:2px solid {c["pink_soft"]} !important; box-shadow:0 6px 16px rgba(190,140,190,.10) !important; }}
div[class*="st-key-opt_"] button p {{ font-weight:600 !important; }}
div[class*="st-key-opt_"] button:hover {{ transform:translateY(-2px); border-color:{c["pink"]} !important; background:{c["cream"]} !important; }}
div[class*="st-key-opt_"] button[kind="primary"] {{ background:linear-gradient(135deg,{c["pink_soft"]},{c["lilac_soft"]}) !important;
  border-color:{c["accent"]} !important; box-shadow:0 8px 20px rgba(231,138,171,.28) !important; }}
div[class*="st-key-opt_"] button[kind="primary"] p::after {{ content:"  🐾"; }}
div[class*="st-key-main_"] button {{ width:100%; min-height:56px; border:none !important; color:#fff !important;
  background:linear-gradient(135deg,{c["accent"]},{c["lilac"]}) !important; box-shadow:0 10px 24px rgba(231,138,171,.35) !important; }}
div[class*="st-key-main_"] button p {{ font-size:1.12rem !important; color:#fff !important; }}
div[class*="st-key-main_"] button:hover {{ transform:translateY(-2px) scale(1.01); }}
div[class*="st-key-main_"] button:disabled {{ opacity:.45; filter:grayscale(.3); transform:none; }}
div[class*="st-key-back_"] button {{ background:transparent !important; border:none !important; color:{c["muted"]} !important; min-height:56px; }}
div[class*="st-key-back_"] button:hover {{ color:{c["accent"]} !important; }}

/* 2 колонки и на телефоне */
div[class*="st-key-grid_"] [data-testid="stHorizontalBlock"] {{ flex-wrap:nowrap !important; flex-direction:row !important; gap:.6rem !important; }}
div[class*="st-key-grid_"] [data-testid="stColumn"] {{ min-width:0 !important; }}
div[class*="st-key-grid_"] {{ gap:.6rem !important; }}

/* убегающая «Нет» */
.no-zone {{ display:flex; justify-content:center; min-height:64px; margin-top:.5rem; }}
#no-btn {{ font-family:'Nunito',sans-serif; font-weight:600; font-size:1rem; color:{c["text"]}; background:{c["card"]};
  border:2px solid {c["pink_soft"]}; border-radius:22px; padding:.85rem 2.4rem; cursor:pointer; z-index:999;
  box-shadow:0 6px 16px rgba(190,140,190,.10); transition:left .25s ease, top .25s ease, transform .2s ease; }}
#no-counter {{ text-align:center; font-size:.85rem; color:{c["muted"]}; min-height:1.3rem; margin-top:.3rem; }}

/* поля ввода */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stTimeInput"] input {{
  font-family:'Nunito',sans-serif !important; font-size:1rem !important; color:{c["text"]} !important; background:{c["card"]} !important; }}
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stTimeInput"] div[data-baseweb="select"] > div {{
  border-radius:18px !important; border:2px solid {c["pink_soft"]} !important; background:{c["card"]} !important; overflow:hidden; }}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within {{ border-color:{c["accent"]} !important; }}
[data-testid="stWidgetLabel"] p {{ font-weight:700 !important; color:{c["text"]} !important; }}

/* таблетки (дни, время) */
[data-testid="stButtonGroup"] {{ justify-content:center; }}
[data-testid="stButtonGroup"] > div {{ justify-content:center; gap:.45rem !important; }}
[data-testid="stButtonGroup"] button {{ border-radius:999px !important; border:2px solid {c["pink_soft"]} !important; background:{c["card"]} !important;
  color:{c["text"]} !important; padding:.4rem .95rem !important; font-weight:600 !important; min-height:42px; transition:transform .15s ease; }}
[data-testid="stButtonGroup"] button:hover {{ transform:translateY(-2px); border-color:{c["pink"]} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background:linear-gradient(135deg,{c["pink"]},{c["lilac"]}) !important;
  border-color:transparent !important; color:#fff !important; box-shadow:0 6px 16px rgba(231,138,171,.3); }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color:#fff !important; }}

/* карточки итога */
.result-card {{ margin:1rem 0 .8rem; padding:1.4rem 1.3rem; border-radius:30px; text-align:center;
  background:linear-gradient(135deg,{c["card"]} 0%,{c["pink_soft"]} 55%,{c["lilac_soft"]} 100%);
  box-shadow:0 16px 40px rgba(190,140,190,.25); border:2px solid #fff; animation:pop .7s .2s cubic-bezier(.2,.9,.3,1.2) both; }}
.result-label {{ font-weight:800; font-size:.82rem; letter-spacing:.12em; text-transform:uppercase; color:{c["muted"]}; }}
.result-big {{ font-family:'Comfortaa','Nunito',system-ui,sans-serif; font-weight:700; font-size:1.5rem; line-height:1.35; margin:.4rem 0; }}
.summary {{ text-align:left; display:grid; gap:.45rem; margin-top:.8rem; }}
.summary div {{ background:rgba(255,255,255,.7); border-radius:14px; padding:.5rem .8rem; font-size:.97rem; }}
.summary b {{ color:{c["muted"]}; font-weight:700; }}
.ps {{ text-align:center; font-size:.88rem; color:{c["muted"]}; font-style:italic; margin:.6rem 0 1.2rem; }}

/* самолётик и котик-преследователь */
@keyframes hop {{ 0%,100% {{transform:translateY(0);}} 50% {{transform:translateY(-26px);}} }}
.plane {{ position:fixed; left:0; top:0; z-index:9990; cursor:pointer; filter:drop-shadow(0 6px 8px rgba(120,90,140,.25)); }}
.plane.caught {{ animation:pop .4s reverse forwards; }}
.chaser {{ position:fixed; left:0; bottom:6px; z-index:9989; pointer-events:none; }}
.chaser > svg {{ display:block; }}
.chaser > div {{ animation:hop .45s ease-in-out infinite; }}

/* дождь из котиков, подглядывающий котик, пасхалки */
.rain {{ position:fixed; inset:0; pointer-events:none; z-index:9999; overflow:hidden; }}
.rain span {{ position:absolute; top:0; font-size:2rem; animation:fall linear forwards; }}
.peek {{ position:fixed; left:18px; bottom:0; width:96px; z-index:50; cursor:pointer; line-height:0;
  transform:translateY(105%); transition:transform .55s cubic-bezier(.3,1.4,.5,1); }}
.peek.up {{ transform:translateY(30%); }}
.peek svg {{ width:100%; height:auto; }}
.peek.up:hover {{ transform:translateY(18%); }}
.paw-mark {{ position:fixed; pointer-events:none; z-index:9998; font-size:18px; animation:fadeUp .2s reverse, sparkle 1.2s ease forwards; }}
.bubble {{ position:fixed; z-index:9999; pointer-events:none; background:#fff; border:2px solid {c["pink"]}; color:{c["text"]};
  border-radius:16px; padding:.35rem .75rem; font:700 .9rem 'Nunito',sans-serif; box-shadow:0 8px 20px rgba(190,140,190,.25);
  animation:pop .35s ease both; white-space:nowrap; }}
.sparkles {{ position:relative; height:0; }}
.sparkles span {{ position:absolute; font-size:1.4rem; animation:sparkle 2.2s ease-in-out infinite; }}

@media (max-width:640px) {{
  .block-container {{ padding:1.1rem .9rem 4rem !important; }}
  .h1 {{ font-size:1.65rem; }} .h2 {{ font-size:1.2rem; }} .result-big {{ font-size:1.3rem; }}
  div[class*="st-key-opt_"] button {{ min-height:58px; padding:.55rem .6rem !important; }}
  div[class*="st-key-opt_"] button p {{ font-size:.92rem !important; line-height:1.25 !important; }}
  div[class*="st-key-opt_"] button[kind="primary"] p::after {{ content:""; }}
  .peek {{ width:72px; left:10px; }}
  .stApp::before, .stApp::after {{ font-size:32px; }}
}}
</style>""", unsafe_allow_html=True)


# JS: убегающая кнопка, клик по котику, лапки от кликов, «мяу» → дождь из котиков
JS = r"""
<script>
(function () {
  if (window.__catQuiz) return; window.__catQuiz = true;
  const doc = document;
  const CATS = ['🐱','😺','😸','😻','😼','🐈','🐾','🐈‍⬛'];

  function rain(n) {
    const box = doc.createElement('div'); box.className = 'rain';
    for (let i = 0; i < (n || 32); i++) {
      const s = doc.createElement('span');
      s.textContent = CATS[Math.floor(Math.random() * CATS.length)];
      s.style.left = Math.random() * 100 + 'vw';
      s.style.fontSize = (1.4 + Math.random() * 1.8) + 'rem';
      s.style.animationDuration = (2.6 + Math.random() * 2.6) + 's';
      s.style.animationDelay = (Math.random() * 1.4) + 's';
      box.appendChild(s);
    }
    doc.body.appendChild(box); setTimeout(() => box.remove(), 7000);
  }
  window.catRain = rain;

  function bubble(x, y, text) {
    const b = doc.createElement('div'); b.className = 'bubble'; b.textContent = text;
    b.style.left = Math.max(8, Math.min(x - 40, innerWidth - 220)) + 'px';
    b.style.top = Math.max(8, y - 54) + 'px';
    doc.body.appendChild(b); setTimeout(() => b.remove(), 1400);
  }

  // клики: лапки + реакции котиков
  const PURR = ['Мур!', 'Мяу?', 'Ещё!', 'Почеши за ушком', 'Мррр…', 'Щекотно 😹', 'Котик доволен', 'Ты нашла котика!'];
  let catClicks = 0;
  doc.addEventListener('click', (e) => {
    const p = doc.createElement('div'); p.className = 'paw-mark'; p.textContent = '🐾';
    p.style.left = (e.clientX - 9) + 'px'; p.style.top = (e.clientY - 9) + 'px';
    p.style.transform = 'rotate(' + (Math.random() * 60 - 30) + 'deg)';
    doc.body.appendChild(p); setTimeout(() => p.remove(), 1200);

    if (e.target.closest('svg.cat, .peek')) {
      catClicks++;
      if (catClicks % 7 === 0) { bubble(e.clientX, e.clientY, 'Ты нашла пасхалку! 🎉'); rain(40); }
      else bubble(e.clientX, e.clientY, PURR[Math.floor(Math.random() * PURR.length)]);
    }
  }, true);

  // набери «мяу» или «meow» → дождь из котиков
  let typed = '';
  doc.addEventListener('keydown', (e) => {
    if (!e.key || e.key.length !== 1) return;
    typed = (typed + e.key.toLowerCase()).slice(-6);
    if (typed.endsWith('мяу') || typed.endsWith('meow')) { rain(36); typed = ''; }
  }, true);

  // убегающая кнопка «Нет»
  let escapes = 0;
  const LINES = ['', 'Кнопка «Нет» сбежала 😹', 'Сбежала уже 2 раза', 'Сбежала уже 3 раза 🙀',
                 'Котик говорит, что это знак', 'Может, всё-таки «Да»? 😼'];
  function flee(btn, e) {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    escapes++;
    const r = btn.getBoundingClientRect(), pad = 16;
    const cx = e && e.touches ? e.touches[0].clientX : (e ? e.clientX : r.left);
    const cy = e && e.touches ? e.touches[0].clientY : (e ? e.clientY : r.top);
    let x, y, tries = 0;
    do {
      x = pad + Math.random() * (innerWidth - r.width - pad * 2);
      y = pad + Math.random() * (innerHeight - r.height - pad * 2);
      tries++;
    } while (Math.hypot(x + r.width / 2 - cx, y + r.height / 2 - cy) < 180 && tries < 30);
    if (btn.style.position !== 'fixed') {
      btn.style.position = 'fixed'; btn.style.left = r.left + 'px'; btn.style.top = r.top + 'px';
      btn.getBoundingClientRect();
    }
    btn.style.left = x + 'px'; btn.style.top = y + 'px';
    btn.style.transform = 'rotate(' + (Math.random() * 30 - 15) + 'deg)';
    if (escapes >= 8) btn.textContent = ['Не поймаешь 😹', 'Ну нет так нет… шучу', 'Мяу! 🙅‍♀️'][escapes % 3];
    const c = doc.getElementById('no-counter');
    if (c) c.textContent = LINES[Math.min(escapes, LINES.length - 1)] + (escapes > 5 ? ' (' + escapes + ')' : '');
    if (escapes === 12) rain(24);
  }
  doc.addEventListener('mouseover', (e) => { const b = e.target.closest && e.target.closest('#no-btn'); if (b) flee(b, e); }, true);
  doc.addEventListener('touchstart', (e) => { const b = e.target.closest && e.target.closest('#no-btn'); if (b) flee(b, e); }, {capture: true, passive: false});
  doc.addEventListener('click', (e) => { const b = e.target.closest && e.target.closest('#no-btn'); if (b) flee(b, e); }, true);
  doc.addEventListener('focusin', (e) => { if (e.target.id === 'no-btn') e.target.blur(); }, true);

  // ✈️ иногда пролетает бумажный самолётик, а котик бежит за ним
  const PLANE = '\x3csvg viewBox="0 0 64 40" width="58" height="36">\x3cpath d="M2 20 L62 4 L40 36 L30 24 Z" fill="#fff" stroke="#4A3B52" stroke-width="2.5" stroke-linejoin="round"/>\x3cpath d="M62 4 L30 24 L26 34 L22 22 Z" fill="#C9B6F2" stroke="#4A3B52" stroke-width="2.5" stroke-linejoin="round"/>\x3c/svg>';
  const CHASER = '__CHASER_SVG__';
  let flying = false, caught = 0;
  function flyPlane() {
    if (flying || document.hidden) return;
    flying = true;
    peek.classList.remove('up');
    const ltr = Math.random() < 0.5, W = innerWidth, H = innerHeight;
    const plane = doc.createElement('div'); plane.className = 'plane'; plane.innerHTML = PLANE;
    const cat = doc.createElement('div'); cat.className = 'chaser'; cat.innerHTML = '\x3cdiv>' + CHASER + '\x3c/div>';
    doc.body.appendChild(plane); doc.body.appendChild(cat);
    const baseY = H * (0.12 + Math.random() * 0.25), amp = 18 + Math.random() * 22;
    const dur = 7000 + Math.random() * 3000, lag = 900, t0 = performance.now();
    const xAt = (t) => { const k = t / dur; return ltr ? -90 + k * (W + 180) : W + 90 - k * (W + 180); };
    let done = false;
    plane.addEventListener('click', (e) => {          // пасхалка: поймай самолётик сама
      e.stopPropagation(); if (done) return; done = true; caught++;
      plane.classList.add('caught');
      bubble(e.clientX, e.clientY, caught > 2 ? 'Ты ловишь их лучше котика 😹' : 'Поймала! Котик в шоке 🙀');
      rain(18);
    });
    function frame(now) {
      const t = now - t0;
      if (!done) {
        const x = xAt(t), y = baseY + Math.sin(t / 380) * amp;
        const tilt = Math.cos(t / 380) * 14 * (ltr ? 1 : -1);
        plane.style.transform = `translate(${x}px, ${y}px) scaleX(${ltr ? 1 : -1}) rotate(${tilt}deg)`;
      }
      const cx = xAt(Math.max(0, t - lag));
      cat.style.transform = `translateX(${cx - 32}px)`;
      cat.firstElementChild.firstElementChild.style.transform = `scaleX(${ltr ? 1 : -1}) rotate(${ltr ? 12 : -12}deg)`;
      if (t < dur + lag + 200) requestAnimationFrame(frame);
      else { plane.remove(); cat.remove(); flying = false; }
    }
    requestAnimationFrame(frame);
  }
  window.flyPlane = flyPlane;
  setTimeout(function loop() { flyPlane(); setTimeout(loop, 25000 + Math.random() * 20000); }, 9000);

  // 🐱 котик выглядывает из левого нижнего угла
  const PEEK_SVG = '__PEEK_SVG__';
  const peek = doc.createElement('div'); peek.className = 'peek'; peek.innerHTML = PEEK_SVG;
  doc.body.appendChild(peek);
  let hideTimer = null;
  function peekUp(ms) {
    peek.classList.add('up');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (peek.matches(':hover')) return peekUp(1500);      // пока мышка на котике — не прячется
      peek.classList.remove('up');
    }, ms);
  }
  peek.addEventListener('click', () => peekUp(3500));      // после клика задерживается подольше
  setTimeout(function loop() {
    const finale = !!doc.querySelector('.cat-row');          // на финальном экране котиков и так много
    if (!flying && !finale && !document.hidden) peekUp(4500);
    setTimeout(loop, 11000 + Math.random() * 9000);
  }, 3500);

  // кнопка «Нет» с position:fixed не должна остаться висеть после смены экрана
  new MutationObserver(() => { if (!doc.getElementById('no-btn')) escapes = 0; })
    .observe(doc.body, {childList: true, subtree: true});
})();
</script>
"""


def html(s: str):
    st.markdown(" ".join(line.strip() for line in s.splitlines()), unsafe_allow_html=True)


def show_cat(step: int, size=140, pop=False, hint=False):
    mood, fur, acc, cap = CATS[step]
    cap_html = f'<div class="cat-caption">{cap}</div>' if cap else ""
    hint_html = '<div class="cat-hint">(котика можно погладить — просто нажми)</div>' if hint else ""
    html(f'<div class="cat-wrap{" pop" if pop else ""}">{cat_svg(mood, fur, acc, size)}{cap_html}{hint_html}</div>')


def cat_rain_html(n=28) -> str:
    rnd = random.Random(n)
    cats = ["🐱", "😺", "😸", "😻", "😼", "🐈", "🐾"]
    spans = "".join(
        f'<span style="left:{rnd.uniform(0, 96):.1f}vw; animation-duration:{rnd.uniform(2.6, 5):.2f}s; '
        f'animation-delay:{rnd.uniform(0, 1.6):.2f}s; font-size:{rnd.uniform(1.4, 3):.2f}rem">{rnd.choice(cats)}</span>'
        for _ in range(n))
    return f'<div class="rain">{spans}</div>'


def progress_bar(step: int):
    pct = (step - 1) / TOTAL_Q * 100           # 6 позиций: 5 вопросов + выбор дня
    label = f"Вопрос {step} из {TOTAL_Q}" if step <= TOTAL_Q else "Последний шаг 🗓️"
    html(f"""<div class="progress-label">{label}</div>
    <div class="progress"><span class="paw">🐾</span>
    <div class="track"><div class="fill" style="width:{pct}%"></div><span class="runner" style="left:{pct}%">🐈</span></div>
    <span class="paw">🏁</span></div>""")


def option_grid(q_name: str, options, selected_key, on_pick=set_ans):
    # контейнер с key → CSS держит 2 колонки даже на телефоне
    with st.container(key=f"grid_{q_name}"):
        for row in range(0, len(options), 2):
            cols = st.columns(2, gap="small")
            for j, (k, e, text, *_) in enumerate(options[row:row + 2]):
                with cols[j]:
                    st.button(f"{e}  {text}".strip(), key=f"opt_{q_name}_{row + j}",
                              type="primary" if selected_key == k else "secondary",
                              on_click=on_pick, args=(q_name, k), width="stretch")


def nav(step: int, next_label="Дальше →", back=True):
    st.write("")
    with st.container(key=f"grid_nav_{step}"):
        b, n = st.columns([1, 2.2], gap="small")
    with b:
        if back:
            st.button("← Назад", key=f"back_{step}", on_click=go, args=(step - 1,), width="stretch")
    with n:
        st.button(next_label, key=f"main_next_{step}", on_click=go_next, args=(step,),
                  disabled=not choice_made(step), width="stretch")
    if S.get("nudge") == step:
        html('<div class="reaction">Котик ждёт ответ в поле ✍️🐾</div>')


def reaction(text: str):
    html(f'<div class="reaction">{text}</div>' if text else '<div style="height:3rem"></div>')


# ═══════════════════════════════════════════════════════════════════
# 6. ЭКРАНЫ
# ═══════════════════════════════════════════════════════════════════

def screen_start():
    show_cat(0, size=190, pop=True, hint=True)
    hello = f"Привет, {HER_NAME} 👋<br>" if HER_NAME else ""
    html(f"""<div class="fade">
      <div class="h1">{hello}Ну что, куда идём? 🐱</div>
      <div class="sub">Давай доверим этот важный выбор маленькому котику.</div>
      <div class="muted">Он задаст пять вопросов, а потом мы выберем день. Всё серьёзно 😼</div>
    </div>""")
    st.button("Начать 🐾", key="main_start", on_click=go, args=(1,), width="stretch")


def screen_q1():
    progress_bar(1); show_cat(1, size=120)
    html('<div class="fade"><div class="h2">Для начала… что тебе больше хочется?</div><div class="muted">Котик готов к любому варианту</div></div>')
    sel = S.ans.get("format")
    option_grid("format", Q1_OPTIONS, sel, on_pick=pick_format)
    reaction(reaction_of(Q1_OPTIONS, sel) if sel else "")
    nav(1, back=False)


def pick_format(_, key):
    if S.ans.get("format") != key and (S.ans.get("format") in DESSERT_FORMATS) != (key in DESSERT_FORMATS):
        S.ans.pop("dish", None)            # список блюд поменялся → сбросить старый выбор
    S.ans["format"] = key


def screen_q2():
    sweet = S.ans.get("format") in DESSERT_FORMATS
    progress_bar(2); show_cat(2, size=120)
    title = "Выбери любимый десерт 🍰" if sweet else "Выбери любимое блюдо 🍽️"
    html(f'<div class="fade"><div class="h2">{title}</div><div class="muted">Нет в списке? Жми «Своё» и напиши сама</div></div>')
    items = (DESSERTS if sweet else DISHES) + [CUSTOM]
    options = [(x, "", x, "") for x in items]
    sel = S.ans.get("dish")
    option_grid("dish", options, sel)
    if sel == CUSTOM:
        val = text_input_compat("Что это будет?", value=S.ans.get("dish_custom", ""), key="w_dish_custom",
                            placeholder="Например: сырники, том ям, мамина паста…", max_chars=80)
        S.ans["dish_custom"] = val
        reaction(text_egg(val) or ("Котик записывает… ✍️" if val.strip() else ""))
    else:
        reaction("Котик одобряет этот выбор 😋" if sel else "")
    nav(2)


def screen_q3():
    progress_bar(3); show_cat(3, size=120)
    html('<div class="fade"><div class="h2">Есть место, куда ты давно хотела сходить, но всё никак не получалось?</div>'
         '<div class="muted">Кафе, ресторан, бар, что угодно</div></div>')
    sel = S.ans.get("dream")
    option_grid("dream", Q3_OPTIONS, sel)
    if sel == "yes":
        val = text_input_compat("Как называется это место?", value=S.ans.get("dream_text", ""), key="w_dream",
                            placeholder="Название, адрес или ссылка", max_chars=150)
        S.ans["dream_text"] = val
        reaction(text_egg(val) or ("Отличный выбор. Котик запомнил 📍" if val.strip() else reaction_of(Q3_OPTIONS, sel)))
    else:
        reaction(reaction_of(Q3_OPTIONS, sel) if sel else "")
    nav(3)


def screen_q4():
    progress_bar(4); show_cat(4, size=120)
    html('<div class="fade"><div class="h2">Очень серьёзный вопрос 🎀</div>'
         '<div class="muted">Готова доверить мне выбор заведения?</div></div>')
    sel = S.ans.get("trust")
    for i, (k, e, text, _) in enumerate(Q4_OPTIONS):
        st.button(f"{e}  {text}", key=f"opt_trust_{i}", type="primary" if sel == k else "secondary",
                  on_click=set_ans, args=("trust", k), width="stretch")
    html('<div class="no-zone"><button id="no-btn" type="button">🙅‍♀️  Нет</button></div><div id="no-counter"></div>')
    reaction(reaction_of(Q4_OPTIONS, sel) if sel else "")
    nav(4)


def screen_q5():
    progress_bar(5); show_cat(5, size=120)
    html('<div class="fade"><div class="h2">И последний вопрос 😼</div>'
         '<div class="muted">Как тебе идея, что я сделал целый сайт с котиком, чтобы позвать тебя?</div></div>')
    sel = S.ans.get("vibe")
    option_grid("vibe", Q5_OPTIONS, sel)
    reaction(reaction_of(Q5_OPTIONS, sel) if sel else "")
    if sel == "too_many":
        html(cat_rain_html())              # пасхалка: «слишком много котиков» → ещё больше котиков
    nav(5)


def screen_date():
    progress_bar(6); show_cat(6, size=110)
    html('<div class="fade"><div class="h2">Осталось выбрать день и время 🗓️</div>'
         '<div class="muted">Котик подстроится под любой вариант</div></div>')

    today = today_local()
    days = [today + timedelta(days=i) for i in range(DAYS_AHEAD)]
    html('<div class="section">📅 День</div>')
    cur_day = S.ans.get("day")
    day = st.pills("День", [d.isoformat() for d in days], selection_mode="single",
                   default=cur_day if cur_day in [d.isoformat() for d in days] else None,
                   format_func=lambda iso: day_label(date.fromisoformat(iso)),
                   key="w_day", label_visibility="collapsed")
    S.ans["day"] = day

    html('<div class="section">⏰ Время</div>')
    slot_opts = TIME_SLOTS + ["other"]
    cur_t = S.ans.get("time")
    t = st.pills("Время", slot_opts, selection_mode="single",
                 default=cur_t if cur_t in slot_opts else None,
                 format_func=lambda x: "Другое время ✍️" if x == "other" else x,
                 key="w_time", label_visibility="collapsed")
    S.ans["time"] = t
    if t == "other":
        prev = S.ans.get("time_custom")
        tv = st.time_input("Во сколько?", value=time.fromisoformat(prev) if prev else time(19, 0),
                           step=timedelta(minutes=15), key="w_time_custom")
        S.ans["time_custom"] = tv.strftime("%H:%M") if tv else ""

    if day and chosen_time():
        d = date.fromisoformat(day)
        msg = f"{day_label(d, short=False).capitalize()} в {chosen_time()}. Котик записал 🐾"
        if d.weekday() >= 5:
            msg += " Выходной — отличный выбор 😌"
        reaction(msg)
    else:
        reaction("")
    nav(6, next_label="Почти всё →")


def screen_review():
    show_cat(7, size=110)
    a = S.ans
    d = date.fromisoformat(a["day"])
    dream = a.get("dream")
    dream_txt = a.get("dream_text", "").strip() if dream == "yes" else ("секрет 🤫" if dream == "secret" else "котик удивит 😼")
    html(f"""<div class="fade"><div class="h2">Проверим, всё ли котик понял правильно?</div></div>
    <div class="result-card">
      <div class="result-label">🐾 Наш план</div>
      <div class="result-big">🗓️ {day_label(d, short=False).capitalize()} в {chosen_time()}</div>
      <div class="summary">
        <div><b>Формат:</b> {label_of(Q1_OPTIONS, a.get("format"))}</div>
        <div><b>Любимое:</b> {escape(chosen_dish())}</div>
        <div><b>Место мечты:</b> {escape(dream_txt)}</div>
        <div><b>Выбор заведения:</b> {label_of(Q4_OPTIONS, a.get("trust"))}</div>
      </div>
    </div>""")
    val = st.text_area("Хочешь что-то добавить котику? (необязательно)", value=a.get("comment", ""),
                       key="w_comment", max_chars=300, height=90, placeholder="Пожелания, уточнения, или просто «мяу»")
    S.ans["comment"] = val
    st.write("")
    with st.container(key="grid_nav_7"):
        b, n = st.columns([1, 2.2], gap="small")
    with b:
        st.button("← Назад", key="back_7", on_click=go, args=(6,), width="stretch")
    with n:
        st.button("Отправить котику 📨", key="main_submit", on_click=submit, width="stretch")


def screen_thanks():
    a = S.ans
    d = date.fromisoformat(a["day"])
    html(cat_rain_html(22))
    html("""<div class="sparkles"><span style="left:10%;top:10px">✨</span><span style="left:85%;top:30px;animation-delay:.6s">✨</span>
         <span style="left:22%;top:120px;animation-delay:1.1s">✨</span><span style="left:74%;top:115px;animation-delay:1.5s">✨</span></div>""")
    html(f'<div class="cat-row">{cat_svg("happy", "ginger", None, 96)}{cat_svg("happy", "cream", "hat", 130)}'
         f'{cat_svg("happy", "gray", None, 96)}</div>')
    html(f"""<div class="fade">
      <div class="h1">Котик всё передал 📨</div>
      <div class="sub">Значит, договорились:</div>
    </div>
    <div class="result-card"><div class="result-label">🐾 Свидание назначено</div>
      <div class="result-big">{day_label(d, short=False).capitalize()}<br>в {chosen_time()}</div>
      <div class="muted" style="margin:0">Детали котик уже передал мне 😼</div>
    </div>
    <div class="ps">P.S. Котик утверждает, что у него очень хороший вкус. И у тебя тоже.</div>""")
    if S.saved_ok is False:
        html('<div class="muted">Котик немного запутался с сохранением 🙀 Сделай, пожалуйста, скриншот этого экрана и отправь мне.</div>')
    st.button("Пройти ещё раз 🔄", key="back_restart", on_click=restart, width="stretch")


def screen_admin():
    st.markdown("### 🐾 Ответы")
    if DATA_FILE.exists():
        import pandas as pd
        df = pd.read_csv(DATA_FILE, encoding="utf-8-sig")
        st.dataframe(df, hide_index=True, width="stretch")
        st.download_button("Скачать CSV", DATA_FILE.read_bytes(), file_name="answers.csv", mime="text/csv")
    else:
        st.info("Пока ответов нет.")
    tg = "настроен ✅" if get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID") else "не настроен"
    st.caption(f"Файл: {DATA_FILE.resolve()} · Telegram: {tg}")
    if st.button("Отправить тестовое сообщение в Telegram"):
        st.success("Отправлено") if send_telegram("🐾 Тест: котик на связи!") else st.error("Не получилось — проверь токен и chat_id")


# ═══════════════════════════════════════════════════════════════════
# 7. ЗАПУСК
# ═══════════════════════════════════════════════════════════════════

inject_css()

admin_pw = get_secret("ADMIN_PASSWORD")
if admin_pw and st.query_params.get("admin") == admin_pw:
    screen_admin()
    st.stop()

# Внутри <script> не должно быть «<тегов» в строках — некоторые версии Streamlit тогда вырезают весь скрипт
def _js_str(svg: str) -> str:
    return svg.replace("<", "\\x3c")


st.html(JS.replace("__CHASER_SVG__", _js_str(cat_svg("looking", "ginger", None, 64)))
          .replace("__PEEK_SVG__", _js_str(cat_svg("looking", "gray", None, 96))),
        unsafe_allow_javascript=True)


# защита от «перепрыгивания»: если предыдущий шаг не готов — вернуть на него
for s in range(1, min(S.step, 7)):
    if not step_ready(s):
        S.step = s
        break
if S.step == 8 and not S.submitted:
    S.step = 7

SCREENS = {0: screen_start, 1: screen_q1, 2: screen_q2, 3: screen_q3, 4: screen_q4,
           5: screen_q5, 6: screen_date, 7: screen_review, 8: screen_thanks}
SCREENS[S.step]()
