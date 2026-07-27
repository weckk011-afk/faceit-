"""
OCR scoreboard Standoff 2 (мобильный клиент, ландшафтная ориентация).

Распознаёт:
- команды CT / T;
- никнеймы;
- деньги;
- Убийства / Смерти / Ассисты;
- Score / рейтинг;
- Ping;
- счёт матча.

Для скриншотов Standoff 2 важно: таблица находится примерно в центральной
части изображения, поэтому используется несколько вариантов OCR и
пространственная привязка колонок.
"""
from __future__ import annotations

import io
import os
import re
from typing import Any

from PIL import Image, ImageOps, ImageEnhance, ImageFilter

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


HEADER_WORDS = (
    "имя", "деньги", "счёт", "счет", "пинг", "оборона", "атака",
    "турнир", "овертайм", "россия", "кастом", "наблюдател",
    "соревнователь", "время", "раунд",
)

NUM_RE = re.compile(r"^\d{1,5}$")


def _to_pil(image: Any) -> Image.Image:
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, (bytes, bytearray)):
        return Image.open(io.BytesIO(image))
    if isinstance(image, str):
        return Image.open(image)
    raise TypeError("image должен быть PIL.Image, bytes или путём к файлу")


def _preprocess(img: Image.Image, scale: int = 3) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    img = img.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.8)
    gray = ImageEnhance.Sharpness(gray).enhance(2.0)
    return gray


def _ocr_data(img: Image.Image, psm: int = 6):
    pre = _preprocess(img)
    return pytesseract.image_to_data(
        pre,
        lang="rus+eng",
        config=f"--psm {psm}",
        output_type=Output.DICT,
    )


def _ocr_text(img: Image.Image, psm: int = 6) -> str:
    return pytesseract.image_to_string(
        _preprocess(img),
        lang="rus+eng",
        config=f"--psm {psm}",
    )


def _group_words_by_line(data: dict) -> list[list[dict]]:
    words = []
    for i, txt in enumerate(data.get("text", [])):
        txt = (txt or "").strip()
        if not txt:
            continue

        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1

        # Не выкидываем низкую confidence полностью: игровой шрифт часто
        # распознаётся Tesseract с низкой уверенностью.
        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])

        words.append({
            "text": txt,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "cy": y + h / 2,
            "conf": conf,
        })

    if not words:
        return []

    words.sort(key=lambda x: x["cy"])
    median_h = sorted(w["h"] for w in words)[len(words) // 2]
    y_tol = max(10, median_h * 0.75)

    lines = []
    current = []
    current_y = None

    for word in words:
        if current_y is None or abs(word["cy"] - current_y) <= y_tol:
            current.append(word)
            current_y = (
                word["cy"] if current_y is None
                else (current_y * 0.6 + word["cy"] * 0.4)
            )
        else:
            lines.append(sorted(current, key=lambda x: x["x"]))
            current = [word]
            current_y = word["cy"]

    if current:
        lines.append(sorted(current, key=lambda x: x["x"]))

    return lines


def _normalise_number(s: str) -> str:
    s = s.strip()
    replacements = {
        "O": "0", "o": "0", "О": "0", "о": "0",
        "I": "1", "l": "1", "|": "1",
        "S": "5", "s": "5",
    }
    return "".join(replacements.get(ch, ch) for ch in s)


def _numbers_from_line(line: list[dict]) -> list[tuple[dict, int]]:
    result = []

    for word in line:
        raw = word["text"].strip()
        raw = re.sub(r"[$€₽₴БбSs§]+$", "", raw)
        raw = _normalise_number(raw)

        # OCR иногда склеивает цифры с мусором.
        match = re.search(r"\d{1,5}", raw)
        if not match:
            continue

        try:
            value = int(match.group())
        except ValueError:
            continue

        result.append((word, value))

    return result


def _clean_nick(raw: str) -> str:
    raw = raw.replace("|", "I")
    raw = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_\-\[\] ]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    # Удаляем случайные одиночные мусорные символы, но не удаляем цифры:
    # в Standoff 2 ники часто содержат цифры.
    raw = re.sub(r"(?<!\S)[А-Яа-яA-Za-z](?=\s|$)", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" _-")

    return raw or "?"


def _parse_row(line: list[dict], side: str) -> dict | None:
    if not line:
        return None

    joined = " ".join(w["text"] for w in line).lower()

    if any(header in joined for header in HEADER_WORDS):
        return None

    nums = _numbers_from_line(line)

    # В строке игрока должны присутствовать деньги + 5 статистических чисел.
    if len(nums) < 5:
        return None

    # Деньги обычно находятся перед статистикой и имеют 4-5 цифр.
    money_index = None
    for i, (_, value) in enumerate(nums):
        if 1000 <= value <= 99999:
            money_index = i
            break

    if money_index is None:
        # Иногда деньги OCR распознаются неправильно. Тогда берём последние
        # пять чисел как статистику.
        stat = nums[-5:]
        money = None
    else:
        money = nums[money_index][1]
        stat = nums[money_index + 1:]

        if len(stat) < 5:
            return None

        stat = stat[:5]

    # На скриншоте Standoff 2 порядок:
    # У = kills, П = deaths, С = assists, Score, Ping.
    kills, deaths, assists, score, ping = [v for _, v in stat]

    if not (0 <= kills <= 60):
        return None
    if not (0 <= deaths <= 60):
        return None
    if not (0 <= assists <= 60):
        return None
    if not (0 <= score <= 300):
        return None
    if not (0 <= ping <= 999):
        return None

    first_stat_x = stat[0][0]["x"]

    nick_words = []
    for word in line:
        if word["x"] < first_stat_x:
            raw = _normalise_number(word["text"])
            if not re.fullmatch(r"\d{1,5}", raw):
                nick_words.append(word["text"])

    nick = _clean_nick(" ".join(nick_words))

    # Слишком короткие/мусорные строки не считаем игроками.
    if nick == "?" and money is None:
        return None

    return {
        "side": side,
        "nick": nick,
        "money": money,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "score": score,
        "ping": ping,
    }


