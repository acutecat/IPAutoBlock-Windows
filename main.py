"""IP 自动封锁 —— 主程序（Qt 界面 + 后台防护引擎）"""
from __future__ import annotations

import csv
import ctypes
import os
import sys
import threading
import time
from datetime import datetime, timedelta

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QIntValidator, QGuiApplication
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication, QCheckBox, QComboBox,
                             QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                             QPushButton, QScrollArea, QSystemTrayIcon, QTableWidgetItem,
                             QToolButton, QVBoxLayout, QWidget)

import core
import qtui
import version
from qtui import (BLUE, CheckBox, PAGE, WHITE, Section, app_font, make_shield_pixmap)


class Bridge(QObject):
    log = pyqtSignal(str)
    changed = pyqtSignal()
    failures = pyqtSignal(object)


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s v%s" % (version.APP_NAME, version.APP_VERSION))
        self.resize(1040, 900)
        self.setMinimumSize(940, 680)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2,
                  max(screen.top(), screen.center().y() - self.height() // 2))
        self.setFont(app_font(9))

        icon_path = core.resource_path("app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(qtui.app_icon())

        self.store = core.Store()
        self.bridge = Bridge()
        self.bridge.log.connect(self.append_log)
        self.bridge.changed.connect(self.on_manager_change)
        self.bridge.failures.connect(self.show_failures)
        self.manager = core.Manager(self.store, log_cb=self.bridge.log.emit)
        self.manager.set_change_callback(lambda: self.bridge.changed.emit())
        self.list_window = None
        self.fail_events = []
        self._evtx_path = ""
        self._closing = False
        self._quit = False
        self.tray = None
        self._tray_tip_shown = False
        self._last_block_notify = 0.0

        self._build_ui()
        self.load_vars()
        self.sync_states()
        self._setup_autosave()
        self.setup_tray()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)
        QTimer.singleShot(250, self.start_engine)

    # ------------------------------------------------------------ 界面
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("page")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(30, 18, 30, 24)
        root.setSpacing(12)

        root.addWidget(self._build_header())

        self.card = QFrame()
        self.card.setObjectName("card")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        if not core.is_admin():
            card_layout.addWidget(self._build_banner())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("content")
        body = QVBoxLayout(content)
        body.setContentsMargins(30, 16, 30, 18)
        body.setSpacing(10)
        self._build_auto_section(body)
        self._build_fail_section(body)
        self._build_dos_section(body)
        self._build_log_section(body)
        body.addStretch(1)
        scroll.setWidget(content)
        scroll.viewport().setObjectName("scrollViewport")
        card_layout.addWidget(scroll, 1)

        card_layout.addWidget(self._build_footer())
        root.addWidget(self.card, 1)

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        shield = QLabel()
        shield.setPixmap(make_shield_pixmap(30))
        shield.setFixedSize(30, 30)
        layout.addWidget(shield)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("IP 自动封锁")
        title.setObjectName("appTitle")
        subtitle = QLabel("监视 Windows 登录失败事件，自动封锁来源 IP 地址")
        subtitle.setObjectName("muted")
        subtitle.setFont(app_font(8.5))
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.role_label = QLabel("管理员" if core.is_admin() else "标准用户")
        self.role_label.setObjectName("subtle")
        layout.addWidget(self.role_label, 0, Qt.AlignBottom)
        return header

    def _build_banner(self) -> QWidget:
        banner = QFrame()
        banner.setObjectName("banner")
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(24, 8, 20, 8)
        label = QLabel("当前未以管理员身份运行：无法读取安全日志，也无法修改防火墙规则。")
        label.setObjectName("banner")
        layout.addWidget(label)
        layout.addStretch(1)
        button = QPushButton("以管理员身份重新启动")
        button.setObjectName("primary")
        button.clicked.connect(self.relaunch_admin)
        layout.addWidget(button)
        return banner

    # ---- 自动封锁 ----
    def _build_auto_section(self, parent):
        section = Section("自动封锁", expanded=True)
        self.auto_section = section
        body = section.body_layout

        desc = QLabel("启用此选项可封锁登录尝试失败次数过多的 IP 地址。"
                      "系统会持续读取 Windows 安全日志中的登录失败事件（4625 / 4771）。")
        desc.setWordWrap(True)
        body.addWidget(desc)
        body.addSpacing(12)

        self.chk_auto = CheckBox("启用自动封锁")
        self.chk_auto.setChecked(True)
        self.chk_auto.stateChanged.connect(lambda _s: self.sync_states())
        body.addWidget(self.chk_auto)

        indent = QWidget()
        indent_layout = QVBoxLayout(indent)
        indent_layout.setContentsMargins(26, 10, 0, 0)
        indent_layout.setSpacing(0)

        line1 = QLabel("如果在下列设置时间内，登录失败次数达到下列设置的次数，"
                       "系统会自动封锁登录者的 IP。")
        line1.setWordWrap(True)
        indent_layout.addWidget(line1)
        indent_layout.addSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, 110)
        self.edit_attempts = self._num_edit(grid, 0, "尝试登录次数", 1, 100000)
        self.edit_minutes = self._num_edit(grid, 1, "几分钟内", 1, 1440)
        grid.setColumnStretch(2, 1)
        indent_layout.addLayout(grid)
        indent_layout.addSpacing(12)

        self.chk_expiry = CheckBox("启动封锁过期")
        self.chk_expiry.setChecked(True)
        self.chk_expiry.stateChanged.connect(lambda _s: self.sync_states())
        indent_layout.addWidget(self.chk_expiry)
        indent_layout.addSpacing(8)

        line2 = QLabel("当启动封锁过期功能时，经过下列时长后，被封锁的 IP 将会被解除封锁。")
        line2.setWordWrap(True)
        indent_layout.addWidget(line2)
        indent_layout.addSpacing(10)

        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(16)
        grid2.setVerticalSpacing(8)
        grid2.setColumnMinimumWidth(0, 110)
        grid2.addWidget(QLabel("封锁时长（天）"), 0, 0, Qt.AlignLeft)
        self.edit_expiry_value = QLineEdit()
        self.edit_expiry_value.setValidator(QIntValidator(1, 3650, self))
        self.edit_expiry_value.setFixedHeight(34)
        grid2.addWidget(self.edit_expiry_value, 0, 1)
        grid2.setColumnStretch(2, 1)
        indent_layout.addLayout(grid2)

        body.addWidget(indent)
        body.addSpacing(16)

        line3 = QLabel("创建并管理允许名单来添加您信任的 IP 地址，"
                       "或创建封锁名单来防止特定 IP 地址登录。")
        line3.setWordWrap(True)
        body.addWidget(line3)
        body.addSpacing(8)

        open_button = QPushButton("允许 / 封锁名单")
        open_button.clicked.connect(self.open_list)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(open_button)
        row.addStretch(1)
        body.addLayout(row)
        parent.addWidget(section)

    # ---- DoS ----
    def _build_dos_section(self, parent):
        section = Section("拒绝服务（DoS）保护", expanded=True)
        self.dos_section = section
        body = section.body_layout

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("网络界面："))
        self.combo_iface = QComboBox()
        self.combo_iface.setMinimumWidth(300)
        self.combo_iface.setMaximumWidth(360)
        self.combo_iface.setFixedHeight(34)
        self.combo_iface.currentIndexChanged.connect(lambda _i: None)
        row.addWidget(self.combo_iface)
        row.addStretch(1)
        body.addLayout(row)
        body.addSpacing(12)

        desc = QLabel("拒绝服务（DoS）保护有助于防止 Internet 上的恶意攻击。")
        desc.setWordWrap(True)
        body.addWidget(desc)
        body.addSpacing(10)

        self.chk_dos = CheckBox("启用 DoS 保护")
        self.chk_dos.stateChanged.connect(lambda _s: self.sync_states())
        body.addWidget(self.chk_dos)

        indent = QWidget()
        indent_layout = QVBoxLayout(indent)
        indent_layout.setContentsMargins(26, 10, 0, 0)
        indent_layout.setSpacing(0)

        line = QLabel("当单个 IP 的并发连接数超过阈值时，临时封锁该 IP。")
        line.setWordWrap(True)
        indent_layout.addWidget(line)
        indent_layout.addSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, 110)
        self.edit_threshold = self._num_edit(grid, 0, "并发连接阈值", 1, 100000)
        self.edit_dos_minutes = self._num_edit(grid, 1, "临时封锁分钟", 1, 1440)
        grid.setColumnStretch(2, 1)
        indent_layout.addLayout(grid)
        body.addWidget(indent)
        body.addSpacing(14)
        parent.addWidget(section)

    # ---- 最近登录失败 ----
    def _build_fail_section(self, parent):
        section = Section("最近的登录失败记录", expanded=False)
        self.fail_section = section
        body = section.body_layout
        body.addSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("时间范围："))
        self.combo_fail = QComboBox()
        self.combo_fail.setFixedHeight(34)
        self.combo_fail.setMinimumWidth(118)
        self.combo_fail.setMaximumWidth(150)
        for label, minutes in (("最近 1 小时", 60), ("最近 6 小时", 360),
                               ("最近 24 小时", 1440), ("最近 7 天", 10080)):
            self.combo_fail.addItem(label, minutes)
        self.combo_fail.setCurrentIndex(2)
        row.addWidget(self.combo_fail)

        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_failures)
        row.addWidget(refresh)
        evtx = QPushButton("导入 .evtx")
        evtx.clicked.connect(self.import_evtx)
        row.addWidget(evtx)
        live = QPushButton("当前日志")
        live.clicked.connect(self.use_live_log)
        row.addWidget(live)
        row.addStretch(1)
        block_btn = QPushButton("封锁选中")
        block_btn.setObjectName("primary")
        block_btn.clicked.connect(self.block_selected_failures)
        row.addWidget(block_btn)
        body.addLayout(row)
        body.addSpacing(10)

        self.fail_table = qtui.create_table()
        self.fail_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.fail_table.setColumnCount(5)
        self.fail_table.setHorizontalHeaderLabels(["时间", "来源 IP", "账户", "事件", "说明"])
        for idx, width in enumerate((150, 190, 170, 80)):
            self.fail_table.setColumnWidth(idx, width)
        self.fail_table.horizontalHeader().setStretchLastSection(True)
        self.fail_table.setMinimumHeight(170)
        self.fail_table.setMaximumHeight(260)
        body.addWidget(self.fail_table)

        self.fail_tip = QLabel("展开本组可读取最近的登录失败事件；读取 Windows 安全日志需要管理员权限。")
        self.fail_tip.setObjectName("subtle")
        self.fail_tip.setWordWrap(True)
        body.addWidget(self.fail_tip)
        parent.addWidget(section)

        self.fail_section.header.clicked.connect(self._on_fail_header)

    def _on_fail_header(self):
        if self.fail_section.expanded:
            QTimer.singleShot(0, self.refresh_failures)

    def refresh_failures(self):
        if not core.is_admin() and not self._evtx_path:
            self.fail_tip.setText("读取失败：当前是标准用户，Windows 安全日志拒绝访问。"
                                  "请点右上角「以管理员身份重新启动」后重试。")
            return
        minutes = int(self.combo_fail.currentData() or 1440)
        path = self._evtx_path
        self.fail_tip.setText("正在读取最近的登录失败事件…")

        def work():
            rc, events, err = core.query_failures(minutes=minutes, path=path)
            self.bridge.failures.emit((events, err, path))

        threading.Thread(target=work, daemon=True).start()

    def show_failures(self, payload):
        events, err, path = payload
        if err:
            self.fail_events = []
            self.fail_table.setRowCount(0)
            self.fail_tip.setText("读取失败：%s（需要管理员权限；也可以导入从其他电脑复制的 .evtx 文件）" % err)
            self.append_log("[警告] 读取登录失败记录失败：%s" % err)
            return
        self.fail_events = events
        rows = events[:300]
        self.fail_table.setRowCount(len(rows))
        for i, ev in enumerate(rows):
            desc = "登录失败" if ev["event_id"] == 4625 else "Kerberos 预认证失败"
            cells = (ev["time"].strftime("%m-%d %H:%M:%S"), ev["ip"], ev.get("user") or "-",
                     str(ev["event_id"]), desc)
            for col, text in enumerate(cells):
                self.fail_table.setItem(i, col, QTableWidgetItem(text))
        source = ("来源：%s" % os.path.basename(path)) if path else "来源：当前安全日志"
        more = "，仅显示最近 300 条" if len(events) > 300 else ""
        self.fail_tip.setText("共 %d 条失败记录 · %s%s" % (len(events), source, more))
        self.append_log("[信息] 读取到最近登录失败记录 %d 条（%s）" % (len(events), source))

    def block_selected_failures(self):
        model = self.fail_table.selectionModel()
        rows = sorted({i.row() for i in model.selectedRows()}) if model else []
        if not rows:
            self.fail_tip.setText("请先在表格中选中要封锁的行（按住 Ctrl 可多选）。")
            return
        ips = []
        for r in rows:
            if 0 <= r < len(self.fail_events):
                ip = self.fail_events[r]["ip"]
                if ip not in ips:
                    ips.append(ip)
        if not core.is_admin():
            self.fail_tip.setText("需要管理员权限才能写入防火墙规则，请先以管理员身份重新启动。")
            return
        added = skipped = 0
        for ip in ips:
            ok, msg = self.manager.block(ip, note="从失败记录加入", source="手动")
            if ok:
                added += 1
            else:
                skipped += 1
                if msg:
                    self.append_log("[信息] %s 未加入封锁：%s" % (ip, msg))
        self.append_log("[封锁] 失败记录中选中 %d 个地址，新增 %d 个，跳过 %d 个" % (len(ips), added, skipped))
        self.fail_tip.setText("已处理 %d 个地址：新增封锁 %d 个，跳过 %d 个。" % (len(ips), added, skipped))

    def import_evtx(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择事件日志文件", "",
                                              "Windows 事件日志 (*.evtx);;所有文件 (*)")
        if not path:
            return
        self._evtx_path = path
        self.fail_section.set_expanded(True)
        self.refresh_failures()

    def use_live_log(self):
        self._evtx_path = ""
        self.fail_section.set_expanded(True)
        self.refresh_failures()

    # ---- 日志 ----
    def _build_log_section(self, parent):
        section = Section("运行日志", expanded=False)
        self.log_section = section
        body = section.body_layout
        body.addSpacing(10)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        clear = QPushButton("清空")
        clear.clicked.connect(self.clear_log)
        folder = QPushButton("打开日志目录")
        folder.clicked.connect(self.open_log_dir)
        tools.addWidget(clear)
        tools.addWidget(folder)
        tools.addStretch(1)
        body.addLayout(tools)
        body.addSpacing(8)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(600)
        self.log_edit.setMinimumHeight(170)
        self.log_edit.setFont(QFont("Consolas", 9))
        body.addWidget(self.log_edit, 1)
        parent.addWidget(section)

    # ---- 底部 ----
    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(24, 10, 24, 12)
        layout.setSpacing(8)

        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        layout.addWidget(line)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.dot.setObjectName("statusDot")
        self.dot.setStyleSheet("background-color:#39b54a;border-radius:5px;")
        status_row.addWidget(self.dot)
        self.status_label = QLabel("正在启动…")
        self.status_label.setObjectName("muted")
        self.status_label.setFont(app_font(8.5))
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        self.chk_autostart = CheckBox("开机自动启动")
        status_row.addWidget(self.chk_autostart)
        layout.addLayout(status_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        log_link = QPushButton("运行日志")
        log_link.setObjectName("link")
        log_link.clicked.connect(self.focus_log)
        button_row.addWidget(log_link)
        button_row.addStretch(1)
        check = QPushButton("立即检查")
        check.clicked.connect(self.check_now)
        reload_btn = QPushButton("重新载入")
        reload_btn.clicked.connect(self.reload_config)
        for btn in (check, reload_btn):
            button_row.addWidget(btn)
        layout.addLayout(button_row)
        return footer

    # ------------------------------------------------------------ 辅助
    def _num_edit(self, grid, row, label, low, high) -> QLineEdit:
        grid.addWidget(QLabel(label + "："), row, 0, Qt.AlignLeft)
        edit = QLineEdit()
        edit.setFixedWidth(300)
        edit.setValidator(QIntValidator(low, high, self))
        grid.addWidget(edit, row, 1, Qt.AlignLeft)
        return edit

    # ------------------------------------------------------------ 系统托盘
    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = qtui.app_icon()
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("%s v%s" % (version.APP_NAME, version.APP_VERSION))
        menu = QMenu()
        act_open = QAction("打开主界面", self)
        act_open.triggered.connect(self.show_main)
        act_check = QAction("立即检查", self)
        act_check.triggered.connect(self.check_now)
        act_log = QAction("打开日志目录", self)
        act_log.triggered.connect(self.open_log_dir)
        act_about = QAction("关于本程序", self)
        act_about.triggered.connect(self.show_about)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_open)
        menu.addAction(act_check)
        menu.addAction(act_log)
        menu.addSeparator()
        menu.addAction(act_about)
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self.on_tray_activated)
        tray.show()
        self.tray = tray
        self.tray_menu = menu
        QApplication.instance().setQuitOnLastWindowClosed(False)

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_main()

    def show_main(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._quit = True
        self.close()

    def show_about(self):
        dlg = qtui.AboutDialog(self, datetime.now().year)
        dlg.exec_()

    def notify_block(self, text: str):
        if self.tray is None:
            return
        now = time.time()
        if now - self._last_block_notify < 2.5:
            return
        self._last_block_notify = now
        self.tray.showMessage("IP 已封锁", text, QSystemTrayIcon.Information, 5000)

    # ------------------------------------------------------------ 数据
    def auto_expiry_minutes(self) -> int:
        """自动解封设置（分钟）；0 表示永久。"""
        if not self.store.cfg["auto"].get("expiry", True):
            return 0
        return max(0, int(self.store.cfg["auto"].get("days") or 0)) * 1440

    def auto_expiry_days(self) -> int:
        return max(0, int(self.store.cfg["auto"].get("days") or 0))

    def auto_expiry_text(self) -> str:
        minutes = self.auto_expiry_minutes()
        return core.human_duration(minutes) if minutes else "永久（未启用封锁过期）"

    def load_vars(self):
        cfg = self.store.cfg
        auto, dos = cfg["auto"], cfg["dos"]
        self.chk_auto.setChecked(bool(auto.get("enabled", True)))
        self.edit_attempts.setText(str(auto.get("attempts", 10)))
        self.edit_minutes.setText(str(auto.get("minutes", 5)))
        self.chk_expiry.setChecked(bool(auto.get("expiry", True)))
        raw_days = auto.get("days")
        if raw_days is None:
            old_minutes = int(auto.get("expiry_minutes") or 1440)
            raw_days = max(1, (old_minutes + 1439) // 1440)
        self.edit_expiry_value.setText(str(max(1, int(raw_days or 1))))
        self.chk_dos.setChecked(bool(dos.get("enabled", False)))
        self.edit_threshold.setText(str(dos.get("threshold", 100)))
        self.edit_dos_minutes.setText(str(dos.get("block_minutes", 30)))
        self.chk_autostart.setChecked(bool(cfg.get("autostart", False)))
        self.load_ifaces(dos.get("interface") or "")

    def load_ifaces(self, current: str):
        labels = ["全部网络接口"]
        rc, out = core.run_hidden([
            core.system_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command",
            "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
            "ForEach-Object { \"$($_.InterfaceAlias)|$($_.IPAddress)\" }",
        ], timeout=45)
        for line in out.splitlines():
            if "|" not in line:
                continue
            alias, ip = line.split("|", 1)
            alias, ip = alias.strip(), ip.strip()
            if ip.startswith("127.") or ip.startswith("169.254"):
                continue
            labels.append("%s (%s)" % (alias, ip))
        self.combo_iface.clear()
        self.combo_iface.addItems(labels)
        if current and current not in labels:
            self.combo_iface.addItem(current)
        self.combo_iface.setCurrentText(current or "全部网络接口")

    def sync_states(self):
        auto_on = self.chk_auto.isChecked()
        self.edit_attempts.setEnabled(auto_on)
        self.edit_minutes.setEnabled(auto_on)
        self.chk_expiry.setEnabled(auto_on)
        expiry_on = auto_on and self.chk_expiry.isChecked()
        self.edit_expiry_value.setEnabled(expiry_on)

        dos_on = self.chk_dos.isChecked()
        self.combo_iface.setEnabled(dos_on)
        self.edit_threshold.setEnabled(dos_on)
        self.edit_dos_minutes.setEnabled(dos_on)
        self.update_status()

    def _setup_autosave(self):
        """设置项改动即保存，避免只改界面、忘记点“应用”。"""
        for widget in (self.chk_auto, self.chk_expiry, self.chk_dos, self.chk_autostart):
            widget.stateChanged.connect(lambda *_args: self.autosave_settings())
        for edit in (self.edit_attempts, self.edit_minutes, self.edit_expiry_value,
                     self.edit_threshold, self.edit_dos_minutes):
            edit.editingFinished.connect(self.autosave_settings)
        self.combo_iface.currentIndexChanged.connect(lambda _index: self.autosave_settings())

    def autosave_settings(self):
        if not self._closing:
            self.save_settings(quiet=True)

    # ------------------------------------------------------------ 引擎
    def start_engine(self):
        self.manager.start()
        self.append_log("程序已启动，等待登录失败事件")
        if self.store.load_note:
            self.append_log("[提示] " + self.store.load_note)
        if core.is_admin():
            self.append_log("已获得管理员权限，防火墙控制可用")
            QTimer.singleShot(900, self.refresh_failures)
        else:
            self.append_log("未获得管理员权限，仅可查看，无法封锁 IP")

    def append_log(self, message: str):
        text = "%s  %s" % (core.now_str("%H:%M:%S"), message)
        self.log_edit.appendPlainText(text)
        try:
            core.LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(core.LOG_DIR / "app.log", "a", encoding="utf-8") as fh:
                fh.write("%s  %s\n" % (core.now_str(), message))
        except Exception:
            pass
        section = getattr(self, "log_section", None)
        if section is not None and (message.startswith("[警告]") or message.startswith("[错误]")):
            section.set_expanded(True)
        if message.startswith("[封锁]") and "（恢复）" not in message:
            self.notify_block(message[len("[封锁]"):].strip())

    def on_manager_change(self):
        self.update_status()
        if self.list_window is not None:
            self.list_window.refresh()

    def update_status(self):
        cfg = self.store.cfg
        parts = ["自动封锁" + ("运行中" if cfg["auto"].get("enabled") else "已停用")]
        if cfg["dos"].get("enabled"):
            parts.append("DoS 保护运行中")
        parts.append("已封锁 %d 个地址" % len(cfg["block"]))
        if self.manager.last_check:
            parts.append("上次检查 " + self.manager.last_check.strftime("%H:%M:%S"))
        if not core.is_admin():
            parts.append("权限不足")
        self.status_label.setText(" · ".join(parts))
        color = "#39b54a"
        if not core.is_admin():
            color = "#e0a03a"
        elif not cfg["auto"].get("enabled"):
            color = "#9aa3ae"
        self.dot.setStyleSheet("background-color:%s;border-radius:5px;" % color)
        if self.tray is not None:
            tip = "%s v%s · 已封锁 %d 个地址" % (version.APP_NAME, version.APP_VERSION, len(cfg["block"]))
            if not core.is_admin():
                tip += " · 权限不足"
            self.tray.setToolTip(tip)

    # ------------------------------------------------------------ 操作
    def _read_int(self, edit: QLineEdit, label: str, low: int, high: int) -> int:
        text = edit.text().strip()
        if not text.isdigit():
            raise ValueError("%s 请输入 %d-%d 之间的整数" % (label, low, high))
        value = int(text)
        if not low <= value <= high:
            raise ValueError("%s 请输入 %d-%d 之间的整数" % (label, low, high))
        return value

    def apply_settings(self):
        self.save_settings(quiet=False)

    def save_settings(self, quiet: bool) -> bool:
        try:
            attempts = self._read_int(self.edit_attempts, "尝试登录次数", 1, 100000)
            minutes = self._read_int(self.edit_minutes, "几分钟内", 1, 1440)
            expiry_days = self._read_int(self.edit_expiry_value, "封锁时长（天）", 1, 3650)
            threshold = self._read_int(self.edit_threshold, "并发连接阈值", 1, 100000)
            dos_minutes = self._read_int(self.edit_dos_minutes, "临时封锁分钟", 1, 1440)
        except ValueError as exc:
            if not quiet:
                QMessageBox.warning(self, "设置有误", str(exc))
            return False

        new_auto = {
            "enabled": self.chk_auto.isChecked(),
            "attempts": attempts,
            "minutes": minutes,
            "expiry": self.chk_expiry.isChecked(),
            "days": expiry_days,
        }
        new_dos = {
            "enabled": self.chk_dos.isChecked(),
            "interface": self.combo_iface.currentText() if self.chk_dos.isChecked() else "",
            "threshold": threshold,
            "block_minutes": dos_minutes,
        }
        new_autostart = self.chk_autostart.isChecked()

        with self.store.lock:
            previous_autostart = bool(self.store.data.get("autostart"))
            changed = (self.store.data.get("auto") != new_auto
                       or self.store.data.get("dos") != new_dos
                       or previous_autostart != new_autostart)
            if changed:
                self.store.data["auto"] = new_auto
                self.store.data["dos"] = new_dos
                self.store.data["autostart"] = new_autostart
                self.store.save()

        if changed and previous_autostart != new_autostart:
            self.apply_autostart(new_autostart)
        if changed:
            self.manager.watcher.wake.set()
            if not quiet:
                self.append_log("设置已应用：%d 次失败 / %d 分钟，封锁 %s" % (
                    attempts, minutes, "%d 天" % expiry_days
                    if self.chk_expiry.isChecked() else "永久"))
        self.sync_states()
        return True

    def apply_autostart(self, enable: bool):
        ok, msg = core.set_autostart(enable)
        if not ok:
            self.append_log("[警告] 设置开机自启动失败：%s" % msg)
            QMessageBox.warning(self, "开机自启动",
                                "设置失败，请确认以管理员身份运行。\n%s" % msg)

    def reload_config(self):
        self.store.reload()
        self.load_vars()
        self.sync_states()
        if self.list_window is not None:
            self.list_window.refresh()
        self.append_log("已重新载入配置")

    def check_now(self):
        self.manager.watcher.wake.set()
        self.manager.expire_due()
        self.append_log("已触发立即检查")

    def focus_log(self):
        if not self.log_section.expanded:
            self.log_section.toggle()
        self.log_edit.setFocus()

    def clear_log(self):
        self.log_edit.clear()

    def open_log_dir(self):
        try:
            core.LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(core.LOG_DIR))
        except Exception as exc:
            QMessageBox.warning(self, "打开目录失败", str(exc))

    def open_list(self):
        if self.list_window is not None:
            self.list_window.raise_()
            self.list_window.activateWindow()
            return
        self.list_window = qtui.ListWindow(self, self)
        self.list_window.show()

    def relaunch_admin(self):
        if core.relaunch_as_admin():
            self._closing = True
            self.close()
        else:
            QMessageBox.warning(self, "无法提权",
                                "未能以管理员身份重新启动，请手动右键以管理员身份运行。")

    # ------------------------------------------------------------ 名单接口
    def list_rows(self, kind):
        cfg = self.store.cfg
        rows = []
        if kind == "allow":
            for item in cfg["allow"]:
                rows.append({"addr": item.get("addr", ""), "note": item.get("note", ""),
                             "added": item.get("added", "")})
        else:
            for item in cfg["block"]:
                expires = item.get("expires")
                if expires:
                    text = str(expires).replace("T", " ")[:19]
                else:
                    text = "永久"
                rows.append({"addr": item.get("addr", ""),
                             "note": item.get("note", ""),
                             "added": item.get("added", "") or "未知",
                             "expires": text,
                             "source": item.get("source", "手动")})
        return rows

    def submit_new_entry(self, kind, addr, note, minutes):
        if kind == "allow":
            if self.store.find_entry("allow", addr):
                return False, "该地址已在允许名单中"
            if self.store.find_entry("block", addr):
                self.manager.unblock(addr)
            self.store.add_entry("allow", {"addr": addr, "note": note,
                                           "added": core.now_str("%Y-%m-%d %H:%M")})
            self.append_log("[允许] %s 已加入允许名单" % addr)
            return True, ""
        expires = datetime.now() + timedelta(minutes=minutes) if minutes else None
        created, msg = self.manager.block(addr, note=note, source="手动", expires=expires)
        if not created and "已在封锁名单" not in msg:
            return False, msg
        return True, ""

    def remove_entry(self, kind, addr):
        if kind == "allow":
            self.store.remove_entry("allow", addr)
            self.append_log("[允许] %s 已从允许名单移除" % addr)
        else:
            self.manager.unblock(addr)
        return True

    def export_list(self, kind, path):
        rows = self.list_rows(kind)
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                if kind == "allow":
                    writer.writerow(["IP 地址", "备注", "添加时间"])
                    for row in rows:
                        writer.writerow([row["addr"], row["note"], row["added"]])
                else:
                    writer.writerow(["IP 地址", "备注", "封锁时间", "到期时间", "来源"])
                    for row in rows:
                        writer.writerow([row["addr"], row["note"], row.get("added", ""),
                                         row["expires"], row["source"]])
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def import_entries(self, kind, lines):
        added = failed = 0
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.replace("\t", ",").split(",")]
            addr = parts[0]
            note = parts[1] if len(parts) > 1 else ""
            try:
                addr = core.normalize_addr(addr)
            except core.AddrError:
                failed += 1
                continue
            ok, _ = self.submit_new_entry(kind, addr, note, None)
            if ok:
                added += 1
            else:
                failed += 1
        return added, failed

    # ------------------------------------------------------------ 退出
    def closeEvent(self, event):
        # 有托盘时，点关闭按钮只是收进托盘，程序继续在后台监视
        if self.tray is not None and not (self._quit or self._closing):
            event.ignore()
            self.hide()
            if not self._tray_tip_shown:
                self._tray_tip_shown = True
                self.tray.showMessage(
                    "IP 自动封锁",
                    "程序已收进系统托盘，仍在后台监视登录失败事件。\n"
                    "双击托盘图标可重新打开，右键菜单里可以退出。",
                    QSystemTrayIcon.Information, 6000)
            return
        try:
            self.store.save()
        except Exception:
            pass
        self.manager.stop()
        if self.list_window is not None:
            self.list_window.close()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
        QApplication.instance().quit()


