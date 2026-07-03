import tkinter as tk
from tkinter import filedialog, scrolledtext
import threading
import subprocess
import sys
import os

# =============================
# CONFIG
# =============================
# Generic starting point for the browse dialog. Kept high-level because
# shoots now live under different category folders (OperaParis_MaquettesDecors,
# BNF_MAQ_ArtEtSpectacles, ...) and different date folders (2026-02, 2026-06, ...).
# Adjust to whatever common root makes sense on your NAS.
BASE_PATH          = r"\\horus\JOBS\France"
SCRIPT_DIR         = os.path.dirname(os.path.abspath(__file__))
PERSUNWRAP_SCRIPT  = os.path.join(SCRIPT_DIR, "WinPersUnwrap.py")
DETOURAGE_SCRIPT   = os.path.join(SCRIPT_DIR, "WinDetourage.py")
ISLANDS_SCRIPT     = os.path.join(SCRIPT_DIR, "maq_split_islands.py")

# Sub-folders that make up a shoot's arborescence. "input/JPG" is the new
# convention for shoots where students drop their local files; "input" alone
# is kept for backward compatibility with older shoots.
SUBFOLDERS = [
    "input",
    os.path.join("input", "JPG"),
    "debug",
    "output",
    "output_det",
    "islands",
]

# =============================
# THEME
# =============================
BG       = "#0e0e10"      # near-black
CARD     = "#17171a"      # card background
CARD2    = "#1f1f24"      # input / inner
BORDER   = "#2a2a30"      # subtle border
ACCENT   = "#7b6fff"      # violet — modern
ACCENT_H = "#9d94ff"      # hover
SUCCESS  = "#5dbf8f"
ERROR    = "#e06060"
WARN     = "#d4a040"
TEXT     = "#eeeaf8"
DIM      = "#55525e"
TAG_BG   = "#25233a"      # pill background

F_TITLE  = ("Segoe UI", 13, "bold")
F_LABEL  = ("Segoe UI", 8, "bold")
F_BODY   = ("Segoe UI", 10)
F_SMALL  = ("Segoe UI", 9)
F_MONO   = ("Consolas", 9)
F_BTN    = ("Segoe UI", 10, "bold")


def pill(parent, text, fg=None, bg=None):
    """Small labeled badge like in the SHARP screenshot"""
    fg  = fg  or ACCENT
    bg  = bg  or TAG_BG
    lbl = tk.Label(parent, text=text, font=F_LABEL,
                   bg=bg, fg=fg, padx=8, pady=3)
    lbl.config(relief="flat")
    return lbl


def card(parent, **kw):
    f = tk.Frame(parent, bg=CARD,
                 highlightthickness=1, highlightbackground=BORDER,
                 **kw)
    return f


# =====================================================================
# PATH HELPERS
# These are the pieces that make the tool tolerant to being pointed at
# the shoot root, at "input", or at "input/JPG".
# =====================================================================
def derive_shoot_root(path):
    """
    Given ANY of:
        .../ShootName
        .../ShootName/input
        .../ShootName/input/JPG
    return .../ShootName  (the shoot root all scripts expect via --base-path)
    """
    path = os.path.normpath(path)
    parts = path.split(os.sep)
    lower_parts = [p.lower() for p in parts]
    if "input" in lower_parts:
        idx = lower_parts.index("input")
        root_parts = parts[:idx]
        if root_parts:
            return os.sep.join(root_parts)
    return path


