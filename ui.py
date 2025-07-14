import customtkinter as ctk
from tkinter import messagebox, simpledialog
from tracker import Tracker
from notifier import show_alert
from database import init_db, get_usage_today, set_limit, get_top_used_apps, get_latest_window_titles, get_website_usage_today, get_usage_by_day, get_usage_by_week, get_website_usage_by_day, get_website_usage_by_week, get_usage_by_hour, get_website_usage_by_hour
from PIL import Image, ImageTk
import os
import sys
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import calendar
from datetime import datetime, timedelta
from utils import get_friendly_app_name

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    def extract_icon_from_exe(exe_path, size=(32, 32)):
        try:
            import win32api, win32con, win32ui
            large, small = win32gui.ExtractIconEx(exe_path, 0)
            if large:
                hicon = large[0]
            elif small:
                hicon = small[0]
            else:
                return None
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, size[0], size[1])
            hdc = hdc.CreateCompatibleDC()
            hdc.SelectObject(hbmp)
            win32gui.DrawIconEx(hdc.GetHandleOutput(), 0, 0, hicon, size[0], size[1], 0, None, win32con.DI_NORMAL)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)
            win32gui.DestroyIcon(hicon)
            return img
        except Exception:
            return None
else:
    def extract_icon_from_exe(exe_path, size=(32, 32)):
        return None

IGNORE_APPS = {
    'explorer.exe', 'Search', 'System', 'Start Menu', 'program manager', 'ShellExperienceHost.exe', 'StartMenuExperienceHost.exe', 'RuntimeBroker.exe', 'SearchUI.exe', 'backgroundTaskHost.exe', 'ctfmon.exe', 'dwm.exe', 'sihost.exe', 'taskhostw.exe', 'TextInputHost.exe', 'LockApp.exe', 'ApplicationFrameHost.exe', 'WindowsInternal.ComposableShell.Experiences.TextInput.InputApp.exe', 'WindowsShellExperienceHost.exe', 'SearchApp.exe', 'StartMenuExperienceHost', 'Widgets.exe', 'WidgetService.exe', 'YourPhone.exe', 'SystemSettings.exe', 'msedgewebview2.exe', 'SecurityHealthSystray.exe', 'SecurityHealthService.exe', 'smartscreen.exe', 'SearchHost.exe', 'SearchFilterHost.exe', 'SearchProtocolHost.exe', 'SearchIndexer.exe', 'Idle', 'Idle.exe', 'DesktopWindowXamlSource', 'backgroundTaskHost', 'SearchApp', 'Widgets', 'WidgetService', 'YourPhone', 'SystemSettings', 'msedgewebview2', 'SecurityHealthSystray', 'SecurityHealthService', 'smartscreen', 'SearchHost', 'SearchFilterHost', 'SearchProtocolHost', 'SearchIndexer', 'Idle', 'Idle.exe', 'DesktopWindowXamlSource',
}

# Normalize IGNORE_APPS for robust comparison
NORMALIZED_IGNORE_APPS = set(x.lower().replace('.exe', '') for x in IGNORE_APPS)

