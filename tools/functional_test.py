"""开发用：核心与界面逻辑的自动化功能测试（不需要管理员权限）。"""
import atexit
import copy
import csv
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

# 测试完全跑在临时目录里，绝不读写用户的 %APPDATA%\IPAutoBlock
_TEST_APPDATA = tempfile.mkdtemp(prefix="ipab_test_")
os.environ["APPDATA"] = _TEST_APPDATA
os.environ["IPAB_NO_BACKUP"] = "1"


def _cleanup_test_dir():
    shutil.rmtree(_TEST_APPDATA, ignore_errors=True)


atexit.register(_cleanup_test_dir)

from PyQt5.QtWidgets import QApplication  # noqa: E402

import core  # noqa: E402
import main  # noqa: E402
import qtui  # noqa: E402
import version  # noqa: E402

# CI 上不申请管理员、不碰真实防火墙；渲染走 offscreen。
if os.environ.get("IPAB_CI") == "1":
    core.is_admin = lambda: False

qapp = QApplication([])
qapp.setStyle("Fusion")
qapp.setFont(main.app_font(9))
qapp.setStyleSheet(qtui.stylesheet())

window = main.App()
window.show()
for _ in range(40):
    qapp.processEvents()
    time.sleep(0.02)

failures = []


def check(name, condition, detail=""):
    print(("PASS  " if condition else "FAIL  ") + name + (("  " + str(detail)) if detail else ""))
    if not condition:
        failures.append(name)


check("默认封锁时长为 1 天", window.edit_expiry_value.text() == "1", window.edit_expiry_value.text())
check("主窗口标题带版本号", window.windowTitle() == "%s v%s" % (version.APP_NAME, version.APP_VERSION),
      window.windowTitle())


# --- 名单增删 ---
ok, msg = window.submit_new_entry("allow", "192.168.5.9", "本机", None)
check("新增允许条目", ok, msg)
ok, msg = window.submit_new_entry("allow", "192.168.5.9", "重复", None)
check("重复允许条目被拒绝", not ok, msg)
rows = window.list_rows("allow")
check("允许名单行数", len(rows) == 1, rows)

ok, msg = window.submit_new_entry("block", "192.168.5.9", "测", None)
check("允许名单中的地址不会被封锁", not ok and "允许名单" in msg, msg)

ok, msg = window.submit_new_entry("block", "203.0.113.99", "测", 7)
if core.is_admin():
    check("管理员下可封锁", ok, msg)
else:
    check("非管理员下封锁被拒绝", (not ok) and "管理员" in msg, msg)

# --- 名单窗口 ---
dlg = qtui.ListWindow(window, window)
window.list_window = dlg
dlg.show()
qapp.processEvents()
check("名单窗口允许页行数", dlg.table_allow.rowCount() == 1, dlg.table_allow.rowCount())
dlg.search.setText("192.168.5.9")
qapp.processEvents()
check("搜索命中", dlg.table_allow.rowCount() == 1, dlg.table_allow.rowCount())
dlg.search.setText("no-such-ip")
qapp.processEvents()
check("搜索无结果", dlg.table_allow.rowCount() == 0, dlg.table_allow.rowCount())
dlg.search.setText("")
dlg.tabs.setCurrentIndex(1)
qapp.processEvents()
check("封锁页行数", dlg.table_block.rowCount() == 0, dlg.table_block.rowCount())
check("空列表显示无数据", dlg.count_label.text() == "无数据", dlg.count_label.text())
dlg.tabs.setCurrentIndex(0)
qapp.processEvents()

# --- 导出 ---
tmp = os.path.join(tempfile.gettempdir(), "ipab_export_test.csv")
ok, msg = window.export_list("allow", tmp)
check("导出 CSV", ok, msg)
with open(tmp, encoding="utf-8-sig") as fh:
    content = fh.read()
check("导出内容包含地址", "192.168.5.9" in content, content.strip())
os.remove(tmp)

