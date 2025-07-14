import os

BROWSER_MAP = {
    'chrome.exe': 'Google Chrome',
    'msedge.exe': 'Microsoft Edge',
    'firefox.exe': 'Mozilla Firefox',
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

def get_friendly_app_name(exe_path, fallback, window_title=None):
    fallback_l = fallback.lower()
    # Check hardcoded mappings first
    if fallback_l in BROWSER_MAP:
        return BROWSER_MAP[fallback_l]
    if fallback_l in COMMON_MAP:
        return COMMON_MAP[fallback_l]
    if fallback_l.endswith('.exe'):
        # Try mapping without .exe
        base = fallback_l.replace('.exe', '')
        if base in BROWSER_MAP:
            return BROWSER_MAP[base]
        if base in COMMON_MAP:
            return COMMON_MAP[base]
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
    # Fallback: prettify the process name
    if fallback_l.endswith('.exe'):
        return fallback_l.replace('.exe', '').capitalize()
    return fallback.capitalize() 