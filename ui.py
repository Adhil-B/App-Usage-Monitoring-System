import customtkinter as ctk
from tkinter import messagebox, simpledialog
from tracker import Tracker
from notifier import show_alert
from database import init_db, get_usage_today, set_limit, get_top_used_apps, get_latest_window_titles, get_website_usage_today
from PIL import Image, ImageTk
import os
import sys
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import calendar
from datetime import datetime, timedelta

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

def get_friendly_app_name(exe_path, fallback, window_title=None):
    if exe_path and os.path.exists(exe_path):
        try:
            import win32api
            info = win32api.GetFileVersionInfo(exe_path, '\\')
            # Prefer FileDescription, then ProductName
            if 'StringFileInfo' in info:
                for k, v in info['StringFileInfo'].items():
                    if k.lower() == 'filedescription' and v:
                        return v
                for k, v in info['StringFileInfo'].items():
                    if k.lower() == 'productname' and v:
                        return v
            if 'FileDescription' in info and info['FileDescription']:
                return info['FileDescription']
        except Exception:
            pass
    # If window title contains ' - ', use the part after the last ' - '
    if window_title and window_title.strip() and window_title.strip().lower() not in ["", "program manager", "start menu"]:
        title = window_title.strip()
        if ' - ' in title:
            return title.split(' - ')[-1].strip()
        return title
    return fallback

