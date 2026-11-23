# NBA totals research

This folder is an independent NBA Over/Under research pipeline. It does not modify the existing football-data workflows.

## Data integrity rules

- A **total line** (for example, 228.5 points) is not a betting price.
- An **Over/Under price** is stored separately as American odds in the source and converted to decimal odds only for analysis.
- Only rows with a real side price and a real total line are eligible for odds-band ROI tests.
- Missing prices are never imputed. A game with only a total line can support score/line analysis, but not price-band profitability claims.
- Open, consensus and individual-book snapshots remain separately labelled. Consensus is not silently relabelled as a bookmaker close.
- Pushes are void: excluded from win-rate denominator and contribute zero profit.
- Backtests use one-unit stakes and chronological splits; they are research outputs, not a claim of future profitability.

## First source: Action Network public scoreboard

The collector calls `https://api.actionnetwork.com/web/v2/scoreboard/nba?date=YYYYMMDD` once per date and preserves the raw response as JSONL. It stores every returned book market, including the market line and separate Over/Under American prices.

Book IDs 30 (Open) and 15 (Consensus) are labelled explicitly. Other IDs remain individual book records. The source can change its schema or availability; inspect the manifest and raw JSON before relying on any run.

## Run locally

```bash
python nba/src/fetch_actionnetwork.py --start 2023-10-01 --end 2024-06-30 --out nba/output
python nba/src/backtest_totals.py --input nba/output/actionnetwork_totals.csv --min-odds 1.45 --max-odds 1.49 --out nba/output/backtest_145_149.json
```

Use separate date ranges for each season if you want clean season-level reporting. The workflow also accepts date inputs and uploads results as a GitHub Actions artifact; it does not commit large data files to the repository.

## Coverage limitation

The first implementation targets verified price-bearing feed data. The historical SBR archive is useful for total-line/result research, but its published archive fields do not establish side-specific Over/Under juice. Those rows must not enter decimal-price ROI calculations unless a separate source supplies the actual side prices.

## Output schema

Each CSV row represents one game and one book/snapshot:

- `game_date`, `start_time_utc`, `game_id`, `game_type`, `status`
- `away_team`, `home_team`, `away_score`, `home_score`
- `book_id`, `book_name`, `snapshot_type`
- `total_line`, `over_american`, `under_american`
- `source`

The manifest records the requested dates, API dates successfully fetched, games, market rows, rows with actual prices, and errors.
