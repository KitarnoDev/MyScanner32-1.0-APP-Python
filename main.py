import os
import sys
import json
import ctypes
import hashlib
import subprocess
import shutil
import winreg
import tkinter as tk
import threading
import queue
import psutil
import base64

from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont
from datetime import datetime


APP_NAME = "MyScanner32"
APP_VERSION = "3.0"

SYSTEM_ROOT = os.environ.get("SystemRoot", r"C:\Windows")
SYSTEM32 = os.path.join(SYSTEM_ROOT, "System32")
SYSWOW64 = os.path.join(SYSTEM_ROOT, "SysWOW64")

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

FONT_NAME = "Segoe UI"


def resource_path(filename):
    """Поиск ресурсов рядом с EXE или исходным файлом."""
    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, filename)


def set_window_icon(window):
    """Установка иконки приложения."""
    try:
        icon_path = resource_path("app.ico")

        if os.path.isfile(icon_path):
            window.iconbitmap(default=icon_path)
    except Exception:
        pass


def set_app_user_model_id():
    """Задаёт отдельный идентификатор приложения для панели задач Windows."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MyScanner32.Desktop.3"
        )
    except Exception:
        pass


def relaunch_as_admin():
    """Перезапускает приложение с запросом UAC, если оно не повышено."""
    if is_admin():
        return True

    try:
        if getattr(sys, "frozen", False):
            executable = sys.executable
            parameters = subprocess.list2cmdline(sys.argv[1:])
        else:
            executable = sys.executable
            script = os.path.abspath(__file__)
            parameters = subprocess.list2cmdline([script] + sys.argv[1:])

        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, parameters,
            os.path.dirname(os.path.abspath(sys.executable)), 1
        )
        return int(result) > 32
    except Exception:
        return False


THEMES = {
    "dark": {
        "background": "#101010",
        "surface": "#1B1B1B",
        "surface_alt": "#292929",
        "primary": "#F0F0F0",
        "primary_hover": "#FFFFFF",
        "primary_dark": "#D5D5D5",
        "text": "#F2F2F2",
        "muted": "#A0A0A0",
        "border": "#3B3B3B",
        "success": "#D0D0D0",
        "warning": "#BDBDBD",
        "danger": "#FFFFFF",
        "selected": "#414141",
        "white": "#101010"
    }
}


CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    APP_NAME
)


COLORS = dict(THEMES["dark"])


SYSTEM_PROCESSES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe", "svchost.exe",
    "fontdrvhost.exe", "dwm.exe", "spoolsv.exe", "explorer.exe", "lsm.exe",
    "audiodg.exe", "conhost.exe"
}

PROTECTED_SYSTEM_FILES = {
    "ntoskrnl.exe",
    "hal.dll",
    "winload.exe",
    "winlogon.exe",
    "csrss.exe",
    "services.exe",
    "lsass.exe",
    "smss.exe",
    "wininit.exe"
}


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def normalize_path(path):
    if not path:
        return ""

    try:
        return os.path.normcase(
            os.path.realpath(os.path.abspath(path))
        )
    except Exception:
        return str(path).lower()


def is_inside_directory(path, directory):
    try:
        path = normalize_path(path)
        directory = normalize_path(directory)

        return os.path.commonpath(
            [path, directory]
        ) == directory

    except Exception:
        return False


def is_legit_system(path):
    if not path:
        return False

    return (
        is_inside_directory(path, SYSTEM32)
        or is_inside_directory(path, SYSWOW64)
    )


def is_protected_system_file(path):
    if not path:
        return False

    filename = os.path.basename(path).lower()
    return filename in PROTECTED_SYSTEM_FILES


def calculate_sha256(path):
    sha256 = hashlib.sha256()

    with open(path, "rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b""
        ):
            sha256.update(block)

    return sha256.hexdigest()


def open_explorer(path=None):
    try:
        if path and os.path.exists(path):
            if os.path.isfile(path):
                subprocess.Popen(
                    ["explorer.exe", "/select,", path]
                )
            else:
                subprocess.Popen(
                    ["explorer.exe", path]
                )
        else:
            subprocess.Popen(["explorer.exe"])

    except Exception as error:
        messagebox.showerror(APP_NAME, str(error))


def open_registry_key(hive, key_path):
    hive_names = {
        winreg.HKEY_CURRENT_USER: "HKEY_CURRENT_USER",
        winreg.HKEY_LOCAL_MACHINE: "HKEY_LOCAL_MACHINE",
        winreg.HKEY_CLASSES_ROOT: "HKEY_CLASSES_ROOT",
        winreg.HKEY_USERS: "HKEY_USERS",
        winreg.HKEY_CURRENT_CONFIG: "HKEY_CURRENT_CONFIG"
    }

    hive_name = hive_names.get(hive)

    if not hive_name:
        raise ValueError("Неизвестный раздел реестра.")

    full_path = hive_name + "\\" + key_path

    settings = (
        r"Software\Microsoft\Windows\CurrentVersion"
        r"\Applets\Regedit"
    )

    try:
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            settings
        ) as key:
            winreg.SetValueEx(
                key,
                "LastKey",
                0,
                winreg.REG_SZ,
                "Компьютер\\" + full_path
            )
    except Exception:
        pass

    subprocess.Popen(["regedit.exe"])


def run_powershell(script, timeout=60):
    encoded = base64.b64encode(
        script.encode("utf-16le")
    ).decode("ascii")

    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW
    )


def analyze_process(data):
    name = (data.get("name") or "").lower()
    exe = data.get("exe") or ""
    filename = os.path.basename(exe).lower()

    if name in SYSTEM_PROCESSES:
        if not exe:
            return {
                "level": "warning",
                "label": "[!][SYS]",
                "reason": "Не удалось определить расположение"
            }

        if not is_legit_system(exe):
            return {
                "level": "danger",
                "label": "[!][SYS]",
                "reason": "Системное имя вне системной папки"
            }

        if filename != name and name not in (
            "system",
            "system idle process",
            "registry"
        ):
            return {
                "level": "warning",
                "label": "[!][SYS]",
                "reason": "Имя процесса не совпадает с именем файла"
            }

        return {
            "level": "system",
            "label": "[SYS]",
            "reason": "Расположение соответствует системной папке"
        }

    if exe:
        if (
            is_inside_directory(exe, SYSTEM_ROOT)
            and not is_legit_system(exe)
        ):
            return {
                "level": "warning",
                "label": "[!]",
                "reason": "Исполняемый файл находится в необычном месте"
            }

    return {
        "level": "normal",
        "label": "",
        "reason": "Особых признаков не обнаружено"
    }


def check_signature(path):
    if not path or not os.path.isfile(path):
        return "Файл недоступен"

    script = r"""
    param([string]$FilePath)

    try {
        $signature = Get-AuthenticodeSignature -LiteralPath $FilePath

        [PSCustomObject]@{
            Status = [string]$signature.Status
            Publisher = if ($signature.SignerCertificate) {
                $signature.SignerCertificate.Subject
            } else {
                ""
            }
        } | ConvertTo-Json -Compress
    }
    catch {
        Write-Output "{}"
    }
    """

    encoded_path = base64.b64encode(
        path.encode("utf-8")
    ).decode("ascii")

    script = script.replace(
        "param([string]$FilePath)",
        "$FilePath = [System.Text.Encoding]::UTF8.GetString("
        "[System.Convert]::FromBase64String('"
        + encoded_path +
        "'))"
    )

    try:
        result = run_powershell(script, timeout=20)

        data = json.loads(
            result.stdout.strip() or "{}"
        )

        status = data.get("Status", "Unknown")
        publisher = data.get("Publisher", "")

        if status == "Valid":
            return "Подпись действительна: " + publisher

        if status == "NotSigned":
            return "Файл не имеет цифровой подписи"

        if status == "HashMismatch":
            return "ОШИБКА: хеш файла не совпадает с подписью"

        return "Статус подписи: " + status

    except Exception as error:
        return "Не удалось проверить подпись: " + str(error)


class ProgressWindow:

    def __init__(self, parent, title):
        self.window = tk.Toplevel(parent)

        self.window.title(title)
        self.window.geometry("440x185")
        self.window.resizable(False, False)
        self.window.configure(bg=COLORS["surface"])

        set_window_icon(self.window)

        self.window.protocol(
            "WM_DELETE_WINDOW",
            lambda: None
        )


        self.window.deiconify()

        container = tk.Frame(
            self.window,
            bg=COLORS["surface"]
        )

        container.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=20
        )

        tk.Label(
            container,
            text=APP_NAME,
            bg=COLORS["surface"],
            fg=COLORS["primary_dark"],
            font=(FONT_NAME, 16, "bold")
        ).pack(anchor="w")

        self.label = tk.Label(
            container,
            text="Подготовка...",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(FONT_NAME, 10)
        )

        self.label.pack(
            anchor="w",
            pady=(15, 10)
        )

        self.progress = ttk.Progressbar(
            container,
            maximum=100,
            mode="determinate",
            style="Progress.Horizontal.TProgressbar"
        )

        self.progress.pack(
            fill="x",
            pady=5
        )

        self.percent = tk.Label(
            container,
            text="0%",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT_NAME, 9)
        )

        self.percent.pack(anchor="e")

        self.window.update_idletasks()

        x = (
            self.window.winfo_screenwidth()
            - self.window.winfo_width()
        ) // 2

        y = (
            self.window.winfo_screenheight()
            - self.window.winfo_height()
        ) // 2

        self.window.geometry(f"+{x}+{y}")
        self.window.deiconify()
        self.window.lift()

        try:
            self.window.attributes("-topmost", True)
            self.window.after(
                350,
                lambda: self.window.attributes("-topmost", False)
                if self.window.winfo_exists() else None
            )
        except tk.TclError:
            pass

    def update(self, value, text):
        try:
            if not self.window.winfo_exists():
                return

            self.progress["value"] = value
            self.label.config(text=text)
            self.percent.config(text=f"{int(value)}%")

        except tk.TclError:
            pass

    def close(self):
        try:
            self.window.destroy()
        except Exception:
            pass


class MyScanner32App:

    def __init__(self, root):
        self.root = root

        set_window_icon(self.root)

        self.root.title(
            f"{APP_NAME} {APP_VERSION}"
        )

        self.root.geometry("1250x760")
        self.root.minsize(950, 600)
        self.root.configure(bg=COLORS["background"])

        self.startup_items = {}
        self.registry_startup_items = {}
        self.task_items = {}
        self.process_items = {}

        self.process_snapshot = {}

        self.refreshing = False
        self.first_load = True

        self.events = queue.Queue()
        self.monitor_stop = threading.Event()

        self.progress_window = None
        self.offline_windows_path = None
        self.offline_mounts = []
        self.offline_backup_path = None

        self.setup_fonts()
        self.setup_style()
        self.create_interface()

        self.root.withdraw()
        self.refresh_all()

        self.root.after(100, self.poll_events)
        self.start_process_monitor()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )


    def setup_fonts(self):
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            default_font.configure(family=FONT_NAME, size=10)

            text_font = tkfont.nametofont("TkTextFont")
            text_font.configure(family=FONT_NAME, size=10)

            menu_font = tkfont.nametofont("TkMenuFont")
            menu_font.configure(family=FONT_NAME, size=10)

            fixed_font = tkfont.nametofont("TkFixedFont")
            fixed_font.configure(family="Consolas", size=10)

        except Exception:
            pass


    def setup_style(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            ".",
            font=(FONT_NAME, 10),
            background=COLORS["background"],
            foreground=COLORS["text"]
        )

        style.configure(
            "TFrame",
            background=COLORS["background"]
        )

        style.configure(
            "TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=(FONT_NAME, 10)
        )

        style.configure(
            "TButton",
            font=(FONT_NAME, 9),
            padding=(12, 8),
            background=COLORS["surface"],
            foreground=COLORS["text"],
            borderwidth=1,
            relief="flat"
        )

        style.map(
            "TButton",
            background=[
                ("active", COLORS["surface_alt"]),
                ("pressed", COLORS["primary"])
            ],
            foreground=[
                ("disabled", COLORS["muted"])
            ]
        )

        style.configure(
            "Primary.TButton",
            background=COLORS["primary"],
            foreground=COLORS["white"],
            font=(FONT_NAME, 9, "bold"),
            padding=(14, 9)
        )

        style.map(
            "Primary.TButton",
            background=[
                ("active", COLORS["primary_hover"]),
                ("pressed", COLORS["primary_dark"])
            ]
        )

        style.configure(
            "TNotebook",
            background=COLORS["background"],
            borderwidth=0
        )

        style.configure(
            "TNotebook.Tab",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            padding=(18, 11),
            font=(FONT_NAME, 10)
        )

        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", COLORS["surface"])
            ],
            foreground=[
                ("selected", COLORS["text"])
            ]
        )

        style.configure(
            "Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            rowheight=34,
            font=(FONT_NAME, 9),
            borderwidth=0
        )

        style.configure(
            "Treeview.Heading",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            font=(FONT_NAME, 9, "bold"),
            padding=(8, 10),
            relief="flat"
        )

        style.map(
            "Treeview.Heading",
            background=[
                ("active", COLORS["selected"]),
                ("pressed", COLORS["surface_alt"])
            ],
            foreground=[
                ("active", COLORS["text"])
            ]
        )

        style.map(
            "Treeview",
            background=[
                ("selected", COLORS["selected"])
            ],
            foreground=[
                ("selected", COLORS["text"])
            ]
        )

        style.configure(
            "Vertical.TScrollbar",
            background=COLORS["surface_alt"],
            troughcolor=COLORS["background"],
            arrowcolor=COLORS["text"],
            borderwidth=0
        )

        style.configure(
            "Horizontal.TScrollbar",
            background=COLORS["surface_alt"],
            troughcolor=COLORS["background"],
            arrowcolor=COLORS["text"],
            borderwidth=0
        )

        style.configure(
            "TEntry",
            padding=7,
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"]
        )

        style.configure(
            "Progress.Horizontal.TProgressbar",
            troughcolor=COLORS["surface_alt"],
            background=COLORS["primary"],
            thickness=12,
            borderwidth=0
        )

    def update_widget_colors(self, widget, old_colors):
        """Рекурсивно обновляет цвета Tk-виджетов, меню и дочерних окон."""
        color_map = {
            old_colors[key]: COLORS[key]
            for key in old_colors
            if key in COLORS
        }

        try:
            if isinstance(widget, tk.Menu):
                widget.configure(
                    background=COLORS["surface"],
                    foreground=COLORS["text"],
                    activebackground=COLORS["selected"],
                    activeforeground=COLORS["text"],
                    disabledforeground=COLORS["muted"],
                    selectcolor=COLORS["primary"]
                )
            else:


                for option in (
                    "bg", "background", "fg", "foreground",
                    "highlightbackground", "highlightcolor",
                    "insertbackground", "selectbackground",
                    "selectforeground", "troughcolor",
                    "activebackground", "activeforeground",
                    "disabledforeground"
                ):
                    try:
                        current = widget.cget(option)
                        if current in color_map:
                            widget.configure(**{option: color_map[current]})
                    except (tk.TclError, TypeError, KeyError):
                        pass


                if isinstance(widget, (tk.Tk, tk.Toplevel)):
                    widget.configure(bg=COLORS["background"])

        except (tk.TclError, TypeError):
            pass

        try:
            for child in widget.winfo_children():
                self.update_widget_colors(child, old_colors)
        except (tk.TclError, AttributeError):
            pass

    def update_tree_colors(self):
        for tree_name in (
            "process_tree",
            "startup_tree",
            "task_tree"
        ):
            tree = getattr(self, tree_name, None)

            if tree:
                try:
                    tree.tag_configure(
                        "danger",
                        foreground=COLORS["danger"]
                    )

                    tree.tag_configure(
                        "warning",
                        foreground=COLORS["warning"]
                    )

                    tree.tag_configure(
                        "system",
                        foreground=COLORS["primary_dark"]
                    )

                except Exception:
                    pass


    def create_interface(self):
        header = tk.Frame(
            self.root,
            bg=COLORS["surface"],
            height=75,
            highlightbackground=COLORS["border"],
            highlightthickness=1
        )

        header.pack(
            fill="x",
            padx=15,
            pady=(15, 8)
        )

        header.pack_propagate(False)

        title_frame = tk.Frame(
            header,
            bg=COLORS["surface"]
        )

        title_frame.pack(
            side="left",
            padx=20,
            pady=10
        )

        tk.Label(
            title_frame,
            text=APP_NAME,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(FONT_NAME, 19, "bold")
        ).pack(anchor="w")

        tk.Label(
            title_frame,
            text=f"Системная диагностика и восстановление · {APP_VERSION}",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT_NAME, 9)
        ).pack(anchor="w")

        ttk.Button(
            header,
            text="Обновить данные",
            style="Primary.TButton",
            command=self.refresh_all
        ).pack(
            side="right",
            padx=5,
            pady=15
        )

        self.notebook = ttk.Notebook(self.root)

        self.notebook.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=(0, 15)
        )

        self.process_tab = ttk.Frame(self.notebook)
        self.startup_tab = ttk.Frame(self.notebook)
        self.task_tab = ttk.Frame(self.notebook)
        self.extra_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.process_tab, text="  Процессы  ")
        self.notebook.add(self.startup_tab, text="  Автозагрузка  ")
        self.notebook.add(self.task_tab, text="  Планировщик  ")
        self.notebook.add(self.extra_tab, text="  Дополнительно  ")

        self.create_process_tab()
        self.create_startup_tab()
        self.create_task_tab()
        self.create_extra_tab()


    def create_tree(self, parent, columns, headings, widths):
        frame = tk.Frame(
            parent,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1
        )

        frame.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=10
        )

        tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )

        for column, heading, width in zip(
            columns,
            headings,
            widths
        ):
            tree.heading(column, text=heading)

            tree.column(
                column,
                width=width,
                minwidth=70,
                anchor="w"
            )

        vertical = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=tree.yview
        )

        horizontal = ttk.Scrollbar(
            frame,
            orient="horizontal",
            command=tree.xview
        )

        tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set
        )

        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        return tree


    def create_process_tab(self):
        top = tk.Frame(
            self.process_tab,
            bg=COLORS["background"]
        )

        top.pack(
            fill="x",
            padx=12,
            pady=(12, 0)
        )

        tk.Label(
            top,
            text="Поиск процессов",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=(FONT_NAME, 10, "bold")
        ).pack(side="left", padx=(0, 10))

        self.process_search = tk.StringVar()

        entry = ttk.Entry(
            top,
            textvariable=self.process_search
        )

        entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        self.process_search.trace_add(
            "write",
            lambda *_: self.display_processes()
        )

        self.process_tree = self.create_tree(
            self.process_tab,
            ("pid", "name", "exe", "status", "risk"),
            ("PID", "Процесс", "Расположение", "Статус", "Анализ"),
            (75, 220, 470, 100, 300)
        )

        self.process_tree.tag_configure(
            "danger",
            foreground=COLORS["danger"]
        )

        self.process_tree.tag_configure(
            "warning",
            foreground=COLORS["warning"]
        )

        self.process_tree.tag_configure(
            "system",
            foreground=COLORS["primary_dark"]
        )

        self.process_tree.bind(
            "<Button-3>",
            self.process_context_menu
        )

        self.process_tree.bind(
            "<Double-1>",
            lambda event: self.open_process_location()
        )
        self.process_tree.bind("<Control-c>", self.copy_selected_process_name)
        self.process_tree.bind("<Control-C>", self.copy_selected_process_name)

        bottom = tk.Frame(
            self.process_tab,
            bg=COLORS["background"]
        )

        bottom.pack(
            fill="x",
            padx=12,
            pady=(0, 12)
        )

        buttons = [
            ("Завершить", self.terminate_process),
            ("Завершить дерево", self.terminate_process_tree),
            ("Перезапустить", self.restart_process),
            ("Расположение", self.open_process_location),
            ("SHA-256", self.process_hash),
            ("Проверить подпись", self.process_signature)
        ]

        for text, command in buttons:
            ttk.Button(
                bottom,
                text=text,
                command=command
            ).pack(side="left", padx=3)

    def display_processes(self):
        if not hasattr(self, "process_tree"):
            return

        search = self.process_search.get().lower()

        for item in self.process_tree.get_children():
            self.process_tree.delete(item)

        self.process_items.clear()

        for pid, data in sorted(
            self.process_snapshot.items(),
            key=lambda item: item[0]
        ):
            name = data.get("name") or "Неизвестно"
            exe = data.get("exe") or ""

            analysis = analyze_process(data)

            searchable = (
                name + exe + str(pid) + analysis["reason"]
            ).lower()

            if search and search not in searchable:
                continue

            displayed_name = (
                analysis["label"] + " " + name
                if analysis["label"]
                else name
            )

            item = self.process_tree.insert(
                "",
                "end",
                values=(
                    pid,
                    displayed_name,
                    exe,
                    data.get("status", "Работает"),
                    analysis["reason"]
                ),
                tags=(analysis["level"],)
            )

            self.process_items[item] = data

    def copy_selected_process_name(self, event=None):
        """Копирует имя выделенного процесса в буфер обмена по Ctrl+C."""
        data = self.get_selected_process()
        if not data:
            return "break"

        process_name = str(data.get("name") or "")
        if not process_name:
            return "break"

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(process_name)
            self.root.update_idletasks()
        except tk.TclError:
            pass

        return "break"

    def get_selected_process(self):
        selection = self.process_tree.selection()

        if not selection:
            return None

        return self.process_items.get(selection[0])

    def process_context_menu(self, event):
        item = self.process_tree.identify_row(event.y)

        if not item:
            return

        self.process_tree.selection_set(item)

        menu = tk.Menu(
            self.root,
            tearoff=0,
            font=(FONT_NAME, 10),
            bg=COLORS["surface"],
            fg=COLORS["text"],
            activebackground=COLORS["selected"],
            activeforeground=COLORS["text"]
        )

        menu.add_command(
            label="Завершить процесс",
            command=self.terminate_process
        )

        menu.add_command(
            label="Завершить дерево процессов",
            command=self.terminate_process_tree
        )

        menu.add_command(
            label="Копировать название процесса",
            command=self.copy_selected_process_name
        )

        menu.add_command(
            label="Перезапустить процесс",
            command=self.restart_process
        )

        menu.add_separator()

        menu.add_command(
            label="Открыть расположение",
            command=self.open_process_location
        )

        menu.add_command(
            label="Вычислить SHA-256",
            command=self.process_hash
        )

        menu.add_command(
            label="Проверить цифровую подпись",
            command=self.process_signature
        )

        menu.post(event.x_root, event.y_root)

    def terminate_process(self):
        data = self.get_selected_process()

        if not data:
            messagebox.showwarning(APP_NAME, "Выберите процесс.")
            return

        pid = data["pid"]
        name = data.get("name", "")
        exe = data.get("exe", "")

        if (
            is_protected_system_file(exe)
            or is_legit_system(exe)
            or name.lower() in SYSTEM_PROCESSES
        ):
            messagebox.showwarning(
                APP_NAME,
                "Этот процесс защищён от завершения."
            )
            return

        if not messagebox.askyesno(
            APP_NAME,
            f"Завершить процесс {name} (PID {pid})?"
        ):
            return

        try:
            process = psutil.Process(pid)

            if data.get("create_time") != process.create_time():
                messagebox.showerror(
                    APP_NAME,
                    "Процесс изменился. Обновите список."
                )
                return

            process.terminate()

            try:
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                process.kill()

            messagebox.showinfo(APP_NAME, "Процесс завершён.")

        except psutil.AccessDenied:
            messagebox.showerror(APP_NAME, "Недостаточно прав.")

        except psutil.NoSuchProcess:
            messagebox.showwarning(APP_NAME, "Процесс уже завершён.")

        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))

    def terminate_process_tree(self):
        """Завершает выбранный процесс, его потомков и одноимённую ветку приложения."""
        data = self.get_selected_process()
        if not data:
            messagebox.showwarning(APP_NAME, "Выберите процесс.")
            return

        selected_pid = data.get("pid")
        selected_name = data.get("name") or "процесс"
        selected_exe = data.get("exe") or ""

        if (
            is_protected_system_file(selected_exe)
            or is_legit_system(selected_exe)
            or selected_name.lower() in SYSTEM_PROCESSES
        ):
            messagebox.showwarning(
                APP_NAME,
                "Этот системный процесс защищён от завершения."
            )
            return

        try:
            selected = psutil.Process(selected_pid)
            if data.get("create_time") is not None and (
                selected.create_time() != data.get("create_time")
            ):
                messagebox.showerror(
                    APP_NAME,
                    "Процесс изменился. Обновите список."
                )
                return


            root_process = selected
            normalized_exe = os.path.normcase(os.path.abspath(selected_exe)) if selected_exe else ""

            if normalized_exe:
                while True:
                    try:
                        parent = root_process.parent()
                        if parent is None:
                            break
                        parent_exe = parent.exe()
                        parent_normalized = (
                            os.path.normcase(os.path.abspath(parent_exe))
                            if parent_exe else ""
                        )
                        if parent_normalized != normalized_exe:
                            break
                        root_process = parent
                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                        OSError
                    ):
                        break

            candidates = root_process.children(recursive=True)
            candidates.append(root_process)


            unique = {}
            for proc in candidates:
                try:
                    proc_name = (proc.name() or "").lower()
                    proc_exe = proc.exe() or ""
                    if (
                        is_protected_system_file(proc_exe)
                        or is_legit_system(proc_exe)
                        or proc_name in SYSTEM_PROCESSES
                    ):
                        continue
                    unique[proc.pid] = proc
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess
                ):
                    continue

            processes = list(unique.values())
            if not processes:
                messagebox.showwarning(
                    APP_NAME,
                    "Не удалось найти доступные процессы для завершения."
                )
                return

            if not messagebox.askyesno(
                APP_NAME,
                f"Завершить дерево процессов «{selected_name}»?\n\n"
                f"Будет закрыто процессов: {len(processes)}.\n"
                "Несохранённые данные приложения могут быть потеряны."
            ):
                return


            for proc in processes:
                try:
                    proc.terminate()
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess
                ):
                    pass

            _, alive = psutil.wait_procs(processes, timeout=3)

            for proc in alive:
                try:
                    proc.kill()
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess
                ):
                    pass

            _, still_alive = psutil.wait_procs(alive, timeout=2)

            if still_alive:
                messagebox.showwarning(
                    APP_NAME,
                    "Часть процессов не удалось завершить. "
                    "Возможно, они защищены Windows или недоступны."
                )
            else:
                messagebox.showinfo(
                    APP_NAME,
                    f"Дерево процессов «{selected_name}» завершено."
                )

            self.refresh_all()

        except psutil.NoSuchProcess:
            messagebox.showwarning(APP_NAME, "Процесс уже завершён.")
        except psutil.AccessDenied:
            messagebox.showerror(APP_NAME, "Недостаточно прав для завершения процесса.")
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Не удалось завершить дерево процессов:\n{error}")

    def restart_process(self):
        data = self.get_selected_process()

        if not data:
            return

        pid = data["pid"]
        name = data.get("name", "")
        exe = data.get("exe", "")

        if not exe or not os.path.isfile(exe):
            messagebox.showerror(
                APP_NAME,
                "Не удалось определить EXE."
            )
            return

        if (
            is_protected_system_file(exe)
            or is_legit_system(exe)
            or name.lower() in SYSTEM_PROCESSES
        ):
            messagebox.showwarning(
                APP_NAME,
                "Перезапуск системных процессов запрещён."
            )
            return

        if not messagebox.askyesno(
            APP_NAME,
            f"Перезапустить {name}?\n\n"
            "Несохранённые данные могут быть потеряны."
        ):
            return

        try:
            process = psutil.Process(pid)

            if data.get("create_time") != process.create_time():
                messagebox.showerror(
                    APP_NAME,
                    "Процесс изменился."
                )
                return

            cmdline = process.cmdline()

            try:
                cwd = process.cwd()
            except Exception:
                cwd = None

            if not cmdline:
                cmdline = [exe]

            process.terminate()

            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

            subprocess.Popen(
                cmdline,
                cwd=cwd if cwd and os.path.isdir(cwd) else None
            )

            messagebox.showinfo(APP_NAME, "Процесс перезапущен.")

        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))

    def open_process_location(self):
        data = self.get_selected_process()

        if not data:
            return

        exe = data.get("exe")

        if not exe or not os.path.exists(exe):
            messagebox.showwarning(
                APP_NAME,
                "Расположение файла неизвестно."
            )
            return

        open_explorer(exe)

    def process_hash(self):
        data = self.get_selected_process()

        if not data:
            return

        exe = data.get("exe")

        if not exe or not os.path.isfile(exe):
            messagebox.showwarning(APP_NAME, "Файл недоступен.")
            return

        def worker():
            try:
                result = calculate_sha256(exe)
                self.events.put(("hash_result", exe, result))
            except Exception as error:
                self.events.put(("error", str(error)))

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    def process_signature(self):
        data = self.get_selected_process()

        if not data:
            return

        exe = data.get("exe")

        if not exe:
            return

        window = tk.Toplevel(self.root)

        window.title("Проверка подписи")
        window.geometry("550x180")
        window.configure(bg=COLORS["surface"])
        window.transient(self.root)

        set_window_icon(window)

        tk.Label(
            window,
            text="Проверка цифровой подписи...",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(FONT_NAME, 10)
        ).pack(padx=20, pady=25)

        def worker():
            result = check_signature(exe)

            self.events.put((
                "signature_result",
                window,
                result
            ))

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    def copy_text(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)


    def create_startup_tab(self):
        offline_bar = tk.Frame(self.startup_tab, bg=COLORS["background"])
        offline_bar.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(offline_bar, text="Целевая система:", bg=COLORS["background"],
                 fg=COLORS["text"], font=(FONT_NAME, 9, "bold")).pack(side="left", padx=(0, 8))
        self.offline_status = tk.Label(offline_bar, text="Текущая Windows",
                 bg=COLORS["background"], fg=COLORS["muted"], font=(FONT_NAME, 9))
        self.offline_status.pack(side="left", fill="x", expand=True)
        ttk.Button(offline_bar, text="Выбрать Windows для WinRE",
                   command=self.mount_offline_windows).pack(side="right", padx=(5, 0))
        ttk.Button(offline_bar, text="Отключить", command=self.unmount_offline_windows).pack(side="right")
        self.startup_sections = ttk.Notebook(self.startup_tab)
        self.startup_sections.pack(fill="both", expand=True, padx=10, pady=10)

        normal_tab = ttk.Frame(self.startup_sections)
        winlogon_tab = ttk.Frame(self.startup_sections)
        shell_tab = ttk.Frame(self.startup_sections)
        userinit_tab = ttk.Frame(self.startup_sections)
        bootexecute_tab = ttk.Frame(self.startup_sections)

        self.startup_sections.add(normal_tab, text="Обычная автозагрузка")
        self.startup_sections.add(winlogon_tab, text="Winlogon")
        self.startup_sections.add(shell_tab, text="Shell")
        self.startup_sections.add(userinit_tab, text="Userinit")
        self.startup_sections.add(bootexecute_tab, text="BootExecute")

        self.startup_tree = self.create_tree(
            normal_tab,
            ("name", "command", "location"),
            ("Название", "Команда", "Расположение"),
            (200, 600, 300)
        )
        self.startup_tree.bind("<Button-3>", self.startup_context_menu)

        bottom = tk.Frame(normal_tab, bg=COLORS["background"])
        bottom.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(bottom, text="Открыть расположение", command=self.open_startup_location).pack(side="left", padx=3)
        ttk.Button(bottom, text="Удалить запись", command=self.delete_startup).pack(side="left", padx=3)
        ttk.Button(bottom, text="Изменить команду / cmdline", command=self.edit_startup_command).pack(side="left", padx=3)
        ttk.Button(bottom, text="Обновить автозагрузку", command=self.refresh_all).pack(side="right", padx=3)

        self.registry_startup_views = {}
        self.create_registry_startup_view(
            winlogon_tab, "Winlogon", winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
        )
        self.create_registry_startup_view(
            shell_tab, "Shell", winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
            only_names=("Shell",)
        )
        self.create_registry_startup_view(
            userinit_tab, "Userinit", winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
            only_names=("Userinit",)
        )
        self.create_registry_startup_view(
            bootexecute_tab, "BootExecute", winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager",
            only_names=("BootExecute",)
        )

        note = tk.Label(
            bootexecute_tab,
            text="BootExecute запускается на раннем этапе загрузки Windows. Изменение неверного значения может нарушить запуск системы.",
            bg=COLORS["background"], fg=COLORS["warning"],
            font=(FONT_NAME, 9), wraplength=900, justify="left"
        )
        note.pack(anchor="w", padx=12, pady=(0, 10))

    def mount_offline_windows(self):
        folder = filedialog.askdirectory(title="Выберите корневую папку установленной Windows")
        if not folder:
            return
        config_dir = os.path.join(folder, "System32", "Config")
        software, system = os.path.join(config_dir, "SOFTWARE"), os.path.join(config_dir, "SYSTEM")
        if not (os.path.isfile(software) and os.path.isfile(system)):
            messagebox.showerror(APP_NAME, "Не найдены System32\\Config\\SOFTWARE и SYSTEM.")
            return
        if not is_admin():
            messagebox.showerror(APP_NAME, "Для подключения офлайн-реестра требуются права администратора.")
            return
        self.unmount_offline_windows(silent=True)
        mounts = []
        try:
            total_size = os.path.getsize(software) + os.path.getsize(system)
            drive_root = os.path.dirname(os.path.abspath(folder))
            if shutil.disk_usage(drive_root).free < total_size + 20 * 1024 * 1024:
                raise RuntimeError("Недостаточно места для резервной копии офлайн-реестра.")
            backup_root = os.path.join(drive_root, "MyScanner32_Backups")
            self.offline_backup_path = os.path.join(backup_root, datetime.now().strftime("%Y%m%d_%H%M%S"))
            os.makedirs(self.offline_backup_path, exist_ok=False)
            shutil.copy2(software, os.path.join(self.offline_backup_path, "SOFTWARE"))
            shutil.copy2(system, os.path.join(self.offline_backup_path, "SYSTEM"))
            for mount_name, hive_file in (("MyScanner32_Offline_SOFTWARE", software), ("MyScanner32_Offline_SYSTEM", system)):
                result = subprocess.run(["reg.exe", "load", "HKLM\\" + mount_name, hive_file],
                    capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW)
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout or "reg load завершился с ошибкой").strip())
                mounts.append(mount_name)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"MyScanner32_Offline_SYSTEM\Select", 0, winreg.KEY_READ) as key:
                current, _ = winreg.QueryValueEx(key, "Current")
            control_set = f"ControlSet{int(current):03d}"
            self.offline_mounts = mounts
            self.offline_windows_path = os.path.abspath(folder)
            for section, config in self.registry_startup_views.items():
                if section in ("Winlogon", "Shell", "Userinit"):
                    config["key_path"] = r"MyScanner32_Offline_SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
                elif section == "BootExecute":
                    config["key_path"] = "MyScanner32_Offline_SYSTEM\\" + control_set + r"\Control\Session Manager"
            self.offline_status.config(text=f"Офлайн Windows: {self.offline_windows_path}", fg=COLORS["text"])
            self.refresh_registry_startup_views()
            self.refresh_all()
            messagebox.showinfo(APP_NAME, f"Офлайн-реестр подключён. Полная копия SOFTWARE и SYSTEM сохранена в:\\n{self.offline_backup_path}")
        except Exception as error:
            for mount_name in reversed(mounts):
                subprocess.run(["reg.exe", "unload", "HKLM\\" + mount_name], capture_output=True, timeout=20, creationflags=CREATE_NO_WINDOW)
            self.offline_mounts = []
            self.offline_windows_path = None
            messagebox.showerror(APP_NAME, f"Не удалось подключить офлайн-реестр:\\n{error}")

    def unmount_offline_windows(self, silent=False):
        errors = []
        for mount_name in reversed(self.offline_mounts):
            try:
                result = subprocess.run(["reg.exe", "unload", "HKLM\\" + mount_name],
                    capture_output=True, text=True, timeout=20, creationflags=CREATE_NO_WINDOW)
                if result.returncode != 0:
                    errors.append((result.stderr or result.stdout or mount_name).strip())
            except Exception as error:
                errors.append(str(error))
        if errors:
            if not silent:
                messagebox.showerror(APP_NAME, "Не удалось отключить офлайн-реестр.\\n" + "\\n".join(errors))
            return
        self.offline_mounts = []
        self.offline_windows_path = None
        for section, config in getattr(self, "registry_startup_views", {}).items():
            if section in ("Winlogon", "Shell", "Userinit"):
                config["key_path"] = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
            elif section == "BootExecute":
                config["key_path"] = r"SYSTEM\CurrentControlSet\Control\Session Manager"
        if hasattr(self, "offline_status"):
            self.offline_status.config(text="Текущая Windows", fg=COLORS["muted"])
        if not silent and hasattr(self, "registry_startup_views"):
            self.refresh_registry_startup_views()
            self.refresh_all()

    def create_registry_startup_view(self, parent, section, hive, key_path, only_names=None):
        wrapper = tk.Frame(parent, bg=COLORS["background"])
        wrapper.pack(fill="both", expand=True, padx=12, pady=12)
        heading = tk.Label(
            wrapper, text=f"{section} — содержимое реестра", bg=COLORS["background"],
            fg=COLORS["text"], font=(FONT_NAME, 13, "bold")
        )
        heading.pack(anchor="w", pady=(0, 8))
        tree_frame = tk.Frame(wrapper, bg=COLORS["surface"])
        tree_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_frame, columns=("name", "value", "type"), show="headings")
        for col, label, width in (("name", "Имя значения", 180), ("value", "Данные", 650), ("type", "Тип", 130)):
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        tree.bind("<Double-1>", lambda event, t=tree: self.edit_registry_startup_value(t))
        controls = tk.Frame(wrapper, bg=COLORS["background"])
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Изменить выбранное", command=lambda t=tree: self.edit_registry_startup_value(t)).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="Обновить", command=lambda: self.refresh_registry_startup_views()).pack(side="left")
        self.registry_startup_views[section] = {
            "tree": tree, "hive": hive, "key_path": key_path,
            "only_names": tuple(only_names) if only_names else None
        }

    def refresh_registry_startup_views(self):
        self.registry_startup_items.clear()
        for section, config in getattr(self, "registry_startup_views", {}).items():
            tree = config["tree"]
            for iid in tree.get_children():
                tree.delete(iid)
            try:
                rows_added = 0
                access = winreg.KEY_READ
                if hasattr(winreg, "KEY_WOW64_64KEY"):
                    access |= winreg.KEY_WOW64_64KEY
                with winreg.OpenKey(config["hive"], config["key_path"], 0, access) as key:
                    index = 0
                    while True:
                        try:
                            name, value, value_type = winreg.EnumValue(key, index)
                            index += 1
                            if config["only_names"] and name not in config["only_names"]:
                                continue
                            if isinstance(value, (list, tuple)):
                                display = "\n".join(str(x) for x in value)
                            elif isinstance(value, bytes):
                                display = value.hex(" ")
                            else:
                                display = str(value)
                            type_name = {
                                winreg.REG_SZ: "REG_SZ", winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
                                winreg.REG_MULTI_SZ: "REG_MULTI_SZ", winreg.REG_DWORD: "REG_DWORD",
                                winreg.REG_QWORD: "REG_QWORD", winreg.REG_BINARY: "REG_BINARY"
                            }.get(value_type, str(value_type))
                            iid = tree.insert("", "end", values=(name or "(По умолчанию)", display, type_name))
                            self.registry_startup_items[(str(tree), iid)] = {
                                "hive": config["hive"], "key_path": config["key_path"],
                                "name": name, "value": value, "value_type": value_type,
                                "section": section
                            }
                            rows_added += 1
                        except OSError:
                            break
                if rows_added == 0:
                    tree.insert("", "end", values=("Значение не найдено", "", ""))
            except FileNotFoundError:
                tree.insert("", "end", values=("Раздел не найден", "", ""))
            except OSError as error:
                tree.insert("", "end", values=("Ошибка чтения", str(error), ""))

    def edit_registry_startup_value(self, tree):
        selection = tree.selection()
        if not selection:
            messagebox.showinfo(APP_NAME, "Сначала выберите значение реестра.")
            return
        item = self.registry_startup_items.get((str(tree), selection[0]))
        if not item:
            return
        value_type = item["value_type"]
        if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ, winreg.REG_MULTI_SZ):
            messagebox.showwarning(APP_NAME, "Этот тип данных пока доступен только для просмотра.")
            return

        old_value = item["value"]
        initial = "\n".join(str(x) for x in old_value) if isinstance(old_value, (list, tuple)) else str(old_value)
        editor = tk.Toplevel(self.root)
        editor.title(f"Изменение {item['name'] or '(По умолчанию)'}")
        editor.geometry("760x420")
        editor.minsize(520, 300)
        editor.configure(bg=COLORS["surface"])
        set_window_icon(editor)
        tk.Label(editor, text=f"{item['section']} · {item['name'] or '(По умолчанию)'}", bg=COLORS["surface"], fg=COLORS["text"], font=(FONT_NAME, 12, "bold")).pack(anchor="w", padx=14, pady=(14, 5))
        tk.Label(editor, text="Для REG_MULTI_SZ вводите по одной записи на строку.", bg=COLORS["surface"], fg=COLORS["muted"], font=(FONT_NAME, 9)).pack(anchor="w", padx=14, pady=(0, 8))
        text_box = tk.Text(editor, wrap="none", bg=COLORS["surface_alt"], fg=COLORS["text"], insertbackground=COLORS["text"], font=("Consolas", 10), height=12)
        text_box.pack(fill="both", expand=True, padx=14, pady=5)
        text_box.insert("1.0", initial)
        actions = tk.Frame(editor, bg=COLORS["surface"])
        actions.pack(fill="x", padx=14, pady=12)

        def save_value():
            raw = text_box.get("1.0", "end-1c")
            new_value = [line for line in raw.splitlines() if line.strip()] if value_type == winreg.REG_MULTI_SZ else raw
            if not messagebox.askyesno(APP_NAME, "Вы собираетесь изменить системный параметр реестра. Неверное значение может нарушить вход в Windows или загрузку системы.\n\nПеред изменением будет сохранена резервная копия текущего значения. Продолжить?", parent=editor):
                return
            try:
                backup_dir = self.offline_backup_path if self.offline_windows_path and self.offline_backup_path else CONFIG_DIR
                os.makedirs(backup_dir, exist_ok=True)
                backup = {
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "section": item["section"], "key_path": item["key_path"],
                    "value_name": item["name"], "value_type": int(value_type),
                    "value": old_value
                }
                backup_path = os.path.join(backup_dir, "registry_startup_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
                with open(backup_path, "w", encoding="utf-8") as file:
                    json.dump(backup, file, ensure_ascii=False, indent=2)
                access = winreg.KEY_SET_VALUE
                if hasattr(winreg, "KEY_WOW64_64KEY"):
                    access |= winreg.KEY_WOW64_64KEY
                with winreg.OpenKey(item["hive"], item["key_path"], 0, access) as key:
                    winreg.SetValueEx(key, item["name"], 0, value_type, new_value)
                editor.destroy()
                self.refresh_registry_startup_views()
                messagebox.showinfo(APP_NAME, f"Значение обновлено.\nРезервная копия: {backup_path}")
            except Exception as error:
                messagebox.showerror(APP_NAME, f"Не удалось изменить значение:\n{error}", parent=editor)

        ttk.Button(actions, text="Сохранить", style="Primary.TButton", command=save_value).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Отмена", command=editor.destroy).pack(side="right")

    def load_startup_data(self):
        result = []

        if self.offline_windows_path:
            registry_keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"MyScanner32_Offline_SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Офлайн HKLM Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"MyScanner32_Offline_SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "Офлайн HKLM Run 32-bit")
            ]
        else:
            registry_keys = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "HKLM Run 32-bit")
            ]

        for hive, key_path, location in registry_keys:
            try:
                with winreg.OpenKey(
                    hive,
                    key_path,
                    0,
                    winreg.KEY_READ
                ) as key:
                    index = 0

                    while True:
                        try:
                            name, command, _ = winreg.EnumValue(
                                key,
                                index
                            )

                            result.append({
                                "name": name,
                                "command": str(command),
                                "location": location,
                                "type": "registry",
                                "hive": hive,
                                "key_path": key_path,
                                "value_type": _
                            })

                            index += 1

                        except OSError:
                            break

            except OSError:
                pass

        if self.offline_windows_path:
            folders = [
                (os.path.join(self.offline_windows_path, "Users", "Default", "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"), "Офлайн Startup профиля Default"),
                (os.path.join(self.offline_windows_path, "ProgramData", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"), "Офлайн общая Startup")
            ]
        else:
            folders = [
                (os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"), "Startup пользователя"),
                (os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"), "Общая Startup")
            ]

        for folder, location in folders:
            if not os.path.isdir(folder):
                continue

            try:
                for filename in os.listdir(folder):
                    path = os.path.join(folder, filename)

                    result.append({
                        "name": filename,
                        "command": path,
                        "location": location,
                        "type": "file",
                        "path": path
                    })

            except Exception:
                pass

        return result

    def display_startup(self, items):
        for item in self.startup_tree.get_children():
            self.startup_tree.delete(item)

        self.startup_items.clear()

        for data in items:
            item = self.startup_tree.insert(
                "",
                "end",
                values=(
                    data["name"],
                    data["command"],
                    data["location"]
                )
            )

            self.startup_items[item] = data

    def get_selected_startup(self):
        selection = self.startup_tree.selection()

        if not selection:
            return None

        return self.startup_items.get(selection[0])

    def startup_context_menu(self, event):
        item = self.startup_tree.identify_row(event.y)

        if not item:
            return

        self.startup_tree.selection_set(item)

        menu = tk.Menu(
            self.root,
            tearoff=0,
            font=(FONT_NAME, 10),
            bg=COLORS["surface"],
            fg=COLORS["text"],
            activebackground=COLORS["selected"],
            activeforeground=COLORS["text"]
        )

        menu.add_command(
            label="Открыть расположение",
            command=self.open_startup_location
        )

        menu.add_command(
            label="Удалить запись",
            command=self.delete_startup
        )

        menu.post(event.x_root, event.y_root)

    def open_startup_location(self):
        data = self.get_selected_startup()

        if not data:
            return

        try:
            if data["type"] == "file":
                open_explorer(data["path"])
            else:
                open_registry_key(
                    data["hive"],
                    data["key_path"]
                )

        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))

    def delete_startup(self):
        data = self.get_selected_startup()

        if not data:
            return

        if not messagebox.askyesno(
            APP_NAME,
            f"Удалить запись «{data['name']}»?"
        ):
            return

        try:
            if data["type"] == "registry":
                if (
                    data["hive"] == winreg.HKEY_LOCAL_MACHINE
                    and not is_admin()
                ):
                    messagebox.showerror(
                        APP_NAME,
                        "Нужны права администратора."
                    )
                    return

                with winreg.OpenKey(data["hive"], data["key_path"], 0, winreg.KEY_READ) as key:
                    old_value, old_type = winreg.QueryValueEx(key, data["name"])
                backup_dir = self.offline_backup_path if self.offline_windows_path and self.offline_backup_path else CONFIG_DIR
                os.makedirs(backup_dir, exist_ok=True)
                backup = {"created": datetime.now().isoformat(timespec="seconds"), "name": data["name"],
                          "key_path": data["key_path"], "location": data["location"],
                          "value": old_value, "value_type": int(old_type)}
                backup_path = os.path.join(backup_dir, "startup_delete_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
                with open(backup_path, "w", encoding="utf-8") as backup_file:
                    json.dump(backup, backup_file, ensure_ascii=False, indent=2)
                with winreg.OpenKey(data["hive"], data["key_path"], 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, data["name"])

            else:
                path = os.path.realpath(data["path"])

                allowed = [
                    os.path.realpath(os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")),
                    os.path.realpath(os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"))
                ]
                if self.offline_windows_path:
                    allowed.extend([
                        os.path.realpath(os.path.join(self.offline_windows_path, "Users", "Default", "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup")),
                        os.path.realpath(os.path.join(self.offline_windows_path, "ProgramData", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
                    ])

                if not any(
                    is_inside_directory(path, folder)
                    for folder in allowed
                ):
                    messagebox.showerror(
                        APP_NAME,
                        "Файл находится вне разрешённых папок автозагрузки."
                    )
                    return

                if os.path.isfile(path):
                    quarantine_root = os.path.dirname(self.offline_windows_path) if self.offline_windows_path else CONFIG_DIR
                    quarantine = os.path.join(quarantine_root, "MyScanner32_Quarantine")
                    os.makedirs(quarantine, exist_ok=True)
                    destination = os.path.join(quarantine, datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + os.path.basename(path))
                    shutil.move(path, destination)

            self.refresh_all()

        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))


    def edit_startup_command(self):
        data = self.get_selected_startup()
        if not data:
            messagebox.showinfo(APP_NAME, "Выберите запись автозагрузки.")
            return
        if data.get("type") != "registry":
            messagebox.showwarning(APP_NAME, "Для файлов Startup редактирование команды недоступно.")
            return
        if data.get("value_type") not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            messagebox.showwarning(APP_NAME, "Поддерживаются только REG_SZ и REG_EXPAND_SZ.")
            return
        editor = tk.Toplevel(self.root)
        editor.title("Изменение команды автозагрузки")
        editor.geometry("760x300")
        editor.minsize(560, 240)
        editor.configure(bg=COLORS["surface"])
        editor.transient(self.root)
        set_window_icon(editor)
        tk.Label(editor, text=f"{data['name']} · {data['location']}", bg=COLORS["surface"],
                 fg=COLORS["text"], font=(FONT_NAME, 12, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        tk.Label(editor, text="Командная строка (cmdline).", bg=COLORS["surface"],
                 fg=COLORS["muted"], font=(FONT_NAME, 9)).pack(anchor="w", padx=18, pady=(0, 8))
        entry = tk.Text(editor, height=5, wrap="word", bg=COLORS["surface_alt"],
                        fg=COLORS["text"], insertbackground=COLORS["text"],
                        font=("Consolas", 10), relief="flat")
        entry.pack(fill="both", expand=True, padx=18, pady=5)
        entry.insert("1.0", data["command"])
        def save():
            value = entry.get("1.0", "end-1c").strip()
            if not value:
                messagebox.showwarning(APP_NAME, "Команда не может быть пустой.", parent=editor)
                return
            if not messagebox.askyesno(APP_NAME, "Исходное значение будет сохранено в резервную копию. Продолжить?", parent=editor):
                return
            try:
                backup_dir = self.offline_backup_path if self.offline_windows_path and self.offline_backup_path else CONFIG_DIR
                os.makedirs(backup_dir, exist_ok=True)
                backup = {"created": datetime.now().isoformat(timespec="seconds"), "name": data["name"],
                          "key_path": data["key_path"], "old_value": data["command"], "value_type": int(data["value_type"])}
                backup_path = os.path.join(backup_dir, "startup_cmdline_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(backup, f, ensure_ascii=False, indent=2)
                access = winreg.KEY_SET_VALUE
                if data["hive"] == winreg.HKEY_LOCAL_MACHINE and hasattr(winreg, "KEY_WOW64_64KEY"):
                    access |= winreg.KEY_WOW64_64KEY
                with winreg.OpenKey(data["hive"], data["key_path"], 0, access) as key:
                    winreg.SetValueEx(key, data["name"], 0, data["value_type"], value)
                editor.destroy()
                self.refresh_all()
                messagebox.showinfo(APP_NAME, f"Команда обновлена.\\nРезервная копия: {backup_path}")
            except Exception as error:
                messagebox.showerror(APP_NAME, f"Не удалось обновить команду:\\n{error}", parent=editor)
        controls = tk.Frame(editor, bg=COLORS["surface"])
        controls.pack(fill="x", padx=18, pady=14)
        ttk.Button(controls, text="Сохранить", style="Primary.TButton", command=save).pack(side="right", padx=(6, 0))
        ttk.Button(controls, text="Отмена", command=editor.destroy).pack(side="right")

    def create_task_tab(self):
        self.task_tree = self.create_tree(
            self.task_tab,
            ("name", "path", "state", "trigger"),
            ("Название задачи", "Путь", "Состояние", "Триггеры"),
            (220, 260, 110, 550)
        )

        self.task_tree.bind(
            "<Button-3>",
            self.task_context_menu
        )

        bottom = tk.Frame(
            self.task_tab,
            bg=COLORS["background"]
        )

        bottom.pack(
            fill="x",
            padx=12,
            pady=(0, 12)
        )

        ttk.Button(
            bottom,
            text="Открыть планировщик",
            command=self.open_task_scheduler
        ).pack(side="left", padx=3)

        ttk.Button(
            bottom,
            text="Удалить задачу",
            command=self.delete_task
        ).pack(side="left", padx=3)

    def load_tasks_data(self):
        script = r"""
        $ErrorActionPreference = 'SilentlyContinue'

        [Console]::OutputEncoding =
            New-Object System.Text.UTF8Encoding

        $result = @()

        function Get-TriggerDescription($trigger, $xml) {
            $type = $trigger.CimClass.CimClassName
            $description = ''

            switch -Wildcard ($type) {
                '*BootTrigger' {
                    $description = 'При запуске компьютера'
                }

                '*LogonTrigger' {
                    $description = 'При входе пользователя'
                }

                '*TimeTrigger' {
                    $description = 'По расписанию'
                }

                '*IdleTrigger' {
                    $description = 'При простое компьютера'
                }

                '*EventTrigger' {
                    $description = 'При событии Windows'
                }

                '*RegistrationTrigger' {
                    $description = 'При регистрации задачи'
                }

                '*SessionStateChangeTrigger' {
                    $description = 'При изменении состояния сеанса'
                }

                default {
                    $description = 'Другой триггер'
                }
            }

            if ($type -like '*TimeTrigger') {
                $description = 'По расписанию'

                if ($xml -match '<ScheduleByDay') {
                    $description = 'Ежедневно'
                }
                elseif ($xml -match '<ScheduleByWeek') {
                    $description = 'Еженедельно'
                }
                elseif ($xml -match '<ScheduleByMonth') {
                    $description = 'Ежемесячно'
                }
                elseif ($xml -match '<ScheduleByMonthDayOfWeek') {
                    $description = 'Ежемесячно по дням недели'
                }
            }

            if ($trigger.StartBoundary) {
                try {
                    $date = [datetime]$trigger.StartBoundary

                    $description += ' (' +
                        $date.ToString('dd.MM.yyyy HH:mm') +
                        ')'
                }
                catch {}
            }

            if ($trigger.UserId) {
                $description += ' — ' + $trigger.UserId
            }

            if ($trigger.Enabled -eq $false) {
                $description += ' [Отключён]'
            }

            if ($trigger.DaysOfWeek) {
                $description += ' — дни недели: ' +
                    $trigger.DaysOfWeek
            }

            if ($trigger.DaysInterval) {
                $description += ' — интервал: ' +
                    $trigger.DaysInterval + ' дн.'
            }

            if ($trigger.WeeksInterval) {
                $description += ' — интервал: ' +
                    $trigger.WeeksInterval + ' нед.'
            }

            if ($trigger.Repetition.Interval) {
                $description += ' — повтор: ' +
                    $trigger.Repetition.Interval
            }

            return $description
        }

        foreach ($task in Get-ScheduledTask) {
            try {
                $xml = Export-ScheduledTask `
                    -TaskName $task.TaskName `
                    -TaskPath $task.TaskPath

                $descriptions = @()

                foreach ($trigger in $task.Triggers) {
                    $descriptions +=
                        Get-TriggerDescription $trigger $xml
                }

                if ($descriptions.Count -eq 0) {
                    $triggerText = 'Триггер не указан'
                }
                else {
                    $triggerText = $descriptions -join ' | '
                }

                $result += [PSCustomObject]@{
                    Name = [string]$task.TaskName
                    Path = [string]$task.TaskPath
                    State = [string]$task.State
                    Trigger = [string]$triggerText
                }
            }
            catch {}
        }

        ConvertTo-Json -InputObject @($result) -Depth 5 -Compress
        """

        try:
            completed = run_powershell(script, timeout=90)

            if completed.returncode != 0:
                return []

            output = completed.stdout.strip()

            if not output:
                return []

            data = json.loads(output)

            if isinstance(data, dict):
                data = [data]

            return data

        except Exception:
            return []

    def display_tasks(self, items):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        self.task_items.clear()

        for data in items:
            item = self.task_tree.insert(
                "",
                "end",
                values=(
                    data.get("Name", ""),
                    data.get("Path", ""),
                    data.get("State", ""),
                    data.get("Trigger", "")
                )
            )

            self.task_items[item] = data

    def get_selected_task(self):
        selection = self.task_tree.selection()

        if not selection:
            return None

        return self.task_items.get(selection[0])

    def task_context_menu(self, event):
        item = self.task_tree.identify_row(event.y)

        if not item:
            return

        self.task_tree.selection_set(item)

        menu = tk.Menu(
            self.root,
            tearoff=0,
            font=(FONT_NAME, 10),
            bg=COLORS["surface"],
            fg=COLORS["text"],
            activebackground=COLORS["selected"],
            activeforeground=COLORS["text"]
        )

        menu.add_command(
            label="Удалить задачу",
            command=self.delete_task
        )

        menu.post(event.x_root, event.y_root)

    def open_task_scheduler(self):
        try:
            subprocess.Popen(["taskschd.msc"])
        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))

    def delete_task(self):
        data = self.get_selected_task()

        if not data:
            return

        task_name = data.get("Name", "")
        task_path = data.get("Path", "")

        normalized = task_path.casefold()

        if (
            normalized.startswith("\\microsoft\\windows\\")
            or normalized == "\\microsoft\\"
        ):
            messagebox.showwarning(
                APP_NAME,
                "Удаление защищённых системных задач запрещено."
            )
            return

        if not task_path.startswith("\\"):
            messagebox.showerror(
                APP_NAME,
                "Некорректный путь задачи."
            )
            return

        if not messagebox.askyesno(
            APP_NAME,
            f"Удалить задачу?\n\n{task_path}{task_name}"
        ):
            return

        name64 = base64.b64encode(
            task_name.encode("utf-8")
        ).decode("ascii")

        path64 = base64.b64encode(
            task_path.encode("utf-8")
        ).decode("ascii")

        script = f"""
        $name = [System.Text.Encoding]::UTF8.GetString(
            [System.Convert]::FromBase64String('{name64}')
        )

        $path = [System.Text.Encoding]::UTF8.GetString(
            [System.Convert]::FromBase64String('{path64}')
        )

        Unregister-ScheduledTask `
            -TaskName $name `
            -TaskPath $path `
            -Confirm:$false `
            -ErrorAction Stop
        """

        try:
            completed = run_powershell(script, timeout=30)

            if completed.returncode != 0:
                messagebox.showerror(
                    APP_NAME,
                    completed.stderr or "Не удалось удалить задачу."
                )
                return

            self.refresh_all()

        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))


    def create_extra_tab(self):
        shell = tk.Frame(self.extra_tab, bg=COLORS["background"])
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(shell, text="Дополнительные инструменты", bg=COLORS["background"],
                 fg=COLORS["text"], font=(FONT_NAME, 18, "bold")).pack(anchor="w")
        tk.Label(shell, text="Системные утилиты и быстрый доступ к настройкам Windows.",
                 bg=COLORS["background"], fg=COLORS["muted"], font=(FONT_NAME, 9)).pack(anchor="w", pady=(4, 12))
        canvas = tk.Canvas(shell, bg=COLORS["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        grid = tk.Frame(canvas, bg=COLORS["background"])
        window_id = canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units")
                        if self.notebook.select() == str(self.extra_tab) else None)
        tools = [
            ("Терминал", "Открыть Windows Terminal или командную строку.", "Запустить", self.open_terminal),
            ("Поиск Windows", "Открыть параметры поиска. Переназначение Search на экране блокировки штатно не поддерживается Windows.", "Настроить Search", self.open_search_settings),
            ("Проводник", "Открыть проводник Windows.", "Открыть", lambda: open_explorer()),
            ("Редактор реестра", "Открыть системный редактор реестра.", "Открыть", self.open_registry),
            ("Службы Windows", "Открыть консоль служб для штатного запуска, остановки и перезапуска служб.", "Открыть", self.open_services),
            ("Перезапуск Проводника", "Перезапустить оболочку Windows Explorer. Критические процессы Windows защищены.", "Перезапустить", self.restart_explorer),
            ("Проверка системных файлов", "Запустить SFC для проверки и восстановления компонентов Windows.", "Запустить SFC", self.restore_fonts),
            ("Папка шрифтов", "Открыть системную папку шрифтов.", "Открыть", self.open_fonts_folder),
            ("Сведения о программе", "Версия и условия использования.", "О программе", self.about)
        ]
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1, uniform="tiles")
        for i, (title, desc, button, command) in enumerate(tools):
            self.create_extra_card(grid, title, desc, button, command, row=i // 2, column=i % 2)

    def open_terminal(self):
        try:
            terminal = shutil.which("wt.exe")
            if terminal:
                subprocess.Popen([terminal], close_fds=True)
            else:
                subprocess.Popen(["cmd.exe"], creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Не удалось запустить терминал:\\n{error}")

    def open_search_settings(self):
        try:
            os.startfile("ms-settings:search")
        except Exception:
            try:
                os.startfile("ms-settings:lockscreen")
            except Exception as error:
                messagebox.showerror(APP_NAME, f"Не удалось открыть настройки Windows:\\n{error}")

    def open_services(self):
        try:
            subprocess.Popen(["services.msc"], close_fds=True)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Не удалось открыть службы Windows:\\n{error}")

    def restart_explorer(self):
        if not messagebox.askyesno(APP_NAME, "Перезапустить оболочку Windows Explorer? Панель задач и рабочий стол кратковременно исчезнут."):
            return
        try:
            subprocess.run(["taskkill.exe", "/f", "/im", "explorer.exe"], capture_output=True,
                           timeout=10, creationflags=CREATE_NO_WINDOW)
            subprocess.Popen(["explorer.exe"], close_fds=True)
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Не удалось перезапустить Explorer:\\n{error}")

    def create_extra_card(self, parent, title, description, button_text, command, row=0, column=0):
        card = tk.Frame(parent, bg=COLORS["surface"],
                        highlightbackground=COLORS["border"], highlightthickness=1)
        card.grid(row=row, column=column, sticky="nsew", padx=7, pady=7)
        left = tk.Frame(card, bg=COLORS["surface"])
        left.pack(side="left", fill="both", expand=True, padx=15, pady=14)
        tk.Label(left, text=title, bg=COLORS["surface"], fg=COLORS["text"],
                 font=(FONT_NAME, 11, "bold")).pack(anchor="w")
        tk.Label(left, text=description, bg=COLORS["surface"], fg=COLORS["muted"],
                 font=(FONT_NAME, 9), wraplength=330, justify="left").pack(anchor="w", pady=(5, 0))
        ttk.Button(card, text=button_text, style="Primary.TButton", command=command).pack(
            side="right", padx=14, pady=14)

    def restore_fonts(self):
        if not messagebox.askyesno(
            APP_NAME,
            "Будет запущена проверка защищённых системных файлов "
            "Windows.\n\n"
            "Для восстановления может потребоваться подключение "
            "к интернету и права администратора.\n\n"
            "Продолжить?"
        ):
            return

        if is_admin():
            try:
                subprocess.Popen(["sfc.exe", "/scannow"])
            except Exception as error:
                messagebox.showerror(APP_NAME, str(error))

        else:
            try:
                result = ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "sfc.exe",
                    "/scannow",
                    None,
                    1
                )

                if result <= 32:
                    messagebox.showerror(
                        APP_NAME,
                        "Не удалось запустить проверку."
                    )

            except Exception as error:
                messagebox.showerror(APP_NAME, str(error))

    def open_registry(self):
        try:
            subprocess.Popen(["regedit.exe"])
        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))

    def open_fonts_folder(self):
        try:
            subprocess.Popen([
                "explorer.exe",
                os.path.join(SYSTEM_ROOT, "Fonts")
            ])
        except Exception as error:
            messagebox.showerror(APP_NAME, str(error))

    def about(self):
        window = tk.Toplevel(self.root)

        window.title("О программе")
        window.geometry("570x500")
        window.resizable(False, False)
        window.configure(bg=COLORS["background"])
        window.transient(self.root)

        set_window_icon(window)

        container = tk.Frame(
            window,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1
        )

        container.pack(
            fill="both",
            expand=True,
            padx=18,
            pady=18
        )

        header = tk.Frame(
            container,
            bg=COLORS["surface"]
        )

        header.pack(
            fill="x",
            padx=25,
            pady=(25, 15)
        )

        tk.Label(
            header,
            text=APP_NAME,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(FONT_NAME, 25, "bold")
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Системный монитор и инструмент диагностики Windows",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT_NAME, 9)
        ).pack(anchor="w", pady=(5, 0))

        separator = tk.Frame(
            container,
            bg=COLORS["border"],
            height=1
        )

        separator.pack(
            fill="x",
            padx=25,
            pady=5
        )

        info = tk.Frame(
            container,
            bg=COLORS["surface"]
        )

        info.pack(
            fill="x",
            padx=25,
            pady=15
        )

        tk.Label(
            info,
            text=f"Версия: {APP_VERSION}",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(FONT_NAME, 10)
        ).pack(anchor="w", pady=3)

        tk.Label(
            info,
            text="Разработано: Kitarno",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(FONT_NAME, 10, "bold")
        ).pack(anchor="w", pady=3)

        legal_title = tk.Label(
            container,
            text="Юридическая информация",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(FONT_NAME, 11, "bold")
        )

        legal_title.pack(
            anchor="w",
            padx=25,
            pady=(8, 8)
        )

        legal_text = (
            "MyScanner32 предоставляется «как есть».\n\n"
            "Разработчик не гарантирует отсутствие ошибок, "
            "бесперебойную работу или обнаружение всех угроз.\n\n"
            "Пользователь самостоятельно принимает решения "
            "об изменении системных настроек, завершении процессов, "
            "удалении задач и записей автозагрузки. Перед внесением "
            "изменений рекомендуется создать резервную копию.\n\n"
            "Программа не заменяет антивирусное ПО и профессиональные "
            "средства диагностики. Результаты анализа могут быть "
            "неполными или ошибочными.\n\n"
            "Использование программы должно соответствовать "
            "применимому законодательству. Ничто в этом уведомлении "
            "не ограничивает права пользователя, которые не могут "
            "быть ограничены законом."
        )

        text_frame = tk.Frame(
            container,
            bg=COLORS["surface_alt"]
        )

        text_frame.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=(0, 15)
        )

        tk.Label(
            text_frame,
            text=legal_text,
            bg=COLORS["surface_alt"],
            fg=COLORS["text"],
            font=(FONT_NAME, 9),
            justify="left",
            wraplength=465
        ).pack(
            fill="both",
            expand=True,
            padx=15,
            pady=12
        )

        ttk.Button(
            container,
            text="Закрыть",
            command=window.destroy
        ).pack(
            anchor="e",
            padx=25,
            pady=(0, 20)
        )


    @staticmethod
    def collect_processes():
        result = {}

        for process in psutil.process_iter(
            ["pid", "ppid", "name", "exe", "create_time"]
        ):
            try:
                info = process.info
                pid = info.get("pid")

                if pid is None:
                    continue

                result[pid] = {
                    "pid": pid,
                    "ppid": info.get("ppid"),
                    "name": info.get("name") or "",
                    "exe": info.get("exe") or "",
                    "create_time": info.get("create_time"),
                    "status": "Работает"
                }

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess
            ):
                continue

        return result


    def start_process_monitor(self):
        def monitor():
            previous = None

            while not self.monitor_stop.is_set():
                try:
                    current = self.collect_processes()

                    signature = {
                        pid: (
                            data.get("name"),
                            data.get("exe"),
                            data.get("create_time"),
                            data.get("ppid")
                        )
                        for pid, data in current.items()
                    }

                    if signature != previous:
                        previous = signature

                        self.events.put((
                            "process_update",
                            current
                        ))

                except Exception:
                    pass

                self.monitor_stop.wait(3)

        self.monitor_thread = threading.Thread(
            target=monitor,
            daemon=True
        )

        self.monitor_thread.start()


    def refresh_all(self):
        if self.refreshing:
            return

        self.refreshing = True

        title = (
            "Запуск MyScanner32"
            if self.first_load
            else "Обновление данных"
        )

        self.progress_window = ProgressWindow(
            self.root,
            title
        )

        def worker():
            try:
                self.events.put((
                    "progress",
                    10,
                    "Получение списка процессов..."
                ))

                processes = self.collect_processes()

                self.events.put((
                    "progress",
                    40,
                    "Проверка автозагрузки..."
                ))

                startup = self.load_startup_data()

                self.events.put((
                    "progress",
                    70,
                    "Получение задач планировщика..."
                ))

                tasks = self.load_tasks_data()

                self.events.put((
                    "progress",
                    95,
                    "Завершение..."
                ))

                self.events.put((
                    "refresh_result",
                    {
                        "processes": processes,
                        "startup": startup,
                        "tasks": tasks
                    }
                ))

            except Exception as error:
                self.events.put((
                    "refresh_error",
                    str(error)
                ))

            finally:
                self.events.put((
                    "refresh_done",
                    None
                ))

        threading.Thread(
            target=worker,
            daemon=True
        ).start()


    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                event_type = event[0]

                if event_type == "progress":
                    _, value, text = event

                    if self.progress_window:
                        self.progress_window.update(
                            value,
                            text
                        )

                elif event_type == "refresh_result":
                    data = event[1]

                    self.process_snapshot = data["processes"]

                    self.display_processes()
                    self.display_startup(data["startup"])
                    self.refresh_registry_startup_views()
                    self.display_tasks(data["tasks"])

                elif event_type == "process_update":
                    self.process_snapshot = event[1]
                    self.display_processes()

                elif event_type == "refresh_error":
                    messagebox.showerror(
                        APP_NAME,
                        event[1]
                    )

                elif event_type == "refresh_done":
                    self.refreshing = False

                    if self.progress_window:
                        progress = self.progress_window

                        progress.update(
                            100,
                            "Готово!"
                        )

                        self.root.after(
                            500,
                            progress.close
                        )

                    if self.first_load:
                        self.first_load = False

                        self.root.after(
                            500,
                            self.root.deiconify
                        )

                elif event_type == "hash_result":
                    _, path, result = event

                    window = tk.Toplevel(self.root)

                    window.title("SHA-256")
                    window.geometry("650x180")
                    window.configure(bg=COLORS["surface"])

                    set_window_icon(window)

                    tk.Label(
                        window,
                        text=path,
                        bg=COLORS["surface"],
                        fg=COLORS["text"],
                        wraplength=610,
                        font=(FONT_NAME, 9)
                    ).pack(
                        padx=15,
                        pady=15
                    )

                    entry = ttk.Entry(
                        window,
                        font=("Consolas", 10)
                    )

                    entry.pack(
                        fill="x",
                        padx=15
                    )

                    entry.insert(0, result)
                    entry.select_range(0, "end")

                    ttk.Button(
                        window,
                        text="Копировать",
                        command=lambda: self.copy_text(result)
                    ).pack(pady=15)

                elif event_type == "signature_result":
                    _, window, result = event

                    try:
                        if window.winfo_exists():
                            for widget in window.winfo_children():
                                widget.destroy()

                            tk.Label(
                                window,
                                text=result,
                                bg=COLORS["surface"],
                                fg=COLORS["text"],
                                wraplength=500,
                                font=(FONT_NAME, 10),
                                justify="left"
                            ).pack(
                                padx=20,
                                pady=25
                            )

                            ttk.Button(
                                window,
                                text="Закрыть",
                                command=window.destroy
                            ).pack(pady=10)

                    except tk.TclError:
                        pass

                elif event_type == "error":
                    messagebox.showerror(
                        APP_NAME,
                        event[1]
                    )

        except queue.Empty:
            pass

        try:
            if self.root.winfo_exists():
                self.root.after(
                    100,
                    self.poll_events
                )
        except tk.TclError:
            pass


    def on_close(self):
        self.monitor_stop.set()

        try:
            if self.progress_window:
                self.progress_window.close()
        except Exception:
            pass

        try:
            self.unmount_offline_windows(silent=True)
        except Exception:
            pass
        self.root.destroy()


def get_windows_boot_environment():
    """Определяет безопасный режим и среду восстановления Windows."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    drive = os.path.splitdrive(system_root)[0].upper()
    recovery = drive == "X:" or os.environ.get("SYSTEMDRIVE", "").upper() == "X:"
    safe_mode = False
    try:
        safe_mode = bool(ctypes.windll.user32.GetSystemMetrics(67))
    except Exception:
        pass
    return recovery, safe_mode


