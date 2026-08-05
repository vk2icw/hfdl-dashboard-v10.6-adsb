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

try:
    import pystray
    from PIL import Image
except ImportError:
    pystray = None
    Image = None


APP_NAME = "HFDL Operations Dashboard"
APP_VERSION = "10.6.0-rc1"
FIREWALL_RULE_NAME = "HFDL Dashboard UDP"
CONFIG_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "HFDLDashboard"
CONFIG_FILE = CONFIG_DIR / "launcher-settings.json"
DEFAULT_DB = CONFIG_DIR / "data" / "hfdl.sqlite3"
LOG_FILE = CONFIG_DIR / "logs" / "server.log"
PID_FILE = CONFIG_DIR / "server.pid"


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def program_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


class DashboardLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} — v10.6 ADSB.lol Correlation")
        self.geometry("780x700")
        self.minsize(720, 620)
        self.process: subprocess.Popen | None = None
        self.log_handle = None
        self.tray_icon = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.values = {
            "udp_bind_ip": tk.StringVar(value="0.0.0.0"),
            "udp_port": tk.StringVar(value="5557"),
            "web_bind_ip": tk.StringVar(value="127.0.0.1"),
            "web_port": tk.StringVar(value="8090"),
            "database_path": tk.StringVar(value=str(DEFAULT_DB)),
            "username": tk.StringVar(value=""),
            "password": tk.StringVar(value=""),
            "open_browser": tk.BooleanVar(value=True),
            "minimize_to_tray": tk.BooleanVar(value=True),
            "manage_firewall": tk.BooleanVar(value=True),
            "firewall_port": tk.StringVar(value="5557"),
        }

        self.status_var = tk.StringVar(value="Stopped")
        self.url_var = tk.StringVar(value="")
        self.load_settings()
        self.set_window_icon()
        self.build_ui()
        self.cleanup_stale_server_on_startup()
        self.after(1000, self.poll_process)
        if '--autostart' in sys.argv:
            self.after(1200, self.start_server)

    def build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="HFDL Operations Dashboard", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="Windows Polish Candidate — tray operation, firewall management and release branding.",
        ).pack(anchor="w", pady=(2, 16))

        form = ttk.LabelFrame(root, text="Receiver and dashboard settings", padding=14)
        form.pack(fill="x")

        self.add_row(form, 0, "UDP listen address", "udp_bind_ip",
                     "0.0.0.0 listens on all network adapters; use a specific IP to restrict reception.")
        self.add_row(form, 1, "UDP port", "udp_port", "Port receiving decoded JSON from dumphfdl.")
        self.add_row(form, 2, "Web listen address", "web_bind_ip",
                     "127.0.0.1 is recommended unless another computer must open the dashboard.")
        self.add_row(form, 3, "Web port", "web_port", "Local dashboard HTTP port.")

        ttk.Label(form, text="Database file").grid(row=4, column=0, sticky="w", pady=7)
        db_entry = ttk.Entry(form, textvariable=self.values["database_path"], width=48)
        db_entry.grid(row=4, column=1, sticky="ew", padx=(12, 8), pady=7)
        ttk.Button(form, text="Browse…", command=self.choose_database).grid(row=4, column=2, sticky="ew", pady=7)

        self.add_row(form, 5, "Username", "username", "Leave both credential fields blank to disable authentication.")
        ttk.Label(form, text="Password").grid(row=6, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=self.values["password"], show="•").grid(
            row=6, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=7
        )

        form.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(root, text="Launcher behaviour", padding=10)
        options.pack(fill="x", pady=(14, 4))

        ttk.Checkbutton(
            options,
            text="Open the dashboard in my default browser after starting",
            variable=self.values["open_browser"],
        ).pack(anchor="w")
        ttk.Checkbutton(
            options,
            text="Minimise to the Windows notification area while the server is running",
            variable=self.values["minimize_to_tray"],
        ).pack(anchor="w", pady=(5, 0))
        ttk.Checkbutton(
            options,
            text="Keep the Windows Firewall UDP rule aligned with the selected UDP port",
            variable=self.values["manage_firewall"],
        ).pack(anchor="w", pady=(5, 0))

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=8)
        self.start_button = ttk.Button(controls, text="Start dashboard", command=self.start_server)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Stop", command=self.stop_server, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Open dashboard", command=self.open_dashboard).pack(side="left")
        ttk.Button(controls, text="Open logs", command=self.open_logs).pack(side="left", padx=8)
        ttk.Button(controls, text="Firewall", command=self.configure_firewall).pack(side="left")
        ttk.Button(controls, text="About", command=self.show_about).pack(side="left", padx=8)
        ttk.Button(controls, text="Save settings", command=self.save_settings).pack(side="right")
        ttk.Button(controls, text="Stop and exit", command=self.stop_and_exit).pack(side="right", padx=8)

        status = ttk.LabelFrame(root, text="Status", padding=14)
        status.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(status, textvariable=self.status_var, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(status, textvariable=self.url_var).pack(anchor="w", pady=(4, 10))
        self.detail = tk.Text(status, height=8, wrap="word", state="disabled")
        self.detail.pack(fill="both", expand=True)
        self.set_detail(
            "The launcher starts and stops the local HFDL server without Docker. "
            "The UDP address and port must match the destination configured in dumphfdl."
        )

        ttk.Label(
            root,
            text="Developed by Louis LeMerle, VK2ICW · Experimental software · Not for navigation or flight safety",
            foreground="#666666",
        ).pack(anchor="center", pady=(12, 0))


    def set_window_icon(self) -> None:
        try:
            icon = resource_dir() / "hfdl-dashboard.ico"
            if icon.exists():
                self.iconbitmap(default=str(icon))
        except Exception:
            pass

    def tray_image(self):
        if Image is None:
            return None
        for candidate in (resource_dir() / "hfdl-dashboard.png", program_dir() / "hfdl-dashboard.png"):
            if candidate.exists():
                try:
                    return Image.open(candidate)
                except Exception:
                    pass
        return None

    def create_tray_icon(self) -> bool:
        if pystray is None:
            return False
        if self.tray_icon is not None:
            return True
        image = self.tray_image()
        if image is None:
            return False
        menu = pystray.Menu(
            pystray.MenuItem("Open launcher", lambda icon, item: self.after(0, self.restore_from_tray), default=True),
            pystray.MenuItem("Open dashboard", lambda icon, item: self.after(0, self.open_dashboard)),
            pystray.MenuItem("Stop dashboard", lambda icon, item: self.after(0, self.stop_server)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.after(0, self.stop_and_exit)),
        )
        self.tray_icon = pystray.Icon("HFDLDashboard", image, APP_NAME, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        return True

    def minimise_to_tray(self) -> None:
        if self.create_tray_icon():
            self.withdraw()
            self.status_var.set("Running in the Windows notification area")

    def restore_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def stop_tray_icon(self) -> None:
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

    def show_about(self) -> None:
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME}\nVersion {APP_VERSION}\n\n"
            "Developed by Louis LeMerle, VK2ICW\n"
            "Concept, design and project direction by Louis LeMerle, VK2ICW.\n\n"
            f"Application folder:\n{program_dir()}\n\n"
            f"User data folder:\n{CONFIG_DIR}\n\n"
            "Experimental software. Not for navigation or flight safety.",
        )

    def run_elevated_netsh(self, arguments: str) -> bool:
        if os.name != "nt":
            return False
        escaped = arguments.replace("'", "''")
        command = (
            "$p = Start-Process -FilePath netsh.exe "
            f"-ArgumentList '{escaped}' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=90,
            )
            return result.returncode == 0
        except Exception:
            return False

    def configure_firewall(self, quiet: bool = False) -> bool:
        try:
            udp_port = int(self.values["udp_port"].get().strip())
        except ValueError:
            if not quiet:
                messagebox.showerror(APP_NAME, "Enter a valid UDP port first.")
            return False

        server_path = program_dir() / "HFDLDashboardServer.exe"
        self.run_elevated_netsh(f'advfirewall firewall delete rule name="{FIREWALL_RULE_NAME}"')
        success = self.run_elevated_netsh(
            f'advfirewall firewall add rule name="{FIREWALL_RULE_NAME}" '
            f'dir=in action=allow protocol=UDP localport={udp_port} '
            f'profile=private program="{server_path}"'
        )
        if success:
            self.values["firewall_port"].set(str(udp_port))
            self.save_settings(quiet=True)
            if not quiet:
                messagebox.showinfo(APP_NAME, f"Firewall updated for inbound UDP {udp_port}.")
            return True
        if not quiet:
            messagebox.showerror(APP_NAME, "Firewall update failed or the administrator prompt was cancelled.")
        return False

    def ensure_firewall_matches(self) -> bool:
        if not self.values["manage_firewall"].get():
            return True
        try:
            current_port = int(self.values["udp_port"].get().strip())
            configured_port = int(self.values["firewall_port"].get().strip())
        except ValueError:
            return True
        if current_port == configured_port:
            return True
        if not messagebox.askyesno(
            APP_NAME,
            f"The UDP port changed from {configured_port} to {current_port}.\n\n"
            "Update the Windows Firewall rule now?",
        ):
            return True
        return self.configure_firewall(quiet=True)

    def add_row(self, parent, row: int, label: str, key: str, hint: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=7)
        ttk.Entry(parent, textvariable=self.values[key]).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=7
        )
        # Hints are shown through the status area after validation errors; keep layout compact.


    def pid_is_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=5,
                )
                return str(pid) in result.stdout and "No tasks are running" not in result.stdout
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def read_pid_file(self) -> int | None:
        try:
            return int(PID_FILE.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError, OSError):
            return None

    def write_pid_file(self, pid: int) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(pid), encoding="utf-8")

    def clear_pid_file(self) -> None:
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    def kill_process_tree(self, pid: int) -> None:
        if pid <= 0:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15,
                )
            else:
                os.kill(pid, 15)
        except Exception:
            pass

    def cleanup_stale_server_on_startup(self) -> None:
        old_pid = self.read_pid_file()
        if not old_pid:
            return
        if not self.pid_is_running(old_pid):
            self.clear_pid_file()
            return

        answer = messagebox.askyesno(
            APP_NAME,
            "A previous HFDL Dashboard server process is still running.\n\n"
            f"Process ID: {old_pid}\n\n"
            "Stop the old server now?",
        )
        if answer:
            self.kill_process_tree(old_pid)
            self.clear_pid_file()
            self.status_var.set("Stopped leftover server process")
        else:
            self.status_var.set(f"Existing server still running (PID {old_pid})")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")

    def tcp_port_available(self, host: str, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    def udp_port_available(self, host: str, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    def choose_database(self) -> None:
        current = Path(self.values["database_path"].get()).expanduser()
        filename = filedialog.asksaveasfilename(
            title="Choose HFDL database",
            initialdir=str(current.parent),
            initialfile=current.name,
            defaultextension=".sqlite3",
            filetypes=[("SQLite database", "*.sqlite3"), ("All files", "*.*")],
        )
        if filename:
            self.values["database_path"].set(filename)

    def load_settings(self) -> None:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        for key, variable in self.values.items():
            if key in data:
                variable.set(data[key])
        if not self.values['firewall_port'].get():
            self.values['firewall_port'].set(self.values['udp_port'].get() or '5557')

    def save_settings(self, quiet: bool = False) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {key: value.get() for key, value in self.values.items()}
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if not quiet:
            messagebox.showinfo(APP_NAME, "Settings saved.")

    def validate(self) -> tuple[str, int, str, int, Path] | None:
        udp_ip = self.values["udp_bind_ip"].get().strip()
        web_ip = self.values["web_bind_ip"].get().strip()
        try:
            socket.inet_aton(udp_ip)
            socket.inet_aton(web_ip)
        except OSError:
            messagebox.showerror(APP_NAME, "Enter valid IPv4 listener addresses.")
            return None

        try:
            udp_port = int(self.values["udp_port"].get())
            web_port = int(self.values["web_port"].get())
        except ValueError:
            messagebox.showerror(APP_NAME, "UDP and web ports must be whole numbers.")
            return None

        if not 1 <= udp_port <= 65535 or not 1 <= web_port <= 65535:
            messagebox.showerror(APP_NAME, "Ports must be between 1 and 65535.")
            return None
        if udp_port == web_port:
            messagebox.showerror(APP_NAME, "UDP and web ports must be different.")
            return None

        db_path = Path(self.values["database_path"].get()).expanduser()
        if not db_path.name:
            messagebox.showerror(APP_NAME, "Choose a database file.")
            return None

        username = self.values["username"].get().strip()
        password = self.values["password"].get()
        if bool(username) != bool(password):
            messagebox.showerror(APP_NAME, "Enter both username and password, or leave both blank.")
            return None

        existing_pid = self.read_pid_file()
        if existing_pid and self.pid_is_running(existing_pid):
            messagebox.showerror(
                APP_NAME,
                f"An HFDL Dashboard server is already running with process ID {existing_pid}.\n"
                "Stop it before starting another instance.",
            )
            return None

        if not self.udp_port_available(udp_ip, udp_port):
            messagebox.showerror(
                APP_NAME,
                f"UDP {udp_ip}:{udp_port} is already in use.\n"
                "Stop the other program or select another UDP port.",
            )
            return None

        if not self.tcp_port_available(web_ip, web_port):
            messagebox.showerror(
                APP_NAME,
                f"Web address {web_ip}:{web_port} is already in use.\n"
                "Stop the other program or select another web port.",
            )
            return None

        return udp_ip, udp_port, web_ip, web_port, db_path

    def server_command(self) -> list[str]:
        exe = program_dir() / "HFDLDashboardServer.exe"
        if exe.exists():
            return [str(exe)]
        script = program_dir() / "app.py"
        if script.exists():
            return [sys.executable, str(script)]
        bundled_script = resource_dir() / "app.py"
        if bundled_script.exists():
            return [sys.executable, str(bundled_script)]
        raise FileNotFoundError("HFDLDashboardServer.exe was not found beside the launcher.")

    def start_server(self) -> None:
        if self.process and self.process.poll() is None:
            return

        validated = self.validate()
        if not validated:
            return
        if not self.ensure_firewall_matches():
            return
        udp_ip, udp_port, web_ip, web_port, db_path = validated

        db_path.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.save_settings(quiet=True)

        env = os.environ.copy()
        env.update({
            "UDP_BIND_IP": udp_ip,
            "UDP_PORT": str(udp_port),
            "WEB_BIND_IP": web_ip,
            "WEB_PORT": str(web_port),
            "DATABASE_PATH": str(db_path),
            "DASHBOARD_USERNAME": self.values["username"].get().strip(),
            "DASHBOARD_PASSWORD": self.values["password"].get(),
            "LOG_LEVEL": "info",
        })

        try:
            command = self.server_command()
            self.log_handle = LOG_FILE.open("a", encoding="utf-8", buffering=1)
            self.log_handle.write(f"\n--- Starting {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            self.process = subprocess.Popen(
                command,
                cwd=str(program_dir()),
                env=env,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            self.write_pid_file(self.process.pid)
        except Exception as exc:
            if self.log_handle:
                self.log_handle.close()
                self.log_handle = None
            messagebox.showerror(APP_NAME, f"Could not start the dashboard:\n\n{exc}")
            return

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("Starting…")
        self.url_var.set(self.dashboard_url())
        self.set_detail(
            f"UDP listener: {udp_ip}:{udp_port}\n"
            f"Web listener: {web_ip}:{web_port}\n"
            f"Database: {db_path}\n"
            f"Log: {LOG_FILE}"
        )
        threading.Thread(target=self.wait_until_ready, daemon=True).start()

    def dashboard_url(self) -> str:
        host = self.values["web_bind_ip"].get().strip()
        if host == "0.0.0.0":
            host = "127.0.0.1"
        return f"http://{host}:{self.values['web_port'].get().strip()}/?v=10"

    def wait_until_ready(self) -> None:
        health_url = self.dashboard_url().split("/?")[0] + "/health"
        for _ in range(60):
            if not self.process or self.process.poll() is not None:
                self.after(0, lambda: self.status_var.set("Server stopped during startup"))
                return
            try:
                with urllib.request.urlopen(health_url, timeout=1.0) as response:
                    if response.status == 200:
                        self.after(0, self.ready)
                        return
            except Exception:
                pass
            time.sleep(0.5)
        self.after(0, lambda: self.status_var.set("Started, but health check timed out"))

    def ready(self) -> None:
        self.status_var.set("Running")
        if self.values["open_browser"].get():
            self.open_dashboard()

    def open_dashboard(self) -> None:
        base = self.dashboard_url()
        separator = "&" if "?" in base else "?"
        cache_buster = int(time.time())
        webbrowser.open_new_tab(f"{base}{separator}cb={cache_buster}")

    def open_logs(self) -> None:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.touch(exist_ok=True)
        if os.name == "nt":
            os.startfile(LOG_FILE)  # type: ignore[attr-defined]
        else:
            webbrowser.open(LOG_FILE.as_uri())

    def stop_server(self) -> None:
        pid = None
        if self.process and self.process.poll() is None:
            pid = self.process.pid
        else:
            stored = self.read_pid_file()
            if stored and self.pid_is_running(stored):
                pid = stored

        if pid:
            self.status_var.set("Stopping server and child processes…")
            self.kill_process_tree(pid)

        self.process = None
        self.clear_pid_file()

        if self.log_handle:
            try:
                self.log_handle.close()
            except Exception:
                pass
            self.log_handle = None

        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.stop_tray_icon()
        self.deiconify()
        self.status_var.set("Stopped")

    def poll_process(self) -> None:
        if self.process and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            self.clear_pid_file()
            if self.log_handle:
                self.log_handle.close()
                self.log_handle = None
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.status_var.set(f"Stopped unexpectedly (exit code {code})")
        self.after(1000, self.poll_process)

    def set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")


    def stop_and_exit(self) -> None:
        self.stop_server()
        self.stop_tray_icon()
        self.destroy()

    def on_close(self) -> None:
        running = bool(self.process and self.process.poll() is None)
        stored = self.read_pid_file()
        if stored and self.pid_is_running(stored):
            running = True

        if running and self.values["minimize_to_tray"].get():
            self.minimise_to_tray()
            return

        if running:
            if not messagebox.askyesno(
                APP_NAME,
                "The dashboard is running. Stop the server and all child processes, then exit?",
            ):
                return
            self.stop_server()
        else:
            self.clear_pid_file()

        self.stop_tray_icon()
        self.destroy()


if __name__ == "__main__":
    app = DashboardLauncher()
    app.mainloop()
