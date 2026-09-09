from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QLabel, QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QHBoxLayout
)
from PyQt5.QtGui import QBrush, QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates
import logging


logger = logging.getLogger(__name__)


class ChartCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(8, 4), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
        self._style_axes()

    def _style_axes(self):
        self.axes.set_facecolor("#141a22")
        self.figure.patch.set_facecolor("#141a22")
        self.axes.tick_params(colors="#9aa7b8")
        self.axes.grid(color="#2b3645", alpha=0.6)
        for spine in self.axes.spines.values():
            spine.set_color("#2b3645")

    def plot(self, frame):
        self.axes.clear()
        dates = mdates.date2num(frame.index.to_pydatetime())
        for date, open_price, high, low, close in zip(dates, frame["Open"], frame["High"], frame["Low"], frame["Close"]):
            rising = close >= open_price
            color = "#58d68d" if rising else "#ed6a5a"
            self.axes.vlines(date, low, high, color=color, linewidth=0.8)
            self.axes.add_patch(Rectangle((date - 0.3, min(open_price, close)), 0.6, max(abs(close - open_price), 0.001), color=color, alpha=0.9))
        for column, color in [("SMA20", "#f5b041"), ("SMA50", "#5dade2")]:
            if column in frame:
                self.axes.plot(frame.index, frame[column], color=color, linewidth=1, label=column)
        self.axes.xaxis_date()
        self._style_axes()
        legend = self.axes.legend(facecolor="#1b2430", labelcolor="#e9eef5")
        for text in legend.get_texts():
            text.set_color("#e9eef5")
        self.draw_idle()


class EmptyStateWidget(QWidget):
    """Reusable empty state widget with icon, title, and subtitle."""
    def __init__(self, icon: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addStretch()
        
        # Icon
        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 40px; color: #3a4a5c; margin-bottom: 8px;")
        layout.addWidget(self.icon_label)
        
        # Title
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #b8c7d9; margin-bottom: 4px;")
        layout.addWidget(self.title_label)
        
        # Subtitle
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("font-size: 12px; color: #7a8897; max-width: 380px;")
        layout.addWidget(self.subtitle_label)
        
        layout.addStretch()

    def set_content(self, icon: str, title: str, subtitle: str):
        self.icon_label.setText(icon)
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)


class ResultTable(QTableWidget):
    def __init__(self, empty_icon: str = "📊", empty_title: str = "Henüz veri yok", empty_subtitle: str = "Listeleri yükle butonuna basarak başlayın", parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setMouseTracking(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.empty_state = EmptyStateWidget(empty_icon, empty_title, empty_subtitle, self.viewport())
        self.empty_state.show()

    def set_empty_state(self, icon: str, title: str, subtitle: str):
        self.empty_state.set_content(icon, title, subtitle)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.empty_state.setGeometry(0, 0, self.viewport().width(), self.viewport().height())

    def load_rows(self, rows, headers, color_columns=()):
        self.clear()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if column_index in color_columns:
                    try:
                        numeric_value = float(str(value).replace("%", "").replace(",", "."))
                    except ValueError:
                        numeric_value = 0
                    if numeric_value:
                        color = QColor("#58d68d" if numeric_value > 0 else "#ed6a5a")
                        color.setAlpha(38)
                        item.setBackground(QBrush(color))
                self.setItem(row_index, column_index, item)
        self.empty_state.setVisible(not rows)
        # Ensure columns stretch to fit container width
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def fill_container(self):
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(34)
        self.setMinimumHeight(145)


class Worker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.succeeded.emit(self.function(*self.args, **self.kwargs))
        except Exception as exc:
            logger.exception("Worker hatasi: %s", self.function)
            self.failed.emit(str(exc))
