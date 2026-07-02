"""
Thin client for the free public MLB Stats API. No key required.
"""
import requests

BASE = "https://statsapi.mlb.com/api/v1"


def get_live_games(date_str: str) -> list[dict]:
    """
    One call returns every game for the date with live score info attached
    (hydrate=linescore), so we don't need a separate request per game just
    to check the score.
    """
    resp = requests.get(
        f"{BASE}/schedule",
        params={"sportId": 1, "date": date_str, "hydrate": "linescore"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    games = []
    for date_entry in data.get("dates", []):
        for g in date_entry.get("games", []):
            linescore = g.get("linescore", {}) or {}
            teams_ls = linescore.get("teams", {}) or {}
            home_runs = (teams_ls.get("home") or {}).get("runs")
            away_runs = (teams_ls.get("away") or {}).get("runs")

            games.append({
                "game_pk": g["gamePk"],
                "status": g["status"]["detailedState"],
                "abstract_state": g["status"].get("abstractGameState"),  # Preview/Live/Final
                "home_team": g["teams"]["home"]["team"]["name"],
                "away_team": g["teams"]["away"]["team"]["name"],
                "home_runs": home_runs,
                "away_runs": away_runs,
                "inning": linescore.get("currentInning"),
                "inning_state": linescore.get("inningState"),  # Top/Bottom/Middle/End
            })
    return games
