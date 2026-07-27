"""
Standoff 2 Scoreboard OCR
Resolution: 2448x1080

Распознаёт:
- карту
- счёт
- 5 CT игроков
- 5 T игроков
- K / A / D / Score / Ping
"""

from __future__ import annotations

import io
import os
import re
from difflib import SequenceMatcher
from typing import Any

from PIL import Image, ImageOps, ImageFilter


# ============================================================
# TESSERACT
# ============================================================

try:
    import pytesseract
    from pytesseract import Output

    OCR_AVAILABLE = True

except ImportError:

    pytesseract = None
    Output = None
    OCR_AVAILABLE = False


if OCR_AVAILABLE and os.name == "nt":

    paths = [

        r"C:\Program Files\Tesseract-OCR\tesseract.exe",

        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",

    ]

    for path in paths:

        if os.path.exists(path):

            pytesseract.pytesseract.tesseract_cmd = path

            break


# ============================================================
# MAPS
# ============================================================

MAPS = [

    "Dune",

    "Hanami",

    "Province",

    "Prison",

    "Sandstone",

    "Breeze",

    "Rust",

]


MAP_ALIASES = {

    "dune": "Dune",
    "dun": "Dune",
    "dunc": "Dune",
    "dunee": "Dune",

    "hanami": "Hanami",
    "hanam": "Hanami",
    "hanam1": "Hanami",

    "province": "Province",
    "provin": "Province",
    "provinc": "Province",

    "prison": "Prison",
    "pris0n": "Prison",
    "pr1son": "Prison",
    "priso": "Prison",

    "sandstone": "Sandstone",
    "sandston": "Sandstone",
    "sandst0ne": "Sandstone",

    "breeze": "Breeze",
    "breez": "Breeze",
    "breese": "Breeze",

    "rust": "Rust",
    "rus": "Rust",

}


# ============================================================
# IMAGE
# ============================================================

def _to_pil(
    image: Any
) -> Image.Image:

    if isinstance(
        image,
        Image.Image
    ):

        return image

    if isinstance(
        image,
        bytes
    ):

        return Image.open(
            io.BytesIO(image)
        )

    if isinstance(
        image,
        str
    ):

        return Image.open(
            image
        )

    raise TypeError(
        "Unsupported image type"
    )


def _prepare(
    image: Image.Image,
    scale: int = 3,
    threshold: int | None = None
) -> Image.Image:

    image = image.convert(
        "L"
    )

    w, h = image.size

    image = image.resize(
        (
            w * scale,
            h * scale
        ),
        Image.Resampling.LANCZOS
    )

    image = ImageOps.autocontrast(
        image
    )

    image = image.filter(
        ImageFilter.SHARPEN
    )

    if threshold is not None:

        image = image.point(
            lambda p:
            255 if p > threshold else 0
        )

    return image


# ============================================================
# OCR WORDS
# ============================================================

def _ocr_data(
    image: Image.Image,
    psm: int = 6
) -> dict:

    if not OCR_AVAILABLE:

        return {}

    try:

        return pytesseract.image_to_data(
            image,
            lang="eng+rus",
            config=f"--psm {psm}",
            output_type=Output.DICT
        )

    except Exception:

        return {}


def _words_from_data(
    data: dict
) -> list[dict]:

    words = []

    if not data:

        return words

    texts = data.get(
        "text",
        []
    )

    for i in range(
        len(texts)
    ):

        text = str(
            texts[i]
        ).strip()

        if not text:

            continue

        try:

            x = int(
                data["left"][i]
            )

            y = int(
                data["top"][i]
            )

            w = int(
                data["width"][i]
            )

            h = int(
                data["height"][i]
            )

        except Exception:

            continue

        words.append({

            "text": text,

            "x": x,

            "y": y,

            "w": w,

            "h": h,

            "cx": x + w / 2,

            "cy": y + h / 2,

        })

    return words


# ============================================================
# HORIZONTAL ROW DETECTION
# ============================================================

def _find_rows(
    image: Image.Image
) -> list[tuple[int, int]]:

    """
    Находит горизонтальные строки по OCR-словам.

    Возвращает список:
    [
        (y1, y2),
        ...
    ]
    """

    prepared = _prepare(
        image,
        scale=2
    )

    data = _ocr_data(
        prepared,
        psm=6
    )

    words = _words_from_data(
        data
    )

    if not words:

        return []

    # Возвращаем координаты к исходному размеру
    scale = 2

    centers = []

    for word in words:

        y = word["cy"] / scale

        h = word["h"] / scale

        centers.append(
            (
                y,
                h
            )
        )

    centers.sort(
        key=lambda x: x[0]
    )

    groups = []

    current = []

    current_y = None

    for y, h in centers:

        if current_y is None:

            current = [
                (
                    y,
                    h
                )
            ]

            current_y = y

            continue

        tolerance = max(
            20,
            h * 1.4
        )

        if abs(
            y - current_y
        ) <= tolerance:

            current.append(
                (
                    y,
                    h
                )
            )

            current_y = sum(
                x[0]
                for x in current
            ) / len(
                current
            )

        else:

            groups.append(
                current
            )

            current = [
                (
                    y,
                    h
                )
            ]

            current_y = y

    if current:

        groups.append(
            current
        )

    rows = []

    for group in groups:

        if not group:

            continue

        center = sum(
            x[0]
            for x in group
        ) / len(
            group
        )

        height = max(
            x[1]
            for x in group
        )

        y1 = int(
            center - height * 1.7
        )

        y2 = int(
            center + height * 1.7
        )

        rows.append(
            (
                max(
                    0,
                    y1
                ),
                min(
                    image.height,
                    y2
                )
            )
        )

    return rows


