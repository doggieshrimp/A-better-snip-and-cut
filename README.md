# Snip & Retake

Select an area of the screen once, then re-capture that same area whenever you
like. The area stays fixed while whatever is on screen there can change.

## Setup

Needs Python 3 and Pillow:

```
pip install pillow
```

## Run

```
python snip_retake.py
```

## Controls

| Button      | Key        | What it does                                   |
|-------------|------------|------------------------------------------------|
| New Snip    | Ctrl+N     | Drag to select a new area (Esc cancels)        |
| Retake      | F5 / Space | Capture the same area again                    |
| Copy        | Ctrl+C     | Copy the current image to the clipboard        |
| Save As     | Ctrl+S     | Save an extra copy wherever you want           |
| Open Folder |            | Open the `screenshots` folder                  |
| Stay on top |            | Keep the window above other windows            |

Global hotkeys (work while another app is focused):

- **Ctrl+Alt+R** - retake
- **Ctrl+Alt+N** - new snip

## Where screenshots go

Every snip and retake is saved automatically to the `screenshots` folder next
to the script, named by date and time (e.g. `snip_20261026_204124_630.png`).

## Notes

- Works across multiple monitors and with Windows display scaling.
- The tool window hides itself for a moment during a retake so it never ends
  up in the capture.
- Windows only (uses Windows APIs for the clipboard and global hotkeys).
