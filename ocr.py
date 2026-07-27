"""
OCR для таблицы результатов Standoff 2.

Поддерживаемый формат:
1280x720 (и другие разрешения с теми же пропорциями)

CT слева:
# | Имя | Деньги | У | П | С | Счёт | Пинг

T справа:
# | Имя | Деньги | У | П | С | Счёт | Пинг

У = убийства
П = ассисты
С = смерти

Главный принцип:
не распознаём каждую маленькую цифру отдельным OCR.
Сначала получаем слова и их координаты со всей таблицы,
потом собираем строки и определяем числовые колонки по координатам.
"""

from __future__ import annotations

import io
import os
import re
from collections import Counter
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import pytesseract
    from pytesseract import Output

    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    Output = None
    OCR_AVAILABLE = False


if OCR_AVAILABLE and os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )


# ---------------------------------------------------------
# Общие функции
# ---------------------------------------------------------

def _to_pil(image: Any) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")

    if isinstance(image, (bytes, bytearray)):
        return Image.open(io.BytesIO(image)).convert("RGB")

    if isinstance(image, str):
        return Image.open(image).convert("RGB")

    raise TypeError(
        "image должен быть PIL.Image, bytes или путь к файлу"
    )


def _prepare_variants(image: Image.Image) -> list[Image.Image]:
    """
    Несколько вариантов обработки.
    Мы не выбираем один заранее: OCR работает на нескольких вариантах,
    затем результаты объединяются.
    """

    image = image.convert("RGB")

    # Увеличиваем изображение.
    enlarged = image.resize(
        (image.width * 3, image.height * 3),
        Image.Resampling.LANCZOS,
    )

    gray = ImageOps.grayscale(enlarged)
    gray = ImageOps.autocontrast(gray, cutoff=1)

    contrast = ImageEnhance.Contrast(gray).enhance(2.2)
    sharp = ImageEnhance.Sharpness(contrast).enhance(2.0)

    # Мягкий вариант — полезен для светлых цифр на тёмном фоне.
    soft = ImageEnhance.Contrast(gray).enhance(1.5)

    # Чёрно-белый вариант.
    threshold = gray.point(lambda p: 255 if p > 135 else 0)

    return [
        enlarged,
        sharp,
        soft,
        threshold,
    ]


def _normalize_token(text: str) -> str:
    text = text.strip()

    replacements = {
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
    }

    # Замены применяем только если токен почти полностью числовой.
    compact = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]", "", text)

    if compact and sum(ch.isdigit() for ch in compact) >= max(
        1, len(compact) - 1
    ):
        for old, new in replacements.items():
            text = text.replace(old, new)

    return text


def _clean_nick(text: str) -> str:
    text = re.sub(
        r"[^0-9A-Za-zА-Яа-яЁё_\-\[\] ]+",
        " ",
        text,
    )

    text = re.sub(r"\s+", " ", text).strip()

    # Убираем номер позиции.
    text = re.sub(r"^[1-5]\s+", "", text)

    # Убираем мусорные одиночные символы.
    text = re.sub(r"\s+[|Il]\s+", " ", text)

    return text.strip() or "?"


def _is_int_token(text: str) -> bool:
    text = _normalize_token(text)
    return bool(re.fullmatch(r"\d{1,5}", text))


def _int_token(text: str) -> int | None:
    text = _normalize_token(text)

    if not re.fullmatch(r"\d{1,5}", text):
        return None

    try:
        return int(text)
    except ValueError:
        return None


# ---------------------------------------------------------
# OCR data
# ---------------------------------------------------------

def _ocr_data(
    image: Image.Image,
    psm: int = 6,
) -> list[dict]:
    """
    Получает слова с координатами.
    """

    result: list[dict] = []

    for variant in _prepare_variants(image):
        try:
            data = pytesseract.image_to_data(
                variant,
                lang="rus+eng",
                config=f"--psm {psm}",
                output_type=Output.DICT,
            )
        except Exception:
            continue

        n = len(data.get("text", []))

        for i in range(n):
            text = (data["text"][i] or "").strip()

            if not text:
                continue

            try:
                confidence = float(data["conf"][i])
            except Exception:
                confidence = 0.0

            if confidence < 5:
                continue

            result.append(
                {
                    "text": text,
                    "x": int(data["left"][i]),
                    "y": int(data["top"][i]),
                    "w": int(data["width"][i]),
                    "h": int(data["height"][i]),
                    "conf": confidence,
                }
            )

    return result


