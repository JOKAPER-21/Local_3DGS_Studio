"""Qt Style Sheet for the whole application: "Local3DGS Purple
Professional" -- a dark, professional DCC theme built around a single
accent color (#9D00FF), per theme_v01.

One judgment call worth stating: the spec sets text.primary/secondary/
heading/label all to the accent purple. Applied literally to every
label in the app, that would make ordinary sentences and metric values
purple-on-near-black, which hurts readability and isn't really what
"accent color" means in the rest of the spec (status.ready, buttons,
active nav, focus rings). The spec itself draws this same line
elsewhere -- properties.value and console.text are both the light
neutral #D8D8D8, not purple. So here: the accent governs headings,
section labels, sidebar/nav items, active/selected states, buttons, and
borders/focus (exactly as specified) with the light neutral (#D8D8D8)
as the base body/value text color, matching the spec's own
properties.value / console.text choice.
"""

# -- palette (theme_v06_blender_style) ---------------------------------------

# Accent / active state
_ACCENT = "#4C8DFF"
_ACCENT_HOVER = "#6AA1FF"
_ACCENT_PRESSED = "#3268C9"

# Text
_TEXT_PRIMARY = "#F2F2F2"
_TEXT_BODY = "#D6D6D6"
_TEXT_SECONDARY = "#A6A6A6"
_TEXT_MUTED = "#808080"
_TEXT_TIMESTAMP = "#666666"
_TEXT_DISABLED = "#4D4D4D"

# Main backgrounds
_BG_APPLICATION = "#181818"
_BG_SIDEBAR = "#202020"
_BG_WORKSPACE = "#1E1E1E"
_BG_PANEL = "#282828"
_BG_PANEL_SECONDARY = "#303030"
_BG_INPUT = "#222222"
_BG_CONSOLE = "#151515"

# Borders
_BORDER_DEFAULT = "#3A3A3A"
_BORDER_SUBTLE = "#303030"
_BORDER_FOCUS = "#4C8DFF"

# Status
_STATUS_SUCCESS = "#4CAF50"
_STATUS_WARNING = "#E6A23C"
_STATUS_ERROR = "#E05252"
_STATUS_INFO = "#4C9BD8"
_STATUS_INACTIVE = "#666666"

# Disabled controls
_BUTTON_DISABLED_BG = "#292929"
_BUTTON_DISABLED_BORDER = "#363636"

# Sidebar
_SIDEBAR_HOVER_BG = "#2A2A2A"
_SIDEBAR_ACTIVE_BG = "#343434"

_RADIUS = 5

