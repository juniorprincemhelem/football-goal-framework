#!/usr/bin/env python3
"""Backtest O/U price bands using actual side prices; never infer prices from lines."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def american_to_decimal(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    if odds == 0:
        return None
    return 1.0 + (100.0 / abs(odds) if odds < 0 else odds / 100.0)


def number(value: Any) -> float | None:
    try:
        return None if value is None or str(value).strip() == "" else float(value)
    except (TypeError, ValueError):
        return None


def grade(total_score: float, line: float) -> str:
    if total_score > line:
        return "over"
    if total_score < line:
        return "under"
    return "push"


def summarize(bets: list[dict[str, Any]]) -> dict[str, Any]:
    decisive = [b for b in bets if b["outcome"] != "push"]
    wins = sum(b["outcome"] == "win" for b in decisive)
    losses = sum(b["outcome"] == "loss" for b in decisive)
    profit = sum(b["profit"] for b in bets)
    n = len(bets)
    return {
        "bets_including_pushes": n,
        "graded_bets": len(decisive),
        "wins": wins,
        "losses": losses,
        "pushes": n - len(decisive),
        "hit_rate": (wins / len(decisive)) if decisive else None,
        "net_units": round(profit, 6),
        "roi": (profit / n) if n else None,
    }


def load_bets(path: Path, min_odds: float, max_odds: float) -> tuple[list[dict[str, Any]], dict[str, int]]:
    bets: list[dict[str, Any]] = []
    audit = defaultdict(int)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            audit["input_rows"] += 1
            line = number(row.get("total_line"))
            away = number(row.get("away_score"))
            home = number(row.get("home_score"))
            if line is None:
                audit["missing_total_line"] += 1
                continue
            if away is None or home is None:
                audit["missing_final_score"] += 1
                continue
            actual_total = away + home
            for side in ("over", "under"):
                price = american_to_decimal(row.get(f"{side}_american"))
                if price is None:
                    audit[f"missing_{side}_price"] += 1
                    continue
                if not (min_odds <= price <= max_odds):
                    continue
                result = grade(actual_total, line)
                outcome = "push" if result == "push" else "win" if result == side else "loss"
                profit = 0.0 if outcome == "push" else price - 1.0 if outcome == "win" else -1.0
                bets.append({
                    "date": row.get("game_date") or "",
                    "season": season_for(row.get("game_date") or ""),
                    "book_id": row.get("book_id") or "",
                    "book_name": row.get("book_name") or "",
                    "snapshot_type": row.get("snapshot_type") or "",
                    "side": side,
                    "decimal_odds": price,
                    "line": line,
                    "actual_total": actual_total,
                    "outcome": outcome,
                    "profit": profit,
                })
                audit["bets_selected"] += 1
    return bets, dict(audit)


def season_for(date_text: str) -> str:
    try:
        d = dt.date.fromisoformat(date_text[:10])
    except ValueError:
        return "unknown"
    start_year = d.year if d.month >= 7 else d.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--min-odds", type=float, default=1.45)
    parser.add_argument("--max-odds", type=float, default=1.49)
    parser.add_argument("--out", default="nba/output/backtest.json")
    args = parser.parse_args()
    if args.min_odds <= 1 or args.max_odds < args.min_odds:
        parser.error("Odds band must satisfy 1 < min-odds <= max-odds")

    bets, audit = load_bets(Path(args.input), args.min_odds, args.max_odds)
    bets.sort(key=lambda x: (x["date"], x["book_id"], x["side"]))
    overall = summarize(bets)

    by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_book: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bet in bets:
        by_season[bet["season"]].append(bet)
        by_book[f'{bet["book_id"]}:{bet["book_name"]}:{bet["snapshot_type"]}'].append(bet)

    # Chronological holdout: earliest 70% of selected observations vs latest 30%.
    split = int(len(bets) * 0.70)
    train = summarize(bets[:split])
    test = summarize(bets[split:])

    report = {
        "method": "flat one-unit stakes; American side prices converted to decimal; pushes void",
        "odds_band_decimal_inclusive": [args.min_odds, args.max_odds],
        "source_file": args.input,
        "audit": audit,
        "overall": overall,
        "chronological_split": {
            "rule": "first 70% of selected bets by date vs final 30%",
            "train": train,
            "test": test,
            "split_after_date": bets[split - 1]["date"] if split > 0 else None,
        },
        "by_season": {key: summarize(value) for key, value in sorted(by_season.items())},
        "by_book_snapshot": {key: summarize(value) for key, value in sorted(by_book.items())},
        "warning": "Overlapping snapshots for the same game are separate observations. Choose one consistent snapshot/book for a deployable strategy; do not pool them as independent games.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
