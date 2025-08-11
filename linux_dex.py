

#!/usr/bin/env python3
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

# --- Verbesserte Prüfung für adb & scrcpy ---
ADB = shutil.which("adb")
SCRCPY = shutil.which("scrcpy")

if not ADB:
    sys.stderr.write("Fehler: 'adb' nicht gefunden. Bitte installiere adb und füge es zum PATH hinzu.\n")
    sys.exit(1)

if not SCRCPY:
    sys.stderr.write("Fehler: 'scrcpy' nicht gefunden. Bitte installiere scrcpy und füge es zum PATH hinzu.\n")
    sys.exit(1)

def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError as e:
        return 127, "", str(e)

def adb_cmd(cmd_args):
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

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Device:"))
        top_row.addWidget(self.device_combo)
        top_row.addWidget(self.refresh_btn)
        top_row.addWidget(self.connect_btn)

        mid_row = QHBoxLayout()
        mid_row.addWidget(self.launch_btn)
        mid_row.addWidget(self.stop_scrcpy_btn)

        main = QVBoxLayout()
        main.addLayout(top_row)
        main.addLayout(mid_row)
        main.addWidget(QLabel("Log:"))
        main.addWidget(self.log)
        self.setLayout(main)

        self.scrcpy_proc = None

        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.connect_btn.clicked.connect(self.check_connection)
        self.launch_btn.clicked.connect(self.start_scrcpy)
        self.stop_scrcpy_btn.clicked.connect(self.stop_scrcpy)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_devices)
        self.timer.start(5000)

        self.refresh_devices()

    def log_msg(self, *parts):
        self.log.append(" ".join(str(p) for p in parts))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def get_selected_device(self):
        txt = self.device_combo.currentText()
        if not txt:
            return None
        return txt.split()[0]

    def refresh_devices(self):
        code, out, err = adb_cmd(["devices", "-l"])
        if code != 0:
            self.log_msg("adb Fehler:", err)
            self.device_combo.clear()
            return
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        devices = []
        for l in lines[1:]:
            parts = l.split()
            if parts:
                devices.append(parts[0])
        self.device_combo.clear()
        self.device_combo.addItems(devices if devices else ["<kein Gerät>"])
        self.log_msg("Gefundene Geräte:", len(devices))

    def check_connection(self):
        code, out, err = adb_cmd(["get-state"])
        if code == 0 and out.strip() == "device":
            self.log_msg("ADB: Gerät verbunden")
        else:
            self.log_msg("ADB: Kein Gerät verbunden oder Fehler:", err or out)

    def start_scrcpy(self):
        device = self.get_selected_device()
        if not device or device.startswith("<"):
            QMessageBox.warning(self, "Kein Gerät", "Bitte Gerät auswählen.")
            return
        if self.scrcpy_proc and self.scrcpy_proc.poll() is None:
            QMessageBox.information(self, "scrcpy läuft", "scrcpy läuft bereits.")
            return
        cmd = [SCRCPY, "-s", device, "--stay-awake", "--max-size", "1280"]
        self.log_msg("Starte scrcpy:", " ".join(cmd))
        try:
            self.scrcpy_proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
            threading.Thread(target=self._scrcpy_reader, daemon=True).start()
        except FileNotFoundError as e:
            self.log_msg("scrcpy nicht gefunden:", e)

    def _scrcpy_reader(self):
        if not self.scrcpy_proc:
            return
        for line in self.scrcpy_proc.stderr:
            self.log_msg("[scrcpy]", line.strip())

    def stop_scrcpy(self):
        if self.scrcpy_proc and self.scrcpy_proc.poll() is None:
            self.scrcpy_proc.terminate()
            self.scrcpy_proc.wait(timeout=3)
            self.log_msg("scrcpy gestoppt.")
        else:
            self.log_msg("Kein scrcpy Prozess aktiv.")

def main():
    app = QApplication(sys.argv)
    w = DexApp()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()