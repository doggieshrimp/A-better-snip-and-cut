"""
Snip & Retake - select a screen area once, then re-capture that same area
whenever you want (the contents can change, the area stays the same).

Requires: pip install pillow
Run:      python snip_retake.py

In the window:
  New Snip  (Ctrl+N)   drag to select a new area (Esc cancels)
  Retake    (F5/Space) capture the same area again
  Copy      (Ctrl+C)   copy the current image to the clipboard
  Save As   (Ctrl+S)   save the current image somewhere else
  Open Folder          open the screenshots folder

Every snip and retake is saved automatically to the "screenshots" folder
next to this script.

Global hotkeys (work even when another app is focused):
  Ctrl+Alt+R  retake
  Ctrl+Alt+N  new snip
"""
import ctypes
import ctypes.wintypes as wt
import datetime
import io
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageEnhance, ImageGrab, ImageTk

# Use real pixels, so screen coordinates match what Pillow captures.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
PREVIEW_MAX = (1000, 700)
HIDE_DELAY_MS = 200  # time for our window to disappear before capturing


def virtual_screen():
    """Bounds (left, top, width, height) of all monitors combined."""
    gsm = user32.GetSystemMetrics
    return gsm(76), gsm(77), gsm(78), gsm(79)


def grab(bbox=None):
    return ImageGrab.grab(bbox=bbox, all_screens=True)


