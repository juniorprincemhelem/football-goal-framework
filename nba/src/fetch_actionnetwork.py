#!/usr/bin/env python3
"""Collect NBA totals and side prices from Action Network's public scoreboard.

Raw JSON is retained. The CSV keeps total_line distinct from Over/Under prices.
No authentication key is required by the public endpoint at implementation time.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "https://api.actionnetwork.com/web/v2/scoreboard/nba?date="
BOOKS_URL = "https://api.actionnetwork.com/web/v1/books"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
    "Accept": "application/json",
}
FIELDS = [
    "game_date", "start_time_utc", "game_id", "game_type", "status",
    "away_team", "home_team", "away_abbr", "home_abbr", "away_score", "home_score",
    "book_id", "book_name", "snapshot_type", "total_line",
    "over_american", "under_american", "source",
]


def get_json(url: str, retries: int = 4) -> Any:
    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code == 404:
                return None
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except Exception as exc:  # network and JSON decoding errors
            last_error = str(exc)
        time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"Request failed for {url}: {last_error}")


def side_value(entries: Any, wanted_side: str, field: str) -> Any:
    if not isinstance(entries, list):
        return None
    for item in entries:
        if not isinstance(item, dict):
            continue
        if item.get("side") == wanted_side and item.get("period") in (None, "event"):
            return item.get(field)
    return None


def clean_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="Inclusive date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Inclusive date YYYY-MM-DD")
    parser.add_argument("--out", default="nba/output")
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if end < start:
        parser.error("--end must be on or after --start")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    book_names: dict[str, str] = {}
    book_error = None
    try:
        book_payload = get_json(BOOKS_URL)
        for book in (book_payload or {}).get("books", []):
            if isinstance(book, dict) and book.get("id") is not None:
                book_names[str(book["id"])] = str(book.get("display_name") or book["id"])
    except Exception as exc:
        book_error = str(exc)

    raw_path = out / "actionnetwork_raw.jsonl"
    csv_path = out / "actionnetwork_totals.csv"
    manifest = {
        "source": "Action Network public NBA scoreboard",
        "endpoint": BASE + "YYYYMMDD",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "book_directory_loaded": bool(book_names),
        "book_directory_error": book_error,
        "dates_requested": 0,
        "dates_successful": 0,
        "dates_with_games": 0,
        "games_seen": 0,
        "market_rows": 0,
        "rows_with_total_line": 0,
        "rows_with_both_side_prices": 0,
        "errors": [],
        "notes": [
            "Total line and side prices are separate fields.",
            "Book 30 is labelled Open; book 15 is labelled Consensus.",
            "All other book IDs are retained as individual book snapshots.",
            "Inspect raw JSON and game_type/status before selecting a competition subset."
        ],
    }

    with raw_path.open("w", encoding="utf-8") as raw_file, csv_path.open(
        "w", newline="", encoding="utf-8"
    ) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        day = start
        while day <= end:
            manifest["dates_requested"] += 1
            date_key = day.strftime("%Y%m%d")
            try:
                payload = get_json(BASE + date_key)
                manifest["dates_successful"] += 1
                games = (payload or {}).get("games", [])
                if games:
                    manifest["dates_with_games"] += 1
                raw_file.write(json.dumps(
                    {"requested_date": day.isoformat(), "payload": payload},
                    separators=(",", ":"), ensure_ascii=False
                ) + "\n")

                for game in games:
                    if not isinstance(game, dict):
                        continue
                    manifest["games_seen"] += 1
                    teams = {
                        team.get("id"): team
                        for team in (game.get("teams") or [])
                        if isinstance(team, dict)
                    }
                    away = teams.get(game.get("away_team_id"), {})
                    home = teams.get(game.get("home_team_id"), {})
                    box = game.get("boxscore") or {}
                    away_score = box.get("total_away_points")
                    if away_score is None:
                        away_score = (box.get("away") or {}).get("points")
                    home_score = box.get("total_home_points")
                    if home_score is None:
                        home_score = (box.get("home") or {}).get("points")

                    base = {
                        "game_date": day.isoformat(),
                        "start_time_utc": game.get("start_time"),
                        "game_id": game.get("id"),
                        "game_type": game.get("type"),
                        "status": game.get("status"),
                        "away_team": away.get("full_name"),
                        "home_team": home.get("full_name"),
                        "away_abbr": away.get("abbr"),
                        "home_abbr": home.get("abbr"),
                        "away_score": clean_number(away_score),
                        "home_score": clean_number(home_score),
                        "source": "actionnetwork",
                    }
                    markets = game.get("markets") or {}
                    for book_id, market in markets.items():
                        event = (market or {}).get("event") or {}
                        totals = event.get("total")
                        if not totals:
                            continue
                        row = dict(base)
                        row["book_id"] = str(book_id)
                        row["book_name"] = book_names.get(str(book_id), f"book_{book_id}")
                        row["snapshot_type"] = (
                            "open" if str(book_id) == "30"
                            else "consensus" if str(book_id) == "15"
                            else "book"
                        )
                        row["total_line"] = clean_number(side_value(totals, "over", "value"))
                        row["over_american"] = clean_number(side_value(totals, "over", "odds"))
                        row["under_american"] = clean_number(side_value(totals, "under", "odds"))
                        writer.writerow(row)
                        manifest["market_rows"] += 1
                        if row["total_line"] is not None:
                            manifest["rows_with_total_line"] += 1
                        if row["over_american"] is not None and row["under_american"] is not None:
                            manifest["rows_with_both_side_prices"] += 1
                raw_file.flush()
                csv_file.flush()
            except Exception as exc:
                manifest["errors"].append({"date": day.isoformat(), "error": str(exc)})
            day += dt.timedelta(days=1)
            time.sleep(max(0.0, args.sleep))

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    if manifest["dates_successful"] == 0:
        raise SystemExit("No dates were successfully retrieved; inspect manifest.json")


if __name__ == "__main__":
    main()
