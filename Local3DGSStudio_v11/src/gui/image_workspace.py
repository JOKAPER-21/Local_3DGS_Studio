"""Image workspace: combines Input and Image Validation into one page,
per the v04 redesign ("Image and Image Validation are one workspace").

Both existing pages (``InputPage``, ``ImageValidationPage``) are reused
completely unchanged -- neither one's logic, signals, or data source
(``InputManager``/``ImageValidator``) is touched. This module only
arranges them: validation (the primary purpose of this workspace) in the
center, input/source details in a right "Properties" column.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class ImageWorkspace(QWidget):
    def __init__(self, input_page: QWidget, image_validation_page: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.input_page = input_page
        self.image_validation_page = image_validation_page

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(image_validation_page, stretch=1)

        properties_column = QWidget()
        properties_layout = QVBoxLayout(properties_column)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel("PROPERTIES")
        header.setObjectName("propertiesHeader")
        properties_layout.addWidget(header)
        properties_layout.addWidget(input_page)
        properties_column.setFixedWidth(300)
        layout.addWidget(properties_column)

    def refresh(self) -> None:
        self.input_page.refresh()
        self.image_validation_page.refresh()