def copy_image_to_clipboard(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    data = buf.getvalue()[14:]  # strip BMP file header -> DIB

    kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [wt.HWND]
    user32.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p

    handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        raise OSError("Could not open the clipboard")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(8, handle):  # CF_DIB
            raise OSError("Could not set clipboard data")
    finally:
        user32.CloseClipboard()


def start_global_hotkeys(events):
    """Register system-wide hotkeys on a background thread; push names into `events`."""
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
    WM_HOTKEY = 0x0312
    keys = {1: ("retake", ord("R")), 2: ("snip", ord("N"))}

    def run():
        for hk_id, (name, vk) in keys.items():
            if not user32.RegisterHotKey(None, hk_id, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, vk):
                events.put(("warn", f"Ctrl+Alt+{chr(vk)} is already used by another app"))
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in keys:
                events.put((keys[msg.wParam][0], None))

    threading.Thread(target=run, daemon=True).start()


class SnipOverlay:
    """Fullscreen frozen screenshot; drag a rectangle to pick an area."""

    def __init__(self, root, on_done):
        self.on_done = on_done
        self.vx, self.vy, vw, vh = virtual_screen()
        self.shot = shot = grab()
        dim = ImageEnhance.Brightness(shot).enhance(0.45)
        self.shot_tk = ImageTk.PhotoImage(shot)
        self.dim_tk = ImageTk.PhotoImage(dim)

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{vw}x{vh}+{self.vx}+{self.vy}")
        self.canvas = tk.Canvas(self.win, width=vw, height=vh, highlightthickness=0, cursor="cross")
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.dim_tk, anchor="nw")
        # Bright copy of the screenshot, revealed only inside the selection.
        self.bright = self.canvas.create_image(0, 0, image=self.shot_tk, anchor="nw", state="hidden")
        self.rect = self.canvas.create_rectangle(0, 0, 0, 0, outline="#3fa9ff", width=2, state="hidden")
        self.label = self.canvas.create_text(0, 0, fill="white", anchor="sw", font=("Segoe UI", 10, "bold"))
        self.start = None

        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.win.bind("<Escape>", lambda e: self.finish(None))
        self.win.focus_force()

    def press(self, e):
        self.start = (e.x, e.y)

    def drag(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        l, t, r, b = min(x0, e.x), min(y0, e.y), max(x0, e.x), max(y0, e.y)
        self.canvas.coords(self.rect, l, t, r, b)
        self.canvas.itemconfigure(self.rect, state="normal")
        # Show the undimmed screenshot only within the selection by cropping a fresh PhotoImage.
        self.canvas.delete(self.bright)
        if r > l and b > t:
            self._crop_tk = ImageTk.PhotoImage(self.shot.crop((l, t, r, b)))
            self.bright = self.canvas.create_image(l, t, image=self._crop_tk, anchor="nw")
            self.canvas.tag_raise(self.rect)
        self.canvas.coords(self.label, l, max(t - 4, 14))
        self.canvas.itemconfigure(self.label, text=f"{r - l} x {b - t}")
        self.canvas.tag_raise(self.label)

    def release(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        l, t, r, b = min(x0, e.x), min(y0, e.y), max(x0, e.x), max(y0, e.y)
        if r - l < 3 or b - t < 3:
            self.start = None
            return  # treat as a stray click
        self.finish((l + self.vx, t + self.vy, r + self.vx, b + self.vy))

    def finish(self, bbox):
        self.win.destroy()
        self.on_done(bbox)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Snip & Retake")
        self.bbox = None
        self.image = None
        self.count = 0

        bar = tk.Frame(self.root, padx=6, pady=6)
        bar.pack(fill="x")
        tk.Button(bar, text="New Snip", width=10, command=self.new_snip).pack(side="left", padx=2)
        self.retake_btn = tk.Button(bar, text="Retake", width=10, command=self.retake, state="disabled")
        self.retake_btn.pack(side="left", padx=2)
        self.copy_btn = tk.Button(bar, text="Copy", width=8, command=self.copy, state="disabled")
        self.copy_btn.pack(side="left", padx=2)
        self.save_btn = tk.Button(bar, text="Save As", width=8, command=self.save, state="disabled")
        self.save_btn.pack(side="left", padx=2)
        tk.Button(bar, text="Open Folder", width=10, command=self.open_folder).pack(side="left", padx=2)
        self.ontop = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Stay on top", variable=self.ontop,
                       command=lambda: self.root.attributes("-topmost", self.ontop.get())).pack(side="right")

        self.preview = tk.Label(self.root, bg="#222", fg="#aaa", width=60, height=15,
                                text="Click New Snip (Ctrl+N) and drag over an area")
        self.preview.pack(fill="both", expand=True, padx=6)
        self.status = tk.Label(self.root, anchor="w", padx=6,
                               text="Global: Ctrl+Alt+R retake, Ctrl+Alt+N new snip")
        self.status.pack(fill="x", pady=(2, 4))

        self.root.bind("<Control-n>", lambda e: self.new_snip())
        self.root.bind("<F5>", lambda e: self.retake())
        self.root.bind("<space>", lambda e: self.retake())
        self.root.bind("<Control-c>", lambda e: self.copy())
        self.root.bind("<Control-s>", lambda e: self.save())

        self.events = queue.Queue()
        start_global_hotkeys(self.events)
        self.root.after(100, self.poll_events)

    def poll_events(self):
        while not self.events.empty():
            name, info = self.events.get()
            if name == "retake":
                self.retake()
            elif name == "snip":
                self.new_snip()
            elif name == "warn":
                self.status.config(text=info)
        self.root.after(100, self.poll_events)

    def hide_then(self, fn):
        self.root.withdraw()
        self.root.after(HIDE_DELAY_MS, fn)

    def new_snip(self):
        self.hide_then(lambda: SnipOverlay(self.root, self.snip_done))

    def snip_done(self, bbox):
        if bbox:
            self.bbox = bbox
            self.capture()
        self.root.deiconify()
        self.root.lift()

    def retake(self):
        if not self.bbox:
            return
        self.hide_then(self._retake)

    def _retake(self):
        self.capture()
        self.root.deiconify()

    def capture(self):
        self.image = grab(self.bbox)
        self.count += 1
        self.show(self.image)
        for b in (self.retake_btn, self.copy_btn, self.save_btn):
            b.config(state="normal")
        now = datetime.datetime.now()
        os.makedirs(SAVE_DIR, exist_ok=True)
        filename = now.strftime("snip_%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}.png"
        self.image.save(os.path.join(SAVE_DIR, filename))
        l, t, r, b = self.bbox
        self.status.config(text=f"Capture #{self.count} saved as {filename}   area ({l},{t}) {r - l}x{b - t}"
                                f"   |   F5/Space or Ctrl+Alt+R to retake")

    def show(self, img):
        preview = img.copy()
        preview.thumbnail(PREVIEW_MAX)
        self.preview_tk = ImageTk.PhotoImage(preview)
        self.preview.config(image=self.preview_tk, text="", width=preview.width, height=preview.height)

    def copy(self):
        if not self.image:
            return
        try:
            copy_image_to_clipboard(self.image)
            self.status.config(text="Copied to clipboard")
        except OSError as err:
            messagebox.showerror("Copy failed", str(err))

    def save(self):
        if not self.image:
            return
        name = datetime.datetime.now().strftime("snip_%Y%m%d_%H%M%S.png")
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile=name, initialdir=SAVE_DIR,
                                            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if path:
            img = self.image.convert("RGB") if path.lower().endswith((".jpg", ".jpeg")) else self.image
            img.save(path)
            self.status.config(text=f"Saved {os.path.basename(path)}")

    def open_folder(self):
        os.makedirs(SAVE_DIR, exist_ok=True)
        os.startfile(SAVE_DIR)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
