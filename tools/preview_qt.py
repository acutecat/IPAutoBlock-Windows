"""开发用：启动 Qt 界面并截图，检查视觉还原度。"""
import atexit
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from datetime import datetime, timedelta

# 截图跑在临时 APPDATA 里，不会动用户真实的配置和名单
_TEST_APPDATA = tempfile.mkdtemp(prefix="ipab_preview_")
os.environ["APPDATA"] = _TEST_APPDATA
os.environ["IPAB_NO_BACKUP"] = "1"
atexit.register(lambda: shutil.rmtree(_TEST_APPDATA, ignore_errors=True))

from PyQt5.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
import qtui  # noqa: E402


def pump(app, seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


qapp = QApplication([])
qapp.setStyle("Fusion")
qapp.setFont(main.app_font(9))
qapp.setStyleSheet(qtui.stylesheet())

window = main.App()
window.show()
pump(qapp, 1.6)
window.grab().save(os.path.join(HERE, "preview_main.png"))
print("main saved", window.size().width(), window.size().height())

fake = [
    {"record_id": 9001, "time": datetime.now() - timedelta(minutes=2), "event_id": 4625,
     "ip": "203.0.113.9", "user": "admin", "logon_type": "3"},
    {"record_id": 9002, "time": datetime.now() - timedelta(minutes=4), "event_id": 4771,
     "ip": "198.51.100.7", "user": "administrator", "logon_type": ""},
    {"record_id": 9003, "time": datetime.now() - timedelta(minutes=7), "event_id": 4625,
     "ip": "203.0.113.9", "user": "root", "logon_type": "10"},
    {"record_id": 9004, "time": datetime.now() - timedelta(minutes=9), "event_id": 4625,
     "ip": "192.0.2.44", "user": "test", "logon_type": "3"},
]
window.fail_section.set_expanded(True)
window.show_failures((fake, "", ""))
pump(qapp, 0.6)
window.fail_section.grab().save(os.path.join(HERE, "preview_fail.png"))
print("fail saved")

about = qtui.AboutDialog(window, datetime.now().year)
about.show()
pump(qapp, 0.5)
about.grab().save(os.path.join(HERE, "preview_about.png"))
about.close()
print("about saved")

window.store.data["allow"] = [
    {"addr": "192.168.5.9", "note": "本机办公电脑", "added": "2026-11-25 10:20"},
    {"addr": "192.168.5.0/24", "note": "办公局域网", "added": "2026-11-25 10:21"},
]
window.store.data["block"] = [
    {"addr": "203.0.113.9", "note": "10 次登录失败 / 5 分钟 · 用户 admin", "source": "自动封锁",
     "added": "2026-11-25 10:30:00", "expires": "2026-11-25T11:00:00"},
    {"addr": "198.51.100.7", "note": "手动加入", "source": "手动",
     "added": "2026-11-25 10:32:00", "expires": None},
]

add = qtui.AddDialog(window, "block", lambda *args: (True, ""),
                     window.auto_expiry_days(), window.auto_expiry_text())
add.addr_edit.setText("203.0.113.9")
add.note_edit.setText("异常登录")
add.show()
pump(qapp, 0.4)
add.grab().save(os.path.join(HERE, "preview_add_block.png"))
add.close()
print("add saved")

dlg = qtui.ListWindow(window, window)
window.list_window = dlg
dlg.show()
pump(qapp, 0.8)
dlg.grab().save(os.path.join(HERE, "preview_dialog_allow.png"))

dlg.tabs.setCurrentIndex(1)
pump(qapp, 0.5)
dlg.grab().save(os.path.join(HERE, "preview_dialog_block.png"))

dlg.close()
pump(qapp, 0.3)
window.manager.stop()
print("done")