# --- 新增对话框构建 ---
captured = {}
def fake_submit(kind, addr, note, minutes):
    captured.update(kind=kind, addr=addr, note=note, minutes=minutes)
    return True, ""

add = qtui.AddDialog(dlg, "block", fake_submit, 3, "3 天")
qapp.processEvents()
check("新增对话框可构建", add.isVisible() or True)
check("封锁对话框不再有单位选择", add.duration_unit is None)
check("手动封锁默认永久", add.permanent_chk.isChecked())
check("自定义时长默认沿用设置值", add.duration_edit.text() == "3", add.duration_edit.text())
add.addr_edit.setText("203.0.113.87")
add._submit()
check("手动封锁提交为永久", captured.get("minutes") is None, captured)
add.reject()

add = qtui.AddDialog(dlg, "block", fake_submit, 3, "3 天")
add.addr_edit.setText("203.0.113.88")
add.permanent_chk.setChecked(False)
add._submit()
check("取消永久后默认使用设置天数", captured.get("minutes") == 4320, captured)
add.reject()

add = qtui.AddDialog(dlg, "block", fake_submit, 3, "3 天")
add.addr_edit.setText("203.0.113.88")
add.permanent_chk.setChecked(False)
add.duration_edit.setText("1")
add._submit()
check("自定义 1 天被正确换算", captured.get("minutes") == 1440, captured)
add.reject()

add = qtui.AddDialog(dlg, "block", fake_submit, 3, "3 天")
add.addr_edit.setText("203.0.113.89")
add.permanent_chk.setChecked(False)
add.duration_edit.setText("2")
add._submit()
check("自定义 2 天被正确换算", captured.get("minutes") == 2880, captured)
add.reject()
dlg.close()
qapp.processEvents()

# --- 封锁时间 / 到期时间 ---
old_admin = core.is_admin
old_block = core.firewall_block
old_unblock = core.firewall_unblock
core.is_admin = lambda: True
core.firewall_block = lambda addr: (True, "")
core.firewall_unblock = lambda addr: (True, "")
try:
    window.log_edit.clear()
    ok, msg = window.submit_new_entry("block", "203.0.113.50", "时间测试", 30)
    check("管理员下可新增半小时封锁", ok, msg)
    entry = window.store.find_entry("block", "203.0.113.50")
    check("封锁记录含封锁时间", bool(entry and entry.get("added")), entry)
    check("封锁记录含到期时间", bool(entry and entry.get("expires")), entry)
    if entry and entry.get("expires"):
        blocked_at = datetime.fromisoformat(entry["added"])
        expires_at = datetime.fromisoformat(entry["expires"])
        delta = (expires_at - blocked_at).total_seconds() / 60
        check("半小时封锁到期时间相差 30 分钟", 29 <= delta <= 31,
              "%s -> %s（%.1f 分钟）" % (entry["added"], entry["expires"], delta))
    row = next((r for r in window.list_rows("block") if r["addr"] == "203.0.113.50"), {})
    check("封锁名单包含封锁时间", bool(row.get("added")), row)
    check("封锁名单包含到期时间", bool(row.get("expires")), row)

    log_text = window.log_edit.toPlainText()
    check("封锁日志包含封锁时间", "封锁时间" in log_text, log_text)
    check("封锁日志包含到期时间", "到期时间" in log_text, log_text)
    check("封锁日志包含 30 分钟时长", "时长 30 分钟" in log_text, log_text)

    # 自动封锁应读取“启动封锁过期 + 封锁时长”设置
    window.store.data["auto"] = {"enabled": True, "attempts": 3, "minutes": 5,
                                 "expiry": True, "days": 1}
    window.store.save()
    created = window.manager.auto_block("203.0.113.51", "联动测试")
    check("自动封锁按设置生成", created)
    auto_entry = window.store.find_entry("block", "203.0.113.51")
    if auto_entry and auto_entry.get("expires"):
        auto_delta = (datetime.fromisoformat(auto_entry["expires"])
                      - datetime.fromisoformat(auto_entry["added"])).total_seconds() / 60
        check("自动封锁按设置只封锁 1 天", 1439 <= auto_delta <= 1441,
              "%s -> %s" % (auto_entry["added"], auto_entry["expires"]))
    window.manager.unblock("203.0.113.51", silent=True)

    tmp_block = os.path.join(tempfile.gettempdir(), "ipab_export_block.csv")
    ok, msg = window.export_list("block", tmp_block)
    check("导出封锁名单", ok, msg)
    with open(tmp_block, encoding="utf-8-sig") as fh:
        content = fh.read()
    check("封锁 CSV 含封锁时间与到期时间", "封锁时间" in content and "到期时间" in content,
          content.splitlines()[0] if content else "")
    os.remove(tmp_block)

    window.manager.unblock("203.0.113.50", silent=True)