IGNORE_APPS = {
    'explorer.exe', 'Search', 'System', 'Start Menu', 'program manager', 'ShellExperienceHost.exe', 'StartMenuExperienceHost.exe', 'RuntimeBroker.exe', 'SearchUI.exe', 'backgroundTaskHost.exe', 'ctfmon.exe', 'dwm.exe', 'sihost.exe', 'taskhostw.exe', 'TextInputHost.exe', 'LockApp.exe', 'ApplicationFrameHost.exe', 'WindowsInternal.ComposableShell.Experiences.TextInput.InputApp.exe', 'WindowsShellExperienceHost.exe', 'SearchApp.exe', 'StartMenuExperienceHost', 'Widgets.exe', 'WidgetService.exe', 'YourPhone.exe', 'SystemSettings.exe', 'msedgewebview2.exe', 'SecurityHealthSystray.exe', 'SecurityHealthService.exe', 'smartscreen.exe', 'SearchHost.exe', 'SearchFilterHost.exe', 'SearchProtocolHost.exe', 'SearchIndexer.exe', 'Idle', 'Idle.exe', 'DesktopWindowXamlSource', 'backgroundTaskHost', 'SearchApp', 'Widgets', 'WidgetService', 'YourPhone', 'SystemSettings', 'msedgewebview2', 'SecurityHealthSystray', 'SecurityHealthService', 'smartscreen', 'SearchHost', 'SearchFilterHost', 'SearchProtocolHost', 'SearchIndexer', 'Idle', 'Idle.exe', 'DesktopWindowXamlSource',
}

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
        self.limit_btn = ctk.CTkButton(btn_frame, text="Set/Edit App Limit", command=self.set_limit_dialog, width=150, height=32, font=("Segoe UI", 12, "bold"), fg_color="#a21caf", hover_color="#7c1fa2", text_color="#fff")
        self.limit_btn.pack(side="right", padx=8)

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

    def set_limit_dialog(self):
        # Show a dialog with a list of apps to select and set/edit limit
        apps = [app for app, _ in get_top_used_apps(20)]
        if not apps:
            messagebox.showinfo("No Apps", "No app usage data available yet.")
            return
        dialog = ctk.CTkInputDialog(text="Select app and set limit (min):\n" + "\n".join(apps), title="Set/Edit App Limit")
        app_name = dialog.get_input()
        if app_name and app_name in apps:
            try:
                limit = simpledialog.askinteger("Set Limit", f"Max minutes per day for {app_name}:")
                if limit:
                    set_limit(app_name, limit)
                    messagebox.showinfo("Limit Set", f"Limit set for {app_name}: {limit} min/day")
            except Exception:
                messagebox.showerror("Error", "Invalid input.")
        elif app_name:
            messagebox.showerror("Error", "App not found in list.")

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

    def update_usage_table(self, in_place=False):
        usage = get_usage_today()
        exe_map = self.tracker.get_app_exe_map()
        latest_titles = get_latest_window_titles()
        friendly_map = {}
        new_keys = set()
        if not hasattr(self, 'usage_rows'):
            self.usage_rows = {}
        for idx, (app, minutes) in enumerate(usage):
            if app in IGNORE_APPS:
                continue
            exe_path = exe_map.get(app)
            window_title = latest_titles.get(app)
            friendly_name = get_friendly_app_name(exe_path, app, window_title)
            if friendly_name in IGNORE_APPS:
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
                self.usage_rows[friendly_name] = (row, name_label, mins_label, icon_label)
            else:
                row, name_label, mins_label, icon_label = self.usage_rows[friendly_name]
                if name_label.cget("text") != friendly_name:
                    name_label.configure(text=friendly_name)
                if mins_label.cget("text") != f"{minutes:.1f} min":
                    mins_label.configure(text=f"{minutes:.1f} min")
        for key in list(self.usage_rows.keys()):
            if key not in new_keys:
                row, _, _, _ = self.usage_rows[key]
                row.destroy()
                del self.usage_rows[key]
        self.friendly_map = friendly_map

    def update_website_usage_table(self):
        usage = get_website_usage_today()
        new_keys = set()
        if not hasattr(self, 'website_rows'):
            self.website_rows = {}
        for idx, (site, minutes) in enumerate(usage):
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
        # Modern stacked bar chart for weekly usage
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_days = [(week_start + timedelta(days=i)) for i in range(7)]
        day_labels = [calendar.day_abbr[d.weekday()][0] for d in week_days]
        # Prepare data: {day: {category: minutes}}
        day_data = {d: {"Distracting": 0, "Productive": 0, "Others": 0} for d in week_days}
        # Example: classify apps/sites (customize as needed)
        DISTRACTING = set(["youtube", "instagram", "facebook", "twitter", "reddit", "tiktok", "netflix", "discord", "pinterest", "tumblr", "twitch", "roblox", "prime video", "quora", "9gag", "bilibili", "vk", "weibo", "imgur", "kick", "onlyfans"])
        PRODUCTIVE = set(["notion", "vscode", "pycharm", "word", "excel", "onenote", "outlook", "teams", "slack", "zoom", "google docs", "google sheets", "github desktop"])
        # App usage
        for app, minutes in get_usage_today():
            app_lower = app.lower()
            # For demo, treat all as today
            day = today
            if any(site in app_lower for site in DISTRACTING):
                day_data[day]["Distracting"] += minutes
            elif any(site in app_lower for site in PRODUCTIVE):
                day_data[day]["Productive"] += minutes
            else:
                day_data[day]["Others"] += minutes
        # Website usage
        for site, minutes in get_website_usage_today():
            site_lower = site.lower()
            day = today
            if any(site in site_lower for site in DISTRACTING):
                day_data[day]["Distracting"] += minutes
            elif any(site in site_lower for site in PRODUCTIVE):
                day_data[day]["Productive"] += minutes
            else:
                day_data[day]["Others"] += minutes
        # Draw chart
        self.bar_canvas.delete("all")
        bar_width = 18
        gap = 12
        x0 = 18
        max_minutes = max(sum(day_data[d][cat] for cat in day_data[d]) for d in week_days) or 1
        colors = {"Distracting": "#f59e42", "Productive": "#4ade80", "Others": "#9ca3af"}
        for i, d in enumerate(week_days):
            y = 130
            for cat in ["Others", "Productive", "Distracting"]:
                h = int(110 * day_data[d][cat] / max_minutes) if max_minutes > 0 else 0
                if h > 0:
                    self.bar_canvas.create_rectangle(x0 + i * (bar_width + gap), y - h, x0 + i * (bar_width + gap) + bar_width, y, fill=colors[cat], outline="", width=0)
                    y -= h
            # Day label
            self.bar_canvas.create_text(x0 + i * (bar_width + gap) + bar_width // 2, 135, text=day_labels[i], fill="#aaa", font=("Segoe UI", 11, "bold"))
        # Total usage
        total_minutes = sum(sum(day_data[d][cat] for cat in day_data[d]) for d in week_days)
        h = total_minutes // 60
        m = int(total_minutes % 60)
        self.usage_total_label.configure(text=f"{h}h {m}m")
        self.usage_range_label.configure(text=f"{week_days[0].strftime('%d %b')} - {week_days[-1].strftime('%d %b')}")
        # Legend
        for widget in self.bar_legend.winfo_children():
            widget.destroy()
        for cat, color in colors.items():
            dot = ctk.CTkLabel(self.bar_legend, text="●", font=("Segoe UI", 13, "bold"), text_color=color)
            dot.pack(side="left", padx=(0, 4))
            txt = ctk.CTkLabel(self.bar_legend, text=cat, font=("Segoe UI", 11), text_color="#fff")
            txt.pack(side="left", padx=(0, 12))

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