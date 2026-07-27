"""
OCR scoreboard Standoff 2 (мобильный клиент, ландшафтная ориентация).
Две команды (ОБОРОНА CT / АТАКА T), колонки: Деньги | У | П | С | Счёт | Пинг.
"""
from __future__ import annotations

import io
import os
import re
from typing import Any

from PIL import Image, ImageOps

try:
    import pytesseract
    from pytesseract import Output
    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    Output = None
    OCR_AVAILABLE = False

if OCR_AVAILABLE and os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

_NUM_RE   = re.compile(r"^\d+$")
_MONEY_RE = re.compile(r"^\d{3,5}[\$5Ss§]?$")

_HEADER_KEYWORDS = (
    "имя", "деньги", "счет", "счёт", "пинг",
    "оборона", "атака", "турнир", "овертайм",
    "россия", "кастомн", "наблюдател", "соревнователь",
)


def _to_pil(image: Any) -> Image.Image:
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, (bytes, bytearray)):
        return Image.open(io.BytesIO(image))
    if isinstance(image, str):
        return Image.open(image)
    raise TypeError("image должен быть PIL.Image, bytes или путём к файлу")


def _preprocess(img: Image.Image, scale: int = 2) -> Image.Image:
    w, h = img.size
    out = img.convert("L").resize((w * scale, h * scale), Image.LANCZOS)
    out = ImageOps.autocontrast(out, cutoff=2)
    return out


def _clean_nick(raw: str) -> str:
    s = re.sub(r"[^\wА-Яа-яЁё\[\]\-_ ]+", " ", raw, flags=re.UNICODE)
    s = re.sub(r"^\s*\d+\s+", "", s)
    s = re.sub(r"\b[a-zA-Zа-яА-Я]\b(?=\s|$)", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" _-*")
    return s


def _group_words_by_line(data: dict) -> list[list[dict]]:
    words = []
    n = len(data["text"])
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append({"text": txt, "x": x, "y": y, "w": w, "h": h, "cy": y + h / 2})
    if not words:
        return []
    words.sort(key=lambda w: w["cy"])
    heights = sorted(w["h"] for w in words)
    y_tol = max(6, heights[len(heights) // 2] * 0.6)
    lines, cur, cur_cy = [], [], None
    for w in words:
        if cur_cy is None or abs(w["cy"] - cur_cy) <= y_tol:
            cur.append(w)
            cur_cy = (cur_cy or w["cy"]) * 0.5 + w["cy"] * 0.5
        else:
            lines.append(sorted(cur, key=lambda x: x["x"]))
            cur = [w]; cur_cy = w["cy"]
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x"]))
    return lines


def _parse_row(line_words: list[dict], side: str) -> dict | None:
    joined = " ".join(w["text"] for w in line_words).lower()
    if any(k in joined for k in _HEADER_KEYWORDS):
        return None

    nums: list[tuple[dict, int]] = []
    for w in line_words:
        t = w["text"]
        t_clean = re.sub(r"[\$5Ss§]+$", "", t) if _MONEY_RE.match(t) else t
        if _NUM_RE.match(t_clean):
            nums.append((w, int(t_clean)))
    if len(nums) < 5:
        return None

    money = None
    small: list[tuple[dict, int]] = []
    for w, n in nums:
        if n >= 1000:
            money = n
        else:
            small.append((w, n))
    if len(small) < 5:
        return None

    stat_words = small[-5:]
    k, a, d, score, ping = (v for _, v in stat_words)

    if not (0 <= k <= 60 and 0 <= a <= 60 and 0 <= d <= 60
            and 0 <= score <= 300 and 0 <= ping <= 999):
        return None

    x_cut = stat_words[0][0]["x"]
    nick_raw = " ".join(
        w["text"] for w in line_words
        if w["x"] < x_cut and not _NUM_RE.match(re.sub(r"[\$5Ss§]+$", "", w["text"]))
    )
    nick = _clean_nick(nick_raw) or "?"

    return {
        "side": side, "nick": nick, "money": money,
        "kills": k, "assists": a, "deaths": d,
        "score": score, "ping": ping,
    }


def _ocr_side(img: Image.Image, side: str) -> tuple[list[dict], str]:
    pre = _preprocess(img)
    data = pytesseract.image_to_data(pre, lang="rus+eng", config="--psm 6",
                                     output_type=Output.DICT)
    raw_text = pytesseract.image_to_string(pre, lang="rus+eng", config="--psm 6")
    lines = _group_words_by_line(data)

    rows = []
    for line in lines:
        row = _parse_row(line, side)
        if row:
            rows.append(row)

    dedup, seen = [], set()
    for r in rows:
        key = (r["kills"], r["assists"], r["deaths"], r["score"], r["ping"])
        if key in seen:
            continue
        seen.add(key); dedup.append(r)
    return dedup[:5], raw_text


def _parse_match_score(img: Image.Image) -> str | None:
    W, H = img.size
    top = img.crop((int(W * 0.40), int(H * 0.19), int(W * 0.60), int(H * 0.32)))
    pre = _preprocess(top, scale=3)
    txt = pytesseract.image_to_string(
        pre,
        config="--psm 6 -c tessedit_char_whitelist=0123456789 ",
    )
    nums = re.findall(r"\d{1,2}", txt)
    if len(nums) >= 2:
        return f"{nums[0]}:{nums[1]}"
    return None


def parse_standoff_scoreboard(image: Any) -> dict:
    if not OCR_AVAILABLE:
        return {"score": None, "ct": [], "t": [],
                "raw": {"left": "", "right": ""},
                "error": "pytesseract не установлен"}
    try:
        img = _to_pil(image).convert("RGB")
    except Exception as e:
        return {"score": None, "ct": [], "t": [],
                "raw": {"left": "", "right": ""},
                "error": f"невозможно открыть изображение: {e}"}

    W, H = img.size
    band  = img.crop((0, int(H * 0.20), W, int(H * 0.72)))
    bw, bh = band.size
    left  = band.crop((0,              0, int(bw * 0.52), bh))
    right = band.crop((int(bw * 0.48), 0, bw,             bh))

    try:
        ct, ct_raw = _ocr_side(left,  "CT")
        tt, t_raw  = _ocr_side(right, "T")
        score = _parse_match_score(img)
    except Exception as e:
        return {"score": None, "ct": [], "t": [],
                "raw": {"left": "", "right": ""},
                "error": f"OCR ошибка: {e}"}

    return {"score": score, "ct": ct, "t": tt,
            "raw": {"left": ct_raw, "right": t_raw}}


# Совместимость со старым API
def ocr_match_result(image_input):
    r = parse_standoff_scoreboard(image_input)
    players = []
    for p in r["ct"] + r["t"]:
        players.append({
            "nickname": p["nick"],
            "kills":   p["kills"],
            "deaths":  p["deaths"],
            "assists": p["assists"],
            "score":   p["score"],
        })
    return {
        "raw_text": (r["raw"]["left"] + "\n" + r["raw"]["right"]),
        "match_score": r["score"],
        "players": players,
    }


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        print(f"\n════ {path} ════")
        res = parse_standoff_scoreboard(path)
        print(f"Счёт: {res['score']}")
        for side in ("ct", "t"):
            print(f"{side.upper()} ({len(res[side])}):")
            for p in res[side]:
                m = f"${p['money']}" if p['money'] else "  —  "
                print(f"  {p['nick']:<28} {m:>7} "
                      f"У={p['kills']:>2} П={p['assists']:>2} С={p['deaths']:>2} "
                      f"Счёт={p['score']:>3} Пинг={p['ping']}")
