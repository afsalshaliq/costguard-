"""Tkinter desktop interface for CostGuard."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


ROOT_DIR = Path(__file__).resolve().parent.parent
COLORS = {
    "background": "#F2F5F1",
    "surface": "#FFFFFF",
    "ink": "#18251E",
    "muted": "#647269",
    "line": "#D7E0D8",
    "green": "#176B52",
    "green_dark": "#10543F",
    "red": "#A43D31",
    "gold": "#C59635",
}


class CostGuardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CostGuard | Plan Review")
        self.root.geometry("1060x760")
        self.root.minsize(820, 600)
        self.root.configure(background=COLORS["background"])
        self.busy = False
        self._configure_styles()
        self._build_ui()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["ink"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=COLORS["green_dark"], foreground="#FFFFFF", font=("Segoe UI Semibold", 20))
        style.configure("Subtitle.TLabel", background=COLORS["green_dark"], foreground="#DDEBE3", font=("Segoe UI", 10))
        style.configure("TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["ink"], padding=(8, 7))
        style.configure("TCombobox", fieldbackground=COLORS["surface"], padding=(6, 6))
        style.configure("TCheckbutton", background=COLORS["background"], foreground=COLORS["ink"])
        style.configure("Primary.TButton", background=COLORS["green"], foreground="#FFFFFF", padding=(16, 9), font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("disabled", "#9DB7AA"), ("active", COLORS["green_dark"])])
        style.configure("TButton", padding=(11, 8), font=("Segoe UI", 10))
        style.configure("Status.TLabel", font=("Segoe UI Semibold", 10))

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        banner = tk.Frame(self.root, background=COLORS["green_dark"], padx=26, pady=20)
        banner.grid(row=0, column=0, sticky="ew")
        tk.Label(banner, text="COSTGUARD", background=COLORS["green_dark"], foreground="#FFFFFF",
                 font=("Segoe UI Semibold", 20)).pack(anchor="w")
        tk.Label(banner, text="Terraform plan review", background=COLORS["green_dark"], foreground="#DDEBE3",
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        form = ttk.Frame(self.root, padding=(26, 18, 26, 14))
        form.grid(row=1, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Plan file").grid(row=0, column=0, sticky="w", padx=(0, 14), pady=7)
        self.plan_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.plan_var).grid(row=0, column=1, sticky="ew", pady=7)
        ttk.Button(form, text="Browse...", command=self._browse).grid(row=0, column=2, padx=(9, 0), pady=7)

        ttk.Label(form, text="Budget increase").grid(row=1, column=0, sticky="w", padx=(0, 14), pady=7)
        settings = ttk.Frame(form)
        settings.grid(row=1, column=1, columnspan=2, sticky="ew", pady=7)
        settings.columnconfigure(5, weight=1)
        self.threshold_var = tk.StringVar()
        ttk.Entry(settings, textvariable=self.threshold_var, width=13).grid(row=0, column=0, sticky="w")
        ttk.Label(settings, text="Currency").grid(row=0, column=1, padx=(18, 7))
        self.currency_var = tk.StringVar(value="USD")
        ttk.Combobox(settings, textvariable=self.currency_var, values=("USD", "EUR", "GBP", "INR"),
                     width=8, state="readonly").grid(row=0, column=2, sticky="w")
        ttk.Label(settings, text="Output").grid(row=0, column=3, padx=(18, 7))
        self.format_var = tk.StringVar(value="Text")
        ttk.Combobox(settings, textvariable=self.format_var, values=("Text", "Markdown", "JSON"),
                     width=11, state="readonly").grid(row=0, column=4, sticky="w")
        self.offline_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings, text="Offline", variable=self.offline_var).grid(row=0, column=5, sticky="w", padx=(18, 0))

        ttk.Label(form, text="Group by tag").grid(row=2, column=0, sticky="w", padx=(0, 14), pady=7)
        self.group_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.group_var, width=25).grid(row=2, column=1, sticky="w", pady=7)

        actions = ttk.Frame(self.root, padding=(26, 0, 26, 14))
        actions.grid(row=2, column=0, sticky="new")
        self.run_button = ttk.Button(actions, text="Run review", style="Primary.TButton", command=self._run_review)
        self.run_button.pack(side="left")
        self.clear_button = ttk.Button(actions, text="Clear cache", command=self._clear_cache)
        self.clear_button.pack(side="left", padx=(9, 0))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(actions, textvariable=self.status_var, style="Status.TLabel").pack(side="right")

        output_frame = ttk.Frame(self.root, padding=(26, 0, 26, 18))
        output_frame.grid(row=3, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)
        self.output = tk.Text(output_frame, wrap="none", undo=False, relief="flat", borderwidth=0,
                              background=COLORS["surface"], foreground=COLORS["ink"],
                              insertbackground=COLORS["green"], padx=16, pady=14,
                              font=("Cascadia Mono", 9))
        y_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        x_scroll = ttk.Scrollbar(output_frame, orient="horizontal", command=self.output.xview)
        self.output.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.output.tag_configure("passed", foreground=COLORS["green"])
        self.output.tag_configure("failed", foreground=COLORS["red"])
        self.output.tag_configure("warning", foreground=COLORS["gold"])
        self.output.insert("1.0", "Choose a Terraform plan JSON file to begin.")
        self.output.configure(state="disabled")

        footer = ttk.Frame(self.root, padding=(26, 0, 26, 12))
        footer.grid(row=4, column=0, sticky="ew")
        ttk.Label(footer, text=f"Cache: {os.environ.get('COSTGUARD_CACHE', './pricing_cache.db')}",
                  style="Muted.TLabel").pack(anchor="w")

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select Terraform plan JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if path:
            self.plan_var.set(path)

    def _set_output(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", text)
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "FAILED" in line or "CIRCUIT BREAKER" in line:
                self.output.tag_add("failed", f"{line_number}.0", f"{line_number}.end")
            elif "PASSED" in line:
                self.output.tag_add("passed", f"{line_number}.0", f"{line_number}.end")
            elif "[WARN]" in line:
                self.output.tag_add("warning", f"{line_number}.0", f"{line_number}.end")
        self.output.configure(state="disabled")

    def _start_command(self, arguments, success_message):
        if self.busy:
            return
        self.busy = True
        self.run_button.configure(state="disabled")
        self.clear_button.configure(state="disabled")
        self.status_var.set("Running...")

        def worker():
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "costguard", *arguments],
                    cwd=ROOT_DIR,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                output = result.stdout
                if result.stderr.strip():
                    output = f"{output.rstrip()}\n\nWarnings / errors:\n{result.stderr.strip()}\n"
                if not output.strip():
                    output = success_message
                self.root.after(0, self._finish, result.returncode, output, success_message)
            except OSError as exc:
                self.root.after(0, self._finish, 2, f"Could not start CostGuard: {exc}", success_message)

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, code, output, success_message):
        self.busy = False
        self.run_button.configure(state="normal")
        self.clear_button.configure(state="normal")
        self._set_output(output)
        if code == 0:
            self.status_var.set(success_message)
        elif code == 1:
            self.status_var.set("Budget exceeded · exit 1")
        else:
            self.status_var.set(f"Error · exit {code}")

    def _run_review(self):
        plan_path = self.plan_var.get().strip()
        if not plan_path:
            messagebox.showerror("Plan required", "Choose a Terraform plan JSON file.", parent=self.root)
            return
        if not Path(plan_path).is_file():
            messagebox.showerror("Plan not found", "The selected plan file does not exist.", parent=self.root)
            return
        arguments = ["--plan", str(Path(plan_path).resolve()), "--currency", self.currency_var.get()]
        threshold = self.threshold_var.get().strip()
        if threshold:
            try:
                if float(threshold) < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid budget", "Enter a non-negative numeric monthly budget.", parent=self.root)
                return
            arguments.extend(("--max-increase", threshold))
        group = self.group_var.get().strip()
        if group:
            arguments.extend(("--group-by-tag", group))
        output_format = self.format_var.get()
        if output_format == "JSON":
            arguments.append("--json")
        elif output_format == "Markdown":
            arguments.append("--markdown")
        if self.offline_var.get():
            arguments.append("--offline")
        self._start_command(arguments, "Review complete")

    def _clear_cache(self):
        self._start_command(["--clear-cache"], "Cache cleared")


def main():
    root = tk.Tk()
    CostGuardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()