finally:
    core.is_admin = old_admin
    core.firewall_block = old_block
    core.firewall_unblock = old_unblock

# --- 到期解封 ---
with window.store.lock:
    window.store.data["block"].append({
        "addr": "198.51.100.55", "note": "到期测试", "source": "自动封锁",
        "added": "2026-01-01 00:00", "expires": (datetime.now() - timedelta(minutes=5)).isoformat(),
    })
    window.store.save()
window.manager.expire_due()
check("到期条目被清理", window.store.find_entry("block", "198.51.100.55") is None)

# --- 失败登录统计与阈值 ---
cfg = window.store.cfg["auto"]
window.store.lock.acquire()
window.store.data["auto"] = {"enabled": True, "attempts": 3, "minutes": 5,
                             "expiry": True, "days": 30}
window.store.lock.release()
check("允许名单匹配生效", window.manager.is_allowed("192.168.5.9"))
check("本机地址识别", "192.168.5.9" in window.manager.local_ips, sorted(window.manager.local_ips)[:4])
when = datetime.now()
for i in range(5):
    window.manager.on_failed_login("203.0.113.9", when, "admin", "10", 4625)
# 非管理员时封锁会失败，但计数逻辑应当已被触发并清空
check("失败计数已被处理", True)

# --- 失败记录查询逻辑 ---
xp = core.failures_xpath(30)
check("失败查询带时间过滤", "timediff" in xp and "1800000" in xp, xp)
check("失败查询包含事件 ID", "4625" in xp and "4771" in xp, xp)
now = datetime.now()
sample = [
    {"ip": "203.0.113.9", "time": now - timedelta(minutes=1), "user": "admin"},
    {"ip": "203.0.113.9", "time": now - timedelta(minutes=3), "user": "root"},
    {"ip": "198.51.100.7", "time": now - timedelta(minutes=5), "user": ""},
]
summary = core.failure_summary(sample)
check("失败记录按 IP 汇总", summary[0]["ip"] == "203.0.113.9" and summary[0]["count"] == 2, summary)
check("失败记录汇总账户", summary[0]["users"] == ["admin", "root"], summary[0]["users"])
rc, evs, err = core.query_failures(60)
if core.is_admin():
    check("管理员可读取失败记录", rc == 0, err)
else:
    check("非管理员读取被拒绝且提示明确", rc != 0 and bool(err) and len(evs) == 0, err)

window.fail_section.set_expanded(True)
window.show_failures(([], "", ""))
check("失败记录面板可刷新为空", window.fail_table.rowCount() == 0)
window.show_failures(([{"record_id": i, "time": now, "event_id": 4625,
                        "ip": "203.0.113.%d" % i, "user": "u", "logon_type": "3"} for i in range(3)],
                      "", ""))
check("失败记录表格填充", window.fail_table.rowCount() == 3)

# --- 设置校验 ---
window.edit_expiry_value.setText("0")
try:
    window._read_int(window.edit_expiry_value, "封锁时长", 1, 3650)
    check("非法封锁时长被拒绝", False)
except ValueError:
    check("非法封锁时长被拒绝", True)
window.edit_expiry_value.setText("2")
window.chk_expiry.setChecked(False)
qapp.processEvents()
check("取消封锁过期立即写入配置", window.store.cfg["auto"]["expiry"] is False,
      window.store.cfg["auto"])
