import cv2
import pytesseract
import re


pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def recognize_result(path):

    image = cv2.imread(path)


    # увеличиваем скрин
    image = cv2.resize(
        image,
        None,
        fx=3,
        fy=3
    )


    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )


    # убираем шум
    gray = cv2.threshold(
        gray,
        150,
        255,
        cv2.THRESH_BINARY
    )[1]


    text = pytesseract.image_to_string(
        gray,
        lang="eng"
    )


    print(text)


    # ищем счёт 13:8
    match = re.search(
        r"(\d+)\s*[:\-]\s*(\d+)",
        text
    )


    if match:

        team1 = int(match.group(1))
        team2 = int(match.group(2))


        return {
            "team1": team1,
            "team2": team2,
            "winner": (
                "team1"
                if team1 > team2
                else "team2"
            )
        }


    return None