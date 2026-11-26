"""GitHub Actions 入口：在 runner 上固定模拟“非管理员 + 无安全日志权限”的环境。

本地直接运行 tools/functional_test.py 仍按真实权限测试；CI 用本脚本，
避免 GitHub 托管 runner 的权限、网卡和日志状态导致用例偶发失败。
"""
import os
import runpy
import shutil
import sys
import tempfile
import time

_test_appdata = tempfile.mkdtemp(prefix="ipab_ci_")
os.environ["APPDATA"] = _test_appdata
os.environ["IPAB_NO_BACKUP"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402

core.is_admin = lambda: False
core.query_failures = lambda *args, **kwargs: (5, [], "拒绝访问。")


def _fake_refresh_local_ips(self):
    self.local_ips = {"127.0.0.1", "192.168.5.9"}
    self._local_loaded = time.time()


core.Manager.refresh_local_ips = _fake_refresh_local_ips

try:
    sys.argv = ["tools/functional_test.py"]
    runpy.run_path("tools/functional_test.py", run_name="__main__")
finally:
    shutil.rmtree(_test_appdata, ignore_errors=True)
