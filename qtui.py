"""DSM(Synology) 风格 Qt 组件与名单窗口"""
from __future__ import annotations

import os

from PyQt5.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QIcon, QIntValidator,
                         QPainter, QPainterPath, QPen, QPixmap)
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication, QCheckBox, QComboBox,
                             QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox,
                             QPushButton, QSizePolicy, QStackedWidget, QTabBar,
                             QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
                             QWidget)

import core
import version

WHITE = "#ffffff"
PAGE = "#f2f4f7"
TEXT = "#262b33"
MUTED = "#6d7683"
SUBTLE = "#8b95a1"
BLUE = "#1f6fd0"
BLUE_HOVER = "#1659ab"
LINE = "#e3e6eb"
FIELD_BORDER = "#ccd2da"
BTN_BG = "#f2f4f7"
BTN_HOVER = "#e7ebf0"
BTN_BORDER = "#d8dde3"

FAMILY = "Microsoft YaHei UI"


def app_font(size=9.0, bold=False) -> QFont:
    font = QFont(FAMILY)
    font.setPointSizeF(size)
    font.setBold(bold)
    return font


def stylesheet() -> str:
    return f"""
    QWidget {{ color: {TEXT}; font-family: "{FAMILY}"; font-size: 9pt; }}
    QMainWindow, QDialog {{ background-color: {WHITE}; }}
    QWidget#page {{ background-color: {PAGE}; }}
    QWidget#content {{ background-color: {WHITE}; }}
    QWidget#scrollViewport {{ background-color: {WHITE}; }}

    QFrame#card {{ background-color: {WHITE}; border: 1px solid {LINE}; }}
    QFrame#dialog {{ background-color: {WHITE}; border: 1px solid #cbd1d9; }}
    QFrame#banner {{ background-color: #fff6e3; border: none; border-bottom: 1px solid #f1e2bf; }}
    QFrame#dash {{ border: none; border-top: 1px dashed #dfe3e8; background-color: transparent; }}
    QFrame#hline {{ background-color: {LINE}; border: none; }}

    QLabel {{ background: transparent; }}
    QLabel#h1 {{ color: {BLUE}; font-size: 11pt; font-weight: 700; }}
    QLabel#appTitle {{ color: {TEXT}; font-size: 14pt; font-weight: 700; }}
    QLabel#muted {{ color: {MUTED}; }}
    QLabel#subtle {{ color: {SUBTLE}; font-size: 8.5pt; }}
    QLabel#banner {{ color: #8a5a00; font-size: 8.5pt; }}
    QLabel#count {{ color: {SUBTLE}; font-size: 8.5pt; }}
    QLabel#empty {{ color: #9aa3ae; background: transparent; }}

    QLineEdit {{ background-color: {WHITE}; border: 1px solid {FIELD_BORDER}; border-radius: 3px;
                padding: 4px 7px; selection-background-color: #cfe3fb; }}
    QLineEdit:focus {{ border: 1px solid {BLUE}; }}
    QLineEdit:disabled {{ background: #f7f8fa; color: {SUBTLE}; }}

    QComboBox {{ background-color: {WHITE}; border: 1px solid {FIELD_BORDER}; border-radius: 3px;
                padding: 4px 8px; }}
    QComboBox:focus {{ border: 1px solid {BLUE}; }}
    QComboBox:disabled {{ background-color: #f7f8fa; color: {SUBTLE}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{ border: 1px solid {FIELD_BORDER}; background-color: {WHITE};
                selection-background-color: #e8f1fd; selection-color: #1a5cb8; outline: none; }}

    QPushButton {{ background-color: {BTN_BG}; border: 1px solid {BTN_BORDER}; border-radius: 3px;
                padding: 5px 14px; color: {TEXT}; }}
    QPushButton:hover {{ background-color: {BTN_HOVER}; }}
    QPushButton:pressed {{ background-color: #dde2e9; }}
    QPushButton:disabled {{ color: #a8b0bb; background-color: #f7f8fa; border-color: #e8ebef; }}
    QPushButton#primary {{ background-color: {BLUE}; border: 1px solid {BLUE}; color: #ffffff;
                padding: 5px 24px; }}
    QPushButton#primary:hover {{ background-color: {BLUE_HOVER}; border-color: {BLUE_HOVER}; }}
    QPushButton#link {{ background-color: transparent; border: none; color: {BLUE};
                padding: 2px 0px; }}
    QPushButton#link:hover {{ color: {BLUE_HOVER}; }}

    QToolButton {{ background-color: {BTN_BG}; border: 1px solid {BTN_BORDER}; border-radius: 3px;
                padding: 4px 10px; color: {TEXT}; }}
    QToolButton:hover {{ background-color: {BTN_HOVER}; }}
    QToolButton#flat {{ background-color: transparent; border: none; padding: 2px 6px;
                color: {SUBTLE}; }}
    QToolButton#flat:hover {{ color: {BLUE}; }}
    QToolButton::menu-indicator {{ image: none; width: 0px; }}

    QTabBar {{ background: transparent; }}
    QTabBar::tab {{ background: transparent; color: {MUTED}; font-weight: 700;
                padding: 6px 0px 9px 0px; margin-right: 28px; border: none;
                border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {BLUE}; border-bottom: 2px solid {BLUE}; }}
    QTabBar::tab:hover {{ color: {BLUE}; }}

    QTableWidget {{ background: {WHITE}; border: none; outline: none;
                selection-background-color: #e8f1fd; selection-color: #1a5cb8; }}
    QTableWidget::item {{ padding-left: 8px; border: none; }}
    QTableWidget::item:selected {{ background: #e8f1fd; color: #1a5cb8; }}
    QHeaderView {{ background: #f8f9fb; }}
    QHeaderView::section {{ background: #f8f9fb; color: #6b7480; border: none;
                border-bottom: 1px solid #eceff3; padding: 8px 8px; font-weight: normal; }}
    QTableCornerButton::section {{ background: #f8f9fb; border: none; }}

    QScrollArea {{ border: none; background: {WHITE}; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0px; }}
    QScrollBar::handle:vertical {{ background-color: #d7dce3; border-radius: 5px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background-color: #c3cad3; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ height: 10px; background: transparent; }}
    QScrollBar::handle:horizontal {{ background: #dfe3e8; border-radius: 5px; min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

    QPlainTextEdit {{ background: #fbfcfd; border: 1px solid {LINE}; border-radius: 3px;
                color: #3a434f; font-family: Consolas, "Microsoft YaHei UI"; font-size: 9pt;
                padding: 4px; selection-background-color: #cfe3fb; }}
    QMenu {{ background: {WHITE}; border: 1px solid {FIELD_BORDER}; padding: 4px; }}
    QMenu::item {{ padding: 6px 20px 6px 14px; }}
    QMenu::item:selected {{ background: #e8f1fd; color: #1a5cb8; }}
    """


