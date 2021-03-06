#!/usr/bin/env python3
"""
Field Day Morse Simulator
K6GTE
Michael.Bridak@gmail.com
"""

# pylint: disable=c-extension-no-member
# pylint: disable=no-name-in-module
# pylint: disable=arguments-out-of-order
# pylint: disable=invalid-name
# pylint: disable=global-statement

from pathlib import Path
import os
import subprocess
import sys
import logging
import time
import random
from math import ceil
from json import loads, dumps
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtCore import QDir, Qt, QRunnable, QThreadPool
from PyQt5 import QtCore, QtWidgets, uic, QtGui

settings = None

# Globals for IPC
message = ""
guessed_callsign = ""
guessed_class = ""
guessed_section = ""
call_resolved = False
result = ["", "", ""]

settings = {
    "SIDE_TONE": 650,
    "BAND_WIDTH": 500,
    "MAX_CALLERS": 3,
    "MINIMUM_CALLER_SPEED": 10,
    "MAXIMUM_CALLER_SPEED": 25,
    "MY_CALLSIGN": "K6GTE",
    "MY_CLASS": "1B",
    "MY_SECTION": "ORG",
    "MY_SPEED": 30,
}


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


class CalculatePhraseTime:
    """calulates the time to send a phrase"""

    def __init__(self):
        self.character_timing = {
            "A": 5,
            "B": 9,
            "C": 11,
            "D": 7,
            "E": 1,
            "F": 9,
            "G": 9,
            "H": 7,
            "I": 3,
            "J": 13,
            "K": 9,
            "L": 9,
            "M": 7,
            "N": 5,
            "O": 11,
            "P": 11,
            "Q": 13,
            "R": 7,
            "S": 5,
            "T": 3,
            "U": 7,
            "V": 9,
            "W": 9,
            "X": 11,
            "Y": 13,
            "Z": 11,
            "0": 19,
            "1": 17,
            "2": 15,
            "3": 13,
            "4": 11,
            "5": 9,
            "6": 11,
            "7": 13,
            "8": 15,
            "9": 17,
            " ": 7,
            "?": 15,
        }

    def time_for_phrase(self, wpm: int, phrase: str) -> int:
        """Converts a string into the miliseconds needed to send it, given the wpm"""
        miliseconds_per_element = 60 / (50 * wpm) * 1000
        elements = 0
        for character in phrase.upper():
            elements += self.character_timing[character]
            elements += len(phrase)  # one element pause between characters
        return ceil((miliseconds_per_element * elements) / 1000) + 2


