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


def chroma_key_hsv(img_bgr, h_min=BLUE_H_MIN, h_max=BLUE_H_MAX, s_min=BLUE_S_MIN,
                   feather=3, grow=2):
    """
    HSV chroma key cutout based on blue background saturation.
    Works on all object types regardless of their color.

    Returns: RGBA PIL image
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # Blue background mask
    blue_mask = cv2.inRange(hsv,
                            np.array([h_min, s_min, 0]),
                            np.array([h_max, 255, 255]))

    # Grow (dilate) the mask to eat blue fringing on edges
    if grow > 0:
        kernel = np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8)
        blue_mask = cv2.dilate(blue_mask, kernel, iterations=1)

    # Feathering for soft edges
    if feather > 0:
        blue_mask = cv2.GaussianBlur(blue_mask, (feather * 2 + 1, feather * 2 + 1), 0)

    # Alpha = inverse of blue mask
    alpha = 255 - blue_mask

    # Assemble RGBA
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    rgba = np.dstack([img_rgb, alpha])

    return Image.fromarray(rgba.astype(np.uint8))


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
    """Removes blue reflection/spill on object edges"""
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
                  h_min=BLUE_H_MIN, h_max=BLUE_H_MAX, s_min=BLUE_S_MIN):
    """
    Processes an image with optimized cutout.

    Modes:
        auto     : HSV chroma key (recommended for most cases)
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

    elif mode == 'combined':
        # Chroma key first
        print(f"   🔵 HSV Chroma key...")
        result = chroma_key_hsv(img_bgr, h_min, h_max, s_min)

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

    else:  # auto (default)
        print(f"   🔵 HSV Chroma key (H:{h_min}-{h_max}, S>{s_min})...")
        result = chroma_key_hsv(img_bgr, h_min, h_max, s_min)

    if debug:
        result.save(os.path.join(debug_dir, f"{name}_02_chroma.png"))

    # Fill interior holes
    print(f"   🕳️  Filling interior holes...")
    result = fill_interior_holes(result, min_area=5000)

    if debug:
        result.save(os.path.join(debug_dir, f"{name}_03_filled.png"))

    # Color spill correction
    print(f"   ✨ Color spill correction...")
    result = remove_color_spill(result, strength=0.4)

    # Save
    result.save(output_path)
    print(f"   ✅ {output_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description='HSV chroma key cutout')
    parser.add_argument('--mode', choices=['auto', 'rembg', 'combined'], default='auto',
                        help='auto=HSV chroma key, rembg=AI only, combined=both')
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
                                   h_min=args.h_min, h_max=args.h_max, s_min=args.s_min)
            if result:
                ok += 1
            else:
                fail += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")
            fail += 1

        print("-" * 50)

    print(f"\n🎯 DONE — ✅ {ok} OK  ❌ {fail} failed")
    print(f"\n💡 If some images fail:")
    print(f"   Light/grey object eaten  → python WinDetourage.py --s-min 120")
    print(f"   Residual blue inside     → python WinDetourage.py --mode combined")
    print(f"   Very complex shape       → python WinDetourage.py --mode rembg")


if __name__ == "__main__":
    main()
