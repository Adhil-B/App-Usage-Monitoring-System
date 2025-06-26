from win10toast import ToastNotifier
import tkinter as tk
from tkinter import messagebox

def show_alert(app_name, duration, max_minutes):
    message = f"Time limit reached for {app_name}!\nUsed: {duration:.1f} min / Limit: {max_minutes} min."
    try:
        toaster = ToastNotifier()
        toaster.show_toast("App Usage Alert", message, duration=5, threaded=True)
    except Exception:
        # Fallback to Tkinter messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("App Usage Alert", message)
        root.destroy() 