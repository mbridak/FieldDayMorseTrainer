#!/usr/bin/env python3
"""
Field Day Morse Simulator
K6GTE
Michael.Bridak@gmail.com
"""

# pylint: disable=c-extension-no-member
# pylint: disable=no-name-in-module
# pylint: disable=arguments-out-of-order

from pathlib import Path
import os
import subprocess
import sys
import logging
import threading
import time
import random
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtCore import QDir, Qt, QRunnable, QThreadPool
from PyQt5 import QtCore, QtWidgets, uic


SIDE_TONE = 650
BAND_WIDTH = 300
MAX_CALLERS = 3
MINIMUM_CALLER_SPEED = 10
MAXIMUM_CALLER_SPEED = 30
MY_CALLSIGN = "K6GTE"
MY_CLASS = "1B"
MY_SECTION = "ORG"
MY_SPEED = 30

# Globals for IPC
message = ""
guessed_callsign = ""
call_resolved = False


def relpath(filename):
    """
    Checks to see if program has been packaged with pyinstaller.
    If so base dir is in a temp folder.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = getattr(sys, "_MEIPASS")
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, filename)


def load_fonts_from_dir(directory):
    """Load font families"""
    families_set = set()
    for thing in QDir(directory).entryInfoList(["*.ttf", "*.woff", "*.woff2"]):
        _id = QFontDatabase.addApplicationFont(thing.absoluteFilePath())
        families_set |= set(QFontDatabase.applicationFontFamilies(_id))
    return families_set


class Ham(QRunnable):
    def __init__(self, n):
        super().__init__()
        self.n = n

    def run(self):
        """Simulated Field Day participant"""
        global message
        global call_resolved
        current_state = "CQ"
        callsign = self.generate_callsign()
        klass = self.generate_class()
        section = self.generate_section(callsign)
        half_bandwidth = BAND_WIDTH / 2
        pitch = random.randint(SIDE_TONE - half_bandwidth, SIDE_TONE + half_bandwidth)
        speed = random.randint(MINIMUM_CALLER_SPEED, MAXIMUM_CALLER_SPEED)
        volume = 0.3
        side_tone = f"-f {pitch}"
        wpm = f"-w {speed}"
        vol = f"-v {volume}"
        answered_message = False

        while True:

            if "DIE " in message:
                break

            if message != answered_message:
                answered_message = message  # store timestamp

                if "CQ " in message:
                    current_state = "CQ"

                if current_state == "CQ":  # Waiting for CQ call
                    if "CQ " in message:  # different timestamp?
                        time.sleep(0.1 * random.randint(1, 5))
                        command = f"{callsign}"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")
                        answered_message = message  # store timestamp
                        current_state = "RESOLVINGCALL"

                if current_state == "RESOLVINGCALL" and "PARTIAL " in message:
                    error_level = self.run_ltest(callsign, guessed_callsign)
                    if error_level == 0.0:
                        command = "rr"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")
                        current_state = "CALLRESOLVED"
                        call_resolved = True
                    elif (
                        not call_resolved
                        and error_level < 1.0
                        or guessed_callsign == "?"
                    ):
                        command = f"{callsign}"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")

                if current_state == "RESOLVINGCALL" and "RESPONSE " in message:
                    error_level = self.run_ltest(callsign, guessed_callsign)
                    if error_level == 0.0:
                        command = f"tu {klass} {section}"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")
                        current_state = "CALLRESOLVED"
                        call_resolved = True
                        continue
                    elif not call_resolved and error_level < 0.5:  # could be me
                        command = f"de {callsign} {klass} {section}"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")

                if current_state == "CALLRESOLVED":
                    if "RESPONSE " in message:
                        command = f"tu {klass} {section}"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")
                    if "RESENDCLASS" in message:
                        command = f"{klass} {klass}"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")
                    if "RESENDSECTION" in message:
                        command = f"{section} {section}"
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, command],
                                timeout=15,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            print("timeout")
                    if "QRZ" in message:
                        if (
                            self.class_lineEdit.text() == klass
                            and self.section_lineEdit.text() == section
                        ):
                            print("correct")
            time.sleep(0.1)  # Thisi is here just so CPU cores arn't 100%

    @staticmethod
    def generate_class():
        """Generates a valid Field Day class"""
        suffix = ["A", "B", "C", "D", "E", "F"][random.randint(0, 5)]
        if "C" in suffix:
            return "1C"
        if "D" in suffix:
            return "1D"
        if "E" in suffix:
            return "1E"
        if "B" in suffix:
            return str(random.randint(1, 2)) + suffix
        if "A" in suffix:
            return str(random.randint(3, 20)) + suffix

        return str(random.randint(1, 20)) + suffix

    @staticmethod
    def generate_callsign():
        """Generates a US callsign, Need to add the land of maple syrup."""
        prefix = ["A", "K", "N", "W"]
        letters = [
            "A",
            "B",
            "C",
            "D",
            "E",
            "F",
            "G",
            "H",
            "I",
            "J",
            "K",
            "L",
            "M",
            "N",
            "O",
            "P",
            "Q",
            "R",
            "S",
            "T",
            "U",
            "V",
            "W",
            "X",
            "Y",
            "Z",
        ]
        callsign = prefix[random.randint(0, 3)]

        add_second_prefix_letter = random.randint(0, 2) == 0
        if "A" in callsign:  # We have no choice. Must add second prefix.
            callsign += letters[random.randint(0, 11)]
            add_second_prefix_letter = False

        if add_second_prefix_letter:
            callsign += letters[random.randint(0, 25)]

        callsign += str(random.randint(0, 9))
        if "A" in callsign[0]:
            suffix_length = random.randint(1, 2)
        else:
            suffix_length = random.randint(1, 3)

        for unused_variable in range(suffix_length):
            callsign += letters[random.randint(0, 25)]

        return callsign

    @staticmethod
    def generate_section(call):
        """Generate section based on call region"""
        call_areas = {
            "0": "CO MO IA ND KS NE MN SD",
            "1": "CT RI EMA VT ME WMA NH",
            "2": "ENY NNY NLI SNJ NNJ WNY",
            "3": "DE MDC EPA WPA",
            "4": "QL SC GA SFL KY TN NC VA NFL VI PR WCF",
            "5": "AR NTX LA OK MS STX NM WTX",
            "6": "EBA SCV LAX SDG ORG SF PAC SJV SB SV",
            "7": "AK NV AZ OR EWA UT ID WWA MT WY",
            "8": "MI WV OH",
            "9": "IL WI IN",
        }
        if call[1].isdigit():
            area = call[1]
        else:
            area = call[2]
        sections = call_areas[area].split()
        return sections[random.randint(0, len(sections) - 1)]

    def levenshtein(self, str1, str2):
        """This must be magic, This code block is all over github so it works then right?!?"""
        if len(str1) < len(str2):
            return self.levenshtein(str2, str1)

        if len(str2) == 0:
            return len(str1)

        previous_row = range(len(str2) + 1)
        for i, character1 in enumerate(str1):
            current_row = [i + 1]
            for j, character2 in enumerate(str2):
                insertions = (
                    previous_row[j + 1] + 1
                )  # j+1 instead of j since previous_row and current_row are one character longer
                deletions = current_row[j] + 1  # than s2
                substitutions = previous_row[j] + (character1 != character2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def run_ltest(self, str1, str2):
        """Does it work?"""
        ltest = self.levenshtein(str1, str2)
        return float(ltest) / float(len(str1))

    @staticmethod
    def log(line: str) -> None:
        """This is here because I'm too lazy to convert all the 'f' strings to %s crap."""
        logging.info(line)