class Ham(QRunnable):
    """This is the simulated Field Day participant."""

    def __init__(self, n):
        super().__init__()
        self.n = n
        self.timetosend = CalculatePhraseTime()

    def run(self):
        """Main loop for simulant"""
        global call_resolved
        global result
        current_state = "CQ"
        random.seed()
        callsign = self.generate_callsign()
        klass = self.generate_class()
        section = self.generate_section(callsign)
        half_bandwidth = settings["BAND_WIDTH"] / 2
        pitch = random.randint(
            settings["SIDE_TONE"] - half_bandwidth,
            settings["SIDE_TONE"] + half_bandwidth,
        )
        speed = random.randint(
            settings["MINIMUM_CALLER_SPEED"], settings["MAXIMUM_CALLER_SPEED"]
        )
        volume = random.uniform(0.1, 0.3)

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
                    self.log(f"{callsign}: {current_state}")
                    if "CQ " in message:  # different timestamp?
                        time.sleep(
                            0.1 * random.randint(1, 10)
                        )  # slightly random start time
                        morse_output = f"{callsign}"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        self.log(f"{callsign}: {current_state} {time_to_send}")
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )
                        answered_message = message  # store timestamp
                        current_state = "RESOLVINGCALL"

                if current_state == "RESOLVINGCALL" and "PARTIAL " in message:
                    error_level = self.run_ltest(callsign, guessed_callsign)
                    self.log(f"{callsign}: {current_state} {message} {error_level}")
                    if error_level == 0.0:
                        morse_output = "rr"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )
                        current_state = "CALLRESOLVED"
                        call_resolved = True
                        answered_message = message
                        continue
                    elif (
                        not call_resolved
                        and error_level < 0.8
                        or guessed_callsign == "?"
                        or guessed_callsign in callsign
                    ):
                        morse_output = f"{callsign}"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )

                if current_state == "RESOLVINGCALL" and "RESPONSE " in message:
                    error_level = self.run_ltest(callsign, guessed_callsign)
                    self.log(f"{callsign}: {current_state} {message} {error_level}")
                    if error_level == 0.0:
                        result = [callsign, klass, section]
                        morse_output = f"TU {klass} {section}"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )
                        current_state = "CALLRESOLVED"
                        call_resolved = True
                        continue
                    elif (
                        not call_resolved
                        and error_level < 0.5
                        or guessed_callsign in callsign
                    ):  # could be me
                        morse_output = f"DE {callsign} {klass} {section}"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )

                if current_state == "RESOLVINGCALL" and "RESEND" in message:
                    error_level = self.run_ltest(callsign, guessed_callsign)
                    self.log(f"{callsign}: {current_state} {message} {error_level}")
                    if error_level < 0.25:  # if close he must be talking to me right?
                        current_state = "CALLRESOLVED"
                        call_resolved = True

                if current_state == "CALLRESOLVED":
                    self.log(f"{callsign}: {current_state} {message}")
                    result = [callsign, klass, section]
                    if "PARTIAL " in message:
                        # If he's resending a callsign it's not resolved
                        current_state = "RESOLVINGCALL"
                        call_resolved = False
                        answered_message = False
                        continue
                    if "RESPONSE " in message:
                        morse_output = f"tu {klass} {section}"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )
                    if "RESENDCLASS" in message:
                        morse_output = f"{klass} {klass}"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )
                    if "RESENDSECTION" in message:
                        morse_output = f"{section} {section}"
                        time_to_send = self.timetosend.time_for_phrase(
                            speed, morse_output
                        )
                        try:
                            subprocess.run(
                                ["morse", side_tone, wpm, vol, morse_output],
                                timeout=time_to_send,
                                check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.log(
                                f"Morse Timeout: '{morse_output}' [{time_to_send}]"
                            )
                    if "QRZ" in message:
                        result = [callsign, klass, section]
            time.sleep(0.1)  # This is here just so CPU cores arn't 100%
        self.log("DIEDIEDIE")

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
            length = [
                1,
                2,
                2,
                3,
                3,
                3,
            ]  # Stupid way to get a weighted result. But I'm stupid so it's normal.
            suffix_length = length[random.randint(0, 5)]

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
            "4": "AL SC GA SFL KY TN NC VA NFL VI PR WCF",
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
        self.spawn()
        self.cq_pushButton.clicked.connect(self.send_cq)
        self.report_pushButton.clicked.connect(self.send_report)
        self.confirm_pushButton.clicked.connect(self.send_confirm)
        self.agn_call_pushButton.clicked.connect(self.send_repeat_call)
        self.agn_class_pushButton.clicked.connect(self.send_repeat_class)
        self.agn_section_pushButton.clicked.connect(self.send_repeat_section)
        self.callsign_lineEdit.textChanged.connect(self.call_changed)
        self.callsign_lineEdit.textEdited.connect(self.call_test)
        self.class_lineEdit.textEdited.connect(self.class_test)
        self.class_lineEdit.returnPressed.connect(self.send_confirm)
        self.section_lineEdit.textEdited.connect(self.section_test)
        self.section_lineEdit.returnPressed.connect(self.send_confirm)
        self.timetosend = CalculatePhraseTime()
        self.side_tone = f"-f {settings['SIDE_TONE']}"
        self.wpm = f"-w {settings['MY_SPEED']}"
        self.vol = "-v 0.3"
        self.resend_timer = QtCore.QTimer()
        self.resend_timer.timeout.connect(self.reinsert_cq_message)

    def spawn(self):
        """spin up the people"""
        threadCount = QThreadPool.globalInstance().maxThreadCount()
        if threadCount > settings["MAX_CALLERS"]:
            threadCount = settings["MAX_CALLERS"]
        pool = QThreadPool.globalInstance()
        for i in range(threadCount):
            ham = Ham(i)
            pool.start(ham)

    def call_changed(self):
        """Callsign text field to uppercase"""
        global guessed_callsign
        guessed_callsign = self.callsign_lineEdit.text().upper()

    def call_test(self):
        """
        Test and strip class of bad characters, advance to next input field if space pressed.
        """
        text = self.callsign_lineEdit.text()
        if len(text):
            if text[-1] == " ":
                self.callsign_lineEdit.setText(text.strip())
                self.class_lineEdit.setFocus()
                self.class_lineEdit.deselect()
            else:
                washere = self.callsign_lineEdit.cursorPosition()
                cleaned = "".join(ch for ch in text if ch.isalnum()).upper()
                self.callsign_lineEdit.setText(cleaned)
                self.callsign_lineEdit.setCursorPosition(washere)

    def class_test(self):
        """
        Test and strip class of bad characters, advance to next input field if space pressed.
        """
        global guessed_class
        text = self.class_lineEdit.text()
        if len(text):
            if text[-1] == " ":
                self.class_lineEdit.setText(text.strip())
                self.section_lineEdit.setFocus()
                self.section_lineEdit.deselect()
            else:
                washere = self.class_lineEdit.cursorPosition()
                cleaned = "".join(ch for ch in text if ch.isalnum()).upper()
                guessed_class = cleaned
                self.class_lineEdit.setText(cleaned)
                self.class_lineEdit.setCursorPosition(washere)

    def section_test(self):
        """
        Test and strip class of bad characters, advance to next input field if space pressed.
        """
        global guessed_section
        text = self.section_lineEdit.text()
        if len(text):
            if text[-1] == " ":
                self.section_lineEdit.setText(text.strip())
                self.callsign_lineEdit.setFocus()
                self.callsign_lineEdit.deselect()
            else:
                washere = self.section_lineEdit.cursorPosition()
                cleaned = "".join(ch for ch in text if ch.isalnum()).upper()
                guessed_section = cleaned
                self.section_lineEdit.setText(cleaned)
                self.section_lineEdit.setCursorPosition(washere)

    def reinsert_cq_message(self):
        """if no activity from OP callers resend calls"""
        global message
        message = f"CQ {time.clock_gettime(1)}"
        self.resend_timer.start(10000)

    def send_cq(self):
        """Send CQ FD"""
        self.resend_timer.stop()
        global message, result
        result = []
        morse_output = f"CQ FD DE {settings['MY_CALLSIGN']}"
        time_to_send = self.timetosend.time_for_phrase(
            settings["MY_SPEED"], morse_output
        )
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, morse_output],
                timeout=time_to_send,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.log(f"Morse Timeout: '{morse_output}' [{time_to_send}]")
        message = f"CQ {time.clock_gettime(1)}"
        self.resend_timer.start(10000)

    def send_report(self):
        """Answer callers with their callsign"""
        self.resend_timer.stop()
        global message, guessed_callsign
        guessed_callsign = self.callsign_lineEdit.text()
        self.callsign_lineEdit.setText(guessed_callsign.upper())
        morse_output = (
            f"{guessed_callsign} {settings['MY_CLASS']} {settings['MY_SECTION']}"
        )
        time_to_send = self.timetosend.time_for_phrase(
            settings["MY_SPEED"], morse_output
        )
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, morse_output],
                timeout=time_to_send,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.log(f"Morse Timeout: '{morse_output}' [{time_to_send}]")
        message = f"RESPONSE {time.clock_gettime(1)}"

    def send_repeat_call(self):
        """Ask caller for his/her/non-binary call again"""
        self.resend_timer.stop()
        global message
        morse_output = f"{self.callsign_lineEdit.text()}"
        time_to_send = self.timetosend.time_for_phrase(
            settings["MY_SPEED"], morse_output
        )
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, morse_output],
                timeout=time_to_send,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.log(f"Morse Timeout: '{morse_output}' [{time_to_send}]")
        message = f"PARTIAL {time.clock_gettime(1)}"

    def send_repeat_class(self):
        """Ask caller for class again"""
        self.resend_timer.stop()
        global message
        morse_output = "cls?"
        time_to_send = self.timetosend.time_for_phrase(
            settings["MY_SPEED"], morse_output
        )
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, morse_output],
                timeout=time_to_send,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.log(f"Morse Timeout: '{morse_output}' [{time_to_send}]")
        message = f"RESENDCLASS {time.clock_gettime(1)}"

    def send_repeat_section(self):
        """Ask caller for section"""
        self.resend_timer.stop()
        global message
        morse_output = "sec?"
        time_to_send = self.timetosend.time_for_phrase(
            settings["MY_SPEED"], morse_output
        )
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, morse_output],
                timeout=time_to_send,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.log(f"Morse Timeout: '{morse_output}' [{time_to_send}]")
        message = f"RESENDSECTION {time.clock_gettime(1)}"

    def send_confirm(self):
        """Send equivilent of TU QRZ"""
        self.resend_timer.stop()
        global result
        if (
            self.section_lineEdit.text() == ""
            or self.class_lineEdit.text() == ""
            or self.callsign_lineEdit.text() == ""
        ):
            return
        self.resend_timer.stop()
        global message, guessed_callsign, guessed_class, guessed_section, call_resolved
        message = f"QRZ {time.clock_gettime(1)}"
        morse_output = f"tu {settings['MY_CALLSIGN']} fd"
        time_to_send = self.timetosend.time_for_phrase(
            settings["MY_SPEED"], morse_output
        )
        try:
            subprocess.run(
                ["morse", self.side_tone, self.wpm, self.vol, morse_output],
                timeout=time_to_send,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.log(f"Morse Timeout: '{morse_output}' [{time_to_send}]")

        self.check_result()
        result = ["", "", ""]
        message = "DIE "
        time.sleep(1)

        self.section_lineEdit.setText("")
        self.class_lineEdit.setText("")
        self.callsign_lineEdit.setText("")
        self.callsign_lineEdit.setFocus()
        call_resolved = False
        message = ""
        guessed_callsign = ""
        guessed_class = ""
        guessed_section = ""
        self.spawn()
        self.reinsert_cq_message()

    def send_nil(self):
        """Send not in log"""
        global message
        message = "DIE "
        time.sleep(1)
        self.spawn()

    def check_result(self):
        """See if you were right."""
        global result
        if not result:
            result = ["", "", ""]
        if guessed_callsign == result[0]:
            a = guessed_callsign
        else:
            a = f"{guessed_callsign} ({result[0]})"
        if guessed_class == result[1]:
            b = guessed_class
        else:
            b = f"{guessed_class} ({result[1]})"
        if guessed_section == result[2]:
            c = guessed_section
        else:
            c = f"{guessed_section} ({result[2]})"

        logline = f"{a} \t{b} \t{c}"
        self.log_listWidget.addItem(logline)
        self.log_listWidget.scrollToBottom()

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        """This extends QT's KeyPressEvent, handle tab, esc and function keys"""
        global message
        event_key = event.key()
        self.log(event_key)
        if event_key == Qt.Key_Escape:
            self.section_lineEdit.setText("")
            self.class_lineEdit.setText("")
            self.callsign_lineEdit.setText("")
            self.callsign_lineEdit.setFocus()
            return
        if event_key == Qt.Key_Tab:
            if self.section_lineEdit.hasFocus():
                self.callsign_lineEdit.setFocus()
                self.callsign_lineEdit.deselect()
                self.callsign_lineEdit.end(False)
                return
            if self.class_lineEdit.hasFocus():
                self.section_lineEdit.setFocus()
                self.section_lineEdit.deselect()
                self.section_lineEdit.end(False)
                return
            if self.callsign_lineEdit.hasFocus():
                self.class_lineEdit.setFocus()
                self.class_lineEdit.deselect()
                self.class_lineEdit.end(False)
                return
        if event_key == Qt.Key_F1:
            self.send_cq()
            return
        if event_key == Qt.Key_F3:
            self.send_report()
            return
        if event_key == Qt.Key_F4:
            self.send_confirm()
            return
        if event_key == Qt.Key_F2:
            self.send_repeat_call()
            return
        if event_key == Qt.Key_F5:
            self.send_repeat_class()
            return
        if event_key == Qt.Key_F6:
            self.send_repeat_section()
            return
        if event_key == Qt.Key_F9:
            self.send_nil()
            return
        if event_key == Qt.Key_F12:
            message = "DIE "  # kill off the hams
            return

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        """When app is closing send a message to Ham Zombies to signal them to die."""
        global message
        message = "DIE "
        time.sleep(1)
        return super().closeEvent(a0)

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
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        if os.path.exists("./fdm_settings.json"):
            with open("./fdm_settings.json", "rt", encoding="utf-8") as file_descriptor:
                settings = loads(file_descriptor.read())
        else:
            with open("./fdm_settings.json", "wt", encoding="utf-8") as file_descriptor:
                file_descriptor.write(dumps(settings, indent=4))
                logging.info("writing: %s", settings)
    except IOError as exception:
        logging.critical("Reading Preferences: %s", exception)
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    font_dir = relpath("font")
    families = load_fonts_from_dir(os.fspath(font_dir))
    window = MainWindow()
    window.show()
    window.callsign_lineEdit.setFocus()
    app.exec()