def find_jpg_source(shoot_root):
    """
    Look for actual jpg/jpeg files in the two conventions we support,
    preferring input/JPG (new convention) over input (legacy).
    Returns (folder_path_or_None, count).
    """
    candidates = [
        os.path.join(shoot_root, "input", "JPG"),
        os.path.join(shoot_root, "input", "jpg"),
        os.path.join(shoot_root, "input"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            files = [f for f in os.listdir(c) if f.lower().endswith((".jpg", ".jpeg"))]
            if files:
                return c, len(files)
    return None, 0


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MAQ Process — Opéra Paris / BnF")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(760, 720)
        self.geometry("900x820")

        self._shoot_path = tk.StringVar()
        self._run_pers   = tk.BooleanVar(value=True)
        self._run_det    = tk.BooleanVar(value=True)
        self._run_isl    = tk.BooleanVar(value=False)
        self._mode       = tk.StringVar(value="auto")
        self._h_min      = tk.IntVar(value=95)
        self._h_max      = tk.IntVar(value=115)
        self._s_min      = tk.IntVar(value=150)
        self._running    = False

        self._build_ui()
        self._log("MAQ Process ready", "dim")
        self._log(f"Scripts  {SCRIPT_DIR}", "dim")
        self._log("Tip: browse to (or paste) the shoot folder, its 'input', "
                   "or its 'input/JPG' folder — I'll figure out the rest.", "dim")

    # ================================================================= UI ==
    def _build_ui(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Header
        hdr = tk.Frame(outer, bg=BG)
        hdr.pack(fill="x", pady=(0, 16))

        tk.Label(hdr, text="MAQ PROCESS", font=F_TITLE,
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text="  Maquettes Décors — recto/verso pipeline",
                 font=F_SMALL, bg=BG, fg=DIM).pack(side="left", pady=(3, 0))

        # ── Card: Shoot folder
        c1 = card(outer, pady=14, padx=16)
        c1.pack(fill="x", pady=(0, 10))

        pill(c1, "SHOOT FOLDER").pack(anchor="w", pady=(0, 4))
        tk.Label(c1, text="Paste/browse the shoot root, its 'input' folder, or its 'input/JPG' folder.",
                 font=F_SMALL, bg=CARD, fg=DIM).pack(anchor="w", pady=(0, 8))

        row = tk.Frame(c1, bg=CARD)
        row.pack(fill="x")

        self._path_entry = tk.Entry(
            row, textvariable=self._shoot_path,
            font=F_MONO, bg=CARD2, fg=TEXT,
            insertbackground=ACCENT, relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT
        )
        self._path_entry.pack(side="left", fill="x", expand=True, ipady=7, ipadx=10)
        self._path_entry.bind("<Return>", lambda e: self._on_manual_path())
        self._path_entry.bind("<FocusOut>", lambda e: self._on_manual_path())

        self._mkbtn(row, "Browse", self._browse, small=True).pack(
            side="left", padx=(8, 0))
        self._mkbtn(row, "Create structure", self._force_create, small=True).pack(
            side="left", padx=(8, 0))

        self._path_status = tk.Label(c1, text="", font=F_SMALL, bg=CARD, fg=DIM,
                                     anchor="w", justify="left")
        self._path_status.pack(fill="x", pady=(8, 0))

        # ── Card: Pipeline steps
        c2 = card(outer, pady=14, padx=16)
        c2.pack(fill="x", pady=(0, 10))

        pill(c2, "PIPELINE").pack(anchor="w", pady=(0, 12))

        steps = tk.Frame(c2, bg=CARD)
        steps.pack(fill="x")

        self._toggle(steps, "01  Perspective Unwrap", self._run_pers).pack(
            side="left", padx=(0, 24))
        self._toggle(steps, "02  Détourage  (chroma key)", self._run_det).pack(
            side="left", padx=(0, 24))
        self._toggle(steps, "03  Split Islands (recto/verso)", self._run_isl).pack(
            side="left")

        # ── Card: Detourage options
        c3 = card(outer, pady=14, padx=16)
        c3.pack(fill="x", pady=(0, 10))

        pill(c3, "DETOURAGE OPTIONS").pack(anchor="w", pady=(0, 12))

        mode_row = tk.Frame(c3, bg=CARD)
        mode_row.pack(fill="x", pady=(0, 14))

        tk.Label(mode_row, text="MODE", font=F_LABEL,
                 bg=CARD, fg=DIM, width=7, anchor="w").pack(side="left")

        for val, lbl in [("auto", "auto"), ("smart", "smart"),
                         ("combined", "combined"), ("rembg", "rembg")]:
            tk.Radiobutton(
                mode_row, text=lbl, variable=self._mode, value=val,
                font=F_BODY, bg=CARD, fg=TEXT,
                selectcolor=CARD2, activebackground=CARD,
                activeforeground=ACCENT, highlightthickness=0
            ).pack(side="left", padx=(0, 14))

        sliders = tk.Frame(c3, bg=CARD)
        sliders.pack(fill="x")
        self._slider(sliders, "H MIN", self._h_min, 0, 180, 0)
        self._slider(sliders, "H MAX", self._h_max, 0, 180, 1)
        self._slider(sliders, "S MIN", self._s_min, 0, 255, 2)

        # ── Run row
        run_row = tk.Frame(outer, bg=BG)
        run_row.pack(fill="x", pady=(4, 10))

        self._btn_run = self._mkbtn(run_row, "Run Pipeline", self._run, accent=True)
        self._btn_run.pack(side="left")

        # Redo ONLY the detourage step, overwriting output_det, with the
        # current mode/H/S/sliders. Ignores the pipeline checkboxes so you
        # can iterate on a failed key without re-running the unwrap.
        self._btn_redo = self._mkbtn(
            run_row, "↻ Redo Détourage (overwrite)", self._redo_detourage)
        self._btn_redo.pack(side="left", padx=(10, 0))

        self._mkbtn(run_row, "Clear", self._clear_log, small=True).pack(
            side="left", padx=(10, 0))

        self._status_lbl = tk.Label(run_row, text="", font=F_SMALL,
                                    bg=BG, fg=DIM)
        self._status_lbl.pack(side="left", padx=14)

        # ── Card: Output log
        c4 = card(outer, pady=14, padx=16)
        c4.pack(fill="both", expand=True)

        pill(c4, "OUTPUT").pack(anchor="w", pady=(0, 10))

        self._log_box = scrolledtext.ScrolledText(
            c4, font=F_MONO, bg=CARD2, fg=TEXT,
            insertbackground=ACCENT, relief="flat",
            highlightthickness=0,
            state="disabled", wrap="word", pady=6, padx=8
        )
        self._log_box.pack(fill="both", expand=True)

        self._log_box.tag_config("dim",     foreground=DIM)
        self._log_box.tag_config("accent",  foreground=WARN)
        self._log_box.tag_config("success", foreground=SUCCESS)
        self._log_box.tag_config("error",   foreground=ERROR)
        self._log_box.tag_config("normal",  foreground=TEXT)

    # ── Widget helpers
    def _mkbtn(self, parent, text, cmd, accent=False, small=False):
        return tk.Button(
            parent, text=text,
            font=F_BTN if accent else F_SMALL,
            bg=ACCENT if accent else CARD2,
            fg=BG if accent else TEXT,
            activebackground=ACCENT_H if accent else BORDER,
            activeforeground=BG if accent else TEXT,
            relief="flat", bd=0, cursor="hand2",
            padx=20 if accent else 14,
            pady=9 if accent else 6,
            command=cmd
        )

    def _toggle(self, parent, label, var):
        return tk.Checkbutton(
            parent, text=label, variable=var,
            font=F_BODY, bg=CARD, fg=TEXT,
            selectcolor=CARD2, activebackground=CARD,
            activeforeground=ACCENT, highlightthickness=0
        )

    def _slider(self, parent, label, var, lo, hi, col):
        f = tk.Frame(parent, bg=CARD)
        f.grid(row=0, column=col, padx=(0, 40), sticky="w")

        top = tk.Frame(f, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=label, font=F_LABEL, bg=CARD, fg=DIM,
                 width=6, anchor="w").pack(side="left")
        vl = tk.Label(top, text=str(var.get()), font=F_MONO,
                      bg=CARD, fg=ACCENT, width=4, anchor="e")
        vl.pack(side="right")

        tk.Scale(
            f, variable=var, from_=lo, to=hi,
            orient="horizontal", length=170,
            bg=CARD, fg=TEXT, troughcolor=CARD2,
            highlightthickness=0, bd=0,
            activebackground=ACCENT, sliderrelief="flat",
            showvalue=False,
            command=lambda v: vl.config(text=str(int(float(v))))
        ).pack()

    # ===================================================== Path handling ==
    def _ensure_folder_structure(self, shoot_root):
        """
        Creates the shoot root (if needed) plus its standard sub-folders.
        Refuses to create anything if the *parent* of the shoot root doesn't
        exist, to avoid silently building garbage paths from a typo.
        """
        parent = os.path.dirname(shoot_root.rstrip("\\/"))
        if parent and not os.path.isdir(parent):
            self._log(f"Parent folder does not exist, not creating anything: {parent}", "error")
            return False

        created = []
        try:
            if not os.path.isdir(shoot_root):
                os.makedirs(shoot_root, exist_ok=True)
                created.append(os.path.basename(shoot_root) + "  (shoot root)")
            for sf in SUBFOLDERS:
                full = os.path.join(shoot_root, sf)
                if not os.path.isdir(full):
                    os.makedirs(full, exist_ok=True)
                    created.append(sf)
        except Exception as e:
            self._log(f"Could not create folders: {e}", "error")
            return False

        if created:
            self._log("Created: " + ", ".join(created), "accent")

        jpg_dir, count = find_jpg_source(shoot_root)
        if jpg_dir:
            self._log(f"Found {count} JPG(s) in {jpg_dir}", "success")
        else:
            self._log("No JPGs yet in input/ or input/JPG/ — drop the student's files there.", "dim")
        return True

    def _refresh_status(self, shoot_root):
        jpg_dir, count = find_jpg_source(shoot_root)
        if jpg_dir:
            self._path_status.config(
                text=f"Shoot: {os.path.basename(shoot_root)}   |   source: {jpg_dir}   ({count} images)",
                fg=SUCCESS)
        else:
            self._path_status.config(
                text=f"Shoot: {os.path.basename(shoot_root)}   |   no JPGs found yet in input/ or input/JPG/",
                fg=WARN)

    def _on_manual_path(self):
        raw = self._shoot_path.get().strip()
        if not raw:
            return
        root = derive_shoot_root(raw)
        norm = os.path.normpath(root)
        if norm != os.path.normpath(raw):
            self._shoot_path.set(norm)
        self._refresh_status(norm)

    def _browse(self):
        path = filedialog.askdirectory(
            initialdir=BASE_PATH,
            title="Select shoot folder, its 'input' folder, or its 'input/JPG' folder")
        if not path:
            return
        shoot_root = derive_shoot_root(path)
        self._shoot_path.set(os.path.normpath(shoot_root))
        self._ensure_folder_structure(shoot_root)
        self._refresh_status(shoot_root)

    def _force_create(self):
        """Manual 'Create structure' button — same logic, explicit trigger."""
        raw = self._shoot_path.get().strip()
        if not raw:
            self._log("Type or browse a path first.", "error")
            return
        shoot_root = derive_shoot_root(raw)
        self._shoot_path.set(os.path.normpath(shoot_root))
        self._ensure_folder_structure(shoot_root)
        self._refresh_status(shoot_root)

    # ============================================================= Actions ==
    def _clear_log(self):
        self._log_box.config(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.config(state="disabled")

    def _resolve_shoot_path(self):
        """Shared validation for Run and Redo. Returns a normalized shoot path
        or None (and logs the reason)."""
        raw = self._shoot_path.get().strip()
        if not raw:
            self._log("No shoot folder selected.", "error"); return None
        shoot_path = derive_shoot_root(raw)
        self._shoot_path.set(os.path.normpath(shoot_path))
        if not os.path.exists(shoot_path):
            self._log(f"Path does not exist: {shoot_path}", "error"); return None
        return shoot_path

    def _set_busy(self, busy, redo_label="↻ Redo Détourage (overwrite)"):
        """Enable/disable the two action buttons together."""
        self._running = busy
        state = "disabled" if busy else "normal"
        self._btn_run.config(state=state,
                             text="Running..." if busy else "Run Pipeline")
        self._btn_redo.config(state=state, text="Redoing..." if busy else redo_label)

    def _run(self):
        if self._running:
            return
        shoot_path = self._resolve_shoot_path()
        if shoot_path is None:
            return
        if not self._run_pers.get() and not self._run_det.get() and not self._run_isl.get():
            self._log("Select at least one pipeline step.", "error"); return

        self._set_busy(True)
        self._set_status("")
        threading.Thread(target=self._pipeline, args=(shoot_path,),
                         daemon=True).start()

    # ---- Redo detourage only (overwrite) --------------------------------
    def _redo_detourage(self):
        if self._running:
            return
        shoot_path = self._resolve_shoot_path()
        if shoot_path is None:
            return

        # detourage reads from output/ (the unwrapped images). Warn if empty.
        out_dir = os.path.join(shoot_path, "output")
        if not os.path.isdir(out_dir) or not any(
                f.lower().endswith((".jpg", ".jpeg", ".png"))
                for f in os.listdir(out_dir)):
            self._log("Nothing to re-key: 'output/' is empty. "
                      "Run Perspective Unwrap first.", "error")
            return

        self._set_busy(True)
        self._set_status("")
        threading.Thread(target=self._detourage_only, args=(shoot_path,),
                         daemon=True).start()

    def _detourage_only(self, shoot_path):
        shoot_name = os.path.basename(shoot_path.rstrip("\\/"))
        sep = "─" * 52
        self._log(sep, "dim")
        self._log(f"Redo Détourage (overwrite)  {shoot_name}", "accent")
        self._log(f"Mode {self._mode.get()}   "
                  f"H[{self._h_min.get()}-{self._h_max.get()}]  S>{self._s_min.get()}", "dim")
        self._log("Re-keying every image in output/ → output_det/ "
                  "(existing _det.png files are overwritten)", "dim")
        self._log(sep, "dim")

        ok = self._run_script(DETOURAGE_SCRIPT, [
            "--base-path", shoot_path,
            "--mode",      self._mode.get(),
            "--h-min",     str(self._h_min.get()),
            "--h-max",     str(self._h_max.get()),
            "--s-min",     str(self._s_min.get()),
        ])

        if ok:
            self._log(f"\nDétourage redone  {shoot_name}", "success")
            self._set_status(f"Détourage overwritten — {shoot_name}")
        else:
            self._log("Détourage failed — check output.", "error")
            self._set_status("Détourage failed")

        self.after(0, lambda: self._set_busy(False))

    def _pipeline(self, shoot_path):
        shoot_name = os.path.basename(shoot_path.rstrip("\\/"))
        sep = "─" * 52
        self._log(sep, "dim")
        self._log(f"Shoot   {shoot_name}", "accent")
        self._log(f"Path    {shoot_path}", "dim")
        self._log(sep, "dim")

        ok = True
        n_steps = sum([self._run_pers.get(), self._run_det.get(), self._run_isl.get()])
        step_i = 0

        if self._run_pers.get():
            step_i += 1
            self._log(f"\n[ {step_i} / {n_steps} ]  Perspective Unwrap", "accent")
            ok = self._run_script(PERSUNWRAP_SCRIPT,
                                  ["--base-path", shoot_path])
            if not ok:
                self._log("PersUnwrap failed — pipeline stopped.", "error")

        if ok and self._run_det.get():
            step_i += 1
            self._log(f"\n[ {step_i} / {n_steps} ]  Detourage", "accent")
            ok = self._run_script(DETOURAGE_SCRIPT, [
                "--base-path", shoot_path,
                "--mode",      self._mode.get(),
                "--h-min",     str(self._h_min.get()),
                "--h-max",     str(self._h_max.get()),
                "--s-min",     str(self._s_min.get()),
            ])
            if not ok:
                self._log("Detourage failed.", "error")

        if ok and self._run_isl.get():
            step_i += 1
            self._log(f"\n[ {step_i} / {n_steps} ]  Split Islands", "accent")
            ok = self._run_script(ISLANDS_SCRIPT, ["--base-path", shoot_path])
            if not ok:
                self._log("Split Islands failed.", "error")

        if ok:
            self._log(f"\nPipeline complete  {shoot_name}", "success")
            self._set_status(f"Done — {shoot_name}")
        else:
            self._set_status("Failed — check output")

        self.after(0, lambda: self._set_busy(False))

    def _run_script(self, script, args):
        if not os.path.exists(script):
            self._log(f"Script not found: {script}", "error")
            return False

        env = os.environ.copy()
        env["PYTHONUTF8"]        = "1"
        env["PYTHONIOENCODING"]  = "utf-8"

        cmd = [sys.executable, script] + args
        short_cmd = "$ " + os.path.basename(script) + " " + " ".join(
            a if not a.startswith("\\\\") else "..." for a in args)
        self._log(short_cmd, "dim")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, cwd=SCRIPT_DIR
            )
            for raw in proc.stdout:
                line = raw.rstrip()
                if not line:
                    continue
                lo = line.lower()
                if any(x in lo for x in ["done", "complete", "rectified",
                                          "det.png", " ok ", "saved"]):
                    tag = "success"
                elif any(x in lo for x in ["error", "failed", "not found",
                                            "does not exist"]):
                    tag = "error"
                elif any(x in lo for x in ["warning", "duplicate",
                                            "skipping", "markers"]):
                    tag = "accent"
                elif line.startswith("$") or line.startswith("   "):
                    tag = "dim"
                else:
                    tag = "normal"
                self._log(line, tag)

            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            self._log(f"Exception: {e}", "error")
            return False

    # ================================================================= Log ==
    def _log(self, msg, tag="normal", dim=False):
        if dim:
            tag = "dim"
        def _w():
            self._log_box.config(state="normal")
            self._log_box.insert("end", msg + "\n", tag)
            self._log_box.see("end")
            self._log_box.config(state="disabled")
        self.after(0, _w)

    def _set_status(self, msg):
        self.after(0, lambda: self._status_lbl.config(text=msg))


if __name__ == "__main__":
    app = App()
    app.mainloop()