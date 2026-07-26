import pytesseract
from PIL import Image
import re
import io
import os
import math
import sqlite3
from datetime import datetime

# Настройка Tesseract
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ─── НАСТРОЙКИ ───
ELO_DEFAULT = 299
K_FACTOR = 32
DB_NAME = "standoff_stats.db"


# ──────────────────────────────────────────────
# БАЗА ДАННЫХ
# ──────────────────────────────────────────────

class Database:
    def __init__(self, db_name=DB_NAME):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        """Создаёт таблицы, если их нет."""
        # Таблица игроков
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT UNIQUE NOT NULL,
                elo REAL DEFAULT 299,
                matches_played INTEGER DEFAULT 0,
                total_kills INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица матчей
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                score TEXT,
                winner TEXT,
                team_a_elo_change REAL,
                team_b_elo_change REAL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица участников матча
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                nickname TEXT,
                team TEXT,
                kills INTEGER,
                deaths INTEGER,
                assists INTEGER,
                elo_before REAL,
                elo_after REAL,
                FOREIGN KEY (match_id) REFERENCES matches (id)
            )
        """)

        self.conn.commit()

    # ─── ИГРОКИ ───

    def register_player(self, nickname):
        """Регистрирует нового игрока с ELO 299."""
        try:
            self.cursor.execute(
                "INSERT INTO players (nickname, elo) VALUES (?, ?)",
                (nickname, ELO_DEFAULT)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Уже существует

    def get_player(self, nickname):
        """Получает данные игрока."""
        self.cursor.execute(
            "SELECT * FROM players WHERE nickname = ?",
            (nickname,)
        )
        row = self.cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'nickname': row[1],
                'elo': row[2],
                'matches_played': row[3],
                'total_kills': row[4],
                'total_deaths': row[5],
                'wins': row[6],
                'losses': row[7],
                'registered_at': row[8]
            }
        return None

    def get_all_players(self):
        """Список всех игроков."""
        self.cursor.execute(
            "SELECT nickname, elo, matches_played, wins, losses FROM players ORDER BY elo DESC"
        )
        return self.cursor.fetchall()

    def get_elo(self, nickname):
        """Только ELO игрока."""
        player = self.get_player(nickname)
        return player['elo'] if player else ELO_DEFAULT

    def update_player_stats(self, nickname, kills, deaths, is_win):
        """Обновляет статистику игрока после матча."""
        player = self.get_player(nickname)
        if not player:
            self.register_player(nickname)
            player = self.get_player(nickname)

        self.cursor.execute("""
            UPDATE players 
            SET matches_played = matches_played + 1,
                total_kills = total_kills + ?,
                total_deaths = total_deaths + ?,
                wins = wins + ?,
                losses = losses + ?
            WHERE nickname = ?
        """, (
            kills,
            deaths,
            1 if is_win else 0,
            0 if is_win else 1,
            nickname
        ))
        self.conn.commit()

    def update_elo(self, nickname, new_elo):
        """Обновляет ELO игрока."""
        self.cursor.execute(
            "UPDATE players SET elo = ? WHERE nickname = ?",
            (new_elo, nickname)
        )
        self.conn.commit()

    # ─── МАТЧИ ───

    def add_match(self, score, winner, team_a_elo_change, team_b_elo_change):
        """Добавляет матч в БД."""
        self.cursor.execute("""
            INSERT INTO matches (score, winner, team_a_elo_change, team_b_elo_change)
            VALUES (?, ?, ?, ?)
        """, (score, winner, team_a_elo_change, team_b_elo_change))
        self.conn.commit()
        return self.cursor.lastrowid  # ID матча

    def add_match_player(self, match_id, nickname, team, kills, deaths, assists, elo_before, elo_after):
        """Добавляет участника матча."""
        self.cursor.execute("""
            INSERT INTO match_players (match_id, nickname, team, kills, deaths, assists, elo_before, elo_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (match_id, nickname, team, kills, deaths, assists, elo_before, elo_after))
        self.conn.commit()

    def get_recent_matches(self, limit=10):
        """Последние матчи."""
        self.cursor.execute("""
            SELECT * FROM matches ORDER BY played_at DESC LIMIT ?
        """, (limit,))
        return self.cursor.fetchall()

    def get_match_players(self, match_id):
        """Игроки конкретного матча."""
        self.cursor.execute("""
            SELECT * FROM match_players WHERE match_id = ?
        """, (match_id,))
        return self.cursor.fetchall()

    def get_player_matches(self, nickname, limit=10):
        """Матчи конкретного игрока."""
        self.cursor.execute("""
            SELECT m.*, mp.team, mp.kills, mp.deaths, mp.elo_before, mp.elo_after
            FROM matches m
            JOIN match_players mp ON m.id = mp.match_id
            WHERE mp.nickname = ?
            ORDER BY m.played_at DESC
            LIMIT ?
        """, (nickname, limit))
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()