class MainWindow(QtWidgets.QMainWindow):
    """Main Window"""

    def __init__(self, parent=None):
        """init the class"""
        super().__init__(parent)
        uic.loadUi(self.relpath("contest.ui"), self)
        self.participants = None
        self.spawn(MAX_CALLERS)
        self.cq_pushButton.clicked.connect(self.send_cq)
        self.report_pushButton.clicked.connect(self.send_report)
        self.confirm_pushButton.clicked.connect(self.send_confirm)
        self.agn_call_pushButton.clicked.connect(self.send_repeat_call)
        self.agn_class_pushButton.clicked.connect(self.send_repeat_class)
        self.agn_section_pushButton.clicked.connect(self.send_repeat_section)
        self.callsign_lineEdit.textChanged.connect(self.call_to_upper)
        self.class_lineEdit.textChanged.connect(self.class_to_upper)
        self.section_lineEdit.textChanged.connect(self.section_to_upper)
        self.section_lineEdit.returnPressed.connect(self.send_confirm)
        self.side_tone = f"-f {SIDE_TONE}"
        self.wpm = f"-w {MY_SPEED}"
        self.vol = "-v 0.3"
        self.resend_timer = QtCore.QTimer()
        self.resend_timer.timeout.connect(self.reinsert_cq_message)

    def spawn(self, people):
        """spin up the people"""
        threadCount = QThreadPool.globalInstance().maxThreadCount()
        if threadCount < MAX_CALLERS:
            threadCount = MAX_CALLERS
        pool = QThreadPool.globalInstance()
        for i in range(threadCount):
            ham = Ham(i)
            pool.start(ham)

    def call_to_upper(self):
        """Callsign text field to uppercase"""
        global guessed_callsign
        guessed_callsign = self.callsign_lineEdit.text().upper()
        self.callsign_lineEdit.setText(guessed_callsign)

    def class_to_upper(self):
        """Class text field to uppercase"""
        self.class_lineEdit.setText(self.class_lineEdit.text().upper())

    def section_to_upper(self):
        """Section text field to uppercase"""
        self.section_lineEdit.setText(self.section_lineEdit.text().upper())

    def reinsert_cq_message(self):
        """if no activity from OP callers resend calls"""
        global message
        message = f"CQ {time.clock_gettime(1)}"
        pass

    def send_cq(self):
        """Send CQ FD"""
        self.resend_timer.stop()
        self.resend_timer.timeout.connect(self.reinsert_cq_message)
        global message
        command = f"CQ FD DE {MY_CALLSIGN}"
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, command],
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("timeout")
        message = f"CQ {time.clock_gettime(1)}"
        self.resend_timer.start(20000)

    def send_report(self):
        """Answer callers with their callsign"""
        self.resend_timer.stop()
        global message, guessed_callsign
        guessed_callsign = self.callsign_lineEdit.text()
        self.callsign_lineEdit.setText(guessed_callsign.upper())
        command = f"{guessed_callsign} {MY_CLASS} {MY_SECTION}"
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, command],
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("timeout")
        message = f"RESPONSE {time.clock_gettime(1)}"

    def send_repeat_call(self):
        """Ask caller for his/her/non-binary call again"""
        self.resend_timer.stop()
        global message
        command = f"{self.callsign_lineEdit.text()}"
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, command],
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("timeout")
        message = f"PARTIAL {time.clock_gettime(1)}"

    def send_repeat_class(self):
        """Ask caller for class again"""
        self.resend_timer.stop()
        global message
        command = "class?"
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, command],
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("timeout")
        message = f"RESENDCLASS {time.clock_gettime(1)}"

    def send_repeat_section(self):
        """Ask caller for section"""
        self.resend_timer.stop()
        global message
        command = "sect?"
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, command],
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("timeout")
        message = f"RESENDSECTION {time.clock_gettime(1)}"

    def send_confirm(self):
        """Send equivilent of TU QRZ"""
        self.resend_timer.stop()
        global message, guessed_callsign, call_resolved
        message = f"QRZ {time.clock_gettime(1)}"
        self.section_lineEdit.setText("")
        self.class_lineEdit.setText("")
        self.callsign_lineEdit.setText("")
        self.callsign_lineEdit.setFocus()
        call_resolved = False
        message = "DIE "
        time.sleep(1)
        message = ""
        guessed_callsign = ""
        self.spawn(MAX_CALLERS)

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        """This extends QT's KeyPressEvent, handle tab, esc and function keys"""
        global message
        event_key = event.key()
        if event_key == Qt.Key_F1:
            self.send_cq()
            return
        if event_key == Qt.Key_F2:
            self.send_report()
            return
        if event_key == Qt.Key_F3:
            self.send_confirm()
            return
        if event_key == Qt.Key_F4:
            self.send_repeat_call()
            return
        if event_key == Qt.Key_F5:
            self.send_repeat_class()
            return
        if event_key == Qt.Key_F6:
            self.send_repeat_section()
            return
        if event_key == Qt.Key_F12:
            message = "DIE "  # kill off the hams
            return

    @staticmethod
    def relpath(filename: str) -> str:
        """
        If the program is packaged with pyinstaller,
        this is needed since all files will be in a temp
        folder during execution.
        """
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base_path = getattr(sys, "_MEIPASS")
        else:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, filename)

    @staticmethod
    def log(line: str) -> None:
        """This is here because I'm too lazy to convert all the 'f' strings to %s crap."""
        logging.info(line)


if __name__ == "__main__":
    if Path("./debug").exists():
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    font_dir = relpath("font")
    families = load_fonts_from_dir(os.fspath(font_dir))
    window = MainWindow()
    window.show()
    window.callsign_lineEdit.setFocus()
    app.exec()
