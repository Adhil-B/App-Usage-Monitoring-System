import time
import threading
import win32gui
import win32process
import psutil
from datetime import datetime
from database import insert_usage_log, get_limit

class Tracker:
    def __init__(self, alert_callback=None, poll_interval=1):
        self.running = False
        self.thread = None
        self.current_app = None
        self.current_title = None
        self.start_time = None
        self.alert_callback = alert_callback
        self.poll_interval = poll_interval
        self.app_exe_map = {}  # app_name -> exe_path

    def _get_active_window_info(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None, None, None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return None, None, None
            process = psutil.Process(pid)
            app_name = process.name()
            window_title = win32gui.GetWindowText(hwnd)
            exe_path = process.exe() if process else None
            return app_name, window_title, exe_path
        except Exception:
            return None, None, None

    def _track_loop(self):
        while self.running:
            app_name, window_title, exe_path = self._get_active_window_info()
            now = datetime.now()
            if app_name and exe_path:
                self.app_exe_map[app_name] = exe_path
            if app_name != self.current_app or window_title != self.current_title:
                if self.current_app and self.start_time:
                    end_time = now
                    duration = (end_time - self.start_time).total_seconds() / 60.0
                    insert_usage_log(self.current_app, self.current_title, self.start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)
                    # Check limit
                    max_minutes = get_limit(self.current_app)
                    if max_minutes is not None and duration >= max_minutes:
                        if self.alert_callback:
                            self.alert_callback(self.current_app, duration, max_minutes)
                self.current_app = app_name
                self.current_title = window_title
                self.start_time = now
            time.sleep(self.poll_interval)
        # On stop, log the last app
        if self.current_app and self.start_time:
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds() / 60.0
            insert_usage_log(self.current_app, self.current_title, self.start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._track_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
            self.thread = None

    def is_running(self):
        return self.running

    def get_app_exe_map(self):
        return self.app_exe_map 