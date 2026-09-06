from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates


class ChartCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(8, 4), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)

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
        self.axes.set_facecolor("#141a22")
        self.figure.patch.set_facecolor("#141a22")
        self.axes.tick_params(colors="#9aa7b8")
        self.axes.grid(color="#2b3645", alpha=0.6)
        for spine in self.axes.spines.values():
            spine.set_color("#2b3645")
        legend = self.axes.legend(facecolor="#1b2430", labelcolor="#e9eef5")
        for text in legend.get_texts():
            text.set_color("#e9eef5")
        self.draw_idle()


class ResultTable(QTableWidget):
    def load_rows(self, rows, headers):
        self.clear()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                self.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.resizeColumnsToContents()


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
            self.failed.emit(str(exc))
