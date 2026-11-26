"""打包入口：启动前捕获 Qt/运行库加载失败，给出可读提示而不是 PyInstaller 异常框。"""
from __future__ import annotations

import ctypes
import os
import sys
import traceback
from datetime import datetime


APP_NAME = "IP 自动封锁"


def _write_startup_log(detail: str) -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    log_dir = os.path.join(base, "IPAutoBlock", "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "startup.log")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n===== %s =====\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            handle.write(detail + "\n")
        return path
    except Exception:
        return ""


def _show_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, message, APP_NAME + " - 启动失败", 0x10)
    except Exception:
        try:
            print(message)
        except Exception:
            pass


def main() -> None:
    try:
        import main as app_main
    except Exception:
        detail = traceback.format_exc()
        log_path = _write_startup_log(detail)
        message = (
            "程序缺少必要的系统运行组件，无法启动。\n\n"
            "请依次确认：\n"
            "1. 系统为 Windows 7 SP1 / Server 2008 R2 或更高，推荐 Windows 10 / Server 2016 及以上；\n"
            "2. 已安装 Microsoft Visual C++ 2015-2022 x64 运行库（vc_redist.x64.exe）；\n"
            "3. 已安装最新的 Windows 系统更新（旧系统需 UCRT 补丁 KB2999226）；\n"
            "4. 先把 exe 复制到本地磁盘再运行，不要在网络盘、压缩包或只读目录中直接运行。\n\n"
            "技术信息：\n" + detail
        )
        if log_path:
            message += "\n\n详细日志：" + log_path
        _show_error(message[-2000:])
        raise SystemExit(1)

    app_main.main()


if __name__ == "__main__":
    main()
