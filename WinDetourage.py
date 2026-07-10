import os
os.environ["NUMBA_DISABLE_JIT"] = "1"

import cv2
import numpy as np
from PIL import Image
import argparse

SHOOT_NAME = "BMO_MAQ_255_Wagner_La_Walkyrie_1893"

# =============================
# HSV BLUE BACKGROUND CONFIG
# H: 95-115, S > 150
# Calibrated for this specific shoot
# =============================
BLUE_H_MIN = 95
BLUE_H_MAX = 115
BLUE_S_MIN = 150


def _smoothstep(x, lo, hi):
    """Elementwise 0→1 cubic ramp: 0 at/below lo, 1 at/above hi, smooth between.
    Gives anti-aliased transitions without a spatial blur."""
    if hi <= lo:
        return (x >= hi).astype(np.float32)
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


# Soft-key falloff tuning. Wider = softer/more forgiving edge; narrower = crisper.
HUE_MARGIN = 12.0   # degrees past the plate hue window where alpha reaches 1
SAT_BAND   = 40.0   # saturation ramp width below s_min


def chroma_key_hsv(img_bgr, h_min=BLUE_H_MIN, h_max=BLUE_H_MAX, s_min=BLUE_S_MIN,
                   feather=1, grow=0, despill=True, rim_px=3):
    """
    Saturation-preserving SOFT blue-screen key.

    The old version thresholded the blue plate with a hard `inRange`, then blurred
    that binary mask with a Gaussian and set alpha = 255 - blur. Three problems
    fell out of that: (1) the blur spread plate-blue inward from both sides of a
    thin strut and collapsed its alpha — thin pieces got eaten; (2) blurring a
    hard mask smears the edge instead of anti-aliasing it; (3) the semi-transparent
    blue-tinted halo washed fine pieces out ("desaturated").

    This version computes alpha as a CONTINUOUS function of each pixel's colour —
    how close its hue is to the plate AND how saturated it is — so:
      • thin struts keep full alpha (the decision is per-pixel colour, not a
        spatial blur across the object);
      • edges are anti-aliased by the soft ramp itself, not smeared;
      • despill only touches a thin RIM around the silhouette (hue-agnostic), so
        a blue fringe disappears WITHOUT desaturating genuine blue paint in the
        object interior.

    Returns: RGBA PIL image.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    Hc, Sc = hsv[:, :, 0], hsv[:, :, 1]

    # Circular hue distance from the centre of the plate hue window (OpenCV hue
    # is 0..179 and wraps around).
    h_center = (h_min + h_max) * 0.5
    h_half   = max(1.0, (h_max - h_min) * 0.5)
    dh = np.abs(Hc - h_center)
    dh = np.minimum(dh, 180.0 - dh)

    # "background-ness" in 0..1: in-hue AND saturated => plate. Soft ramps give
    # anti-aliased edges with no blur.
    hue_bg = 1.0 - _smoothstep(dh, h_half, h_half + HUE_MARGIN)
    sat_bg = _smoothstep(Sc, float(s_min) - SAT_BAND, float(s_min))
    bg = hue_bg * sat_bg                      # 1 = plate, 0 = object

    # Optional grow: bias toward removing a thin blue halo by max-filtering the
    # background score. OFF by default; unlike the old symmetric dilation of a
    # binary mask it can still nibble, so keep it small.
    if grow > 0:
        k = np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8)
        bg = cv2.dilate(bg, k, iterations=1)

    alpha = np.clip(1.0 - bg, 0.0, 1.0)

    # Optional light anti-alias, confined to the transition BAND so it never
    # touches solid interior or full background — no thin-eating, no wash.
    if feather > 0:
        band    = ((alpha > 0.02) & (alpha < 0.98)).astype(np.float32)
        blurred = cv2.GaussianBlur(alpha, (feather * 2 + 1, feather * 2 + 1), 0)
        alpha   = alpha * (1.0 - band) + blurred * band

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)

    # Despill: pull blue down to the fringe ONLY on a thin rim just inside the
    # silhouette. Hue-agnostic and spatially local, so blue PAINT away from the
    # edge keeps its full saturation (fixes the "desaturated" complaint while
    # still removing the blue edge halo).
    if despill and rim_px > 0:
        keep = (alpha > 0.5).astype(np.uint8)
        er   = cv2.erode(keep, np.ones((rim_px * 2 + 1, rim_px * 2 + 1), np.uint8))
        rim  = ((keep == 1) & (er == 0)).astype(np.float32)
        rim  = cv2.GaussianBlur(rim, (rim_px * 2 + 1, rim_px * 2 + 1), 0)
        b_lim = np.minimum(img_rgb[:, :, 2], np.maximum(img_rgb[:, :, 0], img_rgb[:, :, 1]))
        img_rgb[:, :, 2] = img_rgb[:, :, 2] * (1.0 - rim) + b_lim * rim

    rgba = np.dstack([img_rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(rgba)


# =====================================================================
# SMART MODE  — for maquettes that CONTAIN blue/teal paint
# ---------------------------------------------------------------------
# Pure colour keying can't tell plate-blue from painted-blue (shutters,
# teal washes, blue speckles) because they share the same HSV slice.
# This mode adds a SHAPE prior:
#   1. auto-calibrate the plate colour from the image corners
#   2. flood the background inward from the border through plate-coloured px
#   3. anything the flood never reaches = object (kept), incl. enclosed
#      blue paint (shutters, speckles) and dark foliage
# ---------------------------------------------------------------------
# No morphological "close" is used, so dark teal foliage is NOT bridged
# into the plate and can't be bleached out. Only blue that is actually
# connected to the outside background is removed.
# =====================================================================
def _bluish(hue_med):
    return 80 <= hue_med <= 135


def chroma_key_smart(img_bgr, h_min=BLUE_H_MIN, h_max=BLUE_H_MAX, s_min=BLUE_S_MIN,
                     grow=3, feather=3, plate_frac=0.002,
                     autocal=True, corner=0.05):
    """
    Border-flood cutout. Removes ONLY blue that is connected to the outside
    background; keeps every enclosed blue/teal area (painted shutters, skies,
    water, foliage shadow). Returns RGBA PIL image.

    autocal : sample the four corners (assumed background) and widen the
              H/S window to whatever the plate actually is on THIS image.
              Corners that don't look bluish are ignored, so a leg or tree
              touching a corner won't poison the calibration.
    grow    : dilate the plate mask by this many px to swallow blue fringing
              at the object edge (helps the "missed spots").
    """
    h, w = img_bgr.shape[:2]
    frame = h * w
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # 1) auto-calibrate plate colour from bluish corners ----------------
    if autocal:
        cs = max(4, int(min(h, w) * corner))
        patches = [hsv[:cs, :cs], hsv[:cs, -cs:], hsv[-cs:, :cs], hsv[-cs:, -cs:]]
        good = []
        for p in patches:
            f = p.reshape(-1, 3).astype(np.float32)
            hm, sm = np.median(f[:, 0]), np.median(f[:, 1])
            # only a saturated, blue-ish corner is trusted as plate
            if _bluish(hm) and sm > 90:
                good.append(f)
        if good:
            samp = np.concatenate(good, 0)
            H, S = samp[:, 0], samp[:, 1]
            # widen, but clamp so a noisy corner can't blow the window open
            h_min = int(np.clip(min(h_min, np.percentile(H, 2)), 80, h_min))
            h_max = int(np.clip(max(h_max, np.percentile(H, 98)), h_max, 135))
            s_min = int(max(80, min(s_min, np.percentile(S, 10) - 10)))

    # 2) plate-coloured mask -------------------------------------------
    blue = cv2.inRange(hsv,
                       np.array([h_min, s_min, 0]),
                       np.array([h_max, 255, 255]))
    if grow > 0:
        k = np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8)
        blue = cv2.dilate(blue, k, iterations=1)
    _, bm = cv2.threshold(blue, 127, 255, cv2.THRESH_BINARY)

    # 3) background = plate components that TOUCH the border ------------
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bm, 8)
    border = set(lab[0, :]).union(lab[-1, :]).union(lab[:, 0]).union(lab[:, -1])
    border.discard(0)
    bg = np.isin(lab, list(border)).astype(np.uint8) * 255

    # augment with any very-large plate pocket that got cut off from the
    # border by the object (keeps the arch opening transparent) ---------
    thr = plate_frac * frame
    for i in range(1, n):
        if i not in border and stats[i, cv2.CC_STAT_AREA] >= thr:
            bg[lab == i] = 255

    # guards: if the flood found nothing (border wasn't plate) fall back
    # to size; if it ate almost everything, bail to plain colour key ----
    cov = bg.mean() / 255.0
    if cov < 0.01:
        bg = np.zeros_like(bm)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= thr:
                bg[lab == i] = 255
    elif cov > 0.9:
        return chroma_key_hsv(img_bgr, h_min, h_max, s_min)

    alpha = 255 - bg
    if feather > 0:
        alpha = cv2.GaussianBlur(alpha, (feather * 2 + 1, feather * 2 + 1), 0)

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    rgba = np.dstack([img_rgb, alpha]).astype(np.uint8)
    return Image.fromarray(rgba)


def fill_interior_holes(img_pil, min_area=5000):
    """
    Fills interior holes in the alpha mask (internal blue cutout areas).
    Useful for pieces with internal cutouts.
    """
    img_array = np.array(img_pil)
    alpha = img_array[:, :, 3]

    # Binarize alpha
    _, binary = cv2.threshold(alpha, 127, 255, cv2.THRESH_BINARY)

    # Flood fill from edges to identify the outer background
    h, w = binary.shape
    flood = binary.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, mask, (0, 0), 255)
    cv2.floodFill(flood, mask, (w - 1, 0), 255)
    cv2.floodFill(flood, mask, (0, h - 1), 255)
    cv2.floodFill(flood, mask, (w - 1, h - 1), 255)

    # Interior holes = areas not touching the edges
    interior_holes = cv2.bitwise_not(flood)

    # Filter by size to avoid filling real cutouts
    contours, _ = cv2.findContours(interior_holes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hole_mask = np.zeros_like(interior_holes)
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area:
            cv2.drawContours(hole_mask, [cnt], -1, 255, -1)

    # Fill small holes in alpha
    alpha[hole_mask > 0] = 255
    img_array[:, :, 3] = alpha

    return Image.fromarray(img_array)


def remove_color_spill(img_pil, strength=0.4):
    """Removes blue reflection/spill on object edges.
    NOTE: this dulls genuinely blue PAINT too. Keep strength low (or 0) on
    blue-heavy artworks, or the shutters/skies lose their blue."""
    arr = np.array(img_pil).astype(float)
    # Reduce blue where it dominates
    blue_excess = np.maximum(0, arr[:, :, 2] - np.maximum(arr[:, :, 0], arr[:, :, 1]))
    arr[:, :, 2] -= blue_excess * strength
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def process_with_rembg(img_bgr):
    """Fallback rembg for complex cases"""
    try:
        from rembg import remove
        img_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
        result = remove(img_pil)
        return result
    except ImportError:
        print("   ⚠️  rembg not available")
        return None


def process_image(input_path, output_path, mode='auto', debug=False,
                  h_min=BLUE_H_MIN, h_max=BLUE_H_MAX, s_min=BLUE_S_MIN,
                  close_px=3, plate_frac=0.002, spill=0.0, grow=0,
                  despill=True, rim_px=3):
    """
    Processes an image with optimized cutout.

    Modes:
        auto     : HSV chroma key (recommended for most cases)
        smart    : silhouette + plate-carve (for maquettes containing
                   blue/teal PAINT — shutters, skies, water, etc.)
        rembg    : rembg only (for very complex/intricate shapes)
        combined : chroma key + rembg combined
    """
    filename = os.path.basename(input_path)
    print(f"📄 {filename} [{mode.upper()}]")

    img_bgr = cv2.imread(input_path)
    if img_bgr is None:
        print(f"   ❌ Cannot read image")
        return None

    debug_dir = None
    if debug:
        debug_dir = os.path.join(os.path.dirname(output_path), "..", "debug_det")
        os.makedirs(debug_dir, exist_ok=True)
        name = os.path.splitext(filename)[0]

    if mode == 'rembg':
        print(f"   🤖 rembg running...")
        result = process_with_rembg(img_bgr)
        if result is None:
            print(f"   ❌ rembg failed")
            return None

    elif mode == 'smart':
        print(f"   🧠 Smart border-flood "
              f"(H:{h_min}-{h_max}, S>{s_min}, grow={close_px}, autocal on)...")
        result = chroma_key_smart(img_bgr, h_min, h_max, s_min,
                                  grow=close_px, plate_frac=plate_frac)
        if debug:
            result.save(os.path.join(debug_dir, f"{name}_02_smart.png"))
        # smart already isolates the background cleanly; skip hole-fill,
        # and skip spill (it would dull the legit blue paint)
        result.save(output_path)
        print(f"   ✅ {output_path}")
        return result

    elif mode == 'combined':
        # Chroma key first
        print(f"   🔵 HSV Chroma key...")
        result = chroma_key_hsv(img_bgr, h_min, h_max, s_min, grow=grow,
                                despill=despill, rim_px=rim_px)

        if debug:
            result.save(os.path.join(debug_dir, f"{name}_01_chroma.png"))

        # Then rembg to refine
        print(f"   🤖 rembg for refinement...")
        rembg_result = process_with_rembg(img_bgr)
        if rembg_result is not None:
            # Combine: take the minimum of both alphas
            arr_chroma = np.array(result)
            arr_rembg = np.array(rembg_result)
            alpha_combined = np.minimum(arr_chroma[:, :, 3], arr_rembg[:, :, 3])
            arr_chroma[:, :, 3] = alpha_combined
            result = Image.fromarray(arr_chroma)

    else:  # auto (default) — plain, conservative chroma key
        print(f"   🔵 HSV Chroma key (H:{h_min}-{h_max}, S>{s_min}, grow={grow}, "
              f"despill={'on' if despill else 'off'})...")
        result = chroma_key_hsv(img_bgr, h_min, h_max, s_min, grow=grow,
                                despill=despill, rim_px=rim_px)

    if debug:
        result.save(os.path.join(debug_dir, f"{name}_02_chroma.png"))

    # Fill interior holes
    print(f"   🕳️  Filling interior holes...")
    result = fill_interior_holes(result, min_area=5000)

    if debug:
        result.save(os.path.join(debug_dir, f"{name}_03_filled.png"))

    # Color spill correction
    if spill > 0:
        print(f"   ✨ Color spill correction...")
        result = remove_color_spill(result, strength=spill)

    # Save
    result.save(output_path)
    print(f"   ✅ {output_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description='HSV chroma key cutout')
    parser.add_argument('--mode', choices=['auto', 'smart', 'rembg', 'combined'], default='auto',
                        help='auto=HSV chroma key, smart=silhouette+plate-carve (blue-heavy art), '
                             'rembg=AI only, combined=both')
    parser.add_argument('--debug', action='store_true',
                        help='Save intermediate steps')
    parser.add_argument('--shoot', default=SHOOT_NAME,
                        help='Shoot name to process')
    parser.add_argument('--base-path', default=None,
                        help='Full path to shoot folder (overrides --shoot + hardcoded root)')
    parser.add_argument('--h-min', type=int, default=BLUE_H_MIN,
                        help=f'Blue background hue minimum (default: {BLUE_H_MIN})')
    parser.add_argument('--h-max', type=int, default=BLUE_H_MAX,
                        help=f'Blue background hue maximum (default: {BLUE_H_MAX})')
    parser.add_argument('--s-min', type=int, default=BLUE_S_MIN,
                        help=f'Blue background saturation minimum (default: {BLUE_S_MIN})')
    parser.add_argument('--close', type=int, default=3,
                        help='[smart] edge grow in px to swallow blue fringing (default: 3)')
    parser.add_argument('--plate-frac', type=float, default=0.002,
                        help='[smart] min area fraction for a blue blob to count as plate (default: 0.002)')
    parser.add_argument('--spill', type=float, default=0.0,
                        help='blue spill removal strength (0 = off, keeps colours intact; default: 0)')
    parser.add_argument('--grow', type=int, default=0,
                        help='[auto] grow the cut by N px to trim a blue halo (0 = safest; default: 0)')
    parser.add_argument('--despill', action=argparse.BooleanOptionalAction, default=True,
                        help='[auto/combined] remove blue fringe on a thin edge rim only '
                             '(keeps interior paint saturated). Use --no-despill to disable.')
    parser.add_argument('--rim-px', type=int, default=3,
                        help='[auto/combined] width in px of the despill rim (default: 3)')

    args = parser.parse_args()

    # GUI passes --base-path directly; CLI falls back to --shoot + hardcoded root
    if args.base_path:
        base_path = args.base_path
    else:
        base_path = r"\\horus\JOBS\France\OperaParis_MaquettesDecors\2026-02\01-Data\Images_Originals\Maquettes\Models" + "\\" + args.shoot

    input_dir = os.path.join(base_path, "output")
    output_dir = os.path.join(base_path, "output_det")

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(input_dir):
        print(f"❌ Folder {input_dir} does not exist!")
        return

    image_paths = sorted([os.path.join(input_dir, f) for f in os.listdir(input_dir)
                          if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

    if not image_paths:
        print(f"❌ No images found in {input_dir}")
        return

    print(f"📁 Shoot: {args.shoot}")
    print(f"📸 {len(image_paths)} images found")
    print(f"⚙️  Mode: {args.mode.upper()}")
    print(f"🎨 HSV blue background: H[{args.h_min}-{args.h_max}] S>{args.s_min}")
    print("🚀 Starting cutout\n")

    ok, fail = 0, 0
    for input_path in image_paths:
        filename = os.path.basename(input_path)
        name = os.path.splitext(filename)[0]
        output_path = os.path.join(output_dir, f"{name}_det.png")

        try:
            result = process_image(input_path, output_path,
                                   mode=args.mode, debug=args.debug,
                                   h_min=args.h_min, h_max=args.h_max, s_min=args.s_min,
                                   close_px=args.close, plate_frac=args.plate_frac,
                                   spill=args.spill, grow=args.grow,
                                   despill=args.despill, rim_px=args.rim_px)
            if result:
                ok += 1
            else:
                fail += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")
            fail += 1

        print("-" * 50)

    print(f"\n🎯 DONE — ✅ {ok} OK  ❌ {fail} failed")
    print(f"\n💡 Tuning (auto is a soft colour key — it never blurs into the object):")
    print(f"   Too much plate left      : lower S MIN a little  (--s-min 130)")
    print(f"   Object edge eaten        : raise S MIN           (--s-min 170)")
    print(f"   Blue fringe on edges     : despill is on by default; it only")
    print(f"                              touches a thin rim, so paint is safe")
    print(f"   Colours look dulled      : leave --spill 0 (legacy global despill,")
    print(f"                              off by default; the rim despill handles it)")


if __name__ == "__main__":
    main()