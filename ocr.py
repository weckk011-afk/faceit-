"""
OCR Standoff 2 scoreboard
Распознаёт:
Ник | Убийства | Ассисты | Смерти | Счёт

Деньги и пинг игнорируются.
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
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )


HEADER_WORDS = (
    "имя",
    "деньги",
    "счет",
    "счёт",
    "пинг",
    "оборона",
    "атака",
    "турнир",
    "овертайм",
    "наблюдател",
    "россия",
    "кастом",
)


def _to_pil(image: Any):

    if isinstance(image, Image.Image):
        return image

    if isinstance(image, bytes):
        return Image.open(io.BytesIO(image))

    if isinstance(image, str):
        return Image.open(image)

    raise TypeError("Неверный формат изображения")


def _preprocess(img):

    w, h = img.size

    img = img.convert("L")

    img = img.resize(
        (
            w * 3,
            h * 3
        ),
        Image.LANCZOS
    )

    img = ImageOps.autocontrast(img)

    return img



def _clean_nick(text):

    text = re.sub(
        r"[^\wА-Яа-яЁё\[\]\-_ ]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()



def _group_lines(data):

    words = []

    count = len(data["text"])


    for i in range(count):

        txt = data["text"][i]

        if not txt:
            continue


        words.append(
            {
                "text": txt,
                "x": data["left"][i],
                "y": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
                "cy": data["top"][i] + data["height"][i] / 2,
            }
        )


    if not words:
        return []


    words.sort(
        key=lambda x: x["cy"]
    )


    lines = []
    current = []

    last_y = None


    for word in words:

        if (
            last_y is None
            or abs(word["cy"] - last_y) < 25
        ):
            current.append(word)

        else:

            lines.append(
                sorted(
                    current,
                    key=lambda x:x["x"]
                )
            )

            current = [word]


        last_y = word["cy"]


    if current:
        lines.append(
            sorted(
                current,
                key=lambda x:x["x"]
            )
        )


    return lines



def _parse_row(words, side):

    text = " ".join(
        x["text"]
        for x in words
    ).lower()


    # убираем заголовки
    if any(
        h in text
        for h in HEADER_WORDS
    ):
        return None



    numbers = []


    for w in words:

        n = re.sub(
            r"[^\d]",
            "",
            w["text"]
        )


        if n.isdigit():

            numbers.append(
                (
                    w,
                    int(n)
                )
            )



    # минимум:
    # K A D SCORE

    if len(numbers) < 4:
        return None



    stats = numbers[-4:]


    kills = stats[0][1]
    assists = stats[1][1]
    deaths = stats[2][1]
    score = stats[3][1]



    if not (
        0 <= kills <= 60
        and 0 <= assists <= 60
        and 0 <= deaths <= 60
        and 0 <= score <= 300
    ):
        return None



    first_stat_x = stats[0][0]["x"]


    nick = " ".join(
        w["text"]
        for w in words
        if w["x"] < first_stat_x
    )


    nick = _clean_nick(nick)


    if len(nick) < 2:
        return None



    return {
        "side": side,
        "nick": nick,

        "money": None,

        "kills": kills,
        "assists": assists,
        "deaths": deaths,

        "score": score,

        "ping": None,
    }
    def _ocr_side(img, side):

    pre = _preprocess(img)


    data = pytesseract.image_to_data(
        pre,
        lang="rus+eng",
        config="--psm 6",
        output_type=Output.DICT
    )


    raw = pytesseract.image_to_string(
        pre,
        lang="rus+eng",
        config="--psm 6"
    )


    lines = _group_lines(data)


    rows = []


    for line in lines:

        row = _parse_row(
            line,
            side
        )

        if row:
            rows.append(row)



    # убираем дубли OCR

    result = []
    seen = set()


    for r in rows:

        key = (
            r["nick"],
            r["kills"],
            r["assists"],
            r["deaths"],
            r["score"]
        )


        if key in seen:
            continue


        seen.add(key)
        result.append(r)



    return result[:5], raw





def _parse_match_score(img):

    w, h = img.size


    # центр сверху где счёт 12:15

    crop = img.crop(
        (
            int(w * 0.35),
            int(h * 0.15),
            int(w * 0.65),
            int(h * 0.35)
        )
    )


    crop = _preprocess(crop)


    txt = pytesseract.image_to_string(
        crop,
        config="--psm 6 -c tessedit_char_whitelist=0123456789:"
    )


    nums = re.findall(
        r"\d{1,2}",
        txt
    )


    if len(nums) >= 2:

        return (
            f"{nums[0]}:{nums[1]}"
        )


    return None





def parse_standoff_scoreboard(image):


    if not OCR_AVAILABLE:

        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {},
            "error": "OCR недоступен"
        }



    try:

        img = _to_pil(image).convert(
            "RGB"
        )

    except Exception as e:

        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {},
            "error": str(e)
        }




    w, h = img.size



    # берём только таблицу игроков

    table = img.crop(
        (
            0,
            int(h * 0.25),
            w,
            int(h * 0.75)
        )
    )



    tw, th = table.size



    left = table.crop(
        (
            0,
            0,
            int(tw * 0.52),
            th
        )
    )


    right = table.crop(
        (
            int(tw * 0.48),
            0,
            tw,
            th
        )
    )



    try:

        ct, ct_raw = _ocr_side(
            left,
            "CT"
        )


        t, t_raw = _ocr_side(
            right,
            "T"
        )


        score = _parse_match_score(
            img
        )


    except Exception as e:

        return {
            "score": None,
            "ct": [],
            "t": [],
            "raw": {},
            "error": str(e)
        }




    return {

        "score": score,

        "ct": ct,

        "t": t,

        "raw": {
            "left": ct_raw,
            "right": t_raw
        }

    }





# Совместимость со старым ботом

def ocr_match_result(image_input):


    result = parse_standoff_scoreboard(
        image_input
    )


    players = []


    for p in result["ct"] + result["t"]:


        players.append(
            {
                "nickname": p["nick"],

                "kills": p["kills"],

                "deaths": p["deaths"],

                "assists": p["assists"],

                "score": p["score"]
            }
        )



    return {

        "raw_text":
            result["raw"]["left"]
            + "\n"
            + result["raw"]["right"],


        "match_score":
            result["score"],


        "players":
            players
    }





if __name__ == "__main__":


    import sys


    for file in sys.argv[1:]:


        print(
            "\n======",
            file,
            "======"
        )


        r = parse_standoff_scoreboard(
            file
        )


        print(
            "Счёт:",
            r["score"]
        )


        for team in ("ct", "t"):


            print(
                team.upper()
            )


            for p in r[team]:

                print(
                    p["nick"],
                    p["kills"],
                    p["assists"],
                    p["deaths"],
                    p["score"]
                )