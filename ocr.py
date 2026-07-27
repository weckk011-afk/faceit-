"""
Standoff 2 Scoreboard OCR
K / A / D / Score / Ping
Maps detection
"""

from __future__ import annotations

import io
import re
import os

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



MAPS = [
    "Dune",
    "Hanami",
    "Province",
    "Prison",
    "Sandstone",
    "Breeze",
    "Rust"
]



def _to_pil(image):

    if isinstance(image, Image.Image):

        return image


    if isinstance(image, bytes):

        return Image.open(
            io.BytesIO(image)
        )


    if isinstance(image, str):

        return Image.open(image)


    raise TypeError(
        "Unsupported image"
    )



def _preprocess(img, scale=3):

    w, h = img.size


    img = img.convert(
        "L"
    )


    img = img.resize(
        (
            w * scale,
            h * scale
        ),
        Image.LANCZOS
    )


    img = ImageOps.autocontrast(
        img
    )


    return img




def _clean_text(text):

    text = re.sub(
        r"[^A-Za-zА-Яа-яЁё0-9_\-\[\] ]",
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


    for i in range(len(data["text"])):

        txt=data["text"][i].strip()


        if not txt:
            continue


        words.append({

            "text":txt,

            "x":data["left"][i],

            "y":data["top"][i],

            "w":data["width"][i],

            "h":data["height"][i],

            "cy":
            data["top"][i]
            +
            data["height"][i]/2

        })


    if not words:

        return []



    words.sort(
        key=lambda x:x["cy"]
    )


    lines=[]

    current=[]

    last_y=None



    for word in words:


        if (
            last_y is None
            or abs(word["cy"]-last_y)<25
        ):

            current.append(word)

            last_y=word["cy"]


        else:

            lines.append(
                sorted(
                    current,
                    key=lambda x:x["x"]
                )
            )

            current=[word]

            last_y=word["cy"]



    if current:

        lines.append(
            sorted(
                current,
                key=lambda x:x["x"]
            )
        )


    return lines
    def _parse_player(line, side):

    text = " ".join(
        x["text"] for x in line
    )

    low = text.lower()


    if "имя" in low or "деньги" in low:
        return None



    numbers=[]


    for word in line:

        t=word["text"]


        # убираем деньги
        if "$" in t:
            continue


        # заменяем ошибки OCR
        t=t.replace("O","0")
        t=t.replace("I","1")


        if t.isdigit():

            numbers.append(
                (
                    word["x"],
                    int(t)
                )
            )



    # нужны только K A D SCORE PING

    if len(numbers)<5:

        return None



    values = numbers[-5:]


    kills = values[0][1]
    assists = values[1][1]
    deaths = values[2][1]
    score = values[3][1]
    ping = values[4][1]



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



    stat_x = values[0][0]


    nick_parts=[]


    for w in line:

        if w["x"] < stat_x:

            nick_parts.append(
                w["text"]
            )


    nick=_clean_text(
        " ".join(nick_parts)
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



    players=[]


    for line in _group_lines(data):


        p=_parse_player(
            line,
            side
        )


        if p:

            players.append(
                p
            )


    return players[:5], raw





def _get_score(img):


    w,h=img.size


    crop=img.crop(
        (
            int(w*0.42),
            int(h*0.08),
            int(w*0.58),
            int(h*0.22)
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

        return (
            nums[0]
            +
            ":"
            +
            nums[1]
        )


    return None





def _get_map(img):


    w,h=img.size


    crop=img.crop(
        (
            0,
            int(h*0.82),
            int(w*0.6),
            h
        )
    )


    crop=_preprocess(
        crop
    )


    text=pytesseract.image_to_string(
        crop,
        lang="eng+rus",
        config="--psm 7"
    ).lower()



    for m in MAPS:

        if m.lower() in text:

            return m



    fixes={

        "dun":"Dune",

        "dune":"Dune",

        "hanami":"Hanami",

        "rust":"Rust",

        "province":"Province",

        "prison":"Prison",

        "sandstone":"Sandstone",

        "breeze":"Breeze"

    }



    for k,v in fixes.items():

        if k in text:

            return v



    return None





def parse_standoff_scoreboard(image):


    if not OCR_AVAILABLE:

        return {

            "map":None,

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
            int(h*0.25),
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

        "map":_get_map(img),

        "score":_get_score(img),

        "ct":ct,

        "t":tt

    }





def ocr_match_result(image):


    r=parse_standoff_scoreboard(
        image
    )


    players=[]


    for p in r["ct"]+r["t"]:

        players.append({

            "nickname":p["nick"],

            "kills":p["kills"],

            "deaths":p["deaths"],

            "assists":p["assists"],

            "score":p["score"]

        })



    return {

        "match_score":r["score"],

        "map":r["map"],

        "players":players

    }