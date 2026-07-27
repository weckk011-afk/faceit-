"""
Standoff 2 scoreboard OCR
K / A / D / Score / Ping
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
    "овертайм"
)


def _to_pil(image: Any):
    if isinstance(image, Image.Image):
        return image

    if isinstance(image, bytes):
        return Image.open(io.BytesIO(image))

    if isinstance(image, str):
        return Image.open(image)

    raise TypeError("bad image")


def _preprocess(img):

    w, h = img.size

    img = img.convert("L")

    img = img.resize(
        (w * 3, h * 3),
        Image.LANCZOS
    )

    img = ImageOps.autocontrast(
        img
    )

    return img



def _clean_nick(text):

    text = re.sub(
        r"[^A-Za-zА-Яа-яЁё0-9_\[\]\- ]",
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

    words=[]

    total=len(data["text"])

    for i in range(total):

        txt=data["text"][i].strip()

        if not txt:
            continue


        words.append({
            "text":txt,
            "x":data["left"][i],
            "y":data["top"][i],
            "h":data["height"][i],
            "cy":data["top"][i]+data["height"][i]/2
        })


    if not words:
        return []


    words.sort(
        key=lambda x:x["cy"]
    )


    lines=[]

    current=[]
    last_y=None


    for w in words:

        if last_y is None or abs(w["cy"]-last_y)<20:

            current.append(w)
            last_y=w["cy"]

        else:

            lines.append(
                sorted(
                    current,
                    key=lambda x:x["x"]
                )
            )

            current=[w]
            last_y=w["cy"]


    if current:
        lines.append(
            sorted(
                current,
                key=lambda x:x["x"]
            )
        )


    return lines



def _parse_player(line, side):

    text=" ".join(
        x["text"] for x in line
    )


    low=text.lower()


    for h in HEADER_WORDS:

        if h in low:
            return None



    nums=[]


    for word in line:

        t=word["text"]

        # игнорируем деньги
        if "$" in t:
            continue


        if t.isdigit():

            nums.append(
                (
                    word["x"],
                    int(t)
                )
            )



    if len(nums)<5:
        return None



    values=[
        x[1] for x in nums[-5:]
    ]


    kills, assists, deaths, score, ping = values



    if kills>60:
        return None

    if assists>60:
        return None

    if deaths>60:
        return None

    if score>300:
        return None

    if ping>999:
        return None



    first_stat_x=nums[-5][0]


    nick=" ".join(
        x["text"]
        for x in line
        if x["x"] < first_stat_x
    )


    nick=_clean_nick(
        nick
    )



    return {

        "side":side,
        "nick":nick or "?",
        "money":None,

        "kills":kills,
        "assists":assists,
        "deaths":deaths,

        "score":score,
        "ping":ping

    }



def _ocr_side(img, side):

    img=_preprocess(
        img
    )


    data=pytesseract.image_to_data(
        img,
        lang="rus+eng",
        config="--psm 6",
        output_type=Output.DICT
    )


    raw=pytesseract.image_to_string(
        img,
        lang="rus+eng",
        config="--psm 6"
    )


    lines=_group_lines(
        data
    )


    players=[]


    for line in lines:

        player=_parse_player(
            line,
            side
        )

        if player:
            players.append(
                player
            )


    return players[:5], raw



def _get_score(img):

    w,h=img.size


    crop=img.crop(
        (
            int(w*0.42),
            int(h*0.12),
            int(w*0.58),
            int(h*0.25)
        )
    )


    crop=_preprocess(
        crop
    )


    txt=pytesseract.image_to_string(
        crop,
        config="--psm 7"
    )


    nums=re.findall(
        r"\d+",
        txt
    )


    if len(nums)>=2:

        return f"{nums[0]}:{nums[1]}"


    return None



def parse_standoff_scoreboard(image):


    if not OCR_AVAILABLE:

        return {
            "score":None,
            "ct":[],
            "t":[]
        }


    img=_to_pil(
        image
    ).convert(
        "RGB"
    )


    w,h=img.size


    board=img.crop(
        (
            0,
            int(h*0.20),
            w,
            int(h*0.75)
        )
    )


    bw,bh=board.size


    left=board.crop(
        (
            0,
            0,
            int(bw*0.52),
            bh
        )
    )


    right=board.crop(
        (
            int(bw*0.48),
            0,
            bw,
            bh
        )
    )



    ct,_=_ocr_side(
        left,
        "CT"
    )


    tt,_=_ocr_side(
        right,
        "T"
    )


    return {

        "score":_get_score(img),

        "ct":ct,

        "t":tt

    }



def ocr_match_result(image):


    result=parse_standoff_scoreboard(
        image
    )


    players=[]


    for p in result["ct"]+result["t"]:

        players.append({

            "nickname":p["nick"],

            "kills":p["kills"],

            "deaths":p["deaths"],

            "assists":p["assists"],

            "score":p["score"]

        })



    return {

        "match_score":result["score"],

        "players":players

    }