"""Dark theme Qt Style Sheet for the whole application."""

DARK_STYLESHEET = """
QWidget {
    background-color: #1e1f24;
    color: #e6e6e6;
    font-family: "Segoe UI", sans-serif;
    font-size: 10.5pt;
}

QMainWindow, QDialog {
    background-color: #1e1f24;
}

/* Ordinary text elements (labels, headings, status text) must never
   paint their own background -- they sit directly on whatever
   container (window, card) is beneath them. Windows/Qt sometimes
   renders a QLabel with a stray opaque background despite the QWidget
   rule above (a known styled-widget quirk), so this is stated
   explicitly rather than left to inheritance. Cards, buttons, and
   input fields set their own backgrounds below and are unaffected. */
QLabel {
    background: transparent;
}

QListWidget#sidebar {
    background-color: #17181c;
    border: none;
    padding-top: 8px;
    outline: 0;
}

QListWidget#sidebar::item {
    padding: 10px 16px;
    border-radius: 4px;
    margin: 2px 8px;
}

QListWidget#sidebar::item:selected {
    background-color: #3a6ea5;
    color: #ffffff;
}

QListWidget#sidebar::item:hover:!selected {
    background-color: #2a2c33;
}

QLabel#pageTitle {
    font-size: 16pt;
    font-weight: 600;
    padding: 4px 0 12px 0;
}

QLabel#sectionLabel {
    font-weight: 600;
    color: #9fa4ad;
    padding-top: 6px;
}

QFrame#card {
    background-color: #262830;
    border-radius: 8px;
    border: 1px solid #33353d;
}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #2a2c33;
    border: 1px solid #3a3c45;
    border-radius: 4px;
    padding: 6px;
    color: #e6e6e6;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #3a6ea5;
}

QPushButton {
    background-color: #3a6ea5;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #4a7fb8;
}

QPushButton:pressed {
    background-color: #2f5a86;
}

QPushButton:disabled {
    background-color: #3a3c45;
    color: #74767d;
}

QPushButton#secondaryButton {
    background-color: #2a2c33;
    color: #e6e6e6;
    border: 1px solid #3a3c45;
}

QPushButton#secondaryButton:hover {
    background-color: #33353d;
}

QPlainTextEdit#logView {
    background-color: #101114;
    color: #c9d1d9;
    font-family: Consolas, "Courier New", monospace;
    border: 1px solid #33353d;
}

QLabel#statusOk { color: #5fbf6c; }
QLabel#statusWarning { color: #d9a441; }
QLabel#statusError { color: #d9534f; }
QLabel#statusMuted { color: #8a8d95; }

QScrollBar:vertical {
    background: #1e1f24;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: #3a3c45;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #4a4c55;
}
"""
