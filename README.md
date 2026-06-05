# ArucoWarp-ChromaKeying

**Automated perspective correction and background removal pipeline for flat object photography.**

Drop 4 ArUco markers on your shooting board, photograph your objects on a colored background — this tool handles the rest. Detects the markers, rectifies the perspective, removes the background, outputs clean transparent PNGs.

Built for the digitization of historical stage design maquettes at the **Opéra national de Paris**, but the pipeline is fully generic and works for any flat object on any colored background.

---

## What it does

### 1 — Perspective Unwrap
Detects 4 ArUco fiducial markers (DICT_4X4_50, IDs 0–3) placed at the corners of the shooting board and applies a perspective transform to produce a clean, rectified crop — regardless of camera angle or position.

Tries multiple preprocessing strategies (CLAHE, histogram equalization, adaptive threshold) and automatically rejects false positives, keeping only clean 4-marker detections with unique IDs.

### 2 — Chroma Key Détourage
Removes the colored background using HSV-based chroma keying. Fast, reliable, tunable. Handles edge feathering, blue spill correction, and interior hole filling for objects with cutouts.

Three modes:
| Mode | When to use |
|------|-------------|
| `auto` | HSV chroma key only — fast, works for most cases |
| `combined` | Chroma key + AI (rembg) — better on complex shapes |
| `rembg` | AI only — for very intricate or unusual objects |

---

## GUI

A lightweight desktop interface chains both steps into a single pipeline with live log output and adjustable parameters.

```powershell
uv run python WinMAQProcess.py
```

- Browse to your shoot folder
- Toggle steps on/off independently
- Tune HSV background parameters with sliders
- Hit **Run Pipeline**

---

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended)

### Install uv (Windows)
```powershell
winget install astral-sh.uv
```

Dependencies are declared in `pyproject.toml` and installed automatically by uv on first run:
```
opencv-python, numpy, Pillow, numba
```
Optional for `combined` / `rembg` modes: `rembg`

---

## Folder structure

Each shoot folder should follow this structure:

```
MY_SHOOT_NAME/
├── input/          ← raw JPG photographs
├── output/         ← rectified images (created by PersUnwrap)
├── output_det/     ← transparent PNGs (created by Détourage)
└── debug/          ← ArUco detection debug images
```

---

## Command line

```powershell
# Full pipeline
uv run python WinPersUnwrap.py --base-path "C:\path\to\shoot"
uv run python WinDetourage.py  --base-path "C:\path\to\shoot"

# Or by shoot name (if base path is configured in the script)
uv run python WinPersUnwrap.py --shoot MY_SHOOT_NAME
uv run python WinDetourage.py  --shoot MY_SHOOT_NAME --mode combined --s-min 120
```

**HSV tuning tips:**
- Pale or grey object being eaten by the mask → lower `--s-min` (try 120)
- Residual background color remaining → try `--mode combined`
- Very complex or intricate shape → try `--mode rembg`

---

## Shooting setup

- Colored background (default tuned for blue: H 95–115, S > 150)
- 4 ArUco markers (DICT_4X4_50, IDs 0–3) at the corners of the board
- Static camera, consistent lighting
- Works with any background color — just retune the HSV range

---

## Files

| File | Description |
|------|-------------|
| `WinMAQProcess.py` | GUI — chains both steps with live output |
| `WinPersUnwrap.py` | Perspective correction via ArUco detection |
| `WinDetourage.py` | HSV chroma key background removal |
| `pyproject.toml` | Python dependencies |

---

## Use cases

This pipeline was originally built for digitizing over 200 historical set design maquettes from the archives of the **Opéra national de Paris** — unique hand-painted scale models representing stage décors for 19th and early 20th century opera productions.

But the same approach works for:
- Flat artwork and document digitization
- Product photography on colored backgrounds
- Museum object cataloguing
- Any repeated photography workflow where you control the shooting setup

---

## License

MIT — use it for whatever you want. A mention is always appreciated.