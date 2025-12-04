"""Global style definitions for the PySide6 dashboard."""

from __future__ import annotations

GLOBAL_STYLE = """
QMainWindow {
    background-color: #0f1a2a;
}

QWidget#DashboardContainer {
    background-color: #0f1a2a;
}

QLabel#TitleLabel {
    color: #ffffff;
    font-size: 20px;
    font-weight: 600;
}

QLabel#ValueLabel {
    color: #f7f9fb;
    font-size: 28px;
    font-weight: 700;
}

QLabel#SubtitleLabel {
    color: #8aa0c0;
    font-size: 12px;
}

QFrame#Card {
    background-color: #16243a;
    border: 1px solid #233753;
    border-radius: 12px;
}

QPushButton#PrimaryButton {
    background-color: #3c6ef5;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #4d7ef7;
}

QPushButton#PrimaryButton:pressed {
    background-color: #345fd1;
}

QDateEdit, QComboBox {
    background-color: #16243a;
    color: #e1eaf6;
    border: 1px solid #233753;
    border-radius: 8px;
    padding: 4px 10px;
}

QHeaderView::section {
    background-color: #1d2f4b;
    color: #aab9d4;
    border: none;
    padding: 6px;
    font-weight: 600;
}

QTableWidget {
    background-color: #16243a;
    color: #f0f4ff;
    gridline-color: #1d2f4b;
    border: 1px solid #233753;
    border-radius: 12px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
}

QScrollBar::handle:vertical {
    background: #2a3f5f;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    background: none;
}
"""
