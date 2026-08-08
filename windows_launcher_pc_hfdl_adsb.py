from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from adsb_sbs_adapter import SBSClient
from pc_hfdl_adapter import PCHFDLWatcher

APP_NAME = "HFDL Operations Dashboard"
APP_VERSION = "10.6.0-rc3"
FIREWALL_RULE_NAME = "HFDL Dashboard UDP"
CONFIG_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "HFDLDashboard"
CONFIG_FILE = CONFIG_DIR / "launcher-settings.json"
DEFAULT_DB = CONFIG_DIR / "data" / "hfdl.sqlite3"
LOG_FILE = CONFIG_DIR / "logs" / "server.log"
PID_FILE = CONFIG_DIR / "server.pid"


def program_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} — PC-HFDL + ADS-B SBS")
        self.geometry("900x900")
        self.minsize(820, 760)
        self.process = None
        self.log_handle = None

        self.pc_thread = None
        self.pc_stop = threading.Event()
        self.pc_watcher = None
        self.pc_count = 0

        self.adsb_thread = None
        self.adsb_client = None
        self.adsb_count = 0

        self.values = {
            "udp_bind_ip": tk.StringVar(value="0.0.0.0"),
            "udp_port": tk.StringVar(value="5557"),
            "web_bind_ip": tk.StringVar(value="127.0.0.1"),
            "web_port": tk.StringVar(value="8090"),
            "database_path": tk.StringVar(value=str(DEFAULT_DB)),
            "username": tk.StringVar(value=""),
            "password": tk.StringVar(value=""),
            "open_browser": tk.BooleanVar(value=True),
            "minimize_to_tray": tk.BooleanVar(value=False),
            "manage_firewall": tk.BooleanVar(value=True),
            "firewall_port": tk.StringVar(value="5557"),
            "pc_hfdl_enabled": tk.BooleanVar(value=False),
            "pc_hfdl_log_path": tk.StringVar(value=""),
            "pc_hfdl_pattern": tk.StringVar(value="*.txt"),
            "pc_hfdl_autostart": tk.BooleanVar(value=True),
            "adsb_sbs_enabled": tk.BooleanVar(value=False),
            "adsb_sbs_host": tk.StringVar(value="127.0.0.1"),
            "adsb_sbs_port": tk.StringVar(value="30003"),
            "adsb_sbs_autostart": tk.BooleanVar(value=True),
        }
        self.status = tk.StringVar(value="Stopped")
        self.url = tk.StringVar(value="")
        self.pc_status = tk.StringVar(value="Stopped")
        self.pc_count_text = tk.StringVar(value="0 messages")
        self.adsb_status = tk.StringVar(value="Stopped")
        self.adsb_count_text = tk.StringVar(value="0 messages")

        self.load_settings()
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(1000, self.poll_process)
        if "--autostart" in sys.argv:
            self.after(1200, self.start_server)

    def build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(root, text="Windows launcher with dumphfdl UDP, PC-HFDL logfile input and local ADS-B SBS input.").pack(anchor="w", pady=(2, 14))

        form = ttk.LabelFrame(root, text="Dashboard settings", padding=12)
        form.pack(fill="x")
        self.row(form, 0, "UDP listen address", "udp_bind_ip")
        self.row(form, 1, "UDP port", "udp_port")
        self.row(form, 2, "Web listen address", "web_bind_ip")
        self.row(form, 3, "Web port", "web_port")
        ttk.Label(form, text="Database file").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.values["database_path"]).grid(row=4, column=1, sticky="ew", padx=(10, 6), pady=6)
        ttk.Button(form, text="Browse…", command=self.choose_database).grid(row=4, column=2, pady=6)
        self.row(form, 5, "Username", "username")
        ttk.Label(form, text="Password").grid(row=6, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.values["password"], show="•").grid(row=6, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=6)
        form.columnconfigure(1, weight=1)

        pc = ttk.LabelFrame(root, text="PC-HFDL Log Input", padding=12)
        pc.pack(fill="x", pady=(12, 0))
        header = ttk.Frame(pc); header.pack(fill="x")
        ttk.Checkbutton(header, text="Enable PC-HFDL logfile input", variable=self.values["pc_hfdl_enabled"], command=self.refresh_pc_controls).pack(side="left")
        ttk.Label(header, textvariable=self.pc_status, font=("Segoe UI", 10, "bold")).pack(side="right")
        ttk.Label(header, textvariable=self.pc_count_text).pack(side="right", padx=(0, 12))

        pr = ttk.Frame(pc); pr.pack(fill="x", pady=(8, 4))
        ttk.Label(pr, text="Log folder", width=16).pack(side="left")
        self.pc_path = ttk.Entry(pr, textvariable=self.values["pc_hfdl_log_path"]); self.pc_path.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.pc_browse = ttk.Button(pr, text="Browse…", command=self.choose_pc_folder); self.pc_browse.pack(side="left")

        cr = ttk.Frame(pc); cr.pack(fill="x")
        ttk.Label(cr, text="File pattern", width=16).pack(side="left")
        self.pc_pattern = ttk.Entry(cr, textvariable=self.values["pc_hfdl_pattern"], width=12); self.pc_pattern.pack(side="left")
        self.pc_start = ttk.Button(cr, text="Start input", command=self.start_pc_hfdl); self.pc_start.pack(side="left", padx=(10, 5))
        self.pc_stop_btn = ttk.Button(cr, text="Stop input", command=self.stop_pc_hfdl, state="disabled"); self.pc_stop_btn.pack(side="left")
        ttk.Checkbutton(cr, text="Start with dashboard", variable=self.values["pc_hfdl_autostart"]).pack(side="right")
        ttk.Label(pc, text="PC-HFDL still receives audio through VAC. This input follows new decoded records written to its .txt logs.", foreground="#555").pack(anchor="w", pady=(8, 0))

        adsb = ttk.LabelFrame(root, text="ADS-B SBS Input", padding=12)
        adsb.pack(fill="x", pady=(12, 0))
        ah = ttk.Frame(adsb); ah.pack(fill="x")
        ttk.Checkbutton(ah, text="Enable local ADS-B SBS input", variable=self.values["adsb_sbs_enabled"], command=self.refresh_adsb_controls).pack(side="left")
        ttk.Label(ah, textvariable=self.adsb_status, font=("Segoe UI", 10, "bold")).pack(side="right")
        ttk.Label(ah, textvariable=self.adsb_count_text).pack(side="right", padx=(0, 12))

        ar = ttk.Frame(adsb); ar.pack(fill="x", pady=(8, 4))
        ttk.Label(ar, text="SBS host", width=16).pack(side="left")
        self.adsb_host = ttk.Entry(ar, textvariable=self.values["adsb_sbs_host"], width=22); self.adsb_host.pack(side="left")
        ttk.Label(ar, text="Port").pack(side="left", padx=(12, 4))
        self.adsb_port = ttk.Entry(ar, textvariable=self.values["adsb_sbs_port"], width=8); self.adsb_port.pack(side="left")
        self.adsb_start = ttk.Button(ar, text="Start input", command=self.start_adsb_sbs); self.adsb_start.pack(side="left", padx=(12, 5))
        self.adsb_stop_btn = ttk.Button(ar, text="Stop input", command=self.stop_adsb_sbs, state="disabled"); self.adsb_stop_btn.pack(side="left")
        ttk.Checkbutton(ar, text="Start with dashboard", variable=self.values["adsb_sbs_autostart"]).pack(side="right")
        ttk.Label(adsb, text="For the SDRuno ADS-B plugin, the verified local SBS feed is normally 127.0.0.1:30003.", foreground="#555").pack(anchor="w", pady=(8, 0))

        options = ttk.LabelFrame(root, text="Launcher behaviour", padding=10)
        options.pack(fill="x", pady=(12, 4))
        ttk.Checkbutton(options, text="Open dashboard in browser after starting", variable=self.values["open_browser"]).pack(anchor="w")
        ttk.Checkbutton(options, text="Keep Windows Firewall UDP rule aligned with selected UDP port", variable=self.values["manage_firewall"]).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(root); buttons.pack(fill="x", pady=8)
        self.start_btn = ttk.Button(buttons, text="Start dashboard", command=self.start_server); self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop_server, state="disabled"); self.stop_btn.pack(side="left", padx=6)
        ttk.Button(buttons, text="Open dashboard", command=self.open_dashboard).pack(side="left")
        ttk.Button(buttons, text="Open logs", command=self.open_logs).pack(side="left", padx=6)
        ttk.Button(buttons, text="Firewall", command=self.configure_firewall).pack(side="left")
        ttk.Button(buttons, text="Save settings", command=self.save_settings).pack(side="right")

        sf = ttk.LabelFrame(root, text="Status", padding=12); sf.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Label(sf, textvariable=self.status, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(sf, textvariable=self.url).pack(anchor="w", pady=(3, 8))
        self.detail = tk.Text(sf, height=7, state="disabled", wrap="word"); self.detail.pack(fill="both", expand=True)
        self.set_detail("Use dumphfdl UDP, PC-HFDL log input, ADS-B SBS input, or a combination of them.")
        ttk.Label(root, text="Developed by Louis LeMerle, VK2ICW · Experimental software · Not for navigation or flight safety", foreground="#666").pack(pady=(10, 0))
        self.refresh_pc_controls()
        self.refresh_adsb_controls()

    def row(self, parent, row: int, label: str, key: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.values[key]).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=6)

    def load_settings(self) -> None:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        for key, value in self.values.items():
            if key in data:
                value.set(data[key])

    def save_settings(self, quiet: bool = False) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps({k: v.get() for k, v in self.values.items()}, indent=2), encoding="utf-8")
        if not quiet:
            messagebox.showinfo(APP_NAME, "Settings saved.")

    def choose_database(self) -> None:
        current = Path(self.values["database_path"].get()).expanduser()
        filename = filedialog.asksaveasfilename(title="Choose HFDL database", initialdir=str(current.parent), initialfile=current.name, defaultextension=".sqlite3", filetypes=[("SQLite database", "*.sqlite3"), ("All files", "*.*")])
        if filename:
            self.values["database_path"].set(filename)

    def choose_pc_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose PC-HFDL logfile folder")
        if folder:
            self.values["pc_hfdl_log_path"].set(folder)
            self.save_settings(quiet=True)

    def udp_target(self) -> str:
        host = self.values["udp_bind_ip"].get().strip()
        return "127.0.0.1" if host in ("", "0.0.0.0") else host

    def pc_running(self) -> bool:
        return bool(self.pc_thread and self.pc_thread.is_alive())

    def refresh_pc_controls(self) -> None:
        state = "normal" if self.values["pc_hfdl_enabled"].get() else "disabled"
        for widget in (getattr(self, "pc_path", None), getattr(self, "pc_browse", None), getattr(self, "pc_pattern", None)):
            if widget:
                widget.configure(state=state)
        if hasattr(self, "pc_start") and not self.pc_running():
            self.pc_start.configure(state=state)

    def start_pc_hfdl(self, quiet: bool = False) -> bool:
        if self.pc_running():
            return True
        if not self.values["pc_hfdl_enabled"].get():
            return False
        path = Path(self.values["pc_hfdl_log_path"].get().strip()).expanduser()
        if not path.exists():
            if not quiet:
                messagebox.showerror(APP_NAME, f"PC-HFDL log path does not exist:\n\n{path}")
            return False
        try:
            port = int(self.values["udp_port"].get())
        except ValueError:
            return False
        udp_host = self.udp_target()
        pattern = self.values["pc_hfdl_pattern"].get().strip() or "*.txt"
        self.pc_stop.clear(); self.pc_count = 0; self.pc_count_text.set("0 messages"); self.pc_status.set("Starting…")
        self.save_settings(quiet=True)

        def worker() -> None:
            watcher = PCHFDLWatcher([path], udp_host, port, pattern, True)
            self.pc_watcher = watcher
            def on_send(_record):
                self.pc_count += 1
                n = self.pc_count
                self.after(0, lambda: self.pc_count_text.set(f"{n} message" if n == 1 else f"{n} messages"))
            watcher.on_send = on_send
            self.after(0, lambda: self.pc_status.set("Watching"))
            try:
                while not self.pc_stop.is_set():
                    for file in watcher.discover():
                        if self.pc_stop.is_set():
                            break
                        watcher.poll_file(file)
                    self.pc_stop.wait(0.5)
            except Exception as exc:
                text = str(exc)
                self.after(0, lambda: self.pc_status.set(f"Error: {text}"))
            finally:
                watcher.close(); self.pc_watcher = None
        self.pc_thread = threading.Thread(target=worker, daemon=True, name="pc-hfdl-log-input")
        self.pc_thread.start(); self.pc_start.configure(state="disabled"); self.pc_stop_btn.configure(state="normal")
        return True

    def stop_pc_hfdl(self) -> None:
        self.pc_stop.set()
        if self.pc_thread and self.pc_thread.is_alive():
            self.pc_thread.join(timeout=2)
        self.pc_thread = None; self.pc_watcher = None; self.pc_status.set("Stopped"); self.pc_stop_btn.configure(state="disabled")
        self.pc_start.configure(state="normal" if self.values["pc_hfdl_enabled"].get() else "disabled")

    def adsb_running(self) -> bool:
        return bool(self.adsb_thread and self.adsb_thread.is_alive())

    def refresh_adsb_controls(self) -> None:
        state = "normal" if self.values["adsb_sbs_enabled"].get() else "disabled"
        for widget in (getattr(self, "adsb_host", None), getattr(self, "adsb_port", None)):
            if widget:
                widget.configure(state=state)
        if hasattr(self, "adsb_start") and not self.adsb_running():
            self.adsb_start.configure(state=state)

    def start_adsb_sbs(self, quiet: bool = False) -> bool:
        if self.adsb_running():
            return True
        if not self.values["adsb_sbs_enabled"].get():
            return False
        host = self.values["adsb_sbs_host"].get().strip() or "127.0.0.1"
        try:
            sbs_port = int(self.values["adsb_sbs_port"].get())
            udp_port = int(self.values["udp_port"].get())
        except ValueError:
            if not quiet:
                messagebox.showerror(APP_NAME, "Enter a valid ADS-B SBS port and dashboard UDP port.")
            return False
        udp_host = self.udp_target()
        self.adsb_count = 0; self.adsb_count_text.set("0 messages"); self.adsb_status.set("Starting…")
        self.save_settings(quiet=True)

        client = SBSClient(host, sbs_port, udp_host, udp_port)
        self.adsb_client = client
        def on_record(_record):
            self.adsb_count += 1
            n = self.adsb_count
            self.after(0, lambda: self.adsb_count_text.set(f"{n} message" if n == 1 else f"{n} messages"))
        def on_status(text: str):
            self.after(0, lambda: self.adsb_status.set(text))
        client.on_record = on_record
        client.on_status = on_status

        def worker() -> None:
            try:
                client.run()
            finally:
                client.close()
                self.adsb_client = None
        self.adsb_thread = threading.Thread(target=worker, daemon=True, name="adsb-sbs-input")
        self.adsb_thread.start(); self.adsb_start.configure(state="disabled"); self.adsb_stop_btn.configure(state="normal")
        return True

    def stop_adsb_sbs(self) -> None:
        if self.adsb_client is not None:
            self.adsb_client.stop()
        if self.adsb_thread and self.adsb_thread.is_alive():
            self.adsb_thread.join(timeout=2)
        self.adsb_thread = None; self.adsb_client = None; self.adsb_status.set("Stopped"); self.adsb_stop_btn.configure(state="disabled")
        self.adsb_start.configure(state="normal" if self.values["adsb_sbs_enabled"].get() else "disabled")

    def validate(self):
        try:
            udp_ip = self.values["udp_bind_ip"].get().strip(); socket.inet_aton(udp_ip)
            web_ip = self.values["web_bind_ip"].get().strip(); socket.inet_aton(web_ip)
            udp_port = int(self.values["udp_port"].get()); web_port = int(self.values["web_port"].get())
        except Exception:
            messagebox.showerror(APP_NAME, "Enter valid listener addresses and ports."); return None
        db_path = Path(self.values["database_path"].get()).expanduser()
        user = self.values["username"].get().strip(); password = self.values["password"].get()
        if bool(user) != bool(password):
            messagebox.showerror(APP_NAME, "Enter both username and password, or leave both blank."); return None
        return udp_ip, udp_port, web_ip, web_port, db_path

    def server_command(self):
        exe = program_dir() / "HFDLDashboardServer.exe"
        if exe.exists():
            return [str(exe)]
        script = program_dir() / "app.py"
        if script.exists():
            return [sys.executable, str(script)]
        raise FileNotFoundError("HFDLDashboardServer.exe was not found beside the launcher.")

    def start_server(self) -> None:
        if self.process and self.process.poll() is None:
            return
        valid = self.validate()
        if not valid:
            return
        udp_ip, udp_port, web_ip, web_port, db_path = valid
        db_path.parent.mkdir(parents=True, exist_ok=True); LOG_FILE.parent.mkdir(parents=True, exist_ok=True); self.save_settings(quiet=True)
        env = os.environ.copy(); env.update({"UDP_BIND_IP": udp_ip, "UDP_PORT": str(udp_port), "WEB_BIND_IP": web_ip, "WEB_PORT": str(web_port), "DATABASE_PATH": str(db_path), "DASHBOARD_USERNAME": self.values["username"].get().strip(), "DASHBOARD_PASSWORD": self.values["password"].get(), "LOG_LEVEL": "info"})
        try:
            self.log_handle = LOG_FILE.open("a", encoding="utf-8", buffering=1)
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            self.process = subprocess.Popen(self.server_command(), cwd=str(program_dir()), env=env, stdout=self.log_handle, stderr=subprocess.STDOUT, creationflags=flags)
            PID_FILE.parent.mkdir(parents=True, exist_ok=True); PID_FILE.write_text(str(self.process.pid), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not start dashboard:\n\n{exc}"); return
        self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal"); self.status.set("Starting…"); self.url.set(self.dashboard_url())
        self.set_detail(
            f"UDP listener: {udp_ip}:{udp_port}\n"
            f"Web listener: {web_ip}:{web_port}\n"
            f"Database: {db_path}\n"
            f"PC-HFDL input: {'enabled' if self.values['pc_hfdl_enabled'].get() else 'disabled'}\n"
            f"ADS-B SBS input: {'enabled' if self.values['adsb_sbs_enabled'].get() else 'disabled'}"
        )
        if self.values["pc_hfdl_enabled"].get() and self.values["pc_hfdl_autostart"].get():
            self.after(900, lambda: self.start_pc_hfdl(quiet=True))
        if self.values["adsb_sbs_enabled"].get() and self.values["adsb_sbs_autostart"].get():
            self.after(1100, lambda: self.start_adsb_sbs(quiet=True))
        threading.Thread(target=self.wait_ready, daemon=True).start()

    def wait_ready(self) -> None:
        url = self.dashboard_url().split("/?")[0] + "/health"
        for _ in range(60):
            if not self.process or self.process.poll() is not None:
                return
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        self.after(0, self.ready); return
            except Exception:
                pass
            time.sleep(0.5)
        self.after(0, lambda: self.status.set("Started, but health check timed out"))

    def ready(self) -> None:
        self.status.set("Running")
        if self.values["open_browser"].get():
            self.open_dashboard()

    def dashboard_url(self) -> str:
        host = self.values["web_bind_ip"].get().strip(); host = "127.0.0.1" if host == "0.0.0.0" else host
        return f"http://{host}:{self.values['web_port'].get().strip()}/?v=10"

    def open_dashboard(self) -> None:
        webbrowser.open_new_tab(self.dashboard_url() + f"&cb={int(time.time())}")

    def open_logs(self) -> None:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True); LOG_FILE.touch(exist_ok=True)
        os.startfile(LOG_FILE) if os.name == "nt" else webbrowser.open(LOG_FILE.as_uri())

    def stop_server(self) -> None:
        self.stop_pc_hfdl()
        self.stop_adsb_sbs()
        if self.process and self.process.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    self.process.terminate()
            except Exception:
                pass
        self.process = None
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        if self.log_handle:
            try:
                self.log_handle.close()
            except Exception:
                pass
            self.log_handle = None
        self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled"); self.status.set("Stopped")

    def poll_process(self) -> None:
        if self.process and self.process.poll() is not None:
            code = self.process.returncode; self.process = None; self.stop_pc_hfdl(); self.stop_adsb_sbs(); self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled"); self.status.set(f"Stopped unexpectedly (exit code {code})")
        self.after(1000, self.poll_process)

    def configure_firewall(self) -> None:
        if os.name != "nt":
            return
        try:
            port = int(self.values["udp_port"].get())
        except ValueError:
            return
        server = program_dir() / "HFDLDashboardServer.exe"
        args = f'advfirewall firewall add rule name="{FIREWALL_RULE_NAME}" dir=in action=allow protocol=UDP localport={port} profile=private program="{server}"'
        escaped = args.replace("'", "''")
        cmd = "$p=Start-Process -FilePath netsh.exe -ArgumentList '" + escaped + "' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        try:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                self.values["firewall_port"].set(str(port)); self.save_settings(quiet=True); messagebox.showinfo(APP_NAME, f"Firewall updated for UDP {port}.")
        except Exception:
            messagebox.showerror(APP_NAME, "Firewall update failed.")

    def set_detail(self, text: str) -> None:
        self.detail.configure(state="normal"); self.detail.delete("1.0", "end"); self.detail.insert("1.0", text); self.detail.configure(state="disabled")

    def on_close(self) -> None:
        running = bool(self.process and self.process.poll() is None)
        if running and not messagebox.askyesno(APP_NAME, "Stop the dashboard and all live inputs, then exit?"):
            return
        self.stop_server(); self.destroy()


if __name__ == "__main__":
    Launcher().mainloop()
