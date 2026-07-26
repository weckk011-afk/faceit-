"""OCR scoreboard parser for Standoff 2 (strictly 5v5).

Input: image path, bytes or PIL.Image.
Output: map, score, exactly two teams with five players each when recognition succeeds.

Requires:
    pip install pytesseract opencv-python-headless numpy Pillow
System package:
    Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from typing import Any

import cv2
import numpy as np
import pytesseract
from PIL import Image

if os.name == "nt" and not os.environ.get("TESSERACT_CMD"):
    default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default):
        pytesseract.pytesseract.tesseract_cmd = default
elif os.environ.get("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]

KNOWN_MAPS = [
    "Sandstone",
    "Hanami",
    "Prison",
    "Dune",
    "Breeze",
    "Rust",
    "Province",
]

# Coordinates are relative, therefore screenshots of different 16:9 resolutions work.
# Scoreboard panel seen in Standoff 2 match-result screenshots.
TABLE = (0.112, 0.170, 0.888, 0.885)
NAME_X = (0.120, 0.350)
COLS = {
    "kills": (0.350, 0.432),
    "assists": (0.432, 0.515),
    "deaths": (0.515, 0.600),
    "score": (0.600, 0.735),
    "ping": (0.735, 0.884),
}


@dataclass
class Player:
    nickname: str
    kills: int
    assists: int
    deaths: int
    score: int
    ping: int
    team: str
    row: int
    confidence: float = 0.0


class OCRException(RuntimeError):
    pass


def _to_bgr(image_input: str | bytes | Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image_input, str):
        image = cv2.imread(image_input, cv2.IMREAD_COLOR)
        if image is None:
            raise OCRException(f"Не удалось открыть изображение: {image_input}")
        return image
    if isinstance(image_input, bytes):
        arr = np.frombuffer(image_input, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise OCRException("Переданные bytes не являются изображением")
        return image
    if isinstance(image_input, Image.Image):
        rgb = np.asarray(image_input.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input.copy()
    raise TypeError("Ожидается путь, bytes, PIL.Image или numpy.ndarray")


def _crop(img: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    return img[max(0, int(y1*h)):min(h, int(y2*h)), max(0, int(x1*w)):min(w, int(x2*w))]


def _prep(src: np.ndarray, scale: float = 3.0, digits: bool = False) -> np.ndarray:
    if src.size == 0:
        return src
    gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY) if src.ndim == 3 else src
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    # Text may be white, blue, orange or green; adaptive threshold handles all UI backgrounds.
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7
    )
    # Tesseract generally prefers dark glyphs on a light background.
    if np.mean(binary) < 127:
        binary = cv2.bitwise_not(binary)
    if digits:
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    return binary


def _ocr(src: np.ndarray, psm: int, whitelist: str | None = None, lang: str = "eng+rus") -> tuple[str, float]:
    if src.size == 0:
        return "", 0.0
    config = f"--oem 3 --psm {psm}"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    data = pytesseract.image_to_data(src, lang=lang, config=config, output_type=pytesseract.Output.DICT)
    texts, confs = [], []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        text = str(text).strip()
        try:
            value = float(conf)
        except (TypeError, ValueError):
            value = -1
        if text:
            texts.append(text)
            if value >= 0:
                confs.append(value)
    return " ".join(texts).strip(), (sum(confs) / len(confs) if confs else 0.0)


def _clean_number(text: str, max_value: int = 9999) -> int | None:
    table = str.maketrans({"O": "0", "o": "0", "О": "0", "I": "1", "l": "1", "|": "1", "S": "5", "B": "8"})
    digits = re.sub(r"\D", "", text.translate(table))
    if not digits:
        return None
    value = int(digits[:4])
    return value if 0 <= value <= max_value else None


def _clean_name(text: str) -> str:
    text = text.replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^\w\[\](){}.+\-]+|[^\w\[\](){}.+\- ]+$", "", text, flags=re.UNICODE)
    # Remove OCR artifacts that are only punctuation.
    if len(re.sub(r"[^A-Za-zА-Яа-яЁё0-9]", "", text)) < 2:
        return "?"
    return text[:32]


def _best_map(text: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9 ]", "", text.lower())
    for map_name in KNOWN_MAPS:
        if map_name.lower() in normalized:
            return map_name
    words = normalized.split()
    best, score = None, 0.0
    for map_name in KNOWN_MAPS:
        candidate = map_name.lower()
        spans = words + [" ".join(words[i:i+2]) for i in range(max(0, len(words)-1))]
        for span in spans:
            ratio = SequenceMatcher(None, span, candidate).ratio()
            if ratio > score:
                best, score = map_name, ratio
    return best if score >= 0.72 else None


def _recognize_score(img: np.ndarray) -> tuple[int | None, int | None, float]:
    # Result screen: score is near the top center. Overlay: score is around 22% height.
    boxes = [
        (0.430, 0.045, 0.570, 0.185),
        (0.430, 0.165, 0.570, 0.305),
        (0.455, 0.000, 0.545, 0.095),
    ]
    candidates: list[tuple[int, int, float]] = []
    for box in boxes:
        roi = _crop(img, box)
        # Raw grayscale is often better for the large outlined score font.
        variants = [_prep(roi, scale=4.0, digits=True)]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        variants.append(cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC))
        for prepared in variants:
            text, conf = _ocr(prepared, 6, "0123456789:-")
            pairs = re.findall(r"(\d{1,2})\s*[:\-]\s*(\d{1,2})", text)
            for left, right in pairs:
                a, b = int(left), int(right)
                if 0 <= a <= 30 and 0 <= b <= 30:
                    candidates.append((a, b, conf + 10))
            nums = [int(x) for x in re.findall(r"\d{1,2}", text)]
            if len(nums) >= 2:
                for i in range(len(nums)-1):
                    a, b = nums[i], nums[i+1]
                    if a <= 30 and b <= 30:
                        candidates.append((a, b, conf))
    if not candidates:
        return None, None, 0.0
    return max(candidates, key=lambda x: x[2])


def _recognize_map(img: np.ndarray) -> tuple[str | None, float]:
    # Map can be shown in the footer (match result) or at upper-left HUD.
    candidates = []
    for box in ((0.0, 0.0, 0.42, 0.12), (0.0, 0.68, 0.58, 0.82), (0.0, 0.88, 0.65, 1.0)):
        roi = _crop(img, box)
        for variant in (_prep(roi, scale=3.0), cv2.resize(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)):
            text, conf = _ocr(variant, 6)
            found = _best_map(text)
            if found:
                candidates.append((found, conf))
    return max(candidates, key=lambda x: x[1]) if candidates else (None, 0.0)


def _player_boxes(side: str, center_y: float, row_h: float) -> dict[str, tuple[float, float, float, float]]:
    y1, y2 = center_y - row_h * 0.42, center_y + row_h * 0.42
    if side == "A":
        return {
            "nickname": (0.105, y1, 0.345, y2),
            "kills": (0.345, y1, 0.382, y2),
            "assists": (0.382, y1, 0.414, y2),
            "deaths": (0.414, y1, 0.452, y2),
            "score": (0.452, y1, 0.490, y2),
            "ping": (0.490, y1, 0.505, y2),
        }
    return {
        "nickname": (0.555, y1, 0.790, y2),
        "kills": (0.790, y1, 0.833, y2),
        "assists": (0.833, y1, 0.866, y2),
        "deaths": (0.866, y1, 0.905, y2),
        "score": (0.905, y1, 0.947, y2),
        "ping": (0.947, y1, 0.990, y2),
    }


def _recognize_player(img: np.ndarray, side: str, row_index: int, center_y: float, row_h: float) -> Player:
    boxes = _player_boxes(side, center_y, row_h)
    name_roi = _crop(img, boxes["nickname"])
    name_variants = [_prep(name_roi, scale=3.2)]
    name_variants.append(cv2.resize(cv2.cvtColor(name_roi, cv2.COLOR_BGR2GRAY), None, fx=3.2, fy=3.2, interpolation=cv2.INTER_CUBIC))
    name_candidates = []
    for v in name_variants:
        text, conf = _ocr(v, 7)
        cleaned = _clean_name(text)
        if cleaned != "?":
            name_candidates.append((cleaned, conf))
    name, name_conf = max(name_candidates, key=lambda x: x[1]) if name_candidates else ("?", 0.0)

    values: dict[str, int] = {}
    confs = [name_conf]
    limits = {"kills": 99, "assists": 99, "deaths": 99, "score": 999, "ping": 999}
    for key in ("kills", "assists", "deaths", "score", "ping"):
        roi0 = _crop(img, boxes[key])
        variants = [_prep(roi0, scale=5.0, digits=True)]
        variants.append(cv2.resize(cv2.cvtColor(roi0, cv2.COLOR_BGR2GRAY), None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC))
        candidates = []
        for roi in variants:
            text, conf = _ocr(roi, 7, "0123456789")
            value = _clean_number(text, limits[key])
            if value is not None:
                candidates.append((value, conf))
        if candidates:
            value, conf = max(candidates, key=lambda x: x[1])
            values[key] = value
            confs.append(conf)
        else:
            values[key] = 0
            confs.append(0.0)

    return Player(
        nickname=name,
        kills=values["kills"], assists=values["assists"], deaths=values["deaths"],
        score=values["score"], ping=values["ping"], team=side, row=row_index + 1,
        confidence=round(sum(confs) / len(confs), 1),
    )


def _recognize_layout(img: np.ndarray, centers: list[float], row_h: float) -> tuple[list[Player], float]:
    players = []
    for side in ("A", "B"):
        for i, cy in enumerate(centers):
            players.append(_recognize_player(img, side, i, cy, row_h))
    good_names = sum(p.nickname != "?" for p in players)
    nonzero = sum((p.kills + p.assists + p.deaths + p.score + p.ping) > 0 for p in players)
    avg_conf = sum(p.confidence for p in players) / 10
    quality = good_names * 15 + nonzero * 10 + avg_conf
    return players, quality


def recognize_standoff_scoreboard(image_input: str | bytes | Image.Image | np.ndarray) -> dict[str, Any]:
    """Recognize a Standoff 2 scoreboard, strictly as 5 players per side."""
    img = _to_bgr(image_input)
    h, w = img.shape[:2]
    if w / max(h, 1) < 1.45:
        raise OCRException("Нужен горизонтальный скриншот таблицы результатов")

    map_name, map_conf = _recognize_map(img)
    score_a, score_b, score_conf = _recognize_score(img)

    # Two common Standoff 2 variants: transparent in-game overlay and final statistics screen.
    layouts = [
        ([0.367, 0.458, 0.548, 0.638, 0.728], 0.070),
        ([0.280, 0.360, 0.440, 0.520, 0.600], 0.062),
        ([0.302, 0.382, 0.462, 0.542, 0.622], 0.062),
    ]
    attempts = [_recognize_layout(img, centers, row_h) for centers, row_h in layouts]
    players, _ = max(attempts, key=lambda x: x[1])
    # Order must be A1..A5 then B1..B5.
    team_a_players = [p for p in players if p.team == "A"][:5]
    team_b_players = [p for p in players if p.team == "B"][:5]
    players = team_a_players + team_b_players

    valid_names = sum(p.nickname != "?" for p in players)
    valid_stats = sum((p.kills + p.assists + p.deaths + p.score + p.ping) > 0 for p in players)
    warnings = []
    if valid_names < 8:
        warnings.append(f"Уверенно распознано только {valid_names}/10 ников")
    if valid_stats < 8:
        warnings.append(f"Уверенно распознана статистика только {valid_stats}/10 игроков")
    if score_a is None or score_b is None:
        warnings.append("Не удалось распознать общий счёт")
    if map_name is None:
        warnings.append("Не удалось распознать карту")

    team_a = [asdict(p) for p in players[:5]]
    team_b = [asdict(p) for p in players[5:10]]
    winner = None
    if score_a is not None and score_b is not None:
        winner = "A" if score_a > score_b else "B" if score_b > score_a else "draw"

    return {
        "success": valid_names >= 6 and valid_stats >= 6,
        "format": "5v5", "map": map_name,
        "score": f"{score_a}:{score_b}" if score_a is not None and score_b is not None else None,
        "score_a": score_a, "score_b": score_b, "winner": winner,
        "team_a": team_a, "team_b": team_b, "players": team_a + team_b,
        "mvp": _mvp(team_a + team_b),
        "confidence": {"map": round(map_conf, 1), "score": round(score_conf, 1), "average_player": round(sum(p.confidence for p in players) / 10, 1)},
        "warnings": warnings, "image_size": {"width": w, "height": h},
    }


def _mvp(players: list[dict[str, Any]]) -> str | None:
    valid = [p for p in players if p.get("nickname") != "?"]
    if not valid:
        return None
    # In Standoff 2 the scoreboard points column is the safest MVP criterion.
    best = max(valid, key=lambda p: (int(p.get("score", 0)), int(p.get("kills", 0))))
    return best["nickname"]


# Backwards-compatible alias for the old project API.
def parse_scoreboard(image_input: str | bytes | Image.Image | np.ndarray) -> dict[str, Any]:
    return recognize_standoff_scoreboard(image_input)


# Alias matching the old OCR.py API.
def ocr_match_result(image_input: str | bytes | Image.Image | np.ndarray) -> dict[str, Any]:
    return recognize_standoff_scoreboard(image_input)
