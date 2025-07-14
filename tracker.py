import time
import threading
import win32gui
import win32process
import psutil
from datetime import datetime
from database import insert_usage_log, get_limit, log_website_usage
from utils import get_friendly_app_name

DISTRACTING_SITES = [
    'youtube.com', 'youtube', 'instagram', 'facebook.com', 'facebook', 'twitter.com', 'twitter',
    'reddit.com', 'reddit', 'tiktok.com', 'tiktok', 'netflix.com', 'netflix', 'discord.com', 'discord',
    'pinterest.com', 'pinterest', 'tumblr.com', 'tumblr', 'twitch.tv', 'twitch', 'roblox.com', 'roblox',
    'primevideo.com', 'prime video', 'linkedin.com', 'linkedin', 'quora.com', 'quora', '9gag.com', '9gag',
    'bilibili.com', 'bilibili', 'vk.com', 'vk', 'weibo.com', 'weibo', 'imgur.com', 'imgur', 'kick.com', 'kick',
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
        self.alerts_shown = set()  # Track which apps have already shown alerts today
        self.last_flush_time = None

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

    def _check_app_limit(self, app_name, current_duration, exe_path=None, window_title=None):
        """Check if app has exceeded its limit and show alert if needed"""
        if not app_name:
            return
        # Use friendly name for limit check
        friendly_name = get_friendly_app_name(exe_path, app_name, window_title)
        max_minutes = get_limit(friendly_name)
        if max_minutes is not None and current_duration >= max_minutes:
            # Create a unique key for today's alert
            today = datetime.now().strftime('%Y-%m-%d')
            alert_key = f"{friendly_name}_{today}"
            if alert_key not in self.alerts_shown:
                if self.alert_callback:
                    self.alert_callback(friendly_name, current_duration, max_minutes)
                self.alerts_shown.add(alert_key)

    def _track_loop(self):
        self.last_flush_time = time.time()
        while self.running:
            app_name, window_title, exe_path = self._get_active_window_info()
            now = datetime.now()
            now_ts = time.time()
            
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
            
            # App tracking
            if app_name and exe_path:
                self.app_exe_map[app_name] = exe_path
            
            if app_name != self.current_app or window_title != self.current_title:
                # Log previous app usage
                if self.current_app and self.start_time:
                    end_time = now
                    duration = (end_time - self.start_time).total_seconds() / 60.0
                    insert_usage_log(self.current_app, self.current_title, self.start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)
                
                # Start tracking new app
                self.current_app = app_name
                self.current_title = window_title
                self.start_time = now
                self.last_flush_time = now_ts
            else:
                # Same app - check for limit continuously
                if self.current_app and self.start_time:
                    current_duration = (now - self.start_time).total_seconds() / 60.0
                    self._check_app_limit(self.current_app, current_duration, exe_path, window_title)
                    # Periodically flush usage to DB every 10 seconds
                    if now_ts - self.last_flush_time >= 10:
                        end_time = now
                        duration = (end_time - self.start_time).total_seconds() / 60.0
                        insert_usage_log(self.current_app, self.current_title, self.start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), duration)
                        # Reset start time to now for next interval
                        self.start_time = now
                        self.last_flush_time = now_ts
            
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
            # Reset alerts for new day
            self.alerts_shown.clear()
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