# ============================================================
# NUMBER PARSING
# ============================================================

def _number(
    text: str
) -> int | None:

    text = text.strip()

    if not text:

        return None

    replacements = {

        "O": "0",
        "o": "0",

        "I": "1",
        "l": "1",

        "S": "5",
        "s": "5",

        "B": "8",

    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new
        )

    text = re.sub(
        r"[^0-9]",
        "",
        text
    )

    if not text:

        return None

    try:

        return int(
            text
        )

    except ValueError:

        return None


# ============================================================
# PLAYER ROW OCR
# ============================================================

def _parse_player_row(
    row: Image.Image,
    side: str
) -> dict | None:

    """
    Отдельно читает одну строку игрока.
    """

    variants = [

        _prepare(
            row,
            scale=3
        ),

        _prepare(
            row,
            scale=4,
            threshold=150
        ),

        _prepare(
            row,
            scale=4,
            threshold=190
        ),

    ]

    candidates = []

    for prepared in variants:

        data = _ocr_data(
            prepared,
            psm=7
        )

        words = _words_from_data(
            data
        )

        if not words:

            continue

        words.sort(
            key=lambda x: x["x"]
        )

        numbers = []

        for word in words:

            value = _number(
                word["text"]
            )

            if value is None:

                continue

            numbers.append(
                (
                    word["x"],
                    value
                )
            )

        if len(
            numbers
        ) < 5:

            continue

        # Берём статистические числа.
        # Деньги обычно находятся левее K/A/D,
        # поэтому ищем последние 5.
        stats = numbers[-5:]

        kills = stats[0][1]

        assists = stats[1][1]

        deaths = stats[2][1]

        score = stats[3][1]

        ping = stats[4][1]

        if kills > 60:

            continue

        if assists > 60:

            continue

        if deaths > 60:

            continue

        if score > 300:

            continue

        if ping > 999:

            continue

        first_stat_x = stats[0][0]

        nickname_parts = []

        for word in words:

            if word["x"] < first_stat_x:

                text = word["text"]

                if "$" in text:

                    continue

                nickname_parts.append(
                    text
                )

        nickname = " ".join(
            nickname_parts
        ).strip()

        nickname = re.sub(
            r"[^A-Za-zА-Яа-яЁё0-9_\-\[\]]",
            "",
            nickname
        )

        if not nickname:

            nickname = "?"

        candidates.append({

            "side": side,

            "nick": nickname,

            "money": None,

            "kills": kills,

            "assists": assists,

            "deaths": deaths,

            "score": score,

            "ping": ping,

        })

    if not candidates:

        return None

    # Выбираем самый часто повторяющийся вариант
    groups = {}

    for candidate in candidates:

        key = (

            candidate["kills"],

            candidate["assists"],

            candidate["deaths"],

            candidate["score"],

        )

        groups.setdefault(
            key,
            []
        ).append(
            candidate
        )

    best_key = max(
        groups,
        key=lambda key:
        len(
            groups[key]
        )
    )

    return groups[
        best_key
    ][0]


# ============================================================
# SIDE PARSER
# ============================================================

def _parse_side(
    board: Image.Image,
    side: str
) -> list[dict]:

    w, h = board.size

    if side == "CT":

        x1 = 0

        x2 = int(
            w * 0.50
        )

    else:

        x1 = int(
            w * 0.50
        )

        x2 = w

    side_image = board.crop(
        (
            x1,
            0,
            x2,
            h
        )
    )

    rows = _find_rows(
        side_image
    )

    if not rows:

        return []

    # Убираем слишком близкие дубликаты строк
    clean_rows = []

    for y1, y2 in rows:

        center = (
            y1 + y2
        ) / 2

        duplicate = False

        for old_y1, old_y2 in clean_rows:

            old_center = (
                old_y1 + old_y2
            ) / 2

            if abs(
                center - old_center
            ) < 25:

                duplicate = True

                break

        if not duplicate:

            clean_rows.append(
                (
                    y1,
                    y2
                )
            )

    # Табло должно иметь максимум 5 строк на сторону
    if len(
        clean_rows
    ) > 5:

        # Оставляем наиболее крупные/центральные
        clean_rows = sorted(
            clean_rows,
            key=lambda r:
            (
                r[1] - r[0]
            ),
            reverse=True
        )[:5]

        clean_rows.sort(
            key=lambda r:
            r[0]
        )

    players = []

    for y1, y2 in clean_rows:

        row = side_image.crop(
            (
                0,
                y1,
                side_image.width,
                y2
            )
        )

        player = _parse_player_row(
            row,
            side
        )

        if player:

            players.append(
                player
            )

    return players[:5]


