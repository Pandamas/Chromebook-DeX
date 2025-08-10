#!/usr/bin/env python3
"""
linux_dex.py
Ein einfacher DeX-ähnlicher Desktop-Wrapper für Linux (für Samsung/Android Geräte).
Benötigt: adb, scrcpy, PyQt6
"""

import sys
import subprocess
import threading
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QTextEdit, QFileDialog, QLineEdit, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QTimer

ADB = shutil.which("adb") or "adb"
SCRCPY = shutil.which("scrcpy") or "scrcpy"

def run_cmd(cmd):
    """Hilfsfunktion: Kommando ausführen, Rückgabe (retcode, stdout, stderr)."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError as e:
        return 127, "", str(e)

def adb(cmd_args):
    return run_cmd([ADB] + cmd_args)

class DexApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Linux Dex (Prototype)")
        self.resize(700, 480)

        self.device_combo = QComboBox()
        self.refresh_btn = QPushButton("Geräte aktualisieren")
        self.connect_btn = QPushButton("Autorisiere / Verbindung prüfen")
        self.launch_btn = QPushButton("scrcpy starten (DeX-Ansicht)")
        self.stop_scrcpy_btn = QPushButton("scrcpy stoppen")
        self.push_btn = QPushButton("Datei hochladen (push)")
        self.pull_btn = QPushButton("Datei herunterladen (pull)")
        self.install_apk_btn = QPushButton("APK installieren")
        self.start_app_btn = QPushButton("App starten (package/activity)")
        self.clipboard_btn = QPushButton("Clipboard → Gerät senden")

        self.apk_path_input = QLineEdit()
        self.apk_path_input.setPlaceholderText("/pfad/zur/app.apk")

        self.app_start_input = QLineEdit()
        self.app_start_input.setPlaceholderText("com.example.app/.MainActivity")

        self.clip_text = QLineEdit()
        self.clip_text.setPlaceholderText("Text in Gerät einfügen (input text \"...\")")

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # Layout
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Device:"))
        top_row.addWidget(self.device_combo)
        top_row.addWidget(self.refresh_btn)
        top_row.addWidget(self.connect_btn)

        mid_row = QHBoxLayout()
        mid_row.addWidget(self.launch_btn)
        mid_row.addWidget(self.stop_scrcpy_btn)
        mid_row.addStretch()

        file_row = QHBoxLayout()
        file_row.addWidget(self.push_btn)
        file_row.addWidget(self.pull_btn)
        file_row.addWidget(self.install_apk_btn)
        file_row.addWidget(self.apk_path_input)

        app_row = QHBoxLayout()
        app_row.addWidget(self.start_app_btn)
        app_row.addWidget(self.app_start_input)

        clip_row = QHBoxLayout()
        clip_row.addWidget(self.clip_text)
        clip_row.addWidget(self.clipboard_btn)

        main = QVBoxLayout()
        main.addLayout(top_row)
        main.addLayout(mid_row)
        main.addLayout(file_row)
        main.addLayout(app_row)
        main.addLayout(clip_row)
        main.addWidget(QLabel("Log:"))
        main.addWidget(self.log)

        self.setLayout(main)

        # State
        self.scrcpy_proc = None

        # Hooks
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.connect_btn.clicked.connect(self.check_connection)
        self.launch_btn.clicked.connect(self.start_scrcpy)
        self.stop_scrcpy_btn.clicked.connect(self.stop_scrcpy)
        self.push_btn.clicked.connect(self.cmd_push_file)
        self.pull_btn.clicked.connect(self.cmd_pull_file)
        self.install_apk_btn.clicked.connect(self.install_apk)
        self.start_app_btn.clicked.connect(self.start_app)
        self.clipboard_btn.clicked.connect(self.send_clipboard)

        # Auto refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_devices)
        self.timer.start(5000)  # alle 5s

        self.refresh_devices()

    # --- Utility / UI helpers
    def log_msg(self, *parts):
        self.log.append(" ".join(str(p) for p in parts))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def get_selected_device(self):
        txt = self.device_combo.currentText()
        if not txt:
            return None
        return txt.split()[0]  # device id

    # --- Core features
    def refresh_devices(self):
        code, out, err = adb(["devices", "-l"])
        if code != 0:
            self.log_msg("adb fehlt oder Fehler:", err)
            self.device_combo.clear()
            return
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        devices = []
        for l in lines[1:]:  # erste Zeile ist "List of devices attached"
            if not l:
                continue
            parts = l.split()
            device_id = parts[0]
            if device_id == "daemon" or device_id.endswith(":"):
                continue
            devices.append(device_id + " " + " ".join(parts[1:]))
        self.device_combo.clear()
        if devices:
            self.device_combo.addItems(devices)
        else:
            self.device_combo.addItem("<kein Gerät>")
        self.log_msg("Gefundene Geräte:", len(devices))

    def check_connection(self):
        code, out, err = adb(["get-state"])
        if code == 0 and out.strip() in ("device",):
            self.log_msg("ADB: Gerät verbunden (state:", out.strip()+")")
        else:
            self.log_msg("ADB: Kein verbundenes/autorisiertes Gerät oder Fehler:", err or out)

    def start_scrcpy(self):
        device = self.get_selected_device()
        if not device or device.startswith("<"):
            QMessageBox.warning(self, "Kein Gerät", "Bitte zuerst ein Gerät auswählen/verbinden.")
            return
        if self.scrcpy_proc and self.scrcpy_proc.poll() is None:
            QMessageBox.information(self, "scrcpy läuft", "scrcpy läuft bereits.")
            return
        # Beispieloptionen: --max-size reduziert Bandbreite, --prefer-text allows clipboard
        cmd = [SCRCPY, "-s", device, "--stay-awake", "--prefer-text", "--max-size", "1280"]
        self.log_msg("Starte scrcpy:", " ".join(cmd))
        try:
            # Start als subprocess, output in Background
            self.scrcpy_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            threading.Thread(target=self._scrcpy_reader, daemon=True).start()
        except FileNotFoundError as e:
            self.log_msg("scrcpy nicht gefunden:", e)
            QMessageBox.critical(self, "Fehler", "scrcpy nicht installiert oder nicht im PATH.")

    def _scrcpy_reader(self):
        if not self.scrcpy_proc:
            return
        for line in self.scrcpy_proc.stderr:
            self.log_msg("[scrcpy]", line.strip())
        self.log_msg("scrcpy beendet (exit code)", self.scrcpy_proc.poll())

    def stop_scrcpy(self):
        if self.scrcpy_proc and self.scrcpy_proc.poll() is None:
            self.scrcpy_proc.terminate()
            self.scrcpy_proc.wait(timeout=3)
            self.log_msg("scrcpy gestoppt.")
        else:
            self.log_msg("Kein scrcpy Prozess aktiv.")

    def cmd_push_file(self):
        device = self.get_selected_device()
        if not device or device.startswith("<"):
            QMessageBox.warning(self, "Kein Gerät", "Bitte zuerst ein Gerät auswählen/verbinden.")
            return
        local, _ = QFileDialog.getOpenFileName(self, "Datei auswählen zum Hochladen")
        if not local:
            return
        target, ok = QFileDialog.getSaveFileName(self, "Ziel auf Gerät (Pfad, z.B. /sdcard/Download/datei.bin)")
        if not target:
            return
        self.log_msg("adb push", local, "->", target)
        threading.Thread(target=self._adb_push_thread, args=(device, local, target), daemon=True).start()

    def _adb_push_thread(self, device, local, target):
        code, out, err = adb(["-s", device, "push", local, target])
        self.log_msg("push result:", code, out, err)

    def cmd_pull_file(self):
        device = self.get_selected_device()
        if not device or device.startswith("<"):
            QMessageBox.warning(self, "Kein Gerät", "Bitte zuerst ein Gerät auswählen/verbinden.")
            return
        remote, ok = QFileDialog.getOpenFileName(self, "Wähle Datei auf Gerät (Pfad eingeben oder Leave empty)")
        # QFileDialog can't open remote paths; better: ask text input (quick hack)
        if not remote:
            remote, ok2 = QFileDialog.getSaveFileName(self, "Gib Pfad auf Gerät an (z.B. /sdcard/Download/file.jpg)")
            if not remote:
                return
        local, _ = QFileDialog.getSaveFileName(self, "Ziel auf Desktop speichern als")
        if not local:
            return
        self.log_msg("adb pull", remote, "->", local)
        threading.Thread(target=self._adb_pull_thread, args=(device, remote, local), daemon=True).start()

    def _adb_pull_thread(self, device, remote, local):
        code, out, err = adb(["-s", device, "pull", remote, local])
        self.log_msg("pull result:", code, out, err)

    def install_apk(self):
        device = self.get_selected_device()
        if not device or device.startswith("<"):
            QMessageBox.warning(self, "Kein Gerät", "Bitte zuerst ein Gerät auswählen/verbinden.")
            return
        apk_path, _ = QFileDialog.getOpenFileName(self, "APK auswählen", filter="APK files (*.apk)")
        if not apk_path:
            return
        self.log_msg("Installiere APK:", apk_path)
        threading.Thread(target=self._install_thread, args=(device, apk_path), daemon=True).start()

    def _install_thread(self, device, apk_path):
        code, out, err = adb(["-s", device, "install", "-r", apk_path])
        self.log_msg("install result:", code, out, err)

    def start_app(self):
        device = self.get_selected_device()
        pkg_activity = self.app_start_input.text().strip()
        if not pkg_activity:
            QMessageBox.warning(self, "Keine Aktivität", "Bitte package/activity angeben (z.B. com.example.app/.MainActivity).")
            return
        self.log_msg("Starte App:", pkg_activity)
        code, out, err = adb(["-s", device, "shell", "am", "start", "-n", pkg_activity])
        self.log_msg("start app:", code, out, err)

    def send_clipboard(self):
        device = self.get_selected_device()
        text = self.clip_text.text()
        if not text:
            QMessageBox.warning(self, "Kein Text", "Bitte Text eingeben.")
            return
        # Achtung: für einfache Fälle nutzen wir `input text` (quoting)
        safe = text.replace('"', '\\"')
        self.log_msg("Sende text to device:", safe)
        code, out, err = adb(["-s", device, "shell", "input", "text", safe])
        self.log_msg("clipboard send:", code, out, err)


def main():
    app = QApplication(sys.argv)
    w = DexApp()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
