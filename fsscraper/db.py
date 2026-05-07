#!/usr/bin/env python3
"""
SQLite storage layer for preschool survey data.
"""

import sqlite3
import json
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS surveys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    area TEXT NOT NULL,
    preschool TEXT NOT NULL,
    sub_unit TEXT,
    pdf_url TEXT NOT NULL UNIQUE,
    response_rate INTEGER,
    footer_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    question TEXT NOT NULL,
    column_name TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scores_survey ON scores(survey_id);
CREATE INDEX IF NOT EXISTS idx_scores_category ON scores(category);
CREATE INDEX IF NOT EXISTS idx_surveys_year_area ON surveys(year, area);

CREATE TABLE IF NOT EXISTS addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_name TEXT NOT NULL UNIQUE,
    query_address TEXT NOT NULL,
    lat REAL,
    lng REAL,
    geocoded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_addresses_coords ON addresses(lat, lng);
"""


class SurveyDB:
    def __init__(self, db_path: str = "surveys.db"):
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def insert_survey(self, year: int, area: str, preschool: str, sub_unit: str | None,
                      pdf_url: str, response_rate: int | None, footer_name: str | None,
                      scores: list[dict]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO surveys (year, area, preschool, sub_unit, pdf_url, response_rate, footer_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pdf_url) DO UPDATE SET
                    response_rate=excluded.response_rate,
                    footer_name=excluded.footer_name
                RETURNING id
                """,
                (year, area, preschool, sub_unit, pdf_url, response_rate, footer_name)
            )
            row = cur.fetchone()
            survey_id = row["id"]

            # Clear old scores for this survey
            conn.execute("DELETE FROM scores WHERE survey_id = ?", (survey_id,))

            for s in scores:
                category = s.get("category", "Unknown")
                question = s.get("question", "")
                for col_name, value in s.get("values", {}).items():
                    conn.execute(
                        "INSERT INTO scores (survey_id, category, question, column_name, value) VALUES (?, ?, ?, ?, ?)",
                        (survey_id, category, question, col_name, value)
                    )
            conn.commit()
            return survey_id

    def get_surveys(self, year: int | None = None, area: str | None = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            sql = "SELECT * FROM surveys WHERE 1=1"
            params = []
            if year is not None:
                sql += " AND year = ?"
                params.append(year)
            if area is not None:
                sql += " AND area = ?"
                params.append(area)
            sql += " ORDER BY area, preschool, sub_unit"
            return conn.execute(sql, params).fetchall()

    def get_scores(self, survey_id: int, category: str | None = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            sql = "SELECT * FROM scores WHERE survey_id = ?"
            params = [survey_id]
            if category:
                sql += " AND category = ?"
                params.append(category)
            return conn.execute(sql, params).fetchall()

    def rank_by_overall(self, year: int, area: str | None = None, min_response_rate: int = 0) -> list[sqlite3.Row]:
        """
        Rank preschools by their own overall satisfaction score.
        Uses the synthetic '_self' column for unambiguous matching.
        """
        with self._connect() as conn:
            sql = """
            SELECT s.id, s.year, s.area, s.preschool, s.sub_unit, s.response_rate, s.footer_name, sc.value as score
            FROM surveys s
            JOIN scores sc ON sc.survey_id = s.id
            WHERE s.year = ?
              AND sc.category = 'Helhetsomdöme'
              AND sc.question LIKE '%Jag är nöjd%'
              AND sc.column_name = '_self'
              AND s.response_rate >= ?
            """
            params = [year, min_response_rate]
            if area:
                sql += " AND s.area = ?"
                params.append(area)
            sql += " ORDER BY CAST(sc.value AS REAL) DESC, s.preschool, s.sub_unit"
            return conn.execute(sql, params).fetchall()

    def rank_by_category(self, year: int, category: str, area: str | None = None,
                         min_response_rate: int = 0) -> list[sqlite3.Row]:
        """
        Rank preschools by average score within a category.
        Uses the synthetic '_self' column for unambiguous matching.
        """
        with self._connect() as conn:
            sql = """
            SELECT s.id, s.year, s.area, s.preschool, s.sub_unit, s.response_rate,
                   AVG(CAST(sc.value AS REAL)) as avg_score
            FROM surveys s
            JOIN scores sc ON sc.survey_id = s.id
            WHERE s.year = ?
              AND sc.category = ?
              AND sc.column_name = '_self'
              AND s.response_rate >= ?
            GROUP BY s.id
            """
            params = [year, category, min_response_rate]
            if area:
                sql += " AND s.area = ?"
                params.append(area)
            sql += " ORDER BY avg_score DESC, s.preschool, s.sub_unit"
            return conn.execute(sql, params).fetchall()

    # --- Address / geocoding helpers ---

    def get_addresses_to_geocode(self) -> list[sqlite3.Row]:
        """Return unique preschool names that have not yet been geocoded."""
        with self._connect() as conn:
            return conn.execute("""
                SELECT DISTINCT s.preschool as raw_name
                FROM surveys s
                LEFT JOIN addresses a ON a.raw_name = s.preschool
                WHERE a.raw_name IS NULL
            """).fetchall()

    def insert_address(self, raw_name: str, query_address: str, lat: float | None, lng: float | None, error: str | None = None):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO addresses (raw_name, query_address, lat, lng, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(raw_name) DO UPDATE SET
                    query_address=excluded.query_address,
                    lat=excluded.lat,
                    lng=excluded.lng,
                    error=excluded.error,
                    geocoded_at=CURRENT_TIMESTAMP
                """,
                (raw_name, query_address, lat, lng, error)
            )
            conn.commit()

    def get_surveys_with_coords(self, year: int | None = None, area: str | None = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            sql = """
            SELECT s.*, a.lat, a.lng
            FROM surveys s
            LEFT JOIN addresses a ON a.raw_name = s.preschool
            WHERE 1=1
            """
            params = []
            if year is not None:
                sql += " AND s.year = ?"
                params.append(year)
            if area is not None:
                sql += " AND s.area = ?"
                params.append(area)
            sql += " ORDER BY s.area, s.preschool, s.sub_unit"
            return conn.execute(sql, params).fetchall()
