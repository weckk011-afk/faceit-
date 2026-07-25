import io
import os

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")

CARD_W, CARD_H = 934, 350
BG_COLOR = (24, 26, 32)
ACCENT = (88, 101, 242)  # discord blurple
CARD_BG = (32, 34, 42)
TEXT_MAIN = (255, 255, 255)
TEXT_SUB = (163, 166, 178)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    return mask


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


async def generate_profile_card(member, player: dict) -> io.BytesIO:
    """
    member: discord.Member (для аватарки и имени)
    player: строка из БД (sqlite3.Row) с полями nickname/standoff_id/elo/wins/losses/kills/deaths
    """
    img = Image.new("RGB", (CARD_W, CARD_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # фон карточки
    _rounded_rect(draw, (0, 0, CARD_W, CARD_H), 24, CARD_BG)
    # акцентная полоса слева
    draw.rectangle((0, 0, 10, CARD_H), fill=ACCENT)

    # ---------- аватарка ----------
    avatar_size = 200
    avatar_pos = (48, 75)
    try:
        avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar_img = avatar_img.resize((avatar_size, avatar_size))
        mask = _circle_mask(avatar_size)
        img.paste(avatar_img, avatar_pos, mask)
    except Exception:
        # если не удалось скачать аватарку — рисуем заглушку-кружок
        draw.ellipse(
            (avatar_pos[0], avatar_pos[1], avatar_pos[0] + avatar_size, avatar_pos[1] + avatar_size),
            fill=(60, 63, 74),
        )

    # рамка вокруг аватарки
    draw.ellipse(
        (avatar_pos[0] - 4, avatar_pos[1] - 4,
         avatar_pos[0] + avatar_size + 4, avatar_pos[1] + avatar_size + 4),
        outline=ACCENT, width=4,
    )

    # ---------- текстовые блоки ----------
    text_x = avatar_pos[0] + avatar_size + 40

    nickname = player["nickname"] or member.display_name
    standoff_id = player["standoff_id"] or "—"

    font_name = _font(FONT_BOLD, 42)
    font_sub = _font(FONT_REGULAR, 26)
    font_stat_val = _font(FONT_BOLD, 34)
    font_stat_label = _font(FONT_REGULAR, 20)

    draw.text((text_x, 55), nickname, font=font_name, fill=TEXT_MAIN)
    draw.text((text_x, 110), f"Standoff 2: {standoff_id}", font=font_sub, fill=TEXT_SUB)

    # ELO крупно, справа сверху
    elo_text = str(player["elo"])
    elo_label = "ELO"
    font_elo = _font(FONT_BOLD, 56)
    elo_w = _text_w(draw, elo_text, font_elo)
    draw.text((CARD_W - 48 - elo_w, 45), elo_text, font=font_elo, fill=ACCENT)
    label_w = _text_w(draw, elo_label, font_stat_label)
    draw.text((CARD_W - 48 - label_w, 100), elo_label, font=font_stat_label, fill=TEXT_SUB)

    # ---------- статы снизу ----------
    wins = player["wins"]
    losses = player["losses"]
    kills = player["kills"]
    deaths = player["deaths"]
    
    total_matches = wins + losses
    
    # Защита от деления на ноль
    winrate = round(wins / total_matches * 100, 1) if total_matches > 0 else 0.0
    kd = round(kills / deaths, 2) if deaths > 0 else float(kills)

    # Список характеристик для вывода
    stats = [
        ("Матчи", str(total_matches)),
        ("Winrate", f"{winrate}%"),
        ("W / L", f"{wins} / {losses}"),
        ("K / D", str(kd)),
    ]

    stat_y = 220
    stat_x = text_x
    gap = (CARD_W - 48 - text_x) // len(stats)
    
    for label, value in stats:
        draw.text((stat_x, stat_y), value, font=font_stat_val, fill=TEXT_MAIN)
        draw.text((stat_x, stat_y + 46), label, font=font_stat_label, fill=TEXT_SUB)
        stat_x += gap

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