def _deduplicate_words(words: list[dict]) -> list[dict]:
    """
    Убирает одинаковые слова, которые OCR получил в разных вариантах.
    """

    grouped: dict[tuple, list[dict]] = {}

    for word in words:
        text = _normalize_token(word["text"]).lower()

        # Координаты здесь после масштабирования могут немного отличаться.
        key = (
            text,
            round(word["x"] / 15),
            round(word["y"] / 15),
        )

        grouped.setdefault(key, []).append(word)

    result = []

    for group in grouped.values():
        best = max(group, key=lambda x: x["conf"])
        result.append(best)

    return result


def _group_into_lines(words: list[dict]) -> list[list[dict]]:
    """
    Собирает OCR-слова в строки по вертикальной координате.
    """

    if not words:
        return []

    words = sorted(
        words,
        key=lambda x: (
            x["y"] + x["h"] / 2,
            x["x"],
        ),
    )

    lines: list[list[dict]] = []

    for word in words:
        cy = word["y"] + word["h"] / 2

        best_line = None
        best_distance = None

        for line in lines:
            line_cy = sum(
                w["y"] + w["h"] / 2
                for w in line
            ) / len(line)

            distance = abs(cy - line_cy)

            # В увеличенном изображении высота строки около 100-150 px.
            if distance <= max(35, word["h"] * 1.8):
                if best_distance is None or distance < best_distance:
                    best_line = line
                    best_distance = distance

        if best_line is None:
            lines.append([word])
        else:
            best_line.append(word)

    for line in lines:
        line.sort(key=lambda x: x["x"])

    lines.sort(
        key=lambda line: min(w["y"] for w in line)
    )

    return lines


# ---------------------------------------------------------
# Счёт матча
# ---------------------------------------------------------

def _parse_match_score(image: Image.Image) -> str | None:
    """
    Счёт находится в центральной верхней части.
    """

    w, h = image.size

    crops = [
        image.crop(
            (
                int(w * 0.40),
                int(h * 0.10),
                int(w * 0.60),
                int(h * 0.29),
            )
        ),
        image.crop(
            (
                int(w * 0.30),
                int(h * 0.05),
                int(w * 0.70),
                int(h * 0.32),
            )
        ),
    ]

    candidates: list[str] = []

    for crop in crops:
        for variant in _prepare_variants(crop):
            try:
                text = pytesseract.image_to_string(
                    variant,
                    config=(
                        "--psm 6 "
                        "-c tessedit_char_whitelist=0123456789:"
                    ),
                )
            except Exception:
                continue

            nums = re.findall(r"\d{1,2}", text)

            if len(nums) >= 2:
                for i in range(len(nums) - 1):
                    a = int(nums[i])
                    b = int(nums[i + 1])

                    if 0 <= a <= 30 and 0 <= b <= 30:
                        candidates.append(f"{a}:{b}")

    if not candidates:
        return None

    return Counter(candidates).most_common(1)[0][0]


# ---------------------------------------------------------
# Парсинг одной команды
# ---------------------------------------------------------

def _team_geometry(
    image: Image.Image,
    side: str,
) -> tuple[int, int, int, int]:
    """
    Возвращает область команды.

    В оригинале 1280x720:
    таблица игроков примерно y=180..410.

    После OCR изображение увеличивается в 3 раза,
    поэтому ниже всё сначала задаётся в координатах оригинала,
    а затем масштабируется.
    """

    w, h = image.size

    # Реальные границы таблицы.
    y1 = int(h * 0.245)
    y2 = int(h * 0.615)

    if side == "CT":
        x1 = 0
        x2 = int(w * 0.50)
    else:
        x1 = int(w * 0.50)
        x2 = w

    return x1, y1, x2, y2


