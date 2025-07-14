from flask import Flask, render_template_string, jsonify, request
import threading
import webview
from datetime import datetime, timedelta
import os
import pystray
from PIL import Image
import re
import sqlite3

# Import your database functions
from database import get_usage_by_hour, get_usage_by_day, get_usage_by_week, get_website_usage_by_hour, get_website_usage_by_day, get_website_usage_by_week
from database import get_usage_today, get_usage_by_day as get_usage_by_day_flat, get_usage_by_week as get_usage_by_week_flat
from database import get_latest_window_titles
# Assume you have a Tracker class or similar
from tracker import Tracker
from notifier import show_alert

app = Flask(__name__)
tracker = Tracker(alert_callback=show_alert)
tracking_state = {'running': False}

SYSTEM_PROCESSES = set([
    "explorer.exe", "shellexperiencehost.exe", "searchhost.exe",
    "system", "system idle process", "runtimebroker.exe", "startmenuexperiencehost.exe",
    "ctfmon.exe", "dwm.exe", "fontdrvhost.exe", "taskhostw.exe", "smartscreen.exe",
    "securityhealthservice.exe", "searchui.exe", "searchapp.exe", "applicationframehost.exe"
])

@app.route('/api/tracking_state')
def tracking_state_api():
    return jsonify({'running': tracking_state['running']})

@app.route('/api/start_tracking', methods=['POST'])
def start_tracking():
    tracker.start()
    tracking_state['running'] = True
    return jsonify({'success': True})

@app.route('/api/stop_tracking', methods=['POST'])
def stop_tracking():
    tracker.stop()
    tracking_state['running'] = False
    return jsonify({'success': True})

@app.route('/api/current_app')
def current_app():
    """Get current active app info for live updates"""
    if not tracker.is_running():
        return jsonify({'active': False, 'app': None, 'title': None, 'duration': 0})
    
    if tracker.current_app and tracker.start_time:
        now = datetime.now()
        duration = (now - tracker.start_time).total_seconds() / 60.0
        return jsonify({
            'active': True,
            'app': tracker.current_app,
            'title': tracker.current_title,
            'duration': round(duration, 1)
        })
    return jsonify({'active': False, 'app': None, 'title': None, 'duration': 0})

