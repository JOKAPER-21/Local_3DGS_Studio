"""Qt Style Sheet for the whole application: a professional, dark,
DCC-style desktop theme with a single purple accent (#9D00FF), per the
"Professional Desktop Software UI" design prompt.

Corner-radius system (as specified):
    Panel / Card / Dialog (QFrame#card, QPlainTextEdit#logView,
    QTabWidget pane)      10px
    Button / Input / Icon
    button                 8px
    Small control (sidebar
    row, tab)               6px

Color discipline (as specified): normal content is white/light-gray.
Purple is reserved for important actions, active/selected states, focus,
and key status symbols -- not for headings or body text in general. An
earlier pass of this theme made page/section headings purple; that is
corrected here to match this explicit instruction. Purple still marks:
the active sidebar item, primary buttons, focused inputs, the selected
tab, the "ready" status color, and the console's info/command color.

One honest scoping note: Qt's QSS `border-radius` on QMainWindow/QDialog
does not actually round the OS window chrome unless the window is made
frameless (Qt.FramelessWindowHint) with a custom-painted title bar and
its own drag/resize/minimize/maximize handling. That's a much larger,
separate change (a custom window-chrome layer) than a stylesheet, and
this pass does not attempt it -- window *content* (panels, cards,
dialogs' internal frames, buttons, tabs) all get the specified radii,
but the outer window rectangle itself still has the OS's normal corners.
"""

# -- palette ------------------------------------------------------------------
_ACCENT = "#9D00FF"
_ACCENT_HOVER = "#B52CFF"
_ACCENT_PRESSED = "#7800C7"

_TEXT_PRIMARY = "#F2F2F5"     # white/near-white -- normal content
_TEXT_SECONDARY = "#B9BCC7"   # light gray -- supporting text
_TEXT_DISABLED = "#5A5C68"
_TEXT_MUTED = "#8A8FA3"

_BG_APPLICATION = "#0E0F14"
_BG_SIDEBAR = "#11121A"
_BG_PANEL = "#151621"
_BG_PANEL_SECONDARY = "#1B1C29"
_BG_INPUT = "#101119"
_BG_CONSOLE = "#0A0B10"

_BORDER_DEFAULT = "#2A2C3A"
_BORDER_SUBTLE = "#1F212E"

_STATUS_READY = _ACCENT
_STATUS_WARNING = "#FFB000"
_STATUS_ERROR = "#FF3B5C"
_STATUS_SUCCESS = "#3DDC84"
_STATUS_INACTIVE = "#5A5C68"

_BUTTON_DISABLED_BG = "#181922"
_BUTTON_DISABLED_BORDER = "#242530"

_SIDEBAR_HOVER_BG = "#1A1B28"
_SIDEBAR_ACTIVE_BG = "#241539"

# -- corner radius system -------------------------------------------------------
_RADIUS_PANEL = 10   # panels, cards, dialogs, dock/tab panes
_RADIUS_CONTROL = 8  # buttons, inputs, icon buttons
_RADIUS_SMALL = 6    # small controls: sidebar rows, tabs, chips

# -- spacing system (4 / 8 / 12 / 16 / 20 / 24) ---------------------------------
_SP_XS = 4
_SP_SM = 8
_SP_MD = 12
_SP_LG = 16