DARK_STYLESHEET = f"""
QWidget {{
    background-color: {_BG_APPLICATION};
    color: {_TEXT_BODY};
    font-family: "Segoe UI", sans-serif;
    font-size: 10.5pt;
}}

QMainWindow, QDialog {{
    background-color: {_BG_APPLICATION};
}}

/* Ordinary text elements (labels, headings, status text) must never
   paint their own background -- they sit directly on whatever
   container (window, panel) is beneath them. Cards, buttons, and
   input fields set their own backgrounds below and are unaffected. */
QLabel {{
    background: transparent;
}}

QLabel#pageTitle {{
    font-size: 16pt;
    font-weight: 600;
    color: {_ACCENT};
    padding: 4px 0 12px 0;
}}

QLabel#sectionLabel {{
    font-weight: 600;
    color: {_ACCENT};
    padding-top: 6px;
}}

QLabel#propertiesHeader {{
    font-weight: 600;
    font-size: 9pt;
    letter-spacing: 0.5px;
    color: {_ACCENT};
    padding: 4px 0 8px 0;
}}

QFrame#card {{
    background-color: {_BG_PANEL};
    border-radius: {_RADIUS}px;
    border: 1px solid {_BORDER_DEFAULT};
}}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {_BG_INPUT};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: {_RADIUS}px;
    padding: 6px;
    color: {_TEXT_BODY};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {_ACCENT};
}}

QPushButton {{
    background-color: {_ACCENT};
    color: #ffffff;
    border: 1px solid {_ACCENT};
    border-radius: {_RADIUS}px;
    padding: 6px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {_ACCENT_HOVER};
    border-color: {_ACCENT_HOVER};
}}

QPushButton:pressed {{
    background-color: {_ACCENT_PRESSED};
    border-color: {_ACCENT_PRESSED};
}}

QPushButton:disabled {{
    background-color: {_BUTTON_DISABLED_BG};
    color: {_TEXT_DISABLED};
    border: 1px solid {_BUTTON_DISABLED_BORDER};
}}

QPushButton#secondaryButton {{
    background-color: {_BG_PANEL_SECONDARY};
    color: {_ACCENT};
    border: 1px solid {_BORDER_DEFAULT};
}}

QPushButton#secondaryButton:hover {{
    background-color: {_SIDEBAR_HOVER_BG};
}}

QPlainTextEdit#logView {{
    background-color: {_BG_CONSOLE};
    color: {_TEXT_BODY};
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    font-size: 12px;
    border: 1px solid {_BORDER_DEFAULT};
}}

QLabel#statusOk {{ color: {_ACCENT}; }}
QLabel#statusWarning {{ color: {_STATUS_WARNING}; }}
QLabel#statusError {{ color: {_STATUS_ERROR}; }}
QLabel#statusMuted {{ color: {_STATUS_INACTIVE}; }}

QScrollBar:vertical {{
    background: {_BG_APPLICATION};
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {_BORDER_DEFAULT};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_ACCENT};
}}

/* -- Application shell: top bar, workflow sidebar, splitter, console,
   properties panels. No QMenuBar/QMenu rules -- the v04 redesign has
   no traditional main menu. */

QWidget#topBar {{
    background-color: {_BG_SIDEBAR};
    border-bottom: 1px solid {_BORDER_DEFAULT};
}}

QLabel#topBarLabel {{
    font-weight: 600;
    color: {_ACCENT};
    font-size: 10pt;
}}

QListWidget#workflowSidebar {{
    background-color: {_BG_SIDEBAR};
    border: none;
    border-right: 1px solid {_BORDER_DEFAULT};
    padding-top: 6px;
    outline: 0;
    font-size: 10pt;
    color: {_TEXT_BODY};
}}

QListWidget#workflowSidebar::item {{
    padding: 8px 12px;
    border-radius: {_RADIUS - 2}px;
    margin: 1px 6px;
}}

QListWidget#workflowSidebar::item:selected {{
    background-color: {_SIDEBAR_ACTIVE_BG};
    color: {_ACCENT};
}}

QListWidget#workflowSidebar::item:hover:!selected {{
    background-color: {_SIDEBAR_HOVER_BG};
}}

QSplitter::handle {{
    background-color: {_BG_APPLICATION};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

QSplitter::handle:hover {{
    background-color: {_ACCENT};
}}

QWidget#consoleHeader {{
    background-color: {_BG_PANEL};
    border-top: 1px solid {_BORDER_DEFAULT};
}}

QLabel#consoleHeaderLabel {{
    font-weight: 600;
    color: {_ACCENT};
    font-size: 9pt;
    letter-spacing: 0.5px;
}}

QPushButton#consoleToggleButton {{
    background: transparent;
    color: {_ACCENT};
    border: none;
    border-radius: 2px;
    padding: 2px 8px;
    font-weight: 600;
}}

QPushButton#consoleToggleButton:hover {{
    background-color: {_SIDEBAR_HOVER_BG};
}}

QStatusBar {{
    background-color: {_BG_SIDEBAR};
    border-top: 1px solid {_BORDER_DEFAULT};
    color: {_TEXT_MUTED};
    font-size: 9pt;
}}

QStatusBar QLabel {{
    padding: 2px 10px;
    color: {_TEXT_MUTED};
}}

QStatusBar::item {{
    border: none;
}}

QTabWidget::pane {{
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: {_RADIUS}px;
    top: -1px;
}}

QTabBar::tab {{
    background: {_BG_PANEL_SECONDARY};
    color: {_TEXT_MUTED};
    padding: 6px 14px;
    border: 1px solid {_BORDER_SUBTLE};
    border-bottom: none;
    border-top-left-radius: {_RADIUS}px;
    border-top-right-radius: {_RADIUS}px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background: {_BG_PANEL};
    color: {_ACCENT};
    border-color: {_BORDER_DEFAULT};
}}

QTabBar::tab:hover:!selected {{
    color: {_TEXT_BODY};
}}
"""
