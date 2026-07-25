import sqlite3
import json
import time
from typing import Optional

import config


class Database:
    def __init__(self, path: str = config.DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                nickname TEXT NOT NULL,
                standoff_id TEXT,
                elo INTEGER NOT NULL DEFAULT 1000,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                matches_played INTEGER NOT NULL DEFAULT 0,
                kills INTEGER NOT NULL DEFAULT 0,
                deaths INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS queue (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                team1 TEXT NOT NULL,
                team2 TEXT NOT NULL,
                map TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                winner INTEGER,
                created_at INTEGER NOT NULL,
                category_id INTEGER,
                text_channel_id INTEGER,
                voice1_id INTEGER,
                voice2_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                thread_id INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                created_at INTEGER NOT NULL
            );
            """
        )
        self.conn.commit()

    # ---------- players ----------

    def get_player(self, guild_id: int, user_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM players WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        return cur.fetchone()

    def create_player(
        self, guild_id: int, user_id: int, nickname: str, standoff_id: str = None
    ):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO players (guild_id, user_id, nickname, standoff_id, elo) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, nickname, standoff_id, config.START_ELO),
        )
        self.conn.commit()

    def update_nickname(self, guild_id: int, user_id: int, nickname: str):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE players SET nickname=? WHERE guild_id=? AND user_id=?",
            (nickname, guild_id, user_id),
        )
        self.conn.commit()

    def set_standoff_id(self, guild_id: int, user_id: int, standoff_id: str):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE players SET standoff_id=? WHERE guild_id=? AND user_id=?",
            (standoff_id, guild_id, user_id),
        )
        self.conn.commit()

    def set_kd(self, guild_id: int, user_id: int, kills: int, deaths: int):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE players SET kills=?, deaths=? WHERE guild_id=? AND user_id=?",
            (kills, deaths, guild_id, user_id),
        )
        self.conn.commit()

    def delete_all_players(self, guild_id: int) -> int:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM players WHERE guild_id=?", (guild_id,))
        self.conn.commit()
        return cur.rowcount

    def set_elo(self, guild_id: int, user_id: int, elo: int):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE players SET elo=? WHERE guild_id=? AND user_id=?",
            (elo, guild_id, user_id),
        )
        self.conn.commit()

    def record_result(self, guild_id: int, user_id: int, won: bool, new_elo: int):
        cur = self.conn.cursor()
        if won:
            cur.execute(
                "UPDATE players SET elo=?, wins=wins+1, matches_played=matches_played+1 "
                "WHERE guild_id=? AND user_id=?",
                (new_elo, guild_id, user_id),
            )
        else:
            cur.execute(
                "UPDATE players SET elo=?, losses=losses+1, matches_played=matches_played+1 "
                "WHERE guild_id=? AND user_id=?",
                (new_elo, guild_id, user_id),
            )
        self.conn.commit()

    def get_leaderboard(self, guild_id: int, limit: int = 10):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM players WHERE guild_id=? ORDER BY elo DESC LIMIT ?",
            (guild_id, limit),
        )
        return cur.fetchall()

    # ---------- queue ----------

    def queue_add(self, guild_id: int, user_id: int) -> bool:
        cur = self.conn.cursor()
        try:
            cur.execute(
                "INSERT INTO queue (guild_id, user_id, joined_at) VALUES (?, ?, ?)",
                (guild_id, user_id, int(time.time())),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def queue_remove(self, guild_id: int, user_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM queue WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def queue_list(self, guild_id: int):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM queue WHERE guild_id=? ORDER BY joined_at ASC", (guild_id,)
        )
        return cur.fetchall()

    def queue_clear_users(self, guild_id: int, user_ids: list[int]):
        cur = self.conn.cursor()
        cur.executemany(
            "DELETE FROM queue WHERE guild_id=? AND user_id=?",
            [(guild_id, uid) for uid in user_ids],
        )
        self.conn.commit()

    # ---------- matches ----------

    def create_match(
        self, guild_id: int, team1: list[int], team2: list[int]
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO matches (guild_id, team1, team2, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, json.dumps(team1), json.dumps(team2), int(time.time())),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_match_channels(
        self, match_id: int, category_id: int, text_id: int, voice1_id: int, voice2_id: int
    ):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE matches SET category_id=?, text_channel_id=?, voice1_id=?, voice2_id=? "
            "WHERE id=?",
            (category_id, text_id, voice1_id, voice2_id, match_id),
        )
        self.conn.commit()

    def set_match_map(self, match_id: int, map_name: str):
        cur = self.conn.cursor()
        cur.execute("UPDATE matches SET map=? WHERE id=?", (map_name, match_id))
        self.conn.commit()

    def get_match(self, match_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM matches WHERE id=?", (match_id,))
        return cur.fetchone()

    def finish_match(self, match_id: int, winner: int):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE matches SET status='finished', winner=? WHERE id=?",
            (winner, match_id),
        )
        self.conn.commit()

    def cancel_match(self, match_id: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE matches SET status='cancelled' WHERE id=?", (match_id,))
        self.conn.commit()

    # ---------- tickets ----------

    def create_ticket(self, guild_id: int, user_id: int, category: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO tickets (guild_id, user_id, category, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, category, int(time.time())),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_ticket_thread(self, ticket_id: int, thread_id: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE tickets SET thread_id=? WHERE id=?", (thread_id, ticket_id))
        self.conn.commit()

    def get_ticket_by_thread(self, thread_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE thread_id=?", (thread_id,))
        return cur.fetchone()

    def close_ticket(self, ticket_id: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
        self.conn.commit()