DARK_STYLESHEET = f"""
QWidget {{
    background-color: {_BG_APPLICATION};
    color: {_TEXT_PRIMARY};
    font-family: "Segoe UI", sans-serif;
    font-size: 10.5pt;
}}

QMainWindow, QDialog {{
    background-color: {_BG_APPLICATION};
}}

/* Ordinary text elements must never paint their own background -- they
   sit directly on whatever container (window, panel) is beneath them.
   Cards, buttons, and input fields set their own backgrounds below and
   are unaffected. */
QLabel {{
    background: transparent;
    color: {_TEXT_PRIMARY};
}}

/* Headings and section labels are white/light-gray, not purple --
   purple communicates interaction and importance, not text hierarchy. */
QLabel#pageTitle {{
    font-size: 16pt;
    font-weight: 600;
    color: {_TEXT_PRIMARY};
    padding: 0 0 {_SP_MD}px 0;
}}

QLabel#sectionLabel {{
    font-weight: 600;
    color: {_TEXT_SECONDARY};
    padding-top: {_SP_XS}px;
}}

QLabel#propertiesHeader {{
    font-weight: 600;
    font-size: 9pt;
    letter-spacing: 0.5px;
    color: {_TEXT_SECONDARY};
    padding: {_SP_XS}px 0 {_SP_SM}px 0;
}}

QFrame#card {{
    background-color: {_BG_PANEL};
    border-radius: {_RADIUS_PANEL}px;
    border: 1px solid {_BORDER_DEFAULT};
}}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {_BG_INPUT};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: {_RADIUS_CONTROL}px;
    padding: {_SP_XS + 2}px {_SP_SM}px;
    color: {_TEXT_PRIMARY};
}}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {_ACCENT};
}}

/* Primary button: purple accent, white text -- important actions. */
QPushButton {{
    background-color: {_ACCENT};
    color: #ffffff;
    border: 1px solid {_ACCENT};
    border-radius: {_RADIUS_CONTROL}px;
    padding: {_SP_XS + 2}px {_SP_MD + 2}px;
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

/* Secondary button: dark neutral, light text, subtle border, purple only
   on hover/active -- supporting actions ("Browse...", "Detect COLMAP",
   "Settings"). */
QPushButton#secondaryButton {{
    background-color: {_BG_PANEL_SECONDARY};
    color: {_TEXT_PRIMARY};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: {_RADIUS_CONTROL}px;
    padding: {_SP_XS + 2}px {_SP_MD + 2}px;
    font-weight: 600;
}}

QPushButton#secondaryButton:hover {{
    background-color: {_SIDEBAR_HOVER_BG};
    border-color: {_ACCENT};
    color: {_ACCENT};
}}

QPushButton#secondaryButton:pressed {{
    background-color: {_SIDEBAR_ACTIVE_BG};
}}

/* Icon buttons: compact square hit area, subtle hover, purple only when
   active (e.g. the console collapse/expand control). */
QPushButton#consoleToggleButton {{
    background: transparent;
    color: {_TEXT_SECONDARY};
    border: none;
    border-radius: {_RADIUS_SMALL}px;
    padding: {_SP_XS}px {_SP_SM}px;
    font-weight: 600;
}}

QPushButton#consoleToggleButton:hover {{
    background-color: {_SIDEBAR_HOVER_BG};
    color: {_ACCENT};
}}

QPlainTextEdit#logView {{
    background-color: {_BG_CONSOLE};
    color: {_TEXT_PRIMARY};
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    font-size: 12px;
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: {_RADIUS_PANEL}px;
}}

/* Status / importance colors: purple = ready/active, amber = warning,
   red = error, muted gray = inactive. Never the default for plain text. */
QLabel#statusOk {{ color: {_STATUS_READY}; font-weight: 600; }}
QLabel#statusWarning {{ color: {_STATUS_WARNING}; font-weight: 600; }}
QLabel#statusError {{ color: {_STATUS_ERROR}; font-weight: 600; }}
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

/* -- Application shell: top bar, workflow sidebar, splitter, console. */

QWidget#topBar {{
    background-color: {_BG_SIDEBAR};
    border-bottom: 1px solid {_BORDER_DEFAULT};
}}

QLabel#topBarLabel {{
    font-weight: 600;
    color: {_TEXT_PRIMARY};
    font-size: 10pt;
}}

QListWidget#workflowSidebar {{
    background-color: {_BG_SIDEBAR};
    border: none;
    border-right: 1px solid {_BORDER_DEFAULT};
    padding-top: {_SP_SM}px;
    outline: 0;
    font-size: 10pt;
    color: {_TEXT_SECONDARY};
}}

/* Sidebar rows are a "small control" (6px radius) -- compact, not a
   full panel radius. */
QListWidget#workflowSidebar::item {{
    padding: {_SP_SM}px {_SP_MD}px;
    border-radius: {_RADIUS_SMALL}px;
    margin: 1px {_SP_SM - 2}px;
}}

/* Active/selected sidebar item: this is exactly where the accent
   belongs -- an active state, not decoration. */
QListWidget#workflowSidebar::item:selected {{
    background-color: {_SIDEBAR_ACTIVE_BG};
    color: {_ACCENT};
    font-weight: 600;
}}

QListWidget#workflowSidebar::item:hover:!selected {{
    background-color: {_SIDEBAR_HOVER_BG};
    color: {_TEXT_PRIMARY};
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
    color: {_TEXT_SECONDARY};
    font-size: 9pt;
    letter-spacing: 0.5px;
}}

QStatusBar {{
    background-color: {_BG_SIDEBAR};
    border-top: 1px solid {_BORDER_DEFAULT};
    color: {_TEXT_MUTED};
    font-size: 9pt;
}}

QStatusBar QLabel {{
    padding: {_SP_XS - 2}px {_SP_MD - 2}px;
    color: {_TEXT_MUTED};
}}

QStatusBar::item {{
    border: none;
}}

/* -- Tabs: clean horizontal system. Active tab uses the purple accent
   with no surrounding border box; inactive tabs are neutral light-gray
   text with no per-tab border, just a thin pane outline beneath the
   whole strip. Compact spacing, no oversized tabs. */

QTabWidget::pane {{
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: {_RADIUS_PANEL}px;
    top: -1px;
}}

QTabBar::tab {{
    background: transparent;
    color: {_TEXT_SECONDARY};
    padding: {_SP_SM}px {_SP_MD}px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: {_SP_XS}px;
    border-top-left-radius: {_RADIUS_SMALL}px;
    border-top-right-radius: {_RADIUS_SMALL}px;
}}

QTabBar::tab:selected {{
    color: {_ACCENT};
    border-bottom: 2px solid {_ACCENT};
    font-weight: 600;
}}

QTabBar::tab:hover:!selected {{
    color: {_TEXT_PRIMARY};
    background: {_SIDEBAR_HOVER_BG};
}}

QTabBar::tab:disabled {{
    color: {_TEXT_DISABLED};
}}
"""
