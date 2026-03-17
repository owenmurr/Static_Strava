#!/usr/bin/env python3
"""
Strava Static Page Generator
Fetches data from Strava API and generates a static HTML dashboard.
"""

import os
import json
import math
import requests
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Strava API helpers
# ---------------------------------------------------------------------------

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange a refresh token for a new short-lived access token."""
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


def get_athlete(token: str) -> dict:
    resp = requests.get(
        f"{STRAVA_API_BASE}/athlete",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_athlete_stats(token: str, athlete_id: int) -> dict:
    resp = requests.get(
        f"{STRAVA_API_BASE}/athletes/{athlete_id}/stats",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_activities(token: str) -> list:
    """Fetch all activities from the past 365 days via pagination."""
    all_activities = []
    page = 1
    one_year_ago = int((datetime.now(timezone.utc).timestamp()) - 365 * 86400)
    while True:
        resp = requests.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 100, "page": page, "after": one_year_ago},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_activities.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return all_activities


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def metres_to_km(m: float) -> str:
    return f"{m / 1000:.2f} km"


def metres_to_miles(m: float) -> str:
    return f"{m / 1609.344:.2f} mi"


def seconds_to_hms(s: int) -> str:
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m}m {sec:02d}s"


def pace_per_km(distance_m: float, time_s: int) -> str:
    """Returns pace as mm:ss /km"""
    if distance_m <= 0:
        return "—"
    secs_per_km = time_s / (distance_m / 1000)
    mins = int(secs_per_km // 60)
    secs = int(secs_per_km % 60)
    return f"{mins}:{secs:02d} /km"


def elevation_gain(m: float) -> str:
    return f"{m:.0f} m"


def format_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except Exception:
        return iso


def activity_icon(activity_type: str) -> str:
    icons = {
        "Run": "🏃",
        "Ride": "🚴",
        "Swim": "🏊",
        "Walk": "🚶",
        "Hike": "🥾",
        "VirtualRide": "🚴",
        "VirtualRun": "🏃",
        "WeightTraining": "🏋️",
        "Yoga": "🧘",
    }
    return icons.get(activity_type, "⚡")


# ---------------------------------------------------------------------------
# Best efforts extraction
# ---------------------------------------------------------------------------

BEST_EFFORT_DISTANCES = {
    "400m": 400,
    "1K": 1000,
    "5K": 5000,
    "10K": 10000,
    "Half-Marathon": 21097,
    "Marathon": 42195,
}


def extract_best_efforts(activities: list) -> dict:
    """
    Scan activities for best efforts.
    Returns a dict: distance_label -> {time_s, pace, date, activity_name}
    """
    bests: dict = {}
    for act in activities:
        if act.get("type") != "Run":
            continue
        for effort in act.get("best_efforts", []):
            name = effort.get("name", "")
            elapsed = effort.get("elapsed_time", 0)
            if name in BEST_EFFORT_DISTANCES and elapsed > 0:
                if name not in bests or elapsed < bests[name]["time_s"]:
                    dist_m = BEST_EFFORT_DISTANCES[name]
                    bests[name] = {
                        "time_s": elapsed,
                        "formatted": seconds_to_hms(elapsed),
                        "pace": pace_per_km(dist_m, elapsed),
                        "date": format_date(effort.get("start_date_local", "")),
                        "activity_name": act.get("name", "Unknown"),
                    }
    return bests


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def render_activity_card(act: dict, idx: int) -> str:
    name = act.get("name", "Untitled")
    atype = act.get("type", "Run")
    distance = metres_to_km(act.get("distance", 0))
    moving_time = seconds_to_hms(act.get("moving_time", 0))
    elevation = elevation_gain(act.get("total_elevation_gain", 0))
    pace = pace_per_km(act.get("distance", 0), act.get("moving_time", 1))
    date = format_date(act.get("start_date_local", ""))
    icon = activity_icon(atype)
    strava_id = act.get("id", "")
    strava_link = f"https://www.strava.com/activities/{strava_id}" if strava_id else "#"

    delay = idx * 60

    return f"""
    <article class="activity-card" style="animation-delay:{delay}ms">
      <div class="card-header">
        <span class="activity-icon">{icon}</span>
        <div class="card-meta">
          <span class="card-title">{name}</span>
          <span class="card-date">{date} &middot; {atype}</span>
        </div>
      </div>
      <div class="card-stats">
        <div class="stat">
          <span class="stat-value">{distance}</span>
          <span class="stat-label">Distance</span>
        </div>
        <div class="stat">
          <span class="stat-value">{moving_time}</span>
          <span class="stat-label">Time</span>
        </div>
        <div class="stat">
          <span class="stat-value">{pace}</span>
          <span class="stat-label">Pace</span>
        </div>
        <div class="stat">
          <span class="stat-value">{elevation}</span>
          <span class="stat-label">Elevation</span>
        </div>
      </div>
    </article>"""


def render_best_effort_row(label: str, data: dict) -> str:
    return f"""
      <tr>
        <td class="be-distance">{label}</td>
        <td class="be-time">{data['formatted']}</td>
        <td class="be-pace">{data['pace']}</td>
        <td class="be-date">{data['date']}</td>
      </tr>"""


def build_activity_calendar(activities: list) -> str:
    """
    Build a GitHub-style 52-week activity calendar as an HTML grid.
    Each cell is coloured by run distance:
      0 km  → empty cell
      1-5   → level 1 (faint orange)
      5-10  → level 2
      10-15 → level 3
      15+   → level 4 (full orange)
    """
    from datetime import date, timedelta

    # Map date string -> total km run that day
    day_km: dict[str, float] = {}
    for act in activities:
        if act.get("type") != "Run":
            continue
        raw = act.get("start_date_local", "")
        if not raw:
            continue
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
            key = d.isoformat()
            day_km[key] = day_km.get(key, 0) + act.get("distance", 0) / 1000
        except Exception:
            continue

    def km_to_level(km: float) -> int:
        if km <= 0:   return 0
        if km < 5:    return 1
        if km < 10:   return 2
        if km < 15:   return 3
        return 4

    today = date.today()
    # Start from the Sunday of the week 52 weeks ago
    start = today - timedelta(weeks=52)
    start = start - timedelta(days=start.weekday() + 1)  # rewind to Sunday
    if start.weekday() != 6:
        # ensure we start on a Sunday
        start = start - timedelta(days=(start.weekday() + 1) % 7)

    # Build columns (weeks), each column = 7 days (Sun→Sat)
    weeks = []
    cursor = start
    while cursor <= today:
        week = []
        for _ in range(7):
            key = cursor.isoformat()
            km = day_km.get(key, 0)
            level = km_to_level(km)
            in_range = cursor <= today
            week.append((cursor, km, level, in_range))
            cursor += timedelta(days=1)
        weeks.append(week)

    # Month labels — find first week each month appears
    month_labels = []
    seen_months = set()
    for w_idx, week in enumerate(weeks):
        for day, km, level, in_range in week:
            m = (day.year, day.month)
            if m not in seen_months:
                seen_months.add(m)
                month_labels.append((w_idx, day.strftime("%b")))
                break

    # Render month label row
    month_row_cells = []
    label_map = {w_idx: label for w_idx, label in month_labels}
    for w_idx in range(len(weeks)):
        label = label_map.get(w_idx, "")
        month_row_cells.append(f'<div class="cal-month-label">{label}</div>')
    month_row_html = "\n        ".join(month_row_cells)

    # Render week columns
    week_cols = []
    for week in weeks:
        cells = []
        for day, km, level, in_range in week:
            if not in_range:
                cells.append('<div class="cal-cell cal-cell--empty"></div>')
            elif km > 0:
                tip = f"{km:.1f} km on {day.strftime('%d %b %Y')}"
                cells.append(f'<div class="cal-cell cal-cell--l{level}" title="{tip}"></div>')
            else:
                cells.append('<div class="cal-cell cal-cell--rest"></div>')
        week_cols.append('<div class="cal-week">' + "".join(cells) + '</div>')

    weeks_html = "\n        ".join(week_cols)

    day_labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    day_label_html = "\n        ".join(
        f'<div class="cal-day-label">{d if d in ("Mon", "Wed", "Fri") else ""}</div>'
        for d in day_labels
    )

    return f"""
    <section class="section" id="calendar">
      <h2 class="section-title"><span class="title-accent">📅</span> Activity Calendar</h2>
      <div class="calendar-wrap">
        <div class="cal-grid">
          <div class="cal-day-labels">
            {day_label_html}
          </div>
          <div class="cal-body">
            <div class="cal-months">
              {month_row_html}
            </div>
            <div class="cal-weeks">
              {weeks_html}
            </div>
          </div>
        </div>
        <div class="cal-legend">
          <span class="legend-label">Less</span>
          <div class="cal-cell cal-cell--rest legend-cell"></div>
          <div class="cal-cell cal-cell--l1 legend-cell"></div>
          <div class="cal-cell cal-cell--l2 legend-cell"></div>
          <div class="cal-cell cal-cell--l3 legend-cell"></div>
          <div class="cal-cell cal-cell--l4 legend-cell"></div>
          <span class="legend-label">More</span>
        </div>
      </div>
    </section>"""


def generate_html(athlete: dict, stats: dict, activities: list, best_efforts: dict) -> str:
    # ---------- athlete info ----------
    full_name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    profile_pic = athlete.get("profile", "")
    city = athlete.get("city", "")
    country = athlete.get("country", "")
    location = ", ".join(filter(None, [city, country]))

    # ---------- all-time stats ----------
    at = stats.get("all_run_totals", {})
    total_runs = at.get("count", 0)
    total_distance = metres_to_km(at.get("distance", 0))
    total_time = seconds_to_hms(at.get("moving_time", 0))
    total_elevation = elevation_gain(at.get("elevation_gain", 0))

    # ---------- ytd stats ----------
    ytd = stats.get("ytd_run_totals", {})
    ytd_runs = ytd.get("count", 0)
    ytd_distance = metres_to_km(ytd.get("distance", 0))
    ytd_time = seconds_to_hms(ytd.get("moving_time", 0))

    # ---------- activity cards ----------
    activity_cards_html = "\n".join(
        render_activity_card(a, i) for i, a in enumerate(activities[:20])
    )

    # ---------- best efforts rows ----------
    if best_efforts:
        be_rows = "\n".join(
            render_best_effort_row(label, data)
            for label, data in best_efforts.items()
            if label in BEST_EFFORT_DISTANCES
        )
        be_section = f"""
    <section class="section" id="prs">
      <h2 class="section-title"><span class="title-accent">⚡</span> Best Efforts &amp; PRs</h2>
      <div class="table-wrap">
        <table class="be-table">
          <thead>
            <tr>
              <th>Distance</th>
              <th>Time</th>
              <th>Pace</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {be_rows}
          </tbody>
        </table>
      </div>
    </section>"""
    else:
        be_section = """
    <section class="section" id="prs">
      <h2 class="section-title"><span class="title-accent">⚡</span> Best Efforts &amp; PRs</h2>
      <p class="empty-state">No best effort data found. Make sure your activities include segment efforts.</p>
    </section>"""

    # ---------- activity calendar ----------
    calendar_section = build_activity_calendar(activities)

    generated_at = datetime.now(timezone.utc).strftime("%d %b %Y at %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{full_name} · Strava Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg: #0d0d0f;
      --surface: #141417;
      --surface2: #1c1c21;
      --surface3: #232329;
      --border: #2a2a32;
      --orange: #fc4c02;
      --orange-dim: rgba(252, 76, 2, 0.15);
      --orange-glow: rgba(252, 76, 2, 0.35);
      --text: #f0ede8;
      --text-muted: #7a7a8a;
      --text-dim: #4a4a5a;
      --green: #00d68f;
      --radius: 12px;
    }}

    html {{ scroll-behavior: smooth; }}

    body {{
      font-family: 'DM Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      line-height: 1.6;
    }}

    /* ---- Noise texture overlay ---- */
    body::before {{
      content: '';
      position: fixed;
      inset: 0;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
      pointer-events: none;
      z-index: 9999;
      opacity: 0.4;
    }}

    /* ---- Header ---- */
    header {{
      background: linear-gradient(180deg, rgba(252,76,2,0.08) 0%, transparent 100%);
      border-bottom: 1px solid var(--border);
      padding: 2rem 0;
    }}

    .header-inner {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 0 1.5rem;
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }}

    .avatar {{
      width: 72px;
      height: 72px;
      border-radius: 50%;
      border: 2px solid var(--orange);
      box-shadow: 0 0 20px var(--orange-glow);
      object-fit: cover;
      flex-shrink: 0;
    }}

    .avatar-placeholder {{
      width: 72px;
      height: 72px;
      border-radius: 50%;
      border: 2px solid var(--orange);
      background: var(--surface2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
      flex-shrink: 0;
    }}

    .athlete-info h1 {{
      font-family: 'Bebas Neue', sans-serif;
      font-size: 2.4rem;
      letter-spacing: 0.04em;
      line-height: 1;
      color: var(--text);
    }}

    .athlete-info .location {{
      color: var(--text-muted);
      font-size: 0.875rem;
      margin-top: 0.25rem;
    }}

    .strava-badge {{
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      background: var(--orange-dim);
      border: 1px solid var(--orange);
      border-radius: 100px;
      padding: 0.4rem 1rem;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--orange);
      text-decoration: none;
      transition: background 0.2s, box-shadow 0.2s;
    }}

    .strava-badge:hover {{
      background: rgba(252,76,2,0.25);
      box-shadow: 0 0 12px var(--orange-glow);
    }}

    .blog-link {{
      display: flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 100px;
      padding: 0.4rem 1rem;
      font-size: 0.8rem;
      font-weight: 500;
      color: var(--text-muted);
      text-decoration: none;
      transition: color 0.2s, border-color 0.2s, background 0.2s;
    }}

    .blog-link:hover {{
      color: var(--text);
      border-color: var(--text-muted);
      background: var(--surface3);
    }}

    /* ---- Nav ---- */


    /* ---- Main layout ---- */
    main {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 2.5rem 1.5rem 4rem;
    }}

    .section {{
      margin-bottom: 3.5rem;
    }}

    .section-title {{
      font-family: 'Bebas Neue', sans-serif;
      font-size: 1.6rem;
      letter-spacing: 0.06em;
      color: var(--text);
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}

    .title-accent {{
      color: var(--orange);
    }}

    /* ---- Stats grid ---- */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1px;
      background: var(--border);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }}

    .stat-card {{
      background: var(--surface);
      padding: 1.5rem;
      transition: background 0.2s;
    }}

    .stat-card:hover {{
      background: var(--surface2);
    }}

    .stat-card .label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-muted);
      margin-bottom: 0.5rem;
      font-family: 'DM Mono', monospace;
    }}

    .stat-card .value {{
      font-family: 'Bebas Neue', sans-serif;
      font-size: 2rem;
      color: var(--text);
      letter-spacing: 0.03em;
    }}

    .stat-card.highlight .value {{
      color: var(--orange);
    }}

    .stat-card .sub {{
      font-size: 0.75rem;
      color: var(--text-dim);
      margin-top: 0.25rem;
    }}

    /* ---- YTD strip ---- */
    .ytd-strip {{
      display: flex;
      gap: 1rem;
      margin-top: 1rem;
      flex-wrap: wrap;
    }}

    .ytd-pill {{
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 100px;
      padding: 0.4rem 1rem;
      font-size: 0.8rem;
      color: var(--text-muted);
    }}

    .ytd-pill strong {{
      color: var(--green);
      font-family: 'DM Mono', monospace;
    }}

    /* ---- Activity cards ---- */
    .activity-feed {{
      display: grid;
      gap: 0.75rem;
    }}

    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(16px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    .activity-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem 1.5rem;
      opacity: 0;
      animation: fadeUp 0.4s ease forwards;
      transition: border-color 0.2s, background 0.2s;
    }}

    .activity-card:hover {{
      border-color: var(--orange);
      background: var(--surface2);
    }}

    .card-header {{
      display: flex;
      align-items: flex-start;
      gap: 0.9rem;
      margin-bottom: 1rem;
    }}

    .activity-icon {{
      font-size: 1.5rem;
      line-height: 1;
      flex-shrink: 0;
      margin-top: 2px;
    }}

    .card-title {{
      font-weight: 600;
      font-size: 0.95rem;
      color: var(--text);
    }}

    .card-date {{
      font-size: 0.78rem;
      color: var(--text-muted);
      display: block;
      margin-top: 0.1rem;
    }}

    .card-stats {{
      display: flex;
      gap: 2rem;
      flex-wrap: wrap;
    }}

    .stat .stat-value {{
      display: block;
      font-family: 'DM Mono', monospace;
      font-size: 0.9rem;
      font-weight: 500;
      color: var(--text);
    }}

    .stat .stat-label {{
      display: block;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      margin-top: 2px;
    }}

    /* ---- Best efforts table ---- */
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }}

    .be-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }}

    .be-table thead {{
      background: var(--surface2);
    }}

    .be-table th {{
      text-align: left;
      padding: 0.85rem 1.25rem;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-muted);
      font-family: 'DM Mono', monospace;
      font-weight: 400;
      border-bottom: 1px solid var(--border);
    }}

    .be-table td {{
      padding: 0.9rem 1.25rem;
      border-bottom: 1px solid var(--border);
      color: var(--text);
    }}

    .be-table tr:last-child td {{
      border-bottom: none;
    }}

    .be-table tbody tr {{
      background: var(--surface);
      transition: background 0.15s;
    }}

    .be-table tbody tr:hover {{
      background: var(--surface2);
    }}

    .be-distance {{
      font-weight: 600;
      color: var(--orange) !important;
    }}

    .be-time {{
      font-family: 'DM Mono', monospace;
      font-weight: 500;
    }}

    .be-pace {{
      font-family: 'DM Mono', monospace;
      color: var(--text-muted) !important;
    }}

    .be-date {{
      color: var(--text-dim) !important;
      font-size: 0.8rem;
    }}

    /* ---- Footer ---- */
    footer {{
      text-align: center;
      padding: 2rem;
      font-size: 0.78rem;
      color: var(--text-dim);
      border-top: 1px solid var(--border);
    }}

    footer a {{
      color: var(--orange);
      text-decoration: none;
    }}

    .empty-state {{
      color: var(--text-muted);
      font-size: 0.9rem;
      padding: 2rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }}

    /* ---- Activity Calendar ---- */
    .calendar-wrap {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.5rem;
      overflow-x: auto;
    }}

    .cal-grid {{
      display: flex;
      gap: 4px;
      min-width: 700px;
    }}

    .cal-day-labels {{
      display: flex;
      flex-direction: column;
      gap: 3px;
      padding-top: 22px; /* offset for month row */
      margin-right: 4px;
    }}

    .cal-day-label {{
      height: 13px;
      font-size: 0.62rem;
      font-family: 'DM Mono', monospace;
      color: var(--text-dim);
      line-height: 13px;
      text-align: right;
      width: 24px;
    }}

    .cal-body {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }}

    .cal-months {{
      display: flex;
      gap: 3px;
    }}

    .cal-month-label {{
      width: 13px;
      font-size: 0.62rem;
      font-family: 'DM Mono', monospace;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: visible;
    }}

    .cal-weeks {{
      display: flex;
      gap: 3px;
    }}

    .cal-week {{
      display: flex;
      flex-direction: column;
      gap: 3px;
    }}

    .cal-cell {{
      width: 13px;
      height: 13px;
      border-radius: 3px;
      transition: transform 0.1s, opacity 0.1s;
      cursor: default;
    }}

    .cal-cell:hover {{
      transform: scale(1.4);
      z-index: 10;
      position: relative;
    }}

    .cal-cell--empty  {{ background: transparent; }}
    .cal-cell--rest   {{ background: var(--surface3); }}
    .cal-cell--l1     {{ background: rgba(252, 76, 2, 0.25); }}
    .cal-cell--l2     {{ background: rgba(252, 76, 2, 0.50); }}
    .cal-cell--l3     {{ background: rgba(252, 76, 2, 0.75); }}
    .cal-cell--l4     {{ background: var(--orange); box-shadow: 0 0 6px var(--orange-glow); }}

    .cal-legend {{
      display: flex;
      align-items: center;
      gap: 4px;
      margin-top: 0.75rem;
      justify-content: flex-end;
    }}

    .legend-label {{
      font-size: 0.7rem;
      color: var(--text-dim);
      font-family: 'DM Mono', monospace;
    }}

    .legend-cell {{
      cursor: default;
    }}
    .legend-cell:hover {{ transform: none; }}

    @media (max-width: 600px) {{
      .athlete-info h1 {{ font-size: 1.8rem; }}
      .strava-badge {{ display: none; }}
      .card-stats {{ gap: 1.25rem; }}
      .stats-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>

  <header>
    <div class="header-inner">
      {"<img class='avatar' src='" + profile_pic + "' alt='" + full_name + "' />" if profile_pic else "<div class='avatar-placeholder'>🏃</div>"}
      <div class="athlete-info">
        <h1>{full_name}</h1>
        {f'<p class="location">📍 {location}</p>' if location else ''}
      </div>
      <a class="blog-link" href="https://owenmurr.co.uk">← Back to blog</a>
      <a class="strava-badge" href="https://www.strava.com/athletes/{athlete.get('id', '')}" target="_blank" rel="noopener">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>
        View on Strava
      </a>
    </div>
  </header>

  <main>

    <!-- All-time stats -->
    <section class="section" id="stats">
      <h2 class="section-title"><span class="title-accent">📊</span> All-Time Stats</h2>
      <div class="stats-grid">
        <div class="stat-card highlight">
          <div class="label">Total Runs</div>
          <div class="value">{total_runs}</div>
        </div>
        <div class="stat-card">
          <div class="label">Total Distance</div>
          <div class="value">{total_distance}</div>
        </div>
        <div class="stat-card">
          <div class="label">Total Time</div>
          <div class="value">{total_time}</div>
        </div>
        <div class="stat-card">
          <div class="label">Total Elevation</div>
          <div class="value">{total_elevation}</div>
        </div>
      </div>

      <div class="ytd-strip">
        <span class="ytd-pill">Year to date: <strong>{ytd_runs} runs</strong></span>
        <span class="ytd-pill">YTD distance: <strong>{ytd_distance}</strong></span>
        <span class="ytd-pill">YTD time: <strong>{ytd_time}</strong></span>
      </div>
    </section>

    <!-- Activity calendar -->
    {calendar_section}

    <!-- Activity feed -->
    <section class="section" id="activities">
      <h2 class="section-title"><span class="title-accent">🏃</span> Recent Activities</h2>
      <div class="activity-feed">
        {activity_cards_html if activity_cards_html else '<p class="empty-state">No recent activities found.</p>'}
      </div>
    </section>

    <!-- Best efforts -->
    {be_section}

  </main>

  <footer>
    Generated {generated_at} &middot; Powered by <a href="https://www.strava.com" target="_blank">Strava API</a>
  </footer>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    client_id     = os.environ["STRAVA_CLIENT_ID"]
    client_secret = os.environ["STRAVA_CLIENT_SECRET"]
    refresh_token = os.environ["STRAVA_REFRESH_TOKEN"]

    print("🔑  Refreshing Strava access token...")
    token = refresh_access_token(client_id, client_secret, refresh_token)

    print("👤  Fetching athlete profile...")
    athlete = get_athlete(token)
    athlete_id = athlete["id"]

    print("📊  Fetching athlete stats...")
    stats = get_athlete_stats(token, athlete_id)

    print("🏃  Fetching activities (last 365 days)...")
    activities = get_activities(token)

    print("⚡  Extracting best efforts from activities...")
    # For full best efforts, fetch with best_efforts=true (needs individual activity calls)
    # We rely on what's embedded in list activities here
    best_efforts = extract_best_efforts(activities)

    if not best_efforts:
        print("   ℹ️  No best efforts in list endpoint — fetching detailed activities...")
        detailed = []
        for act in activities[:10]:
            if act.get("type") == "Run":
                r = requests.get(
                    f"{STRAVA_API_BASE}/activities/{act['id']}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"include_all_efforts": True},
                    timeout=30,
                )
                if r.ok:
                    detailed.append(r.json())
        best_efforts = extract_best_efforts(detailed)

    print("🎨  Generating HTML...")
    html = generate_html(athlete, stats, activities, best_efforts)

    out_dir = Path("dist")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"✅  Done! Output written to {out_path}")


if __name__ == "__main__":
    main()