def selftest():
    print("== 地址校验 ==")
    for text, expect_ok in [("192.168.1.5", True), ("192.168.1.0/24", True),
                            ("10.0.0.1-10.0.0.9", True), ("2001:db8::1", True),
                            ("abc", False), ("1.2.3.4/33", False),
                            ("10.0.0.9-10.0.0.1", False)]:
        try:
            print("  %-22s -> %s" % (text, core.normalize_addr(text)))
            assert expect_ok, "应当报错：" + text
        except core.AddrError as exc:
            print("  %-22s -> 拒绝：%s" % (text, exc))
            assert not expect_ok, "应当通过：" + text

    print("== 名单匹配 ==")
    assert core.addr_contains("192.168.1.0/24", "192.168.1.20")
    assert core.addr_contains("10.0.0.1-10.0.0.9", "10.0.0.5")
    assert not core.addr_contains("10.0.0.1-10.0.0.9", "10.0.0.10")

    print("== 安全日志解析 ==")
    xml = (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        '<System><EventID>4625</EventID>'
        '<TimeCreated SystemTime="2026-11-25T02:22:33.123456789Z"/>'
        '<EventRecordID>101</EventRecordID></System><EventData>'
        '<Data Name="TargetUserName">admin</Data><Data Name="IpAddress">203.0.113.9</Data>'
        '<Data Name="LogonType">10</Data></EventData></Event>'
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        '<System><EventID>4771</EventID>'
        '<TimeCreated SystemTime="2026-11-25T03:00:00.000000000Z"/>'
        '<EventRecordID>102</EventRecordID></System><EventData>'
        '<Data Name="IpAddress">198.51.100.7</Data></EventData></Event>'
    )
    events = core.parse_security_events(xml)
    for ev in events:
        print("  #%s %s %s %s" % (ev["record_id"], ev["time"].strftime("%H:%M:%S"),
                                  ev["event_id"], ev["ip"]))
    assert len(events) == 2 and events[0]["ip"] == "203.0.113.9"

    print("== 运行环境 ==")
    print("  管理员:", core.is_admin())
    print("  配置目录:", core.app_dir())
    print("  网络连接样本:", len(core.netstat_connections()))
    print("自检完成")


def main():
    for arg in sys.argv[1:]:
        if arg == "--selftest":
            selftest()
            return

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "GK2.IPAutoBlock")
        except Exception:
            pass

    guard, exists = core.single_instance_guard()
    if exists:
        for _ in range(10):
            time.sleep(0.4)
            if not core.another_instance_running():
                break
        else:
            app = QApplication(sys.argv)
            QMessageBox.information(None, "IP 自动封锁",
                                    "程序已经在运行。\n请从系统托盘图标打开主界面。")
            return

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(app_font(9))
    app.setStyleSheet(qtui.stylesheet())
    app.setWindowIcon(qtui.app_icon())
    window = App()
    if "--minimized" in sys.argv[1:] and window.tray is not None:
        window.hide()
    else:
        window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
