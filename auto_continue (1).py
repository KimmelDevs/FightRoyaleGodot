"""
Auto-Continue for ChatGPT desktop (Windows)

Install:   pip install pyautogui pillow numpy keyboard
Run:       python auto_continue.py

Setup (once per run):
  1. Clear the ChatGPT input box and wait until ChatGPT is IDLE
     (the WAVEFORM icon must be showing on the blue button, not the up arrow).
  2. Hover mouse over the blue button      -> press F7
  3. Hover mouse over the text input box   -> press F8
  4. Press F9 to start / pause.   F10 = quit.
     Mouse to top-left corner = emergency stop.

It triggers only on the change: "generating (stop square)" -> "idle (waveform)".
"""
import time
import tkinter as tk

import keyboard
import numpy as np
import pyautogui

# ---------------- settings ----------------
MESSAGE = "continue"
MAX_SENDS = 25            # stops after this many sends
CHECK_EVERY_MS = 700      # how often to look at the button
CONFIRM_CHECKS = 2        # idle must be seen this many times in a row
COOLDOWN_SEC = 5          # minimum gap between sends
MATCH_THRESHOLD = 20      # lower = stricter icon match
CROP = 15                 # half-size of the captured square around the button
SEND_IMMEDIATELY = False  # True = if ChatGPT is idle when you press F9, send right away
# ------------------------------------------

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

state = {
    "button": None,       # (x, y)
    "input": None,        # (x, y)
    "template": None,     # numpy array of the idle icon
    "running": False,
    "armed": False,       # becomes True once we've seen "generating"
    "idle_hits": 0,
    "sent": 0,
    "last_send": 0.0,
    "quit": False,
    "diff": -1.0,
}


def grab(x, y):
    img = pyautogui.screenshot(region=(x - CROP, y - CROP, CROP * 2, CROP * 2))
    return np.asarray(img.convert("L"), dtype=np.int16)


def set_button():
    x, y = pyautogui.position()
    state["button"] = (x, y)
    # move the mouse away so the hover colour isn't baked into the template
    pyautogui.moveTo(max(x - 250, 5), max(y - 120, 5))
    time.sleep(0.5)
    state["template"] = grab(x, y)   # assumes ChatGPT is idle right now
    pyautogui.moveTo(x, y)
    state["armed"] = False


def set_input():
    state["input"] = tuple(pyautogui.position())


def toggle():
    if not (state["button"] and state["input"]):
        return
    state["running"] = not state["running"]
    state["idle_hits"] = 0
    state["armed"] = state["running"] and SEND_IMMEDIATELY


def quit_app():
    state["quit"] = True


# suppress=True stops the key from reaching ChatGPT (so nothing gets typed)
keyboard.add_hotkey("f7", set_button, suppress=True)
keyboard.add_hotkey("f8", set_input, suppress=True)
keyboard.add_hotkey("f9", toggle, suppress=True)
keyboard.add_hotkey("f10", quit_app, suppress=True)


def is_idle():
    x, y = state["button"]
    diff = float(np.abs(grab(x, y) - state["template"]).mean())
    state["diff"] = diff
    return diff < MATCH_THRESHOLD


def send_continue():
    old = pyautogui.position()
    ix, iy = state["input"]
    pyautogui.click(ix, iy)
    time.sleep(0.15)
    pyautogui.write(MESSAGE, interval=0.02)
    time.sleep(0.1)
    pyautogui.press("enter")
    pyautogui.moveTo(old.x, old.y)
    state["sent"] += 1
    state["last_send"] = time.time()
    state["armed"] = False
    state["idle_hits"] = 0


# ---------------- overlay ----------------
root = tk.Tk()
root.title("Auto-Continue")
root.attributes("-topmost", True)
root.overrideredirect(True)
root.geometry("+20+20")
root.configure(bg="#111")
label = tk.Label(root, text="", fg="white", bg="#111", font=("Segoe UI", 10),
                 justify="left", padx=10, pady=6)
label.pack()


# drag the overlay around
def _start(e): root._dx, root._dy = e.x, e.y
def _drag(e): root.geometry(f"+{root.winfo_x()+e.x-root._dx}+{root.winfo_y()+e.y-root._dy}")
label.bind("<Button-1>", _start)
label.bind("<B1-Motion>", _drag)


def status_text():
    if not state["button"]:
        return "F7: hover blue button (idle, waveform icon)\nF8: hover input box\nF9: start/pause   F10: quit"
    if not state["input"]:
        return "Button set ✔\nF8: hover input box"
    if not state["running"]:
        return (f"Paused  ({state['sent']}/{MAX_SENDS})\nF9 to start\n"
                f"match diff: {state['diff']:.1f} (idle if < {MATCH_THRESHOLD})")
    return (f"● Watching  ({state['sent']}/{MAX_SENDS})\n"
            + ("waiting for finish…" if state["armed"] else "waiting for generation…")
            + f"\nmatch diff: {state['diff']:.1f} (idle if < {MATCH_THRESHOLD})")


def tick():
    if state["quit"]:
        root.destroy()
        return

    if state["running"]:
        try:
            idle = is_idle()
            if not idle:
                state["armed"] = True
                state["idle_hits"] = 0
            elif state["armed"]:
                state["idle_hits"] += 1
                cooled = time.time() - state["last_send"] > COOLDOWN_SEC
                if state["idle_hits"] >= CONFIRM_CHECKS and cooled:
                    send_continue()
                    if state["sent"] >= MAX_SENDS:
                        state["running"] = False
        except pyautogui.FailSafeException:
            state["running"] = False

    if state["button"] and state["template"] is not None and not state["running"]:
        try:
            is_idle()
        except Exception:
            pass
    label.config(text=status_text())
    root.after(CHECK_EVERY_MS, tick)


tick()
root.mainloop()
