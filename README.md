# ArucoWarp-ChromaKeying

**Automated perspective correction and background removal pipeline for flat object photography.**

Drop 4 ArUco markers on your shooting board, photograph your objects on a colored background — this tool handles the rest. Detects the markers, rectifies the perspective, removes the background, outputs clean transparent PNGs.

Built for the digitization of historical stage design maquettes at the **Opéra national de Paris**, but the pipeline is fully generic and works for any flat object on any colored background.

---

## Results

| Raw input | Perspective corrected | Final — transparent PNG |
|:---------:|:--------------------:|:-----------------------:|
| ![raw](assets/RAW.png) | ![rectified](assets/RectifiedArUco.jpg) | ![detoured](assets/RectifiedDet.png) |

*Wagner — La Walkyrie, 1893. Opéra national de Paris archives.*

---

## GUI

![gui](assets/Interface.png)

```powershell
uv run python WinMAQProcess.py
```

---

## What it does

### Step 1 — Perspective Unwrap

Detects 4 ArUco fiducial markers (DICT_4X4_50, IDs 0–3) placed at the corners of the shooting board and applies a perspective transform to produce a clean, rectified crop — regardless of camera angle or position.

The detector tries 6 preprocessing strategies in sequence (original, CLAHE, histogram equalization, blur+CLAHE, wide blur, adaptive threshold) and stops at the first one that returns exactly 4 markers with unique IDs. Any result with duplicate IDs is automatically rejected — preventing false positives from color checkers, rulers, or labels present in the frame from corrupting the transform.

### Step 2 — Chroma Key Détourage

Removes the colored background using HSV-based chroma keying. Three modes available:

| Mode | Description |
|------|-------------|
| `auto` | HSV chroma key only — fast, works for most cases |
| `combined` | Chroma key + AI (rembg) — better on complex shapes |
| `rembg` | AI only — for very intricate or unusual objects |

---

## Why these technical choices

### ArUco markers over manual cropping
ArUco markers (from OpenCV's `cv2.aruco` module) are specifically designed for reliable detection under real-world conditions: varying lighting, partial occlusion, motion blur. They encode an ID in a binary matrix pattern that is robust to perspective distortion — exactly what's needed when a camera is never perfectly orthogonal to the board. Detection is deterministic, fast (milliseconds per image), and requires no GPU or trained model.

Using 4 markers at known positions (the corners) turns any photograph into a calibrated document: the perspective transform is computed analytically from 4 point correspondences, with sub-pixel corner refinement (`CORNER_REFINE_SUBPIX`) for maximum geometric accuracy.

### Multi-preprocessing strategy with fallback
A single threshold setting fails when shooting conditions vary — darker frames, blown highlights, or shadows on the markers. Rather than asking the user to tune detection parameters per image, the script tries 6 preprocessing methods and takes the first clean result. This makes the pipeline resilient across an entire shoot without any manual intervention.

### HSV over RGB for chroma keying
RGB is not perceptually uniform — the same blue background looks very different in RGB values under different lighting conditions. HSV separates Hue (color identity) from Saturation (color purity) and Value (brightness), which maps much more cleanly to the human concept of "this is a blue background." By thresholding on Hue range + Saturation minimum, the mask captures the blue background reliably regardless of lighting variation across the frame, while ignoring blue-ish tones in the object itself (which tend to be desaturated).

### Edge feathering + color spill correction
A hard mask edge looks artificial. The pipeline applies Gaussian blur to the alpha mask edges (feathering) and reduces blue channel dominance near the object boundary (spill correction), producing natural-looking cutouts even on objects with semi-transparent or fibrous edges.

### rembg as optional fallback
For objects with very complex silhouettes that HSV keying struggles with, [rembg](https://github.com/danielgatis/rembg) (U2Net) provides an AI-based fallback. In `combined` mode, the minimum of both alpha channels is used — taking the most conservative mask from each method, which tends to give the cleanest result on difficult cases.

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
# By full path
uv run python WinPersUnwrap.py --base-path "C:\path\to\shoot"
uv run python WinDetourage.py  --base-path "C:\path\to\shoot"

# By shoot name (if base path is configured in the script)
uv run python WinPersUnwrap.py --shoot MY_SHOOT_NAME
uv run python WinDetourage.py  --shoot MY_SHOOT_NAME --mode combined --s-min 120
```

**HSV tuning tips:**
- Pale or grey object being eaten → lower `--s-min` (try 120)
- Residual background remaining → try `--mode combined`
- Very complex silhouette → try `--mode rembg`

---

## Shooting setup

- Colored background (default tuned for blue: H 95–115, S > 150 in HSV)
- 4 ArUco markers (DICT_4X4_50, IDs 0–3) at the corners of the board
- Static camera, consistent lighting
- Works with any background color — just retune the HSV range via sliders or CLI args

---

## Files

| File | Description |
|------|-------------|
| `WinMAQProcess.py` | GUI — chains both steps with live output |
| `WinPersUnwrap.py` | Perspective correction via ArUco detection |
| `WinDetourage.py` | HSV chroma key background removal |
| `pyproject.toml` | Python dependencies |

---

## Context

This pipeline was developed for the digitization of over 200 historical set design maquettes from the archives of the **Opéra national de Paris** — unique hand-painted scale models representing stage décors for 19th and early 20th century opera productions. Each piece is a fragile, irreplaceable artifact requiring careful, consistent, and reproducible photographic documentation.

The same approach generalizes to any repeated flat-object photography workflow: artwork digitization, museum cataloguing, document scanning, product photography.

---

## License

MIT — use it for whatever you want. A mention is always appreciated.