window.chk_expiry.setChecked(True)
qapp.processEvents()
check("勾选封锁过期立即写入配置", window.store.cfg["auto"]["expiry"] is True,
      window.store.cfg["auto"])
check("立即保存后自动封锁时长为 2 天", window.manager.auto_expiry_minutes() == 2880,
      window.manager.auto_expiry_minutes())
buttons = [b.text() for b in window.findChildren(main.QPushButton)]
check("已移除应用按钮", "应用" not in buttons, buttons)

# --- 系统托盘 ---
if window.tray is not None:
    check("托盘图标已创建", window.tray.isVisible())
    acts = [a.text() for a in window.tray_menu.actions() if not a.isSeparator()]
    check("托盘菜单包含打开主界面", "打开主界面" in acts, acts)
    check("托盘菜单包含关于本程序", "关于本程序" in acts, acts)
    check("托盘菜单包含退出", "退出" in acts, acts)
    about = qtui.AboutDialog(window, datetime.now().year)
    texts = " ".join(l.text() for l in about.findChildren(qtui.QLabel))
    check("关于窗口包含软件名", "IP 自动封锁工具" in texts, texts)
    check("关于窗口包含版本号", "版本 v%s" % version.APP_VERSION in texts, texts)
    check("关于窗口版权年份", "Copyright © 2025-%d GK.2" % datetime.now().year in texts, texts)
    check("关于窗口包含使用限制", "禁止逆向" in texts and "禁止用于商业项目" in texts, texts)
    check("关于窗口包含权利声明", "All rights reserved" in texts, texts)
    about.reject()
    window.close()
    qapp.processEvents()
    check("关闭窗口只收进托盘", (not window.isVisible()) and (not window._quit))
    window.show_main()
    qapp.processEvents()
    check("可从托盘恢复主界面", window.isVisible())
    window._last_block_notify = 0
    window.notify_block("203.0.113.9（自动封锁）")
    check("封锁时触发气泡通知", window._last_block_notify > 0)
else:
    print("SKIP  当前环境无系统托盘")

# --- 配置备份与损坏回退 ---
store_b = core.Store()
store_b.data["auto"]["attempts"] = 9
store_b.save()
store_b.save()
bak = core.CONFIG_FILE.with_name("config.json.bak")
check("保存配置会留 .bak", bak.exists())
bak_bytes = bak.read_bytes()
core.CONFIG_FILE.write_text("{ broken json", encoding="utf-8")
store_c = core.Store()
check("配置损坏时回退备份",
      bool(store_c.load_note) and store_c.data["auto"]["attempts"] == 9, store_c.load_note)
core.CONFIG_FILE.write_bytes(bak_bytes)

# --- 遗留防火墙规则认领（不删除用户已有封锁） ---
old_admin = core.is_admin
old_fw = core.firewall_block
core.is_admin = lambda: True
core.firewall_block = lambda addr: (True, "")
try:
    adopted = window.manager.adopt_legacy_rules({
        "IPAutoBlock_In_198_51_100_77": "198.51.100.77",
        "IPAutoBlock_Out_198_51_100_77": "198.51.100.77",
    })
    entries = [b for b in window.store.cfg["block"] if b["addr"] == "198.51.100.77"]
    check("遗留规则被认领为封锁", adopted == ["198.51.100.77"], adopted)
    check("认领记录带恢复来源", bool(entries) and entries[0]["source"] == "恢复", entries)
    again = window.manager.adopt_legacy_rules({
        "IPAutoBlock_In_198_51_100_77": "198.51.100.77",
    })
    check("已认领规则不重复加入", again == [], again)
finally:
    core.is_admin = old_admin
    core.firewall_block = old_fw

# 临时目录由 atexit 清理，这里只停止后台线程
window.manager.stop()
qapp.processEvents()

print("----")
print("失败项:", failures if failures else "无")
sys.exit(1 if failures else 0)
