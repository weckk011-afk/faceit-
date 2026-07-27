"""
Standoff 2 Scoreboard OCR
Распознавание:
- Карты
- Счёта
- Игроков
- K / A / D / Score / Ping

Поддерживаемые карты:
Dune
Hanami
Province
Prison
Sandstone
Breeze
Rust
"""

from __future__ import annotations

import io
import os
import re
from typing import Any

from PIL import Image, ImageOps, ImageFilter


# ============================================================
# OCR
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

    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for path in possible_paths:

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


# ============================================================
# MAP OCR FIXES
# ============================================================

MAP_ALIASES = {

    # Dune
    "dune": "Dune",
    "dun": "Dune",
    "dunc": "Dune",
    "dunee": "Dune",
    "dunc": "Dune",

    # Hanami
    "hanami": "Hanami",
    "hanam": "Hanami",
    "hanam1": "Hanami",
    "hanami1": "Hanami",

    # Province
    "province": "Province",
    "provincc": "Province",
    "provin": "Province",
    "provinc": "Province",

    # Prison
    "prison": "Prison",
    "pris0n": "Prison",
    "pr1son": "Prison",
    "priso": "Prison",

    # Sandstone
    "sandstone": "Sandstone",
    "sandston": "Sandstone",
    "sandst0ne": "Sandstone",
    "sand": "Sandstone",

    # Breeze
    "breeze": "Breeze",
    "breez": "Breeze",
    "breese": "Breeze",

    # Rust
    "rust": "Rust",
    "rüst": "Rust",
    "rus": "Rust",
}


# ============================================================
# IMAGE
# ============================================================

def _to_pil(image: Any) -> Image.Image:

    if isinstance(image, Image.Image):

        return image

    if isinstance(image, bytes):

        return Image.open(
            io.BytesIO(image)
        )

    if isinstance(image, str):

        return Image.open(image)

    raise TypeError(
        "Unsupported image type"
    )


def _resize(img: Image.Image, scale: int = 3) -> Image.Image:

    w, h = img.size

    return img.resize(
        (
            max(1, w * scale),
            max(1, h * scale)
        ),
        Image.Resampling.LANCZOS
    )


def _preprocess(
    img: Image.Image,
    scale: int = 3,
    threshold: int | None = None
) -> Image.Image:

    img = img.convert("L")

    img = _resize(
        img,
        scale
    )

    img = ImageOps.autocontrast(
        img
    )

    img = img.filter(
        ImageFilter.SHARPEN
    )

    if threshold is not None:

        img = img.point(
            lambda p: 255 if p > threshold else 0
        )

    return img


# ============================================================
# TEXT
# ============================================================