# ============================================================
# MAP
# ============================================================

def _clean_map_text(
    text: str
) -> str:

    return re.sub(
        r"[^a-z0-9]",
        "",
        text.lower()
    )


def _detect_map(
    text: str
) -> str | None:

    text = _clean_map_text(
        text
    )

    if not text:

        return None

    # Точное вхождение
    for map_name in MAPS:

        if map_name.lower() in text:

            return map_name

    # Алиасы
    for alias, map_name in MAP_ALIASES.items():

        if alias in text:

            return map_name

    # Сравнение по похожести
    best_map = None

    best_ratio = 0

    for map_name in MAPS:

        target = map_name.lower()

        ratio = SequenceMatcher(
            None,
            text,
            target
        ).ratio()

        if ratio > best_ratio:

            best_ratio = ratio

            best_map = map_name

    if best_ratio >= 0.55:

        return best_map

    return None


def _get_map(
    image: Image.Image
) -> str | None:

    """
    Читает название карты несколькими способами.
    """

    if not OCR_AVAILABLE:

        return None

    w, h = image.size

    crops = [

        # Нижняя часть
        image.crop(
            (
                0,
                int(h * 0.60),
                w,
                h
            )
        ),

        # Верхняя часть
        image.crop(
            (
                0,
                0,
                w,
                int(h * 0.40)
            )
        ),

        # Центр
        image.crop(
            (
                int(w * 0.15),
                int(h * 0.20),
                int(w * 0.85),
                int(h * 0.80)
            )
        ),

        # Вся картинка
        image,

    ]

    found = []

    for crop in crops:

        for scale in [3, 4]:

            prepared = _prepare(
                crop,
                scale=scale
            )

            for psm in [6, 11, 12]:

                try:

                    text = pytesseract.image_to_string(
                        prepared,
                        lang="eng",
                        config=f"--psm {psm}"
                    )

                except Exception:

                    continue

                result = _detect_map(
                    text
                )

                if result:

                    found.append(
                        result
                    )

    if not found:

        return None

    return max(
        set(found),
        key=found.count
    )


# ============================================================
# SCORE
# ============================================================

def _get_score(
    image: Image.Image
) -> str | None:

    if not OCR_AVAILABLE:

        return None

    w, h = image.size

    crops = [

        image.crop(
            (
                int(w * 0.35),
                0,
                int(w * 0.65),
                int(h * 0.30)
            )
        ),

        image.crop(
            (
                int(w * 0.40),
                int(h * 0.05),
                int(w * 0.60),
                int(h * 0.25)
            )
        ),

    ]

    results = []

    for crop in crops:

        prepared = _prepare(
            crop,
            scale=4
        )

        for psm in [6, 7, 11]:

            try:

                text = pytesseract.image_to_string(
                    prepared,
                    config=f"--psm {psm}"
                )

            except Exception:

                continue

            matches = re.findall(
                r"(\d{1,2})\s*[:\-]\s*(\d{1,2})",
                text
            )

            for a, b in matches:

                a = int(a)

                b = int(b)

                if a <= 30 and b <= 30:

                    results.append(
                        f"{a}:{b}"
                    )

    if not results:

        return None

    return max(
        set(results),
        key=results.count
    )


# ============================================================
# MAIN
# ============================================================

def parse_standoff_scoreboard(
    image: Any
) -> dict:

    if not OCR_AVAILABLE:

        return {

            "map": None,

            "score": None,

            "ct": [],

            "t": [],

        }

    img = _to_pil(
        image
    ).convert(
        "RGB"
    )

    # Поддержка именно изображения 2448x1080.
    # Если Discord/бот немного изменил размер,
    # логика всё равно работает пропорционально.
    w, h = img.size

    # Расширенная область таблицы
    board = img.crop(
        (
            0,
            int(h * 0.10),
            w,
            int(h * 0.90)
        )
    )

    ct = _parse_side(
        board,
        "CT"
    )

    tt = _parse_side(
        board,
        "T"
    )

    return {

        "map": _get_map(
            img
        ),

        "score": _get_score(
            img
        ),

        "ct": ct,

        "t": tt,

    }


# ============================================================
# MATCH RESULT
# ============================================================

def ocr_match_result(
    image: Any
) -> dict:

    result = parse_standoff_scoreboard(
        image
    )

    players = []

    for player in (
        result["ct"]
        +
        result["t"]
    ):

        players.append({

            "nickname": player.get(
                "nick",
                "?"
            ),

            "kills": player.get(
                "kills",
                0
            ),

            "deaths": player.get(
                "deaths",
                0
            ),

            "assists": player.get(
                "assists",
                0
            ),

            "score": player.get(
                "score",
                0
            ),

            "ping": player.get(
                "ping",
                0
            ),

            "side": player.get(
                "side"
            ),

        })

    return {

        "match_score": result.get(
            "score"
        ),

        "map": result.get(
            "map"
        ),

        "players": players,

    }