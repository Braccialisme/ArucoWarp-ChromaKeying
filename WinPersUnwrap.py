import cv2
import numpy as np
import os

# =============================
# CONFIG - ONLY CHANGE THIS!
# =============================
SHOOT_NAME = "BMO_MAQ_255_Wagner_La_Walkyrie_1893"  # ← Just change this line between shoots!
use_perspective = True  # True for perspective, False for affine (less distortion but no perspective correction)


def find_input_dir(base_path):
    """
    Shoots now come in two flavours:
      base_path/input/JPG/*.jpg   ← new convention (students send local files)
      base_path/input/*.jpg       ← legacy convention

    Tries the new convention first, then falls back, then does a shallow
    recursive search as a last resort so odd folder names don't block a run.
    """
    candidates = [
        os.path.join(base_path, "input", "JPG"),
        os.path.join(base_path, "input", "jpg"),
        os.path.join(base_path, "input"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            files = [f for f in os.listdir(c) if f.lower().endswith(('.jpg', '.jpeg'))]
            if files:
                return c, files

    # Last resort: shallow recursive search under base_path/input
    input_root = os.path.join(base_path, "input")
    if os.path.isdir(input_root):
        for root, _dirs, filenames in os.walk(input_root):
            files = [f for f in filenames if f.lower().endswith(('.jpg', '.jpeg'))]
            if files:
                return root, files

    return None, []


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Perspective unwrap via ArUco markers')
    parser.add_argument('--shoot', default=SHOOT_NAME, help='Shoot folder name')
    parser.add_argument('--base-path', default=None,
                        help='Full path to shoot folder (overrides --shoot + hardcoded root)')
    args = parser.parse_args()

    # GUI passes --base-path directly; CLI falls back to --shoot + hardcoded root
    if args.base_path:
        base_path  = args.base_path
        shoot_name = os.path.basename(base_path.rstrip("\\/"))
    else:
        shoot_name = args.shoot
        base_path  = r"\\horus\JOBS\France\OperaParis_MaquettesDecors\2026-02\01-Data\Images_Originals\Maquettes\Models" + "\\" + shoot_name

    output_dir = os.path.join(base_path, "output")
    debug_dir  = os.path.join(base_path, "debug")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(debug_dir,  exist_ok=True)

    if not os.path.exists(base_path):
        print(f"Folder {base_path} does not exist!")
        return

    input_dir, filenames = find_input_dir(base_path)
    if input_dir is None:
        print(f"No JPG images found. Tried:")
        print(f"   {os.path.join(base_path, 'input', 'JPG')}")
        print(f"   {os.path.join(base_path, 'input')}")
        return

    image_paths = sorted(os.path.join(input_dir, f) for f in filenames)

    print(f"Shoot: {shoot_name}")
    print(f"Source: {input_dir}")
    print(f"{len(image_paths)} images found")

    process_all(image_paths, output_dir, debug_dir, use_perspective=use_perspective)


def process_all(image_paths, output_dir, debug_dir, use_perspective=True):
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()

    # Optimized parameters
    parameters.adaptiveThreshWinSizeMin = 3
    parameters.adaptiveThreshWinSizeMax = 71
    parameters.adaptiveThreshWinSizeStep = 8
    parameters.adaptiveThreshConstant = 3

    parameters.minMarkerPerimeterRate = 0.005
    parameters.maxMarkerPerimeterRate = 4.0

    parameters.polygonalApproxAccuracyRate = 0.03
    parameters.minCornerDistanceRate = 0.02

    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.cornerRefinementWinSize = 7
    parameters.cornerRefinementMaxIterations = 50

    parameters.errorCorrectionRate = 1.0
    parameters.maxErroneousBitsInBorderRate = 0.5
    parameters.perspectiveRemovePixelPerCell = 8
    parameters.perspectiveRemoveIgnoredMarginPerCell = 0.1
    parameters.minOtsuStdDev = 3.0

    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

    # =============================
    # PROCESS ALL IMAGES
    # =============================
    print("🚀 Starting processing\n")

    for path in image_paths:
        if not os.path.exists(path):
            continue

        name = os.path.splitext(os.path.basename(path))[0]
        print(f"\n📄 {path}")

        result = rectify_image(path, detector, use_perspective=use_perspective)
        if result is False:
            continue

        warped, debug = result

        os.makedirs(debug_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        dbg_path = os.path.join(debug_dir, f"{name}_debug.jpg")
        cv2.imwrite(dbg_path, debug)
        print(f"   → Debug: {dbg_path}")

        if warped is not None:
            out_path = os.path.join(output_dir, f"{name}_rectified.jpg")
            cv2.imwrite(out_path, warped)
            print(f"✅ Rectified: {out_path}")
        else:
            print(f"⚠️  Rectification failed")

    print("\n🎯 DONE")


# =============================
# HELPER FUNCTIONS
# =============================
def order_points(pts):
    """Order points as: top-left, top-right, bottom-right, bottom-left"""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]       # TL
    rect[2] = pts[np.argmax(s)]       # BR
    diff = pts[:, 1] - pts[:, 0]      # y - x
    rect[1] = pts[np.argmin(diff)]    # TR
    rect[3] = pts[np.argmax(diff)]    # BL
    return rect

def get_marker_center(corners):
    """Get center point of a marker"""
    return corners[0].mean(axis=0)

def enhance_image(gray):
    """Enhance image with CLAHE"""
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(gray)

# =============================
# CORE FUNCTION
# =============================
def rectify_image(image_path, detector, use_perspective=True):
    """Rectify image using ArUco markers at corners"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"❌ Image not found: {image_path}")
        return False

    print(f"   Resolution: {img.shape[1]}x{img.shape[0]}px")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    VALID_IDS = [0, 1, 2, 3]
    best_corners = None
    best_ids = None
    best_count = 0
    best_method = None
    perfect_corners = None
    perfect_ids = None
    perfect_method = None

    # Try different preprocessing methods
    methods = [
        ("Original", gray),
        ("CLAHE", enhance_image(gray)),
        ("Equalized", cv2.equalizeHist(gray)),
        ("Blur + CLAHE", enhance_image(cv2.GaussianBlur(gray, (3, 3), 0))),
        ("Wide blur", cv2.GaussianBlur(gray, (5, 5), 0)),
        ("CLAHE + Adaptive thresh", cv2.adaptiveThreshold(
            enhance_image(gray), 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 99, 7)),
    ]

    for method_name, processed in methods:
        corners, ids, rejected = detector.detectMarkers(processed)
        if ids is None or len(corners) == 0:
            continue

        # Keep only valid IDs 0-3
        valid_mask = np.isin(ids.flatten(), VALID_IDS)
        filtered_corners = [c for c, v in zip(corners, valid_mask) if v]
        filtered_ids = ids[valid_mask]

        if len(filtered_corners) == 0:
            continue

        # Reject any method that produces duplicate IDs — unreliable detection
        unique_ids, counts = np.unique(filtered_ids.flatten(), return_counts=True)
        if np.any(counts > 1):
            print(f"   ⚠️  {method_name}: duplicate IDs {filtered_ids.flatten()} — skipping")
            continue

        valid_count = len(filtered_corners)

        # Track best partial result
        if valid_count > best_count:
            best_count = valid_count
            best_corners = filtered_corners
            best_ids = filtered_ids
            best_method = method_name

        # Perfect: exactly 4 unique valid markers — stop immediately
        if valid_count == 4:
            perfect_corners = filtered_corners
            perfect_ids = filtered_ids
            perfect_method = method_name
            print(f"   ✅ {method_name}: 4 unique markers found!")
            break

    # Use perfect result if found, otherwise fall back to best partial
    if perfect_corners is not None:
        corners = perfect_corners
        ids = perfect_ids
        best_method = perfect_method
        best_count = 4
    else:
        corners = best_corners
        ids = best_ids

    if best_method and best_count > 0:
        print(f"   Best: {best_method} ({best_count} valid unique markers)")

    # Debug visualization
    debug = img.copy()
    if corners:
        cv2.aruco.drawDetectedMarkers(debug, corners, ids)
        for corner, marker_id in zip(corners, ids):
            center = corner[0].mean(axis=0).astype(int)
            cv2.putText(debug, f"ID:{marker_id[0]}",
                    (center[0] - 50, center[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)

    if ids is None or len(corners) < 4:
        print(f"❌ Only {len(corners) if corners else 0}/4 markers found")
        return None, debug

    ids = ids.flatten()
    print(f"📍 IDs: {ids}")

    # Get centers of all markers
    centers = np.array([get_marker_center(c) for c in corners])
    ordered_centers = order_points(centers)

    center_indices = []
    for ordered_center in ordered_centers:
        distances = np.linalg.norm(centers - ordered_center, axis=1)
        center_indices.append(np.argmin(distances))

    src_pts = []
    corner_names = ['Top-Left', 'Top-Right', 'Bottom-Right', 'Bottom-Left']
    marker_corners_to_use = [0, 1, 2, 3]

    for i, marker_idx in enumerate(center_indices):
        marker_corners = corners[marker_idx][0]
        ordered_marker_corners = order_points(marker_corners)
        src_pts.append(ordered_marker_corners[marker_corners_to_use[i]])
        print(f"   {corner_names[i]}: ID {ids[marker_idx]}")

    src_pts = np.array(src_pts, dtype=np.float32)

    width = int(max(
        np.linalg.norm(src_pts[0] - src_pts[1]),
        np.linalg.norm(src_pts[3] - src_pts[2])
    ))

    height = int(max(
        np.linalg.norm(src_pts[0] - src_pts[3]),
        np.linalg.norm(src_pts[1] - src_pts[2])
    ))

    print(f"📐 Dimensions: {width}x{height}px")

    dst_pts = np.array([
        [0, 0],
        [width, 0],
        [width, height],
        [0, height]
    ], dtype=np.float32)

    if use_perspective:
        H = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(img, H, (width, height), flags=cv2.INTER_LINEAR)
    else:
        H, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts)
        if H is None:
            return None, debug
        warped = cv2.warpAffine(img, H, (width, height), flags=cv2.INTER_LINEAR)

    # Draw corners on debug image
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    labels = ['TL', 'TR', 'BR', 'BL']
    for i, (p, color, label) in enumerate(zip(src_pts.astype(int), colors, labels)):
        cv2.circle(debug, tuple(p), 20, color, -1)
        cv2.putText(debug, label, (p[0] + 30, p[1]),
                cv2.FONT_HERSHEY_SIMPLEX, 2, color, 4)

    for i in range(4):
        pt1 = tuple(src_pts[i].astype(int))
        pt2 = tuple(src_pts[(i + 1) % 4].astype(int))
        cv2.line(debug, pt1, pt2, (0, 255, 255), 4)

    return warped, debug

if __name__ == "__main__":
    main()