def _clean_text(text: str) -> str:

    text = re.sub(
        r"[^A-Za-zА-Яа-яЁё0-9_\-\[\]\(\) ]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def _normalize_ocr_text(text: str) -> str:

    text = text.lower()

    replacements = {

        "0": "o",
        "1": "i",
        "5": "s",
        "8": "b",

    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new
        )

    return text


# ============================================================
# OCR DATA
# ============================================================

def _get_ocr_data(
    img: Image.Image,
    psm: int = 6
) -> dict:

    if not OCR_AVAILABLE:

        return {}

    try:

        return pytesseract.image_to_data(
            img,
            lang="eng+rus",
            config=f"--psm {psm}",
            output_type=Output.DICT
        )

    except Exception:

        return {}


def _get_words(
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


def _group_lines(
    words: list[dict]
) -> list[list[dict]]:

    if not words:

        return []

    words = sorted(
        words,
        key=lambda x: x["cy"]
    )

    lines = []

    current = []

    current_y = None

    for word in words:

        if current_y is None:

            current = [
                word
            ]

            current_y = word["cy"]

            continue

        tolerance = max(
            20,
            word["h"] * 1.5
        )

        if abs(
            word["cy"] - current_y
        ) <= tolerance:

            current.append(
                word
            )

            current_y = (
                current_y + word["cy"]
            ) / 2

        else:

            lines.append(
                sorted(
                    current,
                    key=lambda x: x["x"]
                )
            )

            current = [
                word
            ]

            current_y = word["cy"]

    if current:

        lines.append(
            sorted(
                current,
                key=lambda x: x["x"]
            )
        )

    return lines


# ============================================================
# NUMBERS
# ============================================================

def _parse_number(
    text: str
) -> int | None:

    text = text.strip()

    if not text:

        return None

    # OCR fixes
    text = text.replace(
        "O",
        "0"
    )

    text = text.replace(
        "o",
        "0"
    )

    text = text.replace(
        "I",
        "1"
    )

    text = text.replace(
        "l",
        "1"
    )

    text = text.replace(
        "S",
        "5"
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


def _extract_numbers(
    line: list[dict]
) -> list[tuple[int, int]]:

    result = []

    for word in line:

        text = word["text"]

        # деньги
        if "$" in text:

            continue

        number = _parse_number(
            text
        )

        if number is None:

            continue

        result.append(
            (
                word["x"],
                number
            )
        )

    return result


# ============================================================
# PLAYER
# ============================================================

def _is_valid_stats(
    kills: int,
    assists: int,
    deaths: int,
    score: int,
    ping: int
) -> bool:

    if not 0 <= kills <= 60:

        return False

    if not 0 <= assists <= 60:

        return False

    if not 0 <= deaths <= 60:

        return False

    if not 0 <= score <= 300:

        return False

    if not 0 <= ping <= 999:

        return False

    return True


def _parse_player(
    line: list[dict],
    side: str
) -> dict | None:

    if not line:

        return None

    text = " ".join(
        word["text"]
        for word in line
    )

    low = text.lower()

    # заголовки
    ignored_words = [

        "name",
        "имя",
        "money",
        "деньги",
        "score",
        "ping",
        "kills",
        "deaths",
        "assists",

    ]

    if any(
        word in low
        for word in ignored_words
    ):

        return None

    numbers = _extract_numbers(
        line
    )

    if len(numbers) < 5:

        return None

    # Берём последние 5 чисел строки
    stats = numbers[-5:]

    kills = stats[0][1]
    assists = stats[1][1]
    deaths = stats[2][1]
    score = stats[3][1]
    ping = stats[4][1]

    if not _is_valid_stats(
        kills,
        assists,
        deaths,
        score,
        ping
    ):

        return None

    stat_x = stats[0][0]

    nickname_words = []

    for word in line:

        if word["x"] < stat_x:

            word_text = word["text"]

            # пропускаем деньги
            if "$" in word_text:

                continue

            nickname_words.append(
                word_text
            )

    nickname = _clean_text(
        " ".join(
            nickname_words
        )
    )

    # если ник слишком короткий
    if len(nickname) < 1:

        nickname = "?"

    # отбрасываем очевидный мусор
    if nickname.lower() in [

        "name",
        "имя",
        "score",
        "ping",

    ]:

        return None

    return {

        "side": side,

        "nick": nickname,

        "money": None,

        "kills": kills,

        "assists": assists,

        "deaths": deaths,

        "score": score,

        "ping": ping,

    }


# ============================================================
# SIDE OCR
# ============================================================

def _ocr_side(
    img: Image.Image,
    side: str
) -> tuple[list[dict], str]:

    if not OCR_AVAILABLE:

        return [], ""

    # несколько вариантов обработки
    variants = [

        _preprocess(
            img,
            scale=3
        ),

        _preprocess(
            img,
            scale=4,
            threshold=150
        ),

        _preprocess(
            img,
            scale=4,
            threshold=190
        ),

    ]

    all_players = []

    raw_texts = []

    for prepared in variants:

        data = _get_ocr_data(
            prepared,
            psm=6
        )

        words = _get_words(
            data
        )

        lines = _group_lines(
            words
        )

        for line in lines:

            player = _parse_player(
                line,
                side
            )

            if player:

                all_players.append(
                    player
                )

        try:

            raw_texts.append(
                pytesseract.image_to_string(
                    prepared,
                    lang="eng+rus",
                    config="--psm 6"
                )
            )

        except Exception:

            pass

    # удаляем дубликаты
    unique = []

    seen = set()

    for player in all_players:

        key = (

            player["nick"].lower(),

            player["kills"],

            player["assists"],

            player["deaths"],

            player["score"],

        )

        if key in seen:

            continue

        seen.add(
            key
        )

        unique.append(
            player
        )

    # максимум 5 игроков
    return unique[:5], "\n".join(
        raw_texts
    )


# ============================================================
# SCORE
# ============================================================

def _get_score(
    img: Image.Image
) -> str | None:

    if not OCR_AVAILABLE:

        return None

    w, h = img.size

    # несколько зон вокруг центра
    crops = [

        img.crop(
            (
                int(w * 0.35),
                0,
                int(w * 0.65),
                int(h * 0.30)
            )
        ),

        img.crop(
            (
                int(w * 0.40),
                int(h * 0.03),
                int(w * 0.60),
                int(h * 0.25)
            )
        ),

    ]

    scores = []

    for crop in crops:

        prepared = _preprocess(
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

            text = text.replace(
                " ",
                ""
            )

            # ищем варианты:
            # 5:3
            # 5-3
            # 5 3
            matches = re.findall(
                r"(\d{1,2})\s*[:\-]\s*(\d{1,2})",
                text
            )

            for a, b in matches:

                a = int(a)
                b = int(b)

                if a <= 30 and b <= 30:

                    scores.append(
                        f"{a}:{b}"
                    )

            nums = re.findall(
                r"\d{1,2}",
                text
            )

            if len(nums) >= 2:

                a = int(
                    nums[0]
                )

                b = int(
                    nums[1]
                )

                if a <= 30 and b <= 30:

                    scores.append(
                        f"{a}:{b}"
                    )

    if scores:

        return max(
            set(scores),
            key=scores.count
        )

    return None


# ============================================================
# MAP
# ============================================================

def _normalize_map_text(
    text: str
) -> str:

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9]",
        "",
        text
    )

    return text


def _find_map_in_text(
    text: str
) -> str | None:

    normalized = _normalize_map_text(
        text
    )

    if not normalized:

        return None

    # точное совпадение
    for map_name in MAPS:

        if map_name.lower() in normalized:

            return map_name

    # aliases
    for alias, map_name in MAP_ALIASES.items():

        alias_clean = _normalize_map_text(
            alias
        )

        if alias_clean in normalized:

            return map_name

    # fuzzy-поиск
    best_map = None

    best_score = 0

    for map_name in MAPS:

        target = map_name.lower()

        # общие символы
        common = sum(
            1
            for char in target
            if char in normalized
        )

        score = common / max(
            1,
            len(target)
        )

        if score > best_score:

            best_score = score

            best_map = map_name

    if best_score >= 0.65:

        return best_map

    return None


def _get_map(
    img: Image.Image
) -> str | None:

    if not OCR_AVAILABLE:

        return None

    w, h = img.size

    # Проверяем не только нижнюю часть,
    # а несколько возможных зон
    crops = [

        # нижняя левая
        img.crop(
            (
                0,
                int(h * 0.65),
                int(w * 0.75),
                h
            )
        ),

        # нижняя центральная
        img.crop(
            (
                int(w * 0.20),
                int(h * 0.65),
                int(w * 0.80),
                h
            )
        ),

        # верхняя часть
        img.crop(
            (
                0,
                0,
                w,
                int(h * 0.35)
            )
        ),

        # вся картинка
        img,

    ]

    detected = []

    for crop in crops:

        for scale in [3, 4]:

            prepared = _preprocess(
                crop,
                scale=scale
            )

            for psm in [6, 7, 11, 12]:

                try:

                    text = pytesseract.image_to_string(
                        prepared,
                        lang="eng",
                        config=f"--psm {psm}"
                    )

                except Exception:

                    continue

                found = _find_map_in_text(
                    text
                )

                if found:

                    detected.append(
                        found
                    )

    if detected:

        return max(
            set(detected),
            key=detected.count
        )

    return None


# ============================================================
# MAIN SCOREBOARD PARSER
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

    w, h = img.size

    # Таблица обычно находится в центральной части.
    # Берём расширенную область, чтобы не потерять строки.
    board = img.crop(
        (
            0,
            int(h * 0.15),
            w,
            int(h * 0.90)
        )
    )

    bw, bh = board.size

    # Разделяем строго по центру.
    # Без перекрытия, чтобы игроки не дублировались.
    left = board.crop(
        (
            0,
            0,
            int(bw * 0.50),
            bh
        )
    )

    right = board.crop(
        (
            int(bw * 0.50),
            0,
            bw,
            bh
        )
    )

    ct, _ = _ocr_side(
        left,
        "CT"
    )

    tt, _ = _ocr_side(
        right,
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
        result.get("ct", [])
        +
        result.get("t", [])
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