@app.route('/api/usage_data')
def usage_data():
    period = request.args.get('period', 'today')
    # Expanded sets for categorization
    PRODUCTIVE = set([
        # Code editors
        "vscode", "visual studio code", "pycharm", "sublime", "sublime text", "atom", "webstorm", "intellij", "clion", "android studio", "eclipse", "netbeans", "brackets", "notepad++", "notepadqq", "xcode",
        # Notes
        "notion", "onenote", "simplenote", "evernote", "joplin", "obsidian", "standard notes", "google keep", "apple notes",
        # Office
        "word", "excel", "powerpoint", "outlook", "onenote", "office", "libreoffice", "openoffice", "google docs", "google sheets", "google slides", "wps office",
        # Communication/Productivity
        "teams", "slack", "zoom", "github desktop", "trello", "asana", "todoist", "clickup", "jira", "confluence"
    ])
    DISTRACTING = set([
        # Social/entertainment websites
        "youtube", "instagram", "facebook", "twitter", "reddit", "tiktok", "netflix", "discord", "pinterest", "tumblr", "twitch", "roblox", "prime video", "quora", "9gag", "bilibili", "vk", "weibo", "imgur", "kick", "onlyfans", "snapchat", "threads", "mastodon", "clubhouse", "soundcloud", "spotify", "apple music", "gaana", "wynk", "jiosaavn", "amazon music", "pandora", "deezer", "audible"
    ])
    OTHERS = set([
        # Browsers
        "chrome", "google chrome", "firefox", "mozilla firefox", "edge", "microsoft edge", "opera", "brave", "vivaldi", "safari", "chromium",
        # Music apps
        "spotify", "itunes", "vlc", "windows media player", "groove music", "winamp", "foobar2000", "audacious", "rhythmbox", "banshee", "amarok", "clementine", "musicbee", "apple music", "amazon music", "youtube music", "pandora", "deezer", "soundcloud", "audible"
    ])
    # Define get_category function before using it
    def get_category(name):
        n = name.lower()
        # Productive
        if any(p in n for p in PRODUCTIVE):
            return 'Productive'
        # Distracting (websites and apps)
        if any(d in n for d in DISTRACTING):
            return 'Distracting'
        # Others (browsers, music apps)
        if any(o in n for o in OTHERS):
            return 'Others'
        # Default
        return 'Others'
    app_totals = {}
    site_totals = {}
    analytics = {}
    latest_titles = get_latest_window_titles()
    if period == 'today':
        today = datetime.now().strftime('%Y-%m-%d')
        app_hourly = get_usage_by_hour(today)
        web_hourly = get_website_usage_by_hour(today)
        hours = [f"{h:02d}" for h in range(24)]
        data = {h: {"Productive": 0, "Distracting": 0, "Others": 0} for h in hours}
        for hour, app, minutes in app_hourly:
            if app.lower() in SYSTEM_PROCESSES:
                continue
            cat = get_category(app)
            data[hour][cat] += minutes
            app_totals[app] = app_totals.get(app, 0) + minutes
            analytics[app] = analytics.get(app, 0) + minutes
        for hour, site, minutes in web_hourly:
            cat = get_category(site)
            data[hour][cat] += minutes
            site_totals[site] = site_totals.get(site, 0) + minutes
            analytics[site] = analytics.get(site, 0) + minutes
        labels = hours
        productive = [data[h]["Productive"] for h in hours]
        distracting = [data[h]["Distracting"] for h in hours]
        others = [data[h]["Others"] for h in hours]
    elif period == 'last_week':
        today = datetime.now().date()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        app_daily = get_usage_by_day(str(start), str(end))
        web_daily = get_website_usage_by_day(str(start), str(end))
        days = [(start + timedelta(days=i)).strftime("%a") for i in range(7)]
        day_keys = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        data = {d: {"Productive": 0, "Distracting": 0, "Others": 0} for d in day_keys}
        for day, app, minutes in app_daily:
            if app.lower() in SYSTEM_PROCESSES:
                continue
            cat = get_category(app)
            data[day][cat] += minutes
            app_totals[app] = app_totals.get(app, 0) + minutes
            analytics[app] = analytics.get(app, 0) + minutes
        for day, site, minutes in web_daily:
            cat = get_category(site)
            data[day][cat] += minutes
            site_totals[site] = site_totals.get(site, 0) + minutes
            analytics[site] = analytics.get(site, 0) + minutes
        labels = days
        productive = [data[day_keys[i]]["Productive"] for i in range(7)]
        distracting = [data[day_keys[i]]["Distracting"] for i in range(7)]
        others = [data[day_keys[i]]["Others"] for i in range(7)]
    elif period == 'last_month':
        today = datetime.now().date()
        # Get the first and last day of the previous month
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        start = last_of_last_month.replace(day=1)
        end = last_of_last_month
        app_weekly = get_usage_by_week(str(start), str(end))
        web_weekly = get_website_usage_by_week(str(start), str(end))
        # Get all week labels in range
        def week_label(dt):
            return dt.strftime("%Y-%W")
        week_labels = []
        cur = start
        while cur <= end:
            week_labels.append(week_label(cur))
            cur += timedelta(days=7)
        data = {w: {"Productive": 0, "Distracting": 0, "Others": 0} for w in week_labels}
        for week, app, minutes in app_weekly:
            if app.lower() in SYSTEM_PROCESSES:
                continue
            cat = get_category(app)
            if week not in data:
                data[week] = {"Productive": 0, "Distracting": 0, "Others": 0}
            data[week][cat] += minutes
            app_totals[app] = app_totals.get(app, 0) + minutes
            analytics[app] = analytics.get(app, 0) + minutes
        for week, site, minutes in web_weekly:
            cat = get_category(site)
            if week not in data:
                data[week] = {"Productive": 0, "Distracting": 0, "Others": 0}
            data[week][cat] += minutes
            site_totals[site] = site_totals.get(site, 0) + minutes
            analytics[site] = analytics.get(site, 0) + minutes
        labels = week_labels
        productive = [data[w]["Productive"] for w in week_labels]
        distracting = [data[w]["Distracting"] for w in week_labels]
        others = [data[w]["Others"] for w in week_labels]
    else:
        labels = []
        productive = []
        distracting = []
        others = []
    # For widgets
    filtered_app_totals = {app: mins for app, mins in app_totals.items() if app.lower() not in SYSTEM_PROCESSES}
    filtered_site_totals = {site: mins for site, mins in site_totals.items() if '.com' not in site.lower()}
    # Map process name to window title if available
    def split_on_last_divider(text):
        # Split on the last occurrence of any divider: |, -, –, —
        match = re.search(r'(.*)[\|\-–—](.+)', text)
        if match:
            return match.group(2).strip().title()
        return text.strip().title()
    def display_name(app):
        title = latest_titles.get(app)
        if title and title.strip():
            return split_on_last_divider(title)
        return app.title()
    def display_website(site):
        return split_on_last_divider(site)
    total_minutes = sum(filtered_app_totals.values())
    top_productive = sorted([(display_name(app), mins) for app, mins in filtered_app_totals.items() if get_category(app) == 'Productive'], key=lambda x: -x[1])[:3]
    top_distracting = sorted([(display_name(app), mins) for app, mins in filtered_app_totals.items() if get_category(app) == 'Distracting'], key=lambda x: -x[1])[:3]
    top_websites = sorted([(display_website(site), mins) for site, mins in filtered_site_totals.items()], key=lambda x: -x[1])[:3]
    # Use filtered_app_totals for analytics as well
    analytics_list = sorted([
        {"name": display_name(k) if k in filtered_app_totals else display_website(k),
         "minutes": v,
         "category": get_category(k)}
        for k, v in analytics.items() if k.lower() not in SYSTEM_PROCESSES and (k in filtered_app_totals or ('.com' not in k.lower()))
    ], key=lambda x: -x["minutes"])
    return jsonify({
        'labels': labels,
        'productive': productive,
        'distracting': distracting,
        'others': others,
        'summary': {
            'total_minutes': total_minutes,
            'top_productive': top_productive,
            'top_distracting': top_distracting,
            'top_websites': top_websites
        },
        'analytics': analytics_list
    })