class AppUI:
    def __init__(self, root):
        self.root = root
        self.root.title("App Usage Monitor")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.tracker = Tracker(alert_callback=show_alert)
        self.icon_cache = {}  # exe_path -> PhotoImage
        self.create_widgets()
        self.update_usage_table()
        self.update_website_usage_table()
        self.update_status()
        self.update_stats_charts()
        self.auto_refresh()

    def create_widgets(self):
        # Header
        header = ctk.CTkFrame(self.root, fg_color="#23272e", corner_radius=16)
        header.pack(fill="x", padx=24, pady=(18, 8))
        app_title = ctk.CTkLabel(header, text="App Usage Monitor", font=("Segoe UI", 22, "bold"), text_color="#fff")
        app_title.pack(side="left", padx=16, pady=12)
        self.status_label = ctk.CTkLabel(header, text="Status: Stopped", font=("Segoe UI", 14), text_color="#aaa")
        self.status_label.pack(side="right", padx=16)

        # Period selection
        self.period_var = ctk.StringVar(value="Today")
        period_frame = ctk.CTkFrame(header, fg_color="#23272e")
        period_frame.pack(side="right", padx=16)
        ctk.CTkLabel(period_frame, text="Period:", font=("Segoe UI", 12), text_color="#fff").pack(side="left", padx=(0, 4))
        self.period_menu = ctk.CTkOptionMenu(period_frame, variable=self.period_var, values=["Today", "Last Week", "Last Month"], command=self.on_period_change)
        self.period_menu.pack(side="left")

        # Main horizontal layout
        main = ctk.CTkFrame(self.root, fg_color="#23272e", corner_radius=16)
        main.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.columnconfigure(2, weight=1)

        # Left column: App Usage
        left_col = ctk.CTkFrame(main, fg_color="#1e2127", corner_radius=14)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        app_header = ctk.CTkLabel(left_col, text="App Usage (Today)", font=("Segoe UI", 14, "bold"), text_color="#fff")
        app_header.pack(anchor="w", padx=14, pady=(10, 0))
        self.app_listbox = ctk.CTkScrollableFrame(left_col, width=260, height=320, fg_color="#181a20", corner_radius=8)
        self.app_listbox.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        # Middle column: Website Usage
        mid_col = ctk.CTkFrame(main, fg_color="#1e2127", corner_radius=14)
        mid_col.grid(row=0, column=1, sticky="nsew", padx=8, pady=0)
        web_header = ctk.CTkLabel(mid_col, text="Website Usage (Today)", font=("Segoe UI", 14, "bold"), text_color="#fff")
        web_header.pack(anchor="w", padx=14, pady=(10, 0))
        self.website_listbox = ctk.CTkScrollableFrame(mid_col, width=260, height=320, fg_color="#181a20", corner_radius=8)
        self.website_listbox.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        # Right column: Modern Stacked Bar Chart
        right_col = ctk.CTkFrame(main, fg_color="#1e2127", corner_radius=14)
        right_col.grid(row=0, column=2, sticky="nsew", padx=(8, 0), pady=0)
        stats_header = ctk.CTkLabel(right_col, text="Usage Stats", font=("Segoe UI", 14, "bold"), text_color="#fff")
        stats_header.pack(anchor="w", padx=14, pady=(10, 0))
        self.usage_total_label = ctk.CTkLabel(right_col, text="", font=("Segoe UI", 24, "bold"), text_color="#fff")
        self.usage_total_label.pack(anchor="center", pady=(8, 0))
        self.usage_range_label = ctk.CTkLabel(right_col, text="", font=("Segoe UI", 11), text_color="#aaa")
        self.usage_range_label.pack(anchor="center", pady=(0, 8))
        self.bar_canvas = ctk.CTkCanvas(right_col, width=220, height=140, bg="#181a20", highlightthickness=0)
        self.bar_canvas.pack(padx=18, pady=(0, 8))
        self.bar_legend = ctk.CTkFrame(right_col, fg_color="#181a20")
        self.bar_legend.pack(fill="x", padx=18, pady=(0, 8))

        # Button bar (bottom, right-aligned)
        btn_frame = ctk.CTkFrame(self.root, fg_color="#23272e")
        btn_frame.pack(fill="x", padx=24, pady=(0, 12))
        self.start_btn = ctk.CTkButton(btn_frame, text="Start Tracking", command=self.start_tracking, width=120, height=32, font=("Segoe UI", 12, "bold"), fg_color="#2563eb", hover_color="#1d4ed8", text_color="#fff")
        self.start_btn.pack(side="right", padx=8)
        self.stop_btn = ctk.CTkButton(btn_frame, text="Stop Tracking", command=self.stop_tracking, state="disabled", width=120, height=32, font=("Segoe UI", 12, "bold"), fg_color="#6b7280", hover_color="#374151", text_color="#fff")
        self.stop_btn.pack(side="right", padx=8)

    def start_tracking(self):
        self.tracker.start()
        self.status_label.configure(text="Status: Tracking...")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.root.after(1000, self.update_status)

    def stop_tracking(self):
        self.tracker.stop()
        self.status_label.configure(text="Status: Stopped")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def set_limit_dialog(self, app_name=None):
        # Show a dialog with a list of apps to select and set/edit limit
        if app_name is None:
            apps = [app for app, _ in get_top_used_apps(20)]
            if not apps:
                messagebox.showinfo("No Apps", "No app usage data available yet.")
                return
            dialog = ctk.CTkInputDialog(text="Select app and set limit (min):\n" + "\n".join(apps), title="Set/Edit App Limit")
            app_name = dialog.get_input()
            if not (app_name and app_name in apps):
                if app_name:
                    messagebox.showerror("Error", "App not found in list.")
                return
        try:
            limit = simpledialog.askinteger("Set Limit", f"Max minutes per day for {app_name}:")
            if limit:
                # Normalize app_name for limit storage
                norm_app_name = app_name.lower().replace('.exe', '')
                set_limit(norm_app_name, limit)
                messagebox.showinfo("Limit Set", f"Limit set for {app_name}: {limit} min/day")
        except Exception:
            messagebox.showerror("Error", "Invalid input.")

    def get_icon(self, exe_path, friendly_name=None):
        if not exe_path:
            return None
        key = friendly_name or exe_path
        if key in self.icon_cache:
            return self.icon_cache[key]
        img = extract_icon_from_exe(exe_path)
        if img:
            photo = ImageTk.PhotoImage(img)
            self.icon_cache[key] = photo
            return photo
        return None

    def on_period_change(self, *args):
        self.update_usage_table()
        self.update_website_usage_table()
        self.update_stats_charts()

    def get_period_dates(self):
        today = datetime.now().date()
        if self.period_var.get() == "Today":
            return today, today
        elif self.period_var.get() == "Last Week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end
        elif self.period_var.get() == "Last Month":
            start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            end = today.replace(day=1) - timedelta(days=1)
            return start, end
        return today, today

    def update_usage_table(self, in_place=False):
        start, end = self.get_period_dates()
        usage = []
        if self.period_var.get() == "Today":
            usage = get_usage_today()
        elif self.period_var.get() == "Last Week":
            usage = get_usage_by_day(str(start), str(end))
        elif self.period_var.get() == "Last Month":
            usage = get_usage_by_week(str(start), str(end))
        exe_map = self.tracker.get_app_exe_map()
        latest_titles = get_latest_window_titles()
        friendly_map = {}
        new_keys = set()
        if not hasattr(self, 'usage_rows'):
            self.usage_rows = {}
        # Aggregate usage by app for the period
        app_totals = {}
        if self.period_var.get() == "Today":
            for app, minutes in usage:
                app_totals[app] = app_totals.get(app, 0) + minutes
        elif self.period_var.get() == "Last Week":
            for day, app, minutes in usage:
                app_totals[app] = app_totals.get(app, 0) + minutes
        elif self.period_var.get() == "Last Month":
            for week, app, minutes in usage:
                app_totals[app] = app_totals.get(app, 0) + minutes
        for idx, (app, minutes) in enumerate(sorted(app_totals.items(), key=lambda x: -x[1])):
            app_norm = app.lower().replace('.exe', '')
            exe_path = exe_map.get(app)
            window_title = latest_titles.get(app)
            friendly_name = get_friendly_app_name(exe_path, app, window_title)
            friendly_norm = friendly_name.lower().replace('.exe', '')
            if app_norm in NORMALIZED_IGNORE_APPS or friendly_norm in NORMALIZED_IGNORE_APPS:
                continue
            friendly_map[app] = friendly_name
            new_keys.add(friendly_name)
            icon = self.get_icon(exe_path, friendly_name)
            bg = "#23272e" if idx % 2 == 0 else "#181a20"
            if friendly_name not in self.usage_rows:
                row = ctk.CTkFrame(self.app_listbox, fg_color=bg, corner_radius=6, height=36)
                row.pack(fill="x", pady=1, padx=2)
                if icon:
                    icon_label = ctk.CTkLabel(row, image=icon, text="", width=28)
                    icon_label.image = icon
                    icon_label.pack(side="left", padx=6)
                else:
                    icon_label = ctk.CTkLabel(row, text="🖥️", width=28)
                    icon_label.pack(side="left", padx=6)
                name_label = ctk.CTkLabel(row, text=friendly_name, font=("Segoe UI", 12, "bold"), text_color="#fff")
                name_label.pack(side="left", padx=8)
                mins_label = ctk.CTkLabel(row, text=f"{minutes:.1f} min", font=("Segoe UI", 11), text_color="#aaa")
                mins_label.pack(side="right", padx=8)
                # Only show per-app limit button if not a system process
                limit_btn = ctk.CTkButton(row, text="", width=28, height=28, font=("Segoe UI", 14), fg_color="#a21caf", hover_color="#7c1fa2", command=lambda app=app: self.set_limit_dialog(app))
                limit_btn.configure(text="⏳")
                limit_btn.pack(side="right", padx=4)
                self.usage_rows[friendly_name] = (row, name_label, mins_label, icon_label, limit_btn)
            else:
                row, name_label, mins_label, icon_label, limit_btn = self.usage_rows[friendly_name]
                if name_label.cget("text") != friendly_name:
                    name_label.configure(text=friendly_name)
                if mins_label.cget("text") != f"{minutes:.1f} min":
                    mins_label.configure(text=f"{minutes:.1f} min")
        for key in list(self.usage_rows.keys()):
            if key not in new_keys:
                row, _, _, _, _ = self.usage_rows[key]
                row.destroy()
                del self.usage_rows[key]
        self.friendly_map = friendly_map

    def update_website_usage_table(self):
        start, end = self.get_period_dates()
        usage = []
        if self.period_var.get() == "Today":
            usage = get_website_usage_today()
        elif self.period_var.get() == "Last Week":
            usage = get_website_usage_by_day(str(start), str(end))
        elif self.period_var.get() == "Last Month":
            usage = get_website_usage_by_week(str(start), str(end))
        new_keys = set()
        if not hasattr(self, 'website_rows'):
            self.website_rows = {}
        # Aggregate usage by site for the period
        site_totals = {}
        if self.period_var.get() == "Today":
            for site, minutes in usage:
                site_totals[site] = site_totals.get(site, 0) + minutes
        elif self.period_var.get() == "Last Week":
            for day, site, minutes in usage:
                site_totals[site] = site_totals.get(site, 0) + minutes
        elif self.period_var.get() == "Last Month":
            for week, site, minutes in usage:
                site_totals[site] = site_totals.get(site, 0) + minutes
        for idx, (site, minutes) in enumerate(sorted(site_totals.items(), key=lambda x: -x[1])):
            site_display = site.capitalize()
            new_keys.add(site_display)
            bg = "#23272e" if idx % 2 == 0 else "#181a20"
            if site_display not in self.website_rows:
                row = ctk.CTkFrame(self.website_listbox, fg_color=bg, corner_radius=6, height=36)
                row.pack(fill="x", pady=1, padx=2)
                icon_label = ctk.CTkLabel(row, text="🌐", width=28)
                icon_label.pack(side="left", padx=6)
                name_label = ctk.CTkLabel(row, text=site_display, font=("Segoe UI", 12, "bold"), text_color="#fff")
                name_label.pack(side="left", padx=8)
                mins_label = ctk.CTkLabel(row, text=f"{minutes:.1f} min", font=("Segoe UI", 11), text_color="#aaa")
                mins_label.pack(side="right", padx=8)
                self.website_rows[site_display] = (row, name_label, mins_label, icon_label)
            else:
                row, name_label, mins_label, icon_label = self.website_rows[site_display]
                if name_label.cget("text") != site_display:
                    name_label.configure(text=site_display)
                if mins_label.cget("text") != f"{minutes:.1f} min":
                    mins_label.configure(text=f"{minutes:.1f} min")
        for key in list(self.website_rows.keys()):
            if key not in new_keys:
                row, _, _, _ = self.website_rows[key]
                row.destroy()
                del self.website_rows[key]

    def update_stats_charts(self, in_place=False):
        from database import get_usage_by_hour, get_usage_by_day, get_usage_by_week, get_website_usage_by_hour, get_website_usage_by_day, get_website_usage_by_week
        today = datetime.now().date()
        start, end = self.get_period_dates()
        period = self.period_var.get()
        DISTRACTING = set(["youtube", "instagram", "facebook", "twitter", "reddit", "tiktok", "netflix", "discord", "pinterest", "tumblr", "twitch", "roblox", "prime video", "quora", "9gag", "bilibili", "vk", "weibo", "imgur", "kick", "onlyfans"])
        PRODUCTIVE = set(["notion", "vscode", "pycharm", "word", "excel", "onenote", "outlook", "teams", "slack", "zoom", "google docs", "google sheets", "github desktop"])

        if period == "Today":
            # Hourly
            app_data = get_usage_by_hour(str(today))
            web_data = get_website_usage_by_hour(str(today))
            x_labels = [f"{h:02d}" for h in range(24)]
            x_type = "hour"
        elif period == "Last Week":
            app_data = get_usage_by_day(str(start), str(end))
            web_data = get_website_usage_by_day(str(start), str(end))
            num_days = (end - start).days + 1
            x_labels = [(start + timedelta(days=i)).strftime("%a") for i in range(num_days)]
            x_keys = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(num_days)]
            x_type = "day"
        elif period == "Last Month":
            app_data = get_usage_by_week(str(start), str(end))
            web_data = get_website_usage_by_week(str(start), str(end))
            # Get all week labels in range
            from datetime import date
            def week_label(dt):
                return dt.strftime("%Y-%W")
            week_set = set()
            cur = start
            while cur <= end:
                week_set.add(week_label(cur))
                cur += timedelta(days=7)
            x_labels = sorted(list(week_set))
            x_type = "week"
        else:
            # fallback: clear chart
            self.bar_canvas.delete("all")
            self.usage_total_label.configure(text="")
            self.usage_range_label.configure(text="")
            return

        # Prepare data structure
        if period == "Today":
            data = {h: {"Distracting": 0, "Productive": 0, "Others": 0} for h in x_labels}
            for hour, app, minutes in app_data:
                cat = "Others"
                app_lower = app.lower()
                if any(site in app_lower for site in DISTRACTING):
                    cat = "Distracting"
                elif any(site in app_lower for site in PRODUCTIVE):
                    cat = "Productive"
                data[hour][cat] += minutes
            for hour, site, minutes in web_data:
                cat = "Others"
                site_lower = site.lower()
                if any(s in site_lower for s in DISTRACTING):
                    cat = "Distracting"
                elif any(s in site_lower for s in PRODUCTIVE):
                    cat = "Productive"
                data[hour][cat] += minutes
        elif period == "Last Week":
            data = {d: {"Distracting": 0, "Productive": 0, "Others": 0} for d in x_keys}
            for day, app, minutes in app_data:
                cat = "Others"
                app_lower = app.lower()
                if any(site in app_lower for site in DISTRACTING):
                    cat = "Distracting"
                elif any(site in app_lower for site in PRODUCTIVE):
                    cat = "Productive"
                data[day][cat] += minutes
            for day, site, minutes in web_data:
                cat = "Others"
                site_lower = site.lower()
                if any(s in site_lower for s in DISTRACTING):
                    cat = "Distracting"
                elif any(s in site_lower for s in PRODUCTIVE):
                    cat = "Productive"
                data[day][cat] += minutes
        elif period == "Last Month":
            data = {w: {"Distracting": 0, "Productive": 0, "Others": 0} for w in x_labels}
            for week, app, minutes in app_data:
            cat = "Others"
            app_lower = app.lower()
            if any(site in app_lower for site in DISTRACTING):
                cat = "Distracting"
            elif any(site in app_lower for site in PRODUCTIVE):
                cat = "Productive"
                data[week][cat] += minutes
            for week, site, minutes in web_data:
            cat = "Others"
            site_lower = site.lower()
            if any(s in site_lower for s in DISTRACTING):
                cat = "Distracting"
            elif any(s in site_lower for s in PRODUCTIVE):
                cat = "Productive"
                data[week][cat] += minutes
        else:
            data = {}

        # Draw chart
        self.bar_canvas.delete("all")
        bar_width = 18 if period != "Today" else 8
        gap = 8 if period != "Today" else 4
        x0 = 18
        max_minutes = max((sum(data[k][cat] for cat in data[k]) for k in data), default=1)
        colors = {"Distracting": "#f59e42", "Productive": "#4ade80", "Others": "#9ca3af"}
        for i, k in enumerate(x_labels):
            y = 130
            key = k if period == "Today" else (x_keys[i] if period == "Last Week" else k)
            for cat in ["Others", "Productive", "Distracting"]:
                v = data.get(key, {cat: 0}).get(cat, 0)
                hh = int(110 * v / max_minutes) if max_minutes > 0 else 0
                if hh > 0:
                    self.bar_canvas.create_rectangle(x0 + i * (bar_width + gap), y - hh, x0 + i * (bar_width + gap) + bar_width, y, fill=colors[cat], outline="", width=0)
                    y -= hh
            self.bar_canvas.create_text(x0 + i * (bar_width + gap) + bar_width // 2, 135, text=k, fill="#aaa", font=("Segoe UI", 8, "bold"))
        total_minutes = sum(sum(data[k][cat] for cat in data[k]) for k in data)
        h = int(total_minutes // 60)
        m = int(total_minutes % 60)
        if period == "Today":
            self.usage_range_label.configure(text=f"{today.strftime('%d %b %Y')}")
        elif period == "Last Week":
            self.usage_range_label.configure(text=f"{start.strftime('%d %b')} - {end.strftime('%d %b')}")
        elif period == "Last Month":
            self.usage_range_label.configure(text=f"{start.strftime('%d %b')} - {end.strftime('%d %b')}")
        self.usage_total_label.configure(text=f"{h}h {m}m")

    def update_status(self):
        if self.tracker.is_running():
            self.status_label.configure(text="Status: Tracking...")
            self.root.after(1000, self.update_status)
        else:
            self.status_label.configure(text="Status: Stopped")

    def auto_refresh(self):
        if self.tracker.is_running():
            self.update_usage_table(in_place=True)
            self.update_stats_charts(in_place=True)
            self.update_website_usage_table()
        self.root.after(2000, self.auto_refresh)  # Always reschedule

def main():
    init_db()
    root = ctk.CTk()
    app = AppUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 