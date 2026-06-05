import tkinter as tk
from tkinter import filedialog, scrolledtext
import threading
import subprocess
import sys
import os

# =============================
# CONFIG
# =============================
BASE_PATH         = r"\\horus\JOBS\France\OperaParis_MaquettesDecors\2026-02\01-Data\Images_Originals\Maquettes\Models"
SCRIPT_DIR        = os.path.dirname(os.path.abspath(__file__))
PERSUNWRAP_SCRIPT = os.path.join(SCRIPT_DIR, "WinPersUnwrap.py")
DETOURAGE_SCRIPT  = os.path.join(SCRIPT_DIR, "WinDetourage.py")

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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MAQ Process — Opéra Paris")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(760, 680)
        self.geometry("900x780")

        self._shoot_path = tk.StringVar()
        self._run_pers   = tk.BooleanVar(value=True)
        self._run_det    = tk.BooleanVar(value=True)
        self._mode       = tk.StringVar(value="auto")
        self._h_min      = tk.IntVar(value=95)
        self._h_max      = tk.IntVar(value=115)
        self._s_min      = tk.IntVar(value=150)
        self._running    = False

        self._build_ui()
        self._log("MAQ Process ready", "dim")
        self._log(f"Scripts  {SCRIPT_DIR}", "dim")

    # ================================================================= UI ==
    def _build_ui(self):
        # ── scrollable main area
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Header
        hdr = tk.Frame(outer, bg=BG)
        hdr.pack(fill="x", pady=(0, 16))

        tk.Label(hdr, text="MAQ PROCESS", font=F_TITLE,
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text="  Opéra Paris — Maquettes Décors",
                 font=F_SMALL, bg=BG, fg=DIM).pack(side="left", pady=(3, 0))

        # ── Card: Shoot folder
        c1 = card(outer, pady=14, padx=16)
        c1.pack(fill="x", pady=(0, 10))

        pill(c1, "INPUT FOLDER").pack(anchor="w", pady=(0, 10))

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

        self._mkbtn(row, "Browse", self._browse, small=True).pack(
            side="left", padx=(8, 0))

        # ── Card: Pipeline steps
        c2 = card(outer, pady=14, padx=16)
        c2.pack(fill="x", pady=(0, 10))

        pill(c2, "PIPELINE").pack(anchor="w", pady=(0, 12))

        steps = tk.Frame(c2, bg=CARD)
        steps.pack(fill="x")

        self._toggle(steps, "01  Perspective Unwrap", self._run_pers).pack(
            side="left", padx=(0, 24))
        self._toggle(steps, "02  Détourage  (chroma key)", self._run_det).pack(
            side="left")

        # ── Card: Detourage options
        c3 = card(outer, pady=14, padx=16)
        c3.pack(fill="x", pady=(0, 10))

        pill(c3, "DETOURAGE OPTIONS").pack(anchor="w", pady=(0, 12))

        # Mode row
        mode_row = tk.Frame(c3, bg=CARD)
        mode_row.pack(fill="x", pady=(0, 14))

        tk.Label(mode_row, text="MODE", font=F_LABEL,
                 bg=CARD, fg=DIM, width=7, anchor="w").pack(side="left")

        for val, lbl in [("auto", "auto"), ("combined", "combined"), ("rembg", "rembg")]:
            tk.Radiobutton(
                mode_row, text=lbl, variable=self._mode, value=val,
                font=F_BODY, bg=CARD, fg=TEXT,
                selectcolor=CARD2, activebackground=CARD,
                activeforeground=ACCENT, highlightthickness=0
            ).pack(side="left", padx=(0, 14))

        # Sliders row
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

    # ============================================================= Actions ==
    def _browse(self):
        path = filedialog.askdirectory(initialdir=BASE_PATH,
                                       title="Select shoot folder")
        if path:
            self._shoot_path.set(os.path.normpath(path))

    def _clear_log(self):
        self._log_box.config(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.config(state="disabled")

    def _run(self):
        if self._running:
            return
        shoot_path = self._shoot_path.get().strip()
        if not shoot_path:
            self._log("No shoot folder selected.", "error"); return
        if not os.path.exists(shoot_path):
            self._log(f"Path does not exist: {shoot_path}", "error"); return
        if not self._run_pers.get() and not self._run_det.get():
            self._log("Select at least one pipeline step.", "error"); return

        self._running = True
        self._btn_run.config(state="disabled", text="Running...")
        self._set_status("")
        threading.Thread(target=self._pipeline, args=(shoot_path,),
                         daemon=True).start()

    def _pipeline(self, shoot_path):
        shoot_name = os.path.basename(shoot_path.rstrip("\\/"))
        sep = "─" * 52
        self._log(sep, "dim")
        self._log(f"Shoot   {shoot_name}", "accent")
        self._log(f"Path    {shoot_path}", "dim")
        self._log(sep, "dim")

        ok = True

        if self._run_pers.get():
            self._log("\n[ 1 / 2 ]  Perspective Unwrap", "accent")
            ok = self._run_script(PERSUNWRAP_SCRIPT,
                                  ["--base-path", shoot_path])
            if not ok:
                self._log("PersUnwrap failed — pipeline stopped.", "error")

        if ok and self._run_det.get():
            self._log("\n[ 2 / 2 ]  Detourage", "accent")
            ok = self._run_script(DETOURAGE_SCRIPT, [
                "--base-path", shoot_path,
                "--mode",      self._mode.get(),
                "--h-min",     str(self._h_min.get()),
                "--h-max",     str(self._h_max.get()),
                "--s-min",     str(self._s_min.get()),
            ])
            if not ok:
                self._log("Detourage failed.", "error")

        if ok:
            self._log(f"\nPipeline complete  {shoot_name}", "success")
            self._set_status(f"Done — {shoot_name}")
        else:
            self._set_status("Failed — check output")

        self._running = False
        self.after(0, lambda: self._btn_run.config(
            state="normal", text="Run Pipeline"))

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
                                          "det.png", " ok "]):
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