# ──────────────────────────────────────────────
# OCR
# ──────────────────────────────────────────────

def ocr_match_result(image_input):
    if isinstance(image_input, str):
        image = Image.open(image_input)
    elif isinstance(image_input, bytes):
        image = Image.open(io.BytesIO(image_input))
    elif isinstance(image_input, Image.Image):
        image = image_input
    else:
        raise TypeError("Ожидается путь, bytes или PIL Image")

    config = r'--oem 3 --psm 6 -l rus+eng'
    text = pytesseract.image_to_string(image, config=config)
    return _parse_match_result(text)


def _parse_match_result(text):
    lines = text.split('\n')
    players = []
    match_score = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        score_match = re.search(r'(\d{1,2})\s*[:]\s*(\d{1,2})', line)
        if score_match and not match_score:
            match_score = f"{score_match.group(1)}:{score_match.group(2)}"

        player_match = re.search(
            r'(\S{2,20})\s+(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})\s+(\d{1,3})',
            line
        )
        if player_match:
            players.append({
                'nickname': player_match.group(1),
                'kills': int(player_match.group(2)),
                'deaths': int(player_match.group(3)),
                'assists': int(player_match.group(4)),
                'score': int(player_match.group(5))
            })

    if not players:
        for line in lines:
            line = line.strip()
            simple_match = re.search(r'(\S{2,20})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})', line)
            if simple_match:
                players.append({
                    'nickname': simple_match.group(1),
                    'kills': int(simple_match.group(2)),
                    'deaths': int(simple_match.group(3)),
                    'assists': int(simple_match.group(4)),
                    'score': 0
                })

    return {
        'raw_text': text,
        'match_score': match_score,
        'players': players
    }


# ──────────────────────────────────────────────
# КОМАНДЫ
# ──────────────────────────────────────────────

def split_teams(players, team_a_roster, team_b_roster):
    team_a = []
    team_b = []
    unknown = []

    for p in players:
        nick = p['nickname']
        if nick in team_a_roster:
            team_a.append(p)
        elif nick in team_b_roster:
            team_b.append(p)
        else:
            unknown.append(p)

    return team_a, team_b, unknown


# ──────────────────────────────────────────────
# ELO
# ──────────────────────────────────────────────

def calculate_elo_change(elo_a, elo_b, score_a, score_b, k=K_FACTOR):
    expected_a = 1 / (1 + math.pow(10, (elo_b - elo_a) / 400))
    expected_b = 1 - expected_a

    if score_a > score_b:
        result_a, result_b = 1.0, 0.0
    elif score_a < score_b:
        result_a, result_b = 0.0, 1.0
    else:
        result_a, result_b = 0.5, 0.5

    delta_a = k * (result_a - expected_a)
    delta_b = k * (result_b - expected_b)

    return delta_a, delta_b


# ──────────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ
# ──────────────────────────────────────────────