# ---------------------------------------------------------------- 基础组件
class CheckBox(QCheckBox):
    """DSM 风格：未选中为浅灰方框，选中为蓝色对勾。"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(20 + 6 + metrics.horizontalAdvance(self.text()),
                     max(20, metrics.height()))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        enabled = self.isEnabled()
        top = (self.height() - 18) / 2
        if self.isChecked():
            pen = QPen(QColor(BLUE if enabled else "#a9c3e4"))
            pen.setWidth(2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(3, top + 9), QPointF(7, top + 13))
            painter.drawLine(QPointF(7, top + 13), QPointF(15, top + 3))
        else:
            painter.setPen(QPen(QColor("#c9d0d9" if enabled else "#dfe3e9"), 1))
            painter.drawRect(QRectF(2.5, top + 2.5, 13, 13))
        painter.setPen(QColor(TEXT if enabled else SUBTLE))
        painter.setFont(self.font())
        painter.drawText(QRect(24, 0, self.width() - 24, self.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Chevron(QWidget):
    def __init__(self, expanded=True, parent=None):
        super().__init__(parent)
        self.expanded = expanded
        self.setFixedSize(14, 14)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_expanded(self, flag: bool):
        self.expanded = bool(flag)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(BLUE))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        if self.expanded:
            painter.drawLine(2, 9, 7, 3)
            painter.drawLine(7, 3, 12, 9)
        else:
            painter.drawLine(2, 4, 7, 10)
            painter.drawLine(7, 10, 12, 4)


class ClickableHeader(QWidget):
    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Section(QWidget):
    """可折叠的设置分组。"""

    def __init__(self, title: str, expanded=True, parent=None):
        super().__init__(parent)
        self.expanded = bool(expanded)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.header = ClickableHeader()
        self.header.setCursor(Qt.PointingHandCursor)
        head_layout = QHBoxLayout(self.header)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(7)
        self.chevron = Chevron(self.expanded)
        head_layout.addWidget(self.chevron)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("h1")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        head_layout.addWidget(self.title_label)
        head_layout.addStretch(1)
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)

        dash = QFrame()
        dash.setObjectName("dash")
        dash.setFixedHeight(1)
        layout.addWidget(dash)
        layout.addSpacing(4)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        layout.addWidget(self.body)
        self.body.setVisible(self.expanded)

    def toggle(self):
        self.expanded = not self.expanded
        self.chevron.set_expanded(self.expanded)
        self.body.setVisible(self.expanded)

    def set_expanded(self, flag: bool):
        flag = bool(flag)
        if flag == self.expanded:
            return
        self.expanded = flag
        self.chevron.set_expanded(flag)
        self.body.setVisible(flag)


class SearchEdit(QLineEdit):
    def __init__(self, placeholder="搜索", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(250)
        self.setMaximumWidth(280)
        self.setFixedHeight(34)
        icon = QIcon(make_magnifier_pixmap())
        self.addAction(icon, QLineEdit.LeadingPosition)
        self.setTextMargins(2, 0, 0, 0)


def make_magnifier_pixmap(size=14):
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(scale, scale)
    painter.setPen(QPen(QColor("#8c96a2"), 1.2))
    painter.drawEllipse(QRectF(1.5, 1.5, 8, 8))
    painter.drawLine(QLineF(9, 9, 12.5, 12.5))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def app_icon() -> QIcon:
    """窗口/托盘/任务栏统一图标（优先多尺寸 ICO，回退 PNG 母版）。"""
    candidates = [
        core.resource_path("app_icon.ico"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "app_icon.ico"),
        core.resource_path("app_icon.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return QIcon(path)
    return QIcon(make_shield_pixmap(32))


def make_shield_pixmap(size=30):
    """统一应用图标：所有位置（标题栏/托盘/关于窗口）都取 app_icon.png 母版。"""
    scale = 2
    icon_path = core.resource_path("app_icon.png")
    source = QPixmap(icon_path) if os.path.exists(icon_path) else QPixmap()
    if not source.isNull():
        pixmap = source.scaled(size * scale, size * scale, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
        pixmap.setDevicePixelRatio(scale)
        return pixmap

    # 仅在图标文件缺失时回退到矢量绘制
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(scale, scale)
    path = QPainterPath()
    path.moveTo(15, 2)
    path.lineTo(27, 7.5)
    path.lineTo(27, 17)
    path.lineTo(15, 29)
    path.lineTo(3, 17)
    path.lineTo(3, 7.5)
    path.closeSubpath()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(BLUE))
    painter.drawPath(path)
    pen = QPen(QColor(WHITE))
    pen.setWidth(2.2)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QLineF(9, 15, 13.5, 19.5))
    painter.drawLine(QLineF(13.5, 19.5, 22, 10))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


class EmptyOverlay(QLabel):
    def __init__(self, table: QTableWidget):
        super().__init__(table.viewport())
        self.table = table
        self.setObjectName("empty")
        self.setAlignment(Qt.AlignCenter)
        self.setText("无数据")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        table.viewport().installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            self.setGeometry(0, 0, obj.width(), obj.height())
        return False


def create_table() -> QTableWidget:
    table = QTableWidget(0, 0)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(36)
    table.horizontalHeader().setFixedHeight(38)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    table.horizontalHeader().setHighlightSections(False)
    return table


# ---------------------------------------------------------------- 新增窗口
class AddDialog(QDialog):
    def __init__(self, parent, kind: str, on_submit, default_days: int = 0,
                 follow_text: str = "永久"):
        super().__init__(parent)
        self.kind = kind
        self.on_submit = on_submit
        self.default_days = max(1, int(default_days or 1))
        self.follow_chk = None
        self.setWindowTitle("新增 IP 地址" if kind == "allow" else "新增封锁地址")
        self.setModal(True)
        self.setMinimumWidth(470)
        self.setFont(app_font(9))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel("IP 地址"), 0, 0, Qt.AlignLeft)
        self.addr_edit = QLineEdit()
        self.addr_edit.setMinimumWidth(320)
        grid.addWidget(self.addr_edit, 0, 1)

        grid.addWidget(QLabel("备注"), 1, 0, Qt.AlignLeft)
        self.note_edit = QLineEdit()
        grid.addWidget(self.note_edit, 1, 1)

        self.permanent_chk = None
        self.duration_edit = None
        self.duration_unit = None
        if kind == "block":
            grid.addWidget(QLabel("封锁时长（天）"), 2, 0, Qt.AlignLeft)
            self.duration_edit = QLineEdit()
            self.duration_edit.setValidator(QIntValidator(1, 3650, self))
            self.duration_edit.setText(str(self.default_days))
            grid.addWidget(self.duration_edit, 2, 1)

        layout.addLayout(grid)

        if kind == "block":
            self.permanent_chk = CheckBox("永久封锁")
            self.permanent_chk.setChecked(True)
            self.permanent_chk.stateChanged.connect(lambda _s: self._sync_duration())
            layout.addWidget(self.permanent_chk)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self._submit)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addSpacing(6)
        layout.addLayout(buttons)

        self.addr_edit.setFocus()
        self._sync_duration()

    def _sync_duration(self):
        if self.duration_edit is None:
            return
        self.duration_edit.setEnabled(not self.permanent_chk.isChecked())

    def _submit(self):
        try:
            addr = core.normalize_addr(self.addr_edit.text())
        except core.AddrError as exc:
            QMessageBox.warning(self, "地址无效", str(exc))
            return
        minutes = None
        if self.duration_edit is not None and not self.permanent_chk.isChecked():
            raw = self.duration_edit.text().strip()
            value = int(raw) if raw else 0
            if value > 0:
                minutes = value * 1440
        ok, msg = self.on_submit(self.kind, addr, self.note_edit.text().strip(), minutes)
        if not ok:
            QMessageBox.warning(self, "操作未完成", msg or "添加失败")
            return
        self.accept()


# ---------------------------------------------------------------- 名单窗口
class TitleBar(QWidget):
    """无边框窗口的自定义标题栏，支持拖动。"""

    def __init__(self, window: QWidget):
        super().__init__()
        self._window = window
        self._offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._offset = event.globalPos() - self._window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._offset is not None and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPos() - self._offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._offset = None
        super().mouseReleaseEvent(event)


class ListWindow(QDialog):
    """允许 / 封锁名单：新增、删除、导出、搜索。"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.kind = "allow"
        self.setWindowTitle("允许 / 封锁名单")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(900, 620)
        self.setMinimumSize(800, 520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setObjectName("dialog")
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())
        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        layout.addWidget(line)

        tab_row = QWidget()
        tab_layout = QVBoxLayout(tab_row)
        tab_layout.setContentsMargins(26, 12, 26, 0)
        tab_layout.setSpacing(0)
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.addTab("允许名单")
        self.tabs.addTab("封锁名单")
        self.tabs.currentChanged.connect(self._switch_tab)
        tab_layout.addWidget(self.tabs)
        layout.addWidget(tab_row)
        tab_line = QFrame()
        tab_line.setObjectName("hline")
        tab_line.setFixedHeight(1)
        layout.addWidget(tab_line)

        layout.addWidget(self._build_toolbar())

        self.stack = QStackedWidget()
        table_container = QWidget()
        table_layout = QHBoxLayout(table_container)
        table_layout.setContentsMargins(26, 0, 26, 0)
        table_layout.setSpacing(0)
        self.table_allow = create_table()
        self.table_block = create_table()
        self.tables = {"allow": self.table_allow, "block": self.table_block}
        for table in self.tables.values():
            table.itemSelectionChanged.connect(self._update_buttons)
            table.setColumnCount(0)
        self.stack.addWidget(self.table_allow)
        self.stack.addWidget(self.table_block)
        table_layout.addWidget(self.stack)
        layout.addWidget(table_container, 1)

        layout.addWidget(self._build_footer())
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.refresh()
        self.center_on(parent)

    # ---- 头部 ----
    def _build_header(self) -> QWidget:
        header = TitleBar(self)
        header.setFixedHeight(56)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 0, 16, 0)
        title = QLabel("允许 / 封锁名单")
        title.setFont(app_font(11, True))
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(title)
        layout.addStretch(1)
        close = QToolButton()
        close.setText("✕")
        close.setObjectName("flat")
        close.setFont(app_font(11))
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.close)
        layout.addWidget(close)
        return header

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    # ---- 工具栏 ----
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(26, 14, 26, 14)
        layout.setSpacing(8)

        self.btn_add = QToolButton()
        self.btn_add.setText("新增 ▾")
        self.btn_add.setPopupMode(QToolButton.InstantPopup)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setFixedHeight(34)
        menu = QMenu(self.btn_add)
        menu.addAction("IP 地址 / 网段 / 范围", self._add_entry)
        menu.addAction("从文本批量导入", self._import_file)
        self.btn_add.setMenu(menu)
        layout.addWidget(self.btn_add)

        self.btn_del = QPushButton("删除")
        self.btn_del.clicked.connect(self._delete_selected)
        self.btn_del.setFixedHeight(34)
        layout.addWidget(self.btn_del)

        self.btn_export = QPushButton("导出")
        self.btn_export.clicked.connect(self._export)
        self.btn_export.setFixedHeight(34)
        layout.addWidget(self.btn_export)

        layout.addStretch(1)
        self.search = SearchEdit()
        layout.addWidget(self.search)
        return bar

    # ---- 底部 ----
    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(26, 12, 22, 14)
        self.count_label = QLabel("共 0 条")
        self.count_label.setObjectName("count")
        layout.addWidget(self.count_label)
        layout.addStretch(1)

        refresh = QToolButton()
        refresh.setText("↻")
        refresh.setObjectName("flat")
        refresh.setFont(app_font(12))
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.setToolTip("刷新列表")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        layout.addSpacing(10)

        close = QPushButton("关闭")
        close.setMinimumWidth(88)
        close.clicked.connect(self.close)
        layout.addWidget(close)
        return footer

    # ---- 数据 ----
    def _switch_tab(self, index):
        self.kind = "allow" if index == 0 else "block"
        self.stack.setCurrentIndex(index)
        self.refresh()

    def _columns(self):
        if self.kind == "allow":
            return (("addr", "允许的 IP 地址", 300, QHeaderView.Fixed),
                    ("note", "备注", 320, QHeaderView.Stretch),
                    ("added", "添加时间", 190, QHeaderView.Fixed))
        return (("addr", "封锁 IP", 150, QHeaderView.Fixed),
                ("note", "原因", 260, QHeaderView.Stretch),
                ("added", "封锁时间", 168, QHeaderView.Fixed),
                ("expires", "到期时间", 168, QHeaderView.Fixed),
                ("source", "来源", 88, QHeaderView.Fixed))

    def refresh(self):
        table = self.tables[self.kind]
        columns = self._columns()
        keyword = self.search.text().strip().lower()
        rows = self.app.list_rows(self.kind)
        if keyword:
            rows = [r for r in rows if keyword in " ".join(str(v).lower() for v in r.values())]

        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([c[1] for c in columns])
        header = table.horizontalHeader()
        for index, (_key, _title, width, mode) in enumerate(columns):
            header.setSectionResizeMode(index, mode)
            if mode == QHeaderView.Fixed:
                table.setColumnWidth(index, width)
        table.setRowCount(0)
        for row in rows:
            r = table.rowCount()
            table.insertRow(r)
            for index, (key, _title, _w, _m) in enumerate(columns):
                text = str(row.get(key, ""))
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, row["addr"])
                if key == "note" and text:
                    item.setToolTip(text)
                table.setItem(r, index, item)
        table.clearSelection()

        self.count_label.setText("共 %d 条" % len(rows) if rows else "无数据")
        self._update_buttons()

    def _update_buttons(self):
        table = self.tables[self.kind]
        selected = bool(table.selectedItems())
        self.btn_del.setEnabled(selected)
        self.btn_export.setEnabled(table.rowCount() > 0)

    def _selected_addr(self):
        table = self.tables[self.kind]
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    # ---- 操作 ----
    def _add_entry(self):
        AddDialog(self, self.kind, self.app.submit_new_entry,
                  self.app.auto_expiry_days(), self.app.auto_expiry_text()).exec_()
        self.refresh()

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择包含 IP 的文本文件", "",
                                              "文本文件 (*.txt *.csv);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", str(exc))
            return
        added, failed = self.app.import_entries(self.kind, lines)
        self.refresh()
        QMessageBox.information(self, "导入完成", "成功导入 %d 条，失败 %d 条" % (added, failed))

    def _delete_selected(self):
        addr = self._selected_addr()
        if not addr:
            return
        name = "允许名单" if self.kind == "allow" else "封锁名单"
        answer = QMessageBox.question(self, "确认删除", "确定要从%s移除 %s 吗？" % (name, addr))
        if answer != QMessageBox.Yes:
            return
        self.app.remove_entry(self.kind, addr)
        self.refresh()

    def _export(self):
        table = self.tables[self.kind]
        if table.rowCount() == 0:
            QMessageBox.information(self, "导出", "当前列表没有数据")
            return
        default = "允许名单.csv" if self.kind == "allow" else "封锁名单.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出名单", default, "CSV 文件 (*.csv)")
        if not path:
            return
        ok, msg = self.app.export_list(self.kind, path)
        if ok:
            QMessageBox.information(self, "导出完成", "已保存到：\n%s" % path)
        else:
            QMessageBox.warning(self, "导出失败", msg)

    def closeEvent(self, event):
        self.app.list_window = None
        super().closeEvent(event)

    def center_on(self, parent):
        geometry = self.frameGeometry()
        if parent is not None:
            geometry.moveCenter(parent.frameGeometry().center())
        self.move(geometry.topLeft())


