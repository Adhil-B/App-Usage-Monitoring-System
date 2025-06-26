import time
import threading
import win32gui
import win32process
import psutil
from datetime import datetime
from database import insert_usage_log, get_limit, log_website_usage

DISTRACTING_SITES = [
    'youtube.com', 'youtube', 'instagram.com', 'instagram', 'facebook.com', 'facebook', 'twitter.com', 'twitter',
    'reddit.com', 'reddit', 'tiktok.com', 'tiktok', 'netflix.com', 'netflix', 'discord.com', 'discord',
    'pinterest.com', 'pinterest', 'tumblr.com', 'tumblr', 'twitch.tv', 'twitch', 'roblox.com', 'roblox',
    'primevideo.com', 'prime video', 'linkedin.com', 'linkedin', 'quora.com', 'quora', '9gag.com', '9gag',
    'bilibili.com', 'bilibili', 'vk.com', 'vk', 'weibo.com', 'weibo', 'imgur.com', 'imgur', 'kick.com', 'kick',
    'onlyfans.com', 'onlyfans',
]
BROWSER_PROCESSES = ['chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe', 'opera_gx.exe', 'vivaldi.exe']

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
        self.current_site = None
        self.site_start_time = None

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
            # Website tracking
            site_found = None
            if app_name and app_name.lower() in BROWSER_PROCESSES and window_title:
                for site in DISTRACTING_SITES:
                    if site.lower() in window_title.lower():
                        site_found = site
                        break
            if site_found:
                if self.current_site != site_found:
                    # Log previous site usage
                    if self.current_site and self.site_start_time:
                        end_time = now
                        duration = (end_time - self.site_start_time).total_seconds() / 60.0
                        log_website_usage(self.current_site, app_name, self.site_start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)
                    self.current_site = site_found
                    self.site_start_time = now
            else:
                # If leaving a tracked site, log it
                if self.current_site and self.site_start_time:
                    end_time = now
                    duration = (end_time - self.site_start_time).total_seconds() / 60.0
                    log_website_usage(self.current_site, app_name, self.site_start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)
                    self.current_site = None
                    self.site_start_time = None
            # ... existing app tracking code ...
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
        # On stop, log the last app and last site
        if self.current_app and self.start_time:
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds() / 60.0
            insert_usage_log(self.current_app, self.current_title, self.start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)
        if self.current_site and self.site_start_time:
            end_time = datetime.now()
            duration = (end_time - self.site_start_time).total_seconds() / 60.0
            log_website_usage(self.current_site, self.current_app, self.site_start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)

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