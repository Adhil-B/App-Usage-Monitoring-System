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

        # Right column: Custom Pie Charts
        right_col = ctk.CTkFrame(main, fg_color="#1e2127", corner_radius=14)
        right_col.grid(row=0, column=2, sticky="nsew", padx=(8, 0), pady=0)
        stats_header = ctk.CTkLabel(right_col, text="Usage Overview", font=("Segoe UI", 14, "bold"), text_color="#fff")
        stats_header.pack(anchor="w", padx=14, pady=(10, 0))
        self.pie_canvas_app = ctk.CTkCanvas(right_col, width=140, height=140, bg="#181a20", highlightthickness=0)
        self.pie_canvas_app.pack(padx=18, pady=(16, 8))
        self.pie_canvas_web = ctk.CTkCanvas(right_col, width=140, height=140, bg="#181a20", highlightthickness=0)
        self.pie_canvas_web.pack(padx=18, pady=(8, 16))
        self.pie_legend = ctk.CTkFrame(right_col, fg_color="#181a20")
        self.pie_legend.pack(fill="x", padx=18, pady=(0, 8))

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
        # Modern donut-style pie for app usage
        usage = [(app, minutes) for app, minutes in get_usage_today() if app not in IGNORE_APPS]
        total = sum(minutes for _, minutes in usage)
        top = sorted(usage, key=lambda x: -x[1])[:3]
        other = total - sum(x[1] for x in top)
        colors = ["#60a5fa", "#a78bfa", "#fbbf24", "#9ca3af"]  # Pastel blue, purple, yellow, gray
        self.pie_canvas_app.delete("all")
        # Draw shadow
        self.pie_canvas_app.create_oval(18, 18, 122, 122, fill="#111318", outline="", width=0)
        start = 0
        legend_items = []
        for i, (app, minutes) in enumerate(top):
            extent = 360 * minutes / total if total > 0 else 0
            self.pie_canvas_app.create_arc(18, 18, 122, 122, start=start, extent=extent, style="arc", outline=colors[i], width=22)
            start += extent
            legend_items.append((colors[i], self.friendly_map.get(app, app)))
        if other > 0:
            extent = 360 * other / total if total > 0 else 0
            self.pie_canvas_app.create_arc(18, 18, 122, 122, start=start, extent=extent, style="arc", outline=colors[3], width=22)
            legend_items.append((colors[3], "Other"))
        # Center text and subtitle
        self.pie_canvas_app.create_text(70, 62, text=f"{int(total)}", fill="#fff", font=("Segoe UI", 18, "bold"), justify="center")
        self.pie_canvas_app.create_text(70, 86, text="min", fill="#a3a3a3", font=("Segoe UI", 11, "bold"), justify="center")

        # Modern donut-style pie for website usage
        web_usage = get_website_usage_today()
        web_total = sum(minutes for _, minutes in web_usage)
        web_top = sorted(web_usage, key=lambda x: -x[1])[:3]
        web_other = web_total - sum(x[1] for x in web_top)
        self.pie_canvas_web.delete("all")
        self.pie_canvas_web.create_oval(18, 18, 122, 122, fill="#111318", outline="", width=0)
        start = 0
        web_legend_items = []
        for i, (site, minutes) in enumerate(web_top):
            extent = 360 * minutes / web_total if web_total > 0 else 0
            self.pie_canvas_web.create_arc(18, 18, 122, 122, start=start, extent=extent, style="arc", outline=colors[i], width=22)
            start += extent
            web_legend_items.append((colors[i], site.capitalize()))
        if web_other > 0:
            extent = 360 * web_other / web_total if web_total > 0 else 0
            self.pie_canvas_web.create_arc(18, 18, 122, 122, start=start, extent=extent, style="arc", outline=colors[3], width=22)
            web_legend_items.append((colors[3], "Other"))
        self.pie_canvas_web.create_text(70, 62, text=f"{int(web_total)}", fill="#fff", font=("Segoe UI", 18, "bold"), justify="center")
        self.pie_canvas_web.create_text(70, 86, text="min", fill="#a3a3a3", font=("Segoe UI", 11, "bold"), justify="center")

        # Update legend
        for widget in self.pie_legend.winfo_children():
            widget.destroy()
        for color, label in legend_items:
            dot = ctk.CTkLabel(self.pie_legend, text="●", font=("Segoe UI", 14, "bold"), text_color=color)
            dot.pack(side="left", padx=(0, 3))
            txt = ctk.CTkLabel(self.pie_legend, text=label, font=("Segoe UI", 10), text_color="#fff")
            txt.pack(side="left", padx=(0, 10))
        if legend_items and web_legend_items:
            sep = ctk.CTkLabel(self.pie_legend, text="|", font=("Segoe UI", 13), text_color="#aaa")
            sep.pack(side="left", padx=(0, 8))
        for color, label in web_legend_items:
            dot = ctk.CTkLabel(self.pie_legend, text="●", font=("Segoe UI", 14, "bold"), text_color=color)
            dot.pack(side="left", padx=(0, 3))
            txt = ctk.CTkLabel(self.pie_legend, text=label, font=("Segoe UI", 10), text_color="#fff")
            txt.pack(side="left", padx=(0, 10))

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