class AboutDialog(QDialog):
    """关于本程序（仅从托盘菜单打开，不改动主界面）。"""

    def __init__(self, parent, year: int):
        super().__init__(parent)
        self.setWindowTitle("关于本程序 · v%s" % version.APP_VERSION)
        self.setObjectName("about")
        self.setModal(True)
        self.setFixedWidth(470)
        self.setFont(app_font(9))
        self.setStyleSheet("QDialog#about{background-color:%s;}" % WHITE)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        icon = QLabel()
        icon.setPixmap(make_shield_pixmap(46))
        icon.setFixedSize(46, 46)
        icon.setAlignment(Qt.AlignCenter)
        root.addWidget(icon, 0, Qt.AlignHCenter)
        root.addSpacing(12)

        self.title_label = QLabel("IP 自动封锁工具")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(app_font(14, True))
        self.title_label.setStyleSheet("color:%s;" % TEXT)
        root.addWidget(self.title_label)
        root.addSpacing(6)

        self.version_label = QLabel("版本 v%s" % version.APP_VERSION)
        self.version_label.setAlignment(Qt.AlignCenter)
        self.version_label.setStyleSheet("color:%s;" % MUTED)
        root.addWidget(self.version_label)
        root.addSpacing(8)

        span = "2025-%d" % year if year > 2025 else "2025"
        self.copyright_label = QLabel("Copyright © %s GK.2" % span)
        self.copyright_label.setAlignment(Qt.AlignCenter)
        self.copyright_label.setStyleSheet("color:%s;" % MUTED)
        root.addWidget(self.copyright_label)
        root.addSpacing(14)

        self.warn_label = QLabel("禁止用于商业项目、批量部署、二次打包分发。 禁止逆向、篡改程序。")
        self.warn_label.setAlignment(Qt.AlignCenter)
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet("color:%s;" % TEXT)
        root.addWidget(self.warn_label)
        root.addSpacing(10)

        self.rights_label = QLabel("GK.2 All rights reserved. GK.2保留所有权利.")
        self.rights_label.setAlignment(Qt.AlignCenter)
        self.rights_label.setWordWrap(True)
        self.rights_label.setStyleSheet("color:%s;" % SUBTLE)
        root.addWidget(self.rights_label)
        root.addSpacing(16)

        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        root.addWidget(line)
        root.addSpacing(12)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("primary")
        close_btn.setMinimumWidth(88)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)
