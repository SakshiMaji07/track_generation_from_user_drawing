import sqlite3
from datetime import datetime


class LeaderboardDB:
    def __init__(self, db_path="leaderboard.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS laps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_hash TEXT NOT NULL,
                    map_name TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    lap_time_s REAL NOT NULL,
                    cone_hits INTEGER NOT NULL,
                    checkpoints_passed INTEGER NOT NULL,
                    total_checkpoints INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            con.commit()

    def insert_lap(
        self,
        map_hash,
        map_name,
        player_name,
        source,
        lap_time_s,
        cone_hits,
        checkpoints_passed,
        total_checkpoints,
    ):
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO laps (
                    map_hash, map_name, player_name, source,
                    lap_time_s, cone_hits, checkpoints_passed,
                    total_checkpoints, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                map_hash,
                map_name,
                player_name,
                source,
                float(lap_time_s),
                int(cone_hits),
                int(checkpoints_passed),
                int(total_checkpoints),
                datetime.now().isoformat(timespec="seconds"),
            ))
            con.commit()

    def get_current_map_leaderboard(self, map_hash, limit=20):
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("""
                SELECT *
                FROM laps
                WHERE map_hash = ?
                ORDER BY lap_time_s ASC, cone_hits ASC, created_at ASC
                LIMIT ?
            """, (map_hash, limit))
            return [dict(r) for r in cur.fetchall()]

    def get_duel_stats(self, map_hash):
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()

            cur.execute("""
                SELECT *
                FROM laps
                WHERE map_hash = ? AND source = 'RAMS-e'
                ORDER BY created_at ASC
            """, (map_hash,))
            ramse_rows = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT *
                FROM laps
                WHERE map_hash = ? AND source = 'Human'
                ORDER BY created_at ASC
            """, (map_hash,))
            human_rows = [dict(r) for r in cur.fetchall()]

        comparisons = min(len(ramse_rows), len(human_rows))
        ramse_wins = 0
        human_wins = 0

        for i in range(comparisons):
            r = ramse_rows[i]
            h = human_rows[i]

            r_better = (r["lap_time_s"] < h["lap_time_s"]) and (r["cone_hits"] < h["cone_hits"])
            h_better = (h["lap_time_s"] < r["lap_time_s"]) and (h["cone_hits"] < r["cone_hits"])

            if r_better:
                ramse_wins += 1
            elif h_better:
                human_wins += 1

        return {
            "ramse_wins": ramse_wins,
            "human_wins": human_wins,
            "comparisons": comparisons,
        }