def _deduplicate(rows: list[dict]) -> list[dict]:
    result = []
    seen = set()

    for row in rows:
        key = (
            row["nick"].lower(),
            row["kills"],
            row["deaths"],
            row["assists"],
            row["score"],
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(row)

    return result[:5]


def _ocr_table(table: Image.Image, side: str) -> tuple[list[dict], str]:
    all_rows = []
    raw_texts = []

    # Несколько вариантов PSM повышают шанс распознавания игрового шрифта.
    for psm in (6, 11):
        try:
            data = _ocr_data(table, psm=psm)
            lines = _group_words_by_line(data)

            for line in lines:
                row = _parse_row(line, side)
                if row:
                    all_rows.append(row)

            raw_texts.append(_ocr_text(table, psm=psm))
        except Exception:
            continue

    return _deduplicate(all_rows), "\n".join(raw_texts)


def _parse_score(img: Image.Image) -> str | None:
    W, H = img.size

    # Счёт находится сверху по центру. Берём несколько вариантов области.
    crops = [
        img.crop((int(W * 0.35), int(H * 0.12), int(W * 0.65), int(H * 0.36))),
        img.crop((int(W * 0.40), int(H * 0.16), int(W * 0.60), int(H * 0.32))),
        img.crop((int(W * 0.30), int(H * 0.08), int(W * 0.70), int(H * 0.40))),
    ]

    for crop in crops:
        for psm in (6, 7, 11):
            try:
                text = pytesseract.image_to_string(
                    _preprocess(crop, scale=4),
                    config=f"--psm {psm} -c tessedit_char_whitelist=0123456789:",
                )

                nums = re.findall(r"\d{1,2}", text)
                if len(nums) >= 2:
                    a, b = int(nums[0]), int(nums[1])
                    if 0 <= a <= 30 and 0 <= b <= 30:
                        return f"{a}:{b}"
            except Exception:
                pass

    return None


def parse_standoff_scoreboard(image: Any) -> dict:
    if not OCR_AVAILABLE:
        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {"left": "", "right": ""},
            "error": "pytesseract не установлен",
        }

    try:
        img = _to_pil(image).convert("RGB")
    except Exception as e:
        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {"left": "", "right": ""},
            "error": f"невозможно открыть изображение: {e}",
        }

    W, H = img.size

    # В скриншоте пользователя таблица занимает примерно 40-70% высоты.
    # Делаем несколько вариантов вертикального crop, чтобы не потерять строки.
    table_crops = [
        img.crop((0, int(H * 0.34), W, int(H * 0.78))),
        img.crop((0, int(H * 0.30), W, int(H * 0.82))),
        img.crop((0, int(H * 0.38), W, int(H * 0.74))),
    ]

    ct_rows = []
    t_rows = []
    raw_left = []
    raw_right = []

    for table in table_crops:
        bw, bh = table.size

        # В таблице команды находятся слева и справа.
        # Делаем небольшой overlap, чтобы не обрезать длинные ники.
        left = table.crop((0, 0, int(bw * 0.56), bh))
        right = table.crop((int(bw * 0.44), 0, bw, bh))

        ct, ct_raw = _ocr_table(left, "CT")
        tt, t_raw = _ocr_table(right, "T")

        ct_rows.extend(ct)
        t_rows.extend(tt)
        raw_left.append(ct_raw)
        raw_right.append(t_raw)

        if len(ct_rows) >= 5 and len(t_rows) >= 5:
            break

    ct_rows = _deduplicate(ct_rows)
    t_rows = _deduplicate(t_rows)

    score = _parse_score(img)

    return {
        "score": score,
        "ct": ct_rows,
        "t": t_rows,
        "raw": {
            "left": "\n".join(raw_left),
            "right": "\n".join(raw_right),
        },
    }


def ocr_match_result(image_input):
    r = parse_standoff_scoreboard(image_input)

    players = []
    for p in r["ct"] + r["t"]:
        players.append({
            "nickname": p["nick"],
            "kills": p["kills"],
            "deaths": p["deaths"],
            "assists": p["assists"],
            "score": p["score"],
        })

    return {
        "raw_text": r["raw"]["left"] + "\n" + r["raw"]["right"],
        "match_score": r["score"],
        "players": players,
    }


if __name__ == "__main__":
    import sys

    for path in sys.argv[1:]:
        print(f"\n════ {path} ════")

        result = parse_standoff_scoreboard(path)

        print(f"Счёт: {result['score']}")

        for side in ("ct", "t"):
            print(f"{side.upper()} ({len(result[side])}):")

            for p in result[side]:
                money = f"${p['money']}" if p["money"] else "—"

                print(
                    f"  {p['nick']:<28} "
                    f"{money:>7} "
                    f"У={p['kills']:>2} "
                    f"П={p['deaths']:>2} "
                    f"С={p['assists']:>2} "
                    f"Счёт={p['score']:>3} "
                    f"Пинг={p['ping']}"
                )