def _parse_team(
    image: Image.Image,
    side: str,
) -> tuple[list[dict], str]:
    """
    Важная часть.

    Мы распознаём всю половину таблицы одним OCR,
    а не 25 раз отдельные цифры.

    Затем:
    1. находим строки;
    2. находим в строке числовые токены;
    3. последние 5 чисел — статистика:
       kills, assists, deaths, score, ping;
    4. число перед ними с 4-5 цифрами — деньги;
    5. текст слева — ник.
    """

    x1, y1, x2, y2 = _team_geometry(
        image,
        side,
    )

    # Небольшое перекрытие центра полезно для T.
    crop = image.crop((x1, y1, x2, y2))

    all_words: list[dict] = []

    # PSM 6 — блок текста.
    all_words.extend(_ocr_data(crop, psm=6))

    # PSM 11 — разреженный текст.
    all_words.extend(_ocr_data(crop, psm=11))

    words = _deduplicate_words(all_words)
    lines = _group_into_lines(words)

    rows: list[dict] = []
    raw_lines: list[str] = []

    for line in lines:
        if not line:
            continue

        line_text = " ".join(
            w["text"]
            for w in line
        )

        raw_lines.append(line_text)

        numeric: list[tuple[dict, int]] = []

        for word in line:
            value = _int_token(word["text"])

            if value is not None:
                numeric.append((word, value))

        # В строке игрока должно быть минимум:
        # 5 статистик + желательно деньги.
        if len(numeric) < 5:
            continue

        # Статистика всегда последние 5 числовых полей.
        stat_items = numeric[-5:]

        kills = stat_items[0][1]
        assists = stat_items[1][1]
        deaths = stat_items[2][1]
        score = stat_items[3][1]
        ping = stat_items[4][1]

        # Проверка диапазонов.
        if not (
            0 <= kills <= 60
            and 0 <= assists <= 60
            and 0 <= deaths <= 60
            and 0 <= score <= 300
            and 0 <= ping <= 999
        ):
            continue

        # Деньги — ближайшее число перед статистикой,
        # обычно 3-5 цифр и >= 1000.
        money = None

        for word, value in reversed(
            numeric[:-5]
        ):
            if 1000 <= value <= 99999:
                money = value
                break

        # Все слова до первого статистического поля.
        first_stat_x = stat_items[0][0]["x"]

        nick_words = [
            w["text"]
            for w in line
            if w["x"] < first_stat_x
            and not _is_int_token(w["text"])
        ]

        nick = _clean_nick(
            " ".join(nick_words)
        )

        # Если OCR не распознал ник, строка всё равно сохраняется.
        # Это лучше, чем полностью терять статистику.
        rows.append(
            {
                "side": side,
                "nick": nick,
                "money": money,
                "kills": kills,
                "assists": assists,
                "deaths": deaths,
                "score": score,
                "ping": ping,
            }
        )

    # Убираем дубли строк, появившиеся из-за двух OCR-режимов.
    unique: list[dict] = []
    seen: set[tuple] = set()

    for row in rows:
        key = (
            row["kills"],
            row["assists"],
            row["deaths"],
            row["score"],
            row["ping"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(row)

    # Таблица может содержать максимум 5 игроков.
    return unique[:5], "\n".join(raw_lines)


# ---------------------------------------------------------
# Основной API
# ---------------------------------------------------------

def parse_standoff_scoreboard(image: Any) -> dict:
    if not OCR_AVAILABLE:
        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {
                "left": "",
                "right": "",
            },
            "error": "pytesseract не установлен",
        }

    try:
        img = _to_pil(image)
    except Exception as e:
        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {
                "left": "",
                "right": "",
            },
            "error": f"Не удалось открыть изображение: {e}",
        }

    try:
        score = _parse_match_score(img)

        ct, raw_ct = _parse_team(
            img,
            "CT",
        )

        tt, raw_t = _parse_team(
            img,
            "T",
        )

        return {
            "score": score,
            "ct": ct,
            "t": tt,
            "raw": {
                "left": raw_ct,
                "right": raw_t,
            },
        }

    except Exception as e:
        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {
                "left": "",
                "right": "",
            },
            "error": f"OCR ошибка: {e}",
        }


# ---------------------------------------------------------
# Совместимость со старым API
# ---------------------------------------------------------

def ocr_match_result(image_input):
    result = parse_standoff_scoreboard(image_input)

    players = []

    for player in result["ct"] + result["t"]:
        players.append(
            {
                "nickname": player["nick"],
                "kills": player["kills"],
                "deaths": player["deaths"],
                "assists": player["assists"],
                "score": player["score"],
            }
        )

    return {
        "raw_text": (
            result["raw"]["left"]
            + "\n"
            + result["raw"]["right"]
        ),
        "match_score": result["score"],
        "players": players,
    }


# ---------------------------------------------------------
# Локальная проверка
# ---------------------------------------------------------

if __name__ == "__main__":
    import sys

    if not sys.argv[1:]:
        print(
            "Использование: python ocr.py screenshot.png"
        )
        raise SystemExit(0)

    for path in sys.argv[1:]:
        print(f"\n{'=' * 60}")
        print(path)
        print(f"{'=' * 60}")

        result = parse_standoff_scoreboard(path)

        print("Счёт:", result["score"])
        print("Ошибка:", result.get("error"))

        for side in ("ct", "t"):
            print(f"\n{side.upper()}:")

            for player in result[side]:
                print(
                    f"{player['nick']} | "
                    f"{player['kills']}/"
                    f"{player['assists']}/"
                    f"{player['deaths']} | "
                    f"score={player['score']} | "
                    f"ping={player['ping']} | "
                    f"money={player['money']}"
                )

        print("\nRAW CT:")
        print(result["raw"]["left"])

        print("\nRAW T:")
        print(result["raw"]["right"])