if __name__ == "__main__":

    if sys.platform != "win32":
        print("MyScanner32 предназначен для Windows.")
        sys.exit(1)


    recovery_mode, safe_mode = get_windows_boot_environment()

    if not is_admin() and not (recovery_mode or safe_mode):
        if relaunch_as_admin():
            sys.exit(0)
        print("Не удалось запросить права администратора.")
        sys.exit(1)

    set_app_user_model_id()

    root = tk.Tk()
    set_window_icon(root)

    app = MyScanner32App(root)

    if recovery_mode:
        messagebox.showwarning(
            APP_NAME,
            "Обнаружена среда восстановления Windows (WinRE/WinPE).\n\n"
            "Программа запущена в текущей среде восстановления и показывает её состояние. "
            "Она не подключает автоматически реестр и файлы установленной Windows "
            "на диске компьютера. Для проверки установленной системы требуется "
            "отдельное подключение её офлайн-реестра и каталогов."
        )
    elif safe_mode:
        root.title(f"{APP_NAME} {APP_VERSION} — безопасный режим")
        messagebox.showinfo(
            APP_NAME,
            "MyScanner32 запущен в безопасном режиме Windows.\n\n"
            "Некоторые функции могут быть недоступны, поскольку в безопасном "
            "режиме Windows отключает часть служб и драйверов."
        )

    root.mainloop()