def process_match_screenshot(image_input, db: Database, team_a_roster, team_b_roster):
    """
    Полный цикл обработки скриншота с сохранением в БД.
    """
    # 1. OCR
    ocr_result = ocr_match_result(image_input)
    players = ocr_result['players']

    if not players:
        return {"success": False, "error": "Игроки не найдены"}

    # 2. Разделение по командам
    team_a, team_b, unknown = split_teams(players, team_a_roster, team_b_roster)

    # 3. Счёт
    score_str = ocr_result.get('match_score', '0:0')
    parts = score_str.split(':')
    score_a, score_b = int(parts[0]), int(parts[1])

    # 4. Победитель
    if score_a > score_b:
        winner = "Team A"
        team_a_won = True
    elif score_b > score_a:
        winner = "Team B"
        team_a_won = False
    else:
        winner = "Draw"
        team_a_won = None

    # 5. Авто-регистрация игроков
    for p in players:
        if not db.get_player(p['nickname']):
            db.register_player(p['nickname'])

    # 6. Расчёт ELO
    elo_result = None
    if team_a and team_b:
        elo_a_avg = sum(db.get_elo(p['nickname']) for p in team_a) / len(team_a)
        elo_b_avg = sum(db.get_elo(p['nickname']) for p in team_b) / len(team_b)

        delta_a, delta_b = calculate_elo_change(elo_a_avg, elo_b_avg, score_a, score_b)

        # Сохраняем ELO до изменений
        elo_before = {}
        for p in team_a + team_b:
            elo_before[p['nickname']] = db.get_elo(p['nickname'])

        # Обновляем ELO
        for p in team_a:
            new_elo = elo_before[p['nickname']] + delta_a
            db.update_elo(p['nickname'], new_elo)
        for p in team_b:
            new_elo = elo_before[p['nickname']] + delta_b
            db.update_elo(p['nickname'], new_elo)

        # Обновляем статистику
        for p in team_a:
            db.update_player_stats(p['nickname'], p['kills'], p['deaths'], team_a_won)
        for p in team_b:
            db.update_player_stats(p['nickname'], p['kills'], p['deaths'], not team_a_won)

        elo_result = {
            'team_a_avg_before': round(elo_a_avg, 1),
            'team_b_avg_before': round(elo_b_avg, 1),
            'team_a_change': round(delta_a, 2),
            'team_b_change': round(delta_b, 2),
            'team_a_avg_after': round(elo_a_avg + delta_a, 1),
            'team_b_avg_after': round(elo_b_avg + delta_b, 1)
        }

    # 7. Сохраняем матч в БД
    match_id = db.add_match(
        score_str,
        winner,
        elo_result['team_a_change'] if elo_result else 0,
        elo_result['team_b_change'] if elo_result else 0
    )

    # 8. Сохраняем участников матча
    for p in team_a:
        db.add_match_player(
            match_id, p['nickname'], 'A',
            p['kills'], p['deaths'], p['assists'],
            elo_before.get(p['nickname'], ELO_DEFAULT),
            db.get_elo(p['nickname'])
        )

    for p in team_b:
        db.add_match_player(
            match_id, p['nickname'], 'B',
            p['kills'], p['deaths'], p['assists'],
            elo_before.get(p['nickname'], ELO_DEFAULT),
            db.get_elo(p['nickname'])
        )

    return {
        "success": True,
        "match_id": match_id,
        "match_score": score_str,
        "winner": winner,
        "team_a": team_a,
        "team_b": team_b,
        "unknown_players": unknown,
        "elo": elo_result
    }


# ──────────────────────────────────────────────
# ТЕСТ
# ──────────────────────────────────────────────
if __name__ == "__main__":
    db = Database()
    print(f"✅ База данных: {DB_NAME}")
    print(f"Начальное ELO: {ELO_DEFAULT}\n")

    # Регистрация игроков (если нужно вручную)
    for nick in ["Player1", "Player2", "Enemy1", "Enemy2"]:
        if db.register_player(nick):
            print(f"Зарегистрирован: {nick} (ELO: {ELO_DEFAULT})")

    print("\n" + "=" * 40)

    result = process_match_screenshot(
        "screenshot.png",
        db,
        team_a_roster={"Player1", "Player2"},
        team_b_roster={"Enemy1", "Enemy2"}
    )

    if result['success']:
        print(f"Матч #{result['match_id']}")
        print(f"Счёт: {result['match_score']}")
        print(f"Победитель: {result['winner']}")

        if result['elo']:
            print(f"\nИзменение ELO:")
            print(f"  Team A: {result['elo']['team_a_change']:+.2f}")
            print(f"  Team B: {result['elo']['team_b_change']:+.2f}")

        print(f"\nТекущий рейтинг:")
        for nick, elo, matches, wins, losses in db.get_all_players():
            print(f"  {nick}: {elo:.1f} ELO | {matches} матчей | {wins}W/{losses}L")

    db.close()