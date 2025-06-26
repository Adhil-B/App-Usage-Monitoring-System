import customtkinter as ctk
from tkinter import messagebox, simpledialog
from tracker import Tracker
from notifier import show_alert
from database import init_db, get_usage_today, set_limit, get_top_used_apps, get_latest_window_titles
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
            # Try FileDescription first
            if 'StringFileInfo' in info:
                for k, v in info['StringFileInfo'].items():
                    if k.lower() == 'filedescription' and v:
                        return v
                    if k.lower() == 'productname' and v:
                        return v
            if 'FileDescription' in info and info['FileDescription']:
                return info['FileDescription']
        except Exception:
            pass
    # Fallback to window title if available and not generic
    if window_title and window_title.strip() and window_title.strip().lower() not in ["", "program manager", "start menu"]:
        return window_title.strip()
    return fallback

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
        self.update_status()
        self.update_stats_charts()
        self.auto_refresh()

    def create_widgets(self):
        self.tabview = ctk.CTkTabview(self.root, width=700, height=500)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)
        self.dashboard_tab = self.tabview.add("Dashboard")
        self.stats_tab = self.tabview.add("Statistics")

        # Dashboard Tab
        self.status_label = ctk.CTkLabel(self.dashboard_tab, text="Status: Stopped", font=("Segoe UI", 16))
        self.status_label.pack(pady=10)

        btn_frame = ctk.CTkFrame(self.dashboard_tab)
        btn_frame.pack(pady=10)
        self.start_btn = ctk.CTkButton(btn_frame, text="Start Tracking", command=self.start_tracking, width=140)
        self.start_btn.pack(side="left", padx=10)
        self.stop_btn = ctk.CTkButton(btn_frame, text="Stop Tracking", command=self.stop_tracking, state="disabled", width=140)
        self.stop_btn.pack(side="left", padx=10)
        self.limit_btn = ctk.CTkButton(btn_frame, text="Set/Edit App Limit", command=self.set_limit_dialog, width=180)
        self.limit_btn.pack(side="left", padx=10)

        # App Usage Table (with icon placeholder)
        self.usage_table = ctk.CTkFrame(self.dashboard_tab)
        self.usage_table.pack(fill="both", expand=True, pady=10)
        self.app_listbox = ctk.CTkScrollableFrame(self.usage_table, width=600, height=250)
        self.app_listbox.pack(fill="both", expand=True)

        # Statistics Tab (matplotlib charts)
        self.stats_label = ctk.CTkLabel(self.stats_tab, text="Usage Statistics", font=("Segoe UI", 16))
        self.stats_label.pack(pady=10)
        self.stats_canvas = ctk.CTkFrame(self.stats_tab, width=600, height=350)
        self.stats_canvas.pack(pady=10)
        self.pie_canvas = None
        self.bar_canvas = None

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
        # Build new/updated rows
        for app, minutes in usage:
            exe_path = exe_map.get(app)
            window_title = latest_titles.get(app)
            friendly_name = get_friendly_app_name(exe_path, app, window_title)
            friendly_map[app] = friendly_name
            new_keys.add(friendly_name)
            icon = self.get_icon(exe_path, friendly_name)
            if friendly_name not in self.usage_rows:
                row = ctk.CTkFrame(self.app_listbox)
                row.pack(fill="x", pady=2, padx=5)
                if icon:
                    icon_label = ctk.CTkLabel(row, image=icon, text="")
                    icon_label.image = icon
                    icon_label.pack(side="left", padx=2)
                else:
                    icon_label = ctk.CTkLabel(row, text="🖥️", width=30)
                    icon_label.pack(side="left", padx=2)
                name_label = ctk.CTkLabel(row, text=friendly_name, font=("Segoe UI", 13))
                name_label.pack(side="left", padx=10)
                mins_label = ctk.CTkLabel(row, text=f"{minutes:.1f} min", font=("Segoe UI", 13))
                mins_label.pack(side="right", padx=10)
                self.usage_rows[friendly_name] = (row, name_label, mins_label, icon_label)
            else:
                row, name_label, mins_label, icon_label = self.usage_rows[friendly_name]
                # Only update text if changed
                if name_label.cget("text") != friendly_name:
                    name_label.configure(text=friendly_name)
                if mins_label.cget("text") != f"{minutes:.1f} min":
                    mins_label.configure(text=f"{minutes:.1f} min")
                # Optionally update icon if exe_path changes (not implemented here)
        # Remove rows for apps no longer present
        for key in list(self.usage_rows.keys()):
            if key not in new_keys:
                row, _, _, _ = self.usage_rows[key]
                row.destroy()
                del self.usage_rows[key]
        self.friendly_map = friendly_map

    def update_stats_charts(self, in_place=False):
        if not in_place:
            for widget in self.stats_canvas.winfo_children():
                widget.destroy()
        usage = get_usage_today()
        if not usage:
            if not in_place:
                label = ctk.CTkLabel(self.stats_canvas, text="No usage data to display.")
                label.pack()
            return
        try:
            dark_bg = self.root._apply_appearance_mode(ctk.ThemeManager.theme['CTkFrame']['fg_color'])
            if isinstance(dark_bg, (tuple, list)):
                dark_bg = dark_bg[0]
            if not (isinstance(dark_bg, str) and dark_bg.startswith('#')):
                dark_bg = '#242424'
        except Exception:
            dark_bg = '#242424'
        # Use friendly names for chart labels
        exe_map = self.tracker.get_app_exe_map()
        friendly_map = getattr(self, 'friendly_map', {})
        labels = [friendly_map.get(app, app) for app, _ in usage]
        sizes = [minutes for _, minutes in usage]
        fig1 = Figure(figsize=(3.5, 3), dpi=100, facecolor=dark_bg)
        ax1 = fig1.add_subplot(111, facecolor=dark_bg)
        wedges, texts, autotexts = ax1.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, textprops={'color':'white'})
        ax1.set_title("Today's App Usage Distribution", color='white')
        fig1.patch.set_alpha(1.0)
        if in_place and hasattr(self, 'pie_canvas') and self.pie_canvas:
            self.pie_canvas.get_tk_widget().destroy()
        self.pie_canvas = FigureCanvasTkAgg(fig1, master=self.stats_canvas)
        self.pie_canvas.draw()
        self.pie_canvas.get_tk_widget().pack(side="left", padx=10)
        # Bar chart for top apps
        top_apps = get_top_used_apps(10)
        bar_labels = [get_friendly_app_name(exe_map.get(app), app) for app, _ in top_apps]
        bar_values = [minutes for _, minutes in top_apps]
        fig2 = Figure(figsize=(3.5, 3), dpi=100, facecolor=dark_bg)
        ax2 = fig2.add_subplot(111, facecolor=dark_bg)
        bars = ax2.barh(bar_labels, bar_values, color="#1f77b4")
        ax2.set_xlabel("Minutes Used", color='white')
        ax2.set_title("Top Used Apps (All Time)", color='white')
        ax2.tick_params(axis='x', colors='white')
        ax2.tick_params(axis='y', colors='white')
        fig2.patch.set_alpha(1.0)
        ax2.set_facecolor(dark_bg)
        if in_place and hasattr(self, 'bar_canvas') and self.bar_canvas:
            self.bar_canvas.get_tk_widget().destroy()
        self.bar_canvas = FigureCanvasTkAgg(fig2, master=self.stats_canvas)
        self.bar_canvas.draw()
        self.bar_canvas.get_tk_widget().pack(side="right", padx=10)

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
        self.root.after(2000, self.auto_refresh)  # Always reschedule

def main():
    init_db()
    root = ctk.CTk()
    app = AppUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 