@app.route('/')
def index():
    # The HTML includes Chart.js and fetches data from /api/usage_data
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AppUsage Dashboard</title>
        <link rel="icon" type="image/x-icon" href="/static/appusage.ico">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            :root {
                --accent: #6366f1;
                --accent-light: #a5b4fc;
                --accent2: #f59e42;
                --bg: #f7f8fa;
                --bg-card: #fff;
                --bg-sidebar: #f3f4f6;
                --text: #222;
                --text-muted: #6b7280;
                --border: #e5e7eb;
                --shadow: 0 2px 16px #0001;
            }
            body {
                font-family: 'Inter', Arial, sans-serif;
                background: var(--bg);
                color: var(--text);
                margin: 0;
                padding: 0;
                min-height: 100vh;
            }
            .layout {
                display: grid;
                grid-template-columns: 220px 1fr 320px;
                grid-template-rows: 64px 1fr;
                grid-template-areas:
                    "sidebar topbar topbar"
                    "sidebar main right";
                min-height: 100vh;
                background: var(--bg);
            }
            .sidebar {
                grid-area: sidebar;
                background: var(--bg-sidebar);
                display: flex;
                flex-direction: column;
                align-items: stretch;
                padding: 0 0 0 0;
                border-right: 1px solid var(--border);
                min-width: 180px;
                z-index: 2;
            }
            .sidebar-header {
                font-size: 1.3rem;
                font-weight: 700;
                color: var(--accent);
                padding: 28px 0 18px 32px;
                letter-spacing: -1px;
            }
            .sidebar-nav {
                display: flex;
                flex-direction: column;
                gap: 2px;
                margin-top: 8px;
            }
            .sidebar-link {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 10px 24px 10px 32px;
                color: var(--text-muted);
                text-decoration: none;
                border-radius: 8px 0 0 8px;
                font-size: 1.05rem;
                transition: background 0.15s, color 0.15s;
            }
            .sidebar-link.active, .sidebar-link:hover {
                background: var(--accent);
                color: #fff;
            }
            .sidebar-footer {
                margin-top: auto;
                padding: 18px 0 18px 32px;
                color: var(--text-muted);
                font-size: 0.98rem;
            }
            .topbar {
                grid-area: topbar;
                background: var(--bg-card);
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 32px;
                border-bottom: 1px solid var(--border);
                box-shadow: 0 1px 8px #0001;
                z-index: 1;
            }
            .topbar-title {
                font-size: 1.25rem;
                font-weight: 700;
                color: var(--accent);
                letter-spacing: -1px;
            }
            .topbar-actions {
                display: flex;
                align-items: center;
                gap: 18px;
            }
            .period-select {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 0;
            }
            .widget-btn-group {
                display: flex;
                flex-direction: column;
                gap: 6px;
                margin-top: 8px;
                width: 100%;
            }
            .track-btn {
                background: var(--accent);
                color: #fff;
                border: none;
                border-radius: 6px;
                padding: 7px 0;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.15s;
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
            }
            .track-btn:disabled {
                background: #d1d5db;
                color: #888;
                cursor: not-allowed;
            }
            .main {
                grid-area: main;
                padding: 28px 18px 18px 18px;
                display: flex;
                flex-direction: column;
                gap: 18px;
            }
            .main-card {
                background: var(--bg-card);
                border-radius: 16px;
                box-shadow: var(--shadow);
                padding: 18px 18px 10px 18px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .main-card h2 {
                font-size: 1.1rem;
                color: var(--text-muted);
                margin: 0 0 8px 0;
                font-weight: 600;
            }
            .doughnut-container {
                position: relative;
                width: 220px;
                height: 220px;
                margin: 0 auto 8px auto;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .doughnut-container canvas {
                display: block;
                width: 100% !important;
                height: 100% !important;
                aspect-ratio: 1 / 1;
            }
            .doughnut-center-label {
                position: absolute;
                top: 29%;
                left: 50%;
                transform: translate(-50%, 0);
                font-size: 1.5rem;
                font-weight: bold;
                color: var(--accent);
                text-align: center;
                pointer-events: none;
                width: 100%;
                line-height: 1.1;
                z-index: 2;
                white-space: nowrap;
            }
            .chart-container {
                position: relative;
                height: 320px;
                background: var(--bg-sidebar);
                border-radius: 12px;
                box-shadow: 0 1px 8px #0001;
                padding: 12px 10px 10px 10px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            .rightbar {
                grid-area: right;
                background: var(--bg-card);
                border-left: 1px solid var(--border);
                padding: 28px 18px 18px 18px;
                display: flex;
                flex-direction: column;
                gap: 16px;
                min-width: 220px;
            }
            .widgets-grid {
                display: grid;
                grid-template-columns: 1fr;
                grid-template-rows: repeat(5, auto);
                gap: 12px;
            }
            .widget-card {
                background: var(--bg-sidebar);
                border-radius: 10px;
                box-shadow: 0 1px 6px #0001;
                padding: 18px 10px 14px 10px;
                min-width: 120px;
                min-height: 60px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-start;
            }
            .widget-title {
                color: var(--text-muted);
                font-size: 0.98rem;
                margin-bottom: 4px;
                font-weight: 500;
            }
            .widget-value {
                color: var(--accent);
                font-size: 1.3rem;
                font-weight: bold;
                margin-bottom: 2px;
            }
            .widget-list {
                margin: 0;
                padding: 0 0 0 12px;
                color: var(--text);
                font-size: 0.98rem;
            }
            .widget-list li {
                margin-bottom: 1px;
            }
            .analytics-section {
                background: var(--bg-card);
                border-radius: 16px;
                box-shadow: var(--shadow);
                padding: 16px 18px 10px 18px;
                margin-top: 10px;
            }
            .analytics-title {
                font-size: 1.08rem;
                color: var(--accent);
                font-weight: 600;
                margin-bottom: 10px;
            }
            .analytics-list {
                display: flex;
                flex-wrap: wrap;
                gap: 18px;
            }
            .analytics-item {
                background: var(--bg-sidebar);
                border-radius: 10px;
                box-shadow: 0 1px 6px #0001;
                padding: 10px 16px 10px 16px;
                min-width: 180px;
                flex: 1 1 220px;
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                margin-bottom: 8px;
            }
            .analytics-item-title {
                font-size: 1.01rem;
                color: var(--text-muted);
                font-weight: 500;
                margin-bottom: 4px;
            }
            .analytics-bar {
                width: 100%;
                height: 10px;
                background: #e5e7eb;
                border-radius: 6px;
                margin-bottom: 4px;
                overflow: hidden;
            }
            .analytics-bar-inner {
                height: 100%;
                border-radius: 6px;
                background: linear-gradient(90deg, var(--accent), var(--accent2));
            }
            .analytics-value {
                font-size: 0.98rem;
                color: var(--accent2);
                font-weight: 600;
            }
            @media (max-width: 1200px) {
                .layout { grid-template-columns: 60px 1fr 260px; }
                .sidebar { min-width: 60px; }
                .sidebar-header { font-size: 1.1rem; padding-left: 12px; }
                .sidebar-link, .sidebar-footer { padding-left: 12px; }
                .rightbar { min-width: 160px; padding: 18px 6px 10px 6px; }
            }
            @media (max-width: 900px) {
                .layout { grid-template-columns: 0 1fr 0; grid-template-areas: "topbar topbar topbar" "main main right"; }
                .sidebar, .rightbar { display: none; }
                .main { padding: 18px 4px 8px 4px; }
            }
            @media (max-width: 700px) {
                .main-card, .chart-container, .widget-card, .analytics-section { padding: 8px 4px 6px 4px; }
                .main { gap: 8px; }
            }
        </style>
    </head>
    <body>
        <div class="layout">
            <aside class="sidebar">
                <div class="sidebar-header">AppUsage</div>
                <nav class="sidebar-nav">
                    <a href="#" class="sidebar-link active" id="dashboard-link">Dashboard</a>
                    <a href="#" class="sidebar-link" id="app-limits-link">App Limits</a>
                </nav>
                <div class="sidebar-footer">v1.0</div>
            </aside>
            <header class="topbar">
                <span class="topbar-title">App Usage Monitor</span>
                <div class="topbar-actions">
                    <div class="period-select">
                        <label for="period">Period:</label>
                        <select id="period">
                            <option value="today">Today</option>
                            <option value="last_week">Last Week</option>
                            <option value="last_month">Last Month</option>
                        </select>
                    </div>
                </div>
            </header>
            <main class="main" id="main-dashboard">
                <div class="main-card">
                    <div class="chart-container">
                        <canvas id="usageChart"></canvas>
                    </div>
                </div>
                <div class="analytics-section">
                    <div class="analytics-title">Individual App & Website Analytics</div>
                    <div class="analytics-list" id="analytics-list"></div>
                </div>
            </main>
            <main class="main" id="main-app-limits" style="display:none;">
                <div class="main-card">
                    <h2 style="margin-bottom:16px;">Set App Usage Limits</h2>
                    <div id="app-limits-list" style="display:flex; flex-direction:column; gap:12px;"></div>
                </div>
            </main>
            <aside class="rightbar">
                <div class="widgets-grid">
                    <div class="widget-card">
                        <div class="widget-title">Total Usage</div>
                        <div class="doughnut-container">
                            <canvas id="categoryDoughnut"></canvas>
                            <div class="doughnut-center-label" id="doughnut-center-label">--</div>
                        </div>
                        <div class="widget-btn-group">
                            <button class="track-btn" id="start-btn">Start Tracking</button>
                            <button class="track-btn" id="stop-btn">Stop Tracking</button>
                        </div>
                    </div>
                    <div class="widget-card">
                        <div class="widget-title">Top Websites</div>
                        <ol class="widget-list" id="top-websites"></ol>
                    </div>
                    <div class="widget-card">
                        <div class="widget-title">Top Apps</div>
                        <ol class="widget-list" id="top-apps"></ol>
                    </div>
                </div>
            </aside>
        </div>
        <script>
        let chart;
        async function fetchUsageData(period) {
            const res = await fetch(`/api/usage_data?period=${period}`);
            return await res.json();
        }
        function getChartTitle(period) {
            if (period === 'today') return 'App Usage by Hour (Today)';
            if (period === 'last_week') return 'App Usage by Day (Last Week)';
            if (period === 'last_month') return 'App Usage by Week (Last Month)';
            return '';
        }
        function formatMinutes(mins) {
            if (mins < 1) {
                return `${Math.round(mins * 60)}s`;
            }
            const h = Math.floor(mins / 60);
            const m = Math.round(mins % 60);
            return h > 0 ? `${h}h ${m}m` : `${m}m`;
        }
        function updateWidgets(summary, analytics) {
            const webs = summary.top_websites.map(([site, mins]) => `<li>${site} <span style='color:#38bdf8'>${formatMinutes(mins)}</span></li>`).join('');
            document.getElementById('top-websites').innerHTML = webs || '<li style="color:#aaa">None</li>';
            // Show top 3 apps overall, exclude websites ('.com' in name)
            const topApps = analytics.filter(a => !a.name.toLowerCase().includes('.com')).slice(0, 3);
            const appList = topApps.map(a => `<li>${a.name} <span style='color:${a.category === 'Productive' ? '#6366f1' : (a.category === 'Distracting' ? '#f59e42' : '#9ca3af')}'>${formatMinutes(a.minutes)}</span></li>`).join('');
            document.getElementById('top-apps').innerHTML = appList || '<li style="color:#aaa">None</li>';
        }
        function updateAnalytics(analytics) {
            const max = Math.max(...analytics.map(a => a.minutes), 1);
            document.getElementById('analytics-list').innerHTML = analytics.map(a => `
                <div class="analytics-item">
                    <div class="analytics-item-title">${a.name}</div>
                    <div class="analytics-bar"><div class="analytics-bar-inner" style="width:${Math.round(100*a.minutes/max)}%"></div></div>
                    <div class="analytics-value">${formatMinutes(a.minutes)}</div>
                </div>
            `).join('');
        }
        async function renderChart(period) {
            const data = await fetchUsageData(period);
            updateWidgets(data.summary, data.analytics);
            updateAnalytics(data.analytics);
            const ctx = document.getElementById('usageChart').getContext('2d');
            if (chart) chart.destroy();
            chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Productive',
                            data: data.productive,
                            backgroundColor: '#6366f1',
                            borderRadius: 6,
                            barPercentage: 0.7,
                        },
                        {
                            label: 'Distracting',
                            data: data.distracting,
                            backgroundColor: '#f59e42',
                            borderRadius: 6,
                            barPercentage: 0.7,
                        },
                        {
                            label: 'Others',
                            data: data.others,
                            backgroundColor: '#38bdf8',
                            borderRadius: 6,
                            barPercentage: 0.7,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            labels: { color: '#222', font: { size: 13, weight: 'bold' } }
                        },
                        title: {
                            display: true,
                            text: getChartTitle(period),
                            color: '#222',
                            font: { size: 16, weight: 'bold' }
                        },
                        tooltip: {
                            backgroundColor: '#fff',
                            titleColor: '#6366f1',
                            bodyColor: '#222',
                            borderColor: '#6366f1',
                            borderWidth: 1
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: '#e5e7eb' },
                            ticks: { color: '#6b7280', font: { size: 12 } }
                        },
                        y: {
                            grid: { color: '#e5e7eb' },
                            ticks: { color: '#6b7280', font: { size: 12 } }
                        }
                    }
                }
            });
        }
        async function renderDoughnut(period) {
            const data = await fetchUsageData(period);
            const total = data.summary.total_minutes;
            const prod = data.productive.reduce((a, b) => a + b, 0);
            const dist = data.distracting.reduce((a, b) => a + b, 0);
            const oth = data.others.reduce((a, b) => a + b, 0);
            const ctx = document.getElementById('categoryDoughnut').getContext('2d');
            if (window.doughnutChart) window.doughnutChart.destroy();
            window.doughnutChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Productive', 'Distracting', 'Others'],
                    datasets: [{
                        data: [prod, dist, oth],
                        backgroundColor: ['#6366f1', '#f59e42', '#38bdf8'],
                        borderWidth: 2,
                        borderColor: '#fff',
                        hoverOffset: 8
                    }]
                },
                options: {
                    cutout: '70%',
                    plugins: {
                        legend: {
                            display: true,
                            position: 'bottom',
                            align: 'start',
                            labels: {
                                color: '#222',
                                font: { size: 13, weight: 'bold' },
                                boxWidth: 18,
                                boxHeight: 18,
                                padding: 18,
                                textAlign: 'left',
                                usePointStyle: false,
                                align: 'start'
                            }
                        },
                        tooltip: {
                            backgroundColor: '#fff',
                            titleColor: '#6366f1',
                            bodyColor: '#222',
                            borderColor: '#6366f1',
                            borderWidth: 1
                        }
                    }
                }
            });
            document.getElementById('doughnut-center-label').textContent = formatMinutes(total);
        }
        document.getElementById('period').addEventListener('change', function() {
            renderChart(this.value);
            renderDoughnut(this.value);
        });
        // Initial render
        renderChart('today');
        renderDoughnut('today');
        async function updateTrackingButtons() {
            const res = await fetch('/api/tracking_state');
            const data = await res.json();
            document.getElementById('start-btn').disabled = data.running;
            document.getElementById('stop-btn').disabled = !data.running;
        }
        document.getElementById('start-btn').onclick = async function() {
            await fetch('/api/start_tracking', {method: 'POST'});
            updateTrackingButtons();
        };
        document.getElementById('stop-btn').onclick = async function() {
            await fetch('/api/stop_tracking', {method: 'POST'});
            updateTrackingButtons();
        };
        updateTrackingButtons();
        // --- App Limits Tab Logic ---
        const dashboardLink = document.getElementById('dashboard-link');
        const appLimitsLink = document.getElementById('app-limits-link');
        const mainDashboard = document.getElementById('main-dashboard');
        const mainAppLimits = document.getElementById('main-app-limits');
        dashboardLink.onclick = function() {
            dashboardLink.classList.add('active');
            appLimitsLink.classList.remove('active');
            mainDashboard.style.display = '';
            mainAppLimits.style.display = 'none';
        };
        appLimitsLink.onclick = function() {
            dashboardLink.classList.remove('active');
            appLimitsLink.classList.add('active');
            mainDashboard.style.display = 'none';
            mainAppLimits.style.display = '';
            loadAppLimits();
        };
        async function loadAppLimits() {
            const res = await fetch('/api/app_limits');
            const data = await res.json();
            const list = document.getElementById('app-limits-list');
            list.innerHTML = '';
            if (!data.apps.length) {
                list.innerHTML = '<div style="color:#888;">No apps found.</div>';
                return;
            }
            data.apps.forEach(app => {
                const row = document.createElement('div');
                row.style.display = 'flex';
                row.style.alignItems = 'center';
                row.style.gap = '16px';
                row.style.background = 'var(--bg-sidebar)';
                row.style.borderRadius = '8px';
                row.style.padding = '10px 16px';
                row.style.boxShadow = '0 1px 6px #0001';
                row.innerHTML = `
                    <span style="flex:1;font-weight:500;">${app.display_title}</span>
                    <input type="number" min="1" max="1440" value="${app.limit_minutes ?? ''}" placeholder="Limit (min)" style="width:90px;padding:5px 8px;border:1px solid var(--border);border-radius:6px;font-size:1rem;">
                    <button class="track-btn" style="width:auto;min-width:80px;" >Set Limit</button>
                `;
                const input = row.querySelector('input');
                const btn = row.querySelector('button');
                btn.onclick = async () => {
                    const val = parseInt(input.value);
                    if (!val || val < 1) {
                        input.style.borderColor = 'red';
                        return;
                    }
                    btn.disabled = true;
                    btn.textContent = 'Saving...';
                    const resp = await fetch('/api/set_app_limit', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({app_name: app.app_name, limit_minutes: val})
                    });
                    btn.textContent = 'Set Limit';
                    btn.disabled = false;
                    input.style.borderColor = 'var(--border)';
                };
                input.oninput = () => { input.style.borderColor = 'var(--border)'; };
                list.appendChild(row);
            });
        }
        
        // --- Live Updates ---
        async function updateCurrentApp() {
            try {
                const res = await fetch('/api/current_app');
                const data = await res.json();
                
                if (data.active) {
                    document.getElementById('current-app-name').textContent = data.app;
                    document.getElementById('current-app-duration').textContent = `${data.duration} min`;
                } else {
                    document.getElementById('current-app-name').textContent = '--';
                    document.getElementById('current-app-duration').textContent = '--';
                }
            } catch (error) {
                console.error('Error updating current app:', error);
            }
        }
        
        // Auto-refresh functionality
        let refreshInterval;
        
        function startAutoRefresh() {
            // Update current app every second
            updateCurrentApp();
            setInterval(updateCurrentApp, 1000);
            
            // Update charts and data every 30 seconds when tracking
            refreshInterval = setInterval(async () => {
                const trackingState = await fetch('/api/tracking_state').then(r => r.json());
                if (trackingState.running) {
                    const currentPeriod = document.getElementById('period').value;
                    renderChart(currentPeriod);
                    renderDoughnut(currentPeriod);
                }
            }, 30000); // 30 seconds
        }
        
        function stopAutoRefresh() {
            if (refreshInterval) {
                clearInterval(refreshInterval);
                refreshInterval = null;
            }
        }
        
        // Start auto-refresh when page loads
        startAutoRefresh();
        
        // Update tracking buttons and start auto-refresh when tracking starts
        document.getElementById('start-btn').onclick = async function() {
            await fetch('/api/start_tracking', {method: 'POST'});
            updateTrackingButtons();
            startAutoRefresh();
        };
        
        document.getElementById('stop-btn').onclick = async function() {
            await fetch('/api/stop_tracking', {method: 'POST'});
            updateTrackingButtons();
            stopAutoRefresh();
        };
        </script>
    </body>
    </html>
    ''')

# Tray icon support
tray_icon = None
window = None

def on_tray_show_window(icon, item):
    if window:
        window.restore()

def on_tray_exit(icon, item):
    icon.stop()
    os._exit(0)

def setup_tray():
    global tray_icon
    image_path = os.path.join(os.path.dirname(__file__), 'static', 'appusage.ico')
    try:
        image = Image.open(image_path)
    except Exception:
        image = Image.new('RGB', (64, 64), color=(99, 102, 241))  # fallback: purple square
    tray_icon = pystray.Icon("AppUsage", image, "AppUsage Dashboard", menu=pystray.Menu(
        pystray.MenuItem('Show Dashboard', on_tray_show_window),
        pystray.MenuItem('Exit', on_tray_exit)
    ))
    tray_icon.run()

def on_window_closing():
    if window:
        window.hide()
    return False  # Prevent window from closing

def run_flask():
    app.run(port=5000, debug=False, use_reloader=False)

# --- App Limits API ---
@app.route('/api/app_limits')
def app_limits():
    # Get all used apps (from usage logs) and their limits
    conn = sqlite3.connect('app_usage.db')
    c = conn.cursor()
    # Ensure usage_logs table exists
    c.execute('CREATE TABLE IF NOT EXISTS usage_logs (app_name TEXT, title TEXT, start_time TEXT, end_time TEXT, duration REAL)')
    # Get all used apps
    c.execute('SELECT DISTINCT app_name FROM usage_logs')
    apps = [row[0] for row in c.fetchall()]
    # Get all limits
    c.execute('CREATE TABLE IF NOT EXISTS app_limits (app_name TEXT PRIMARY KEY, limit_minutes INTEGER)')
    c.execute('SELECT app_name, limit_minutes FROM app_limits')
    limits = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    # Friendly name mapping for browsers and common apps
    BROWSER_MAP = {
        'chrome.exe': 'Chrome',
        'msedge.exe': 'Edge',
        'firefox.exe': 'Firefox',
        'brave.exe': 'Brave',
        'opera.exe': 'Opera',
        'opera_gx.exe': 'Opera GX',
        'vivaldi.exe': 'Vivaldi',
        'safari.exe': 'Safari',
    }
    COMMON_MAP = {
        'code.exe': 'VSCode',
        'pycharm64.exe': 'PyCharm',
        'word.exe': 'Word',
        'excel.exe': 'Excel',
        'powerpnt.exe': 'PowerPoint',
        'onenote.exe': 'OneNote',
        'outlook.exe': 'Outlook',
        'notepad.exe': 'Notepad',
        'notepad++.exe': 'Notepad++',
        'obsidian.exe': 'Obsidian',
        'teams.exe': 'Teams',
        'slack.exe': 'Slack',
        'discord.exe': 'Discord',
        'spotify.exe': 'Spotify',
        'zoom.exe': 'Zoom',
    }
    def get_friendly_name(app):
        app_l = app.lower()
        if app_l in BROWSER_MAP:
            return BROWSER_MAP[app_l]
        if app_l in COMMON_MAP:
            return COMMON_MAP[app_l]
        if app_l.endswith('.exe'):
            return app_l.replace('.exe', '').capitalize()
        return app.capitalize()
    # Compose result
    result = []
    for app in sorted(apps, key=lambda x: x.lower()):
        friendly_name = get_friendly_name(app)
        result.append({
            'app_name': app,
            'display_title': friendly_name,
            'limit_minutes': limits.get(app)
        })
    return jsonify({'apps': result})

@app.route('/api/set_app_limit', methods=['POST'])
def set_app_limit():
    data = request.get_json()
    app_name = data.get('app_name')
    limit_minutes = data.get('limit_minutes')
    if not app_name or limit_minutes is None:
        return jsonify({'success': False, 'error': 'Missing app_name or limit_minutes'}), 400
    conn = sqlite3.connect('app_usage.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS app_limits (app_name TEXT PRIMARY KEY, limit_minutes INTEGER)')
    c.execute('INSERT OR REPLACE INTO app_limits (app_name, limit_minutes) VALUES (?, ?)', (app_name, limit_minutes))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    tray_thread = threading.Thread(target=setup_tray, daemon=True)
    tray_thread.start()
    window = webview.create_window("AppUsage Dashboard", "http://127.0.0.1:5000",
                                   width=1200, height=800,
                                   min_size=(900, 600),
                                   # icon parameter is not supported by pywebview, so we rely on favicon and OS default
    )
    window.events.closing += on_window_closing
    webview.start() 