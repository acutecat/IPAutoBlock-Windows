"""IP 自动封锁 —— 核心逻辑

包含：配置存储、Windows 防火墙规则、安全日志（4625/4771）监视、
拒绝服务（DoS）连接检测、封锁到期清理。
全部依赖 Python 标准库，便于 PyInstaller 打包为单文件 exe。
"""
from __future__ import annotations

import copy
import ctypes
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

RULE_PREFIX = "IPAutoBlock_"
CREATE_NO_WINDOW = 0x08000000
MUTEX_NAME = "Global\\IPAutoBlock.SingleInstance"

DEFAULT_CONFIG = {
    "auto": {"enabled": True, "attempts": 10, "minutes": 5, "expiry": True,
             "days": 1},
    "dos": {"enabled": False, "interface": "", "threshold": 100, "block_minutes": 30},
    "allow": [],
    "block": [],
    "rules": {},
    "autostart": False,
}


# ---------------------------------------------------------------- 基础工具
def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def system_exe(name: str) -> str:
    """返回系统程序的绝对路径，避免依赖 PATH。"""
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidates = []
    if name.lower() == "powershell":
        candidates.append(root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    for folder in ("System32", "Sysnative"):
        candidates.append(root / folder / (name + ".exe"))
    for path in candidates:
        if path.exists():
            return str(path)
    found = shutil.which(name)
    return found or name


def run_hidden(args, timeout: int = 30):
    """隐藏窗口执行命令，返回 (returncode, 输出文本)。"""
    try:
        cp = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        return 127, "找不到命令：" + str(args[0])
    except subprocess.TimeoutExpired:
        return 124, "命令执行超时"
    except Exception as exc:                                    # pragma: no cover
        return 1, str(exc)
    return cp.returncode, (_decode(cp.stdout) + _decode(cp.stderr)).strip()


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """以管理员身份重新启动本程序。"""
    try:
        if getattr(sys, "frozen", False):
            target = sys.executable
            params = ""
        else:
            target = sys.executable
            params = '"%s"' % os.path.abspath(sys.argv[0])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, params, None, 1)
        return int(rc) > 32
    except Exception:
        return False


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / "IPAutoBlock"
    p.mkdir(parents=True, exist_ok=True)
    return p


LOG_DIR = app_dir() / "logs"
CONFIG_FILE = app_dir() / "config.json"
BACKUP_DIR = app_dir() / "backups"


def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


def human_duration(minutes: int) -> str:
    """把分钟数写成便于阅读的 30 分钟 / 6 小时 / 30 天。"""
    minutes = max(0, int(round(minutes)))
    if minutes < 60:
        return "%d 分钟" % minutes
    if minutes % 1440 == 0:
        return "%d 天" % (minutes // 1440)
    if minutes % 60 == 0:
        return "%d 小时" % (minutes // 60)
    return "%d 分钟" % minutes


# ---------------------------------------------------------------- 地址处理
class AddrError(ValueError):
    pass


def normalize_addr(text: str) -> str:
    """校验并规范化单个 IP / 网段 / IP 范围。"""
    s = (text or "").strip().replace(" ", "")
    if not s:
        raise AddrError("请输入 IP 地址")
    if "-" in s and "/" not in s:
        parts = s.split("-")
        if len(parts) != 2:
            raise AddrError("IP 范围格式应为：起始地址-结束地址")
        try:
            a = ipaddress.ip_address(parts[0])
            b = ipaddress.ip_address(parts[1])
        except ValueError:
            raise AddrError("IP 地址格式不正确")
        if a.version != b.version:
            raise AddrError("IP 范围两端的地址版本不一致")
        if int(a) > int(b):
            raise AddrError("IP 范围的起始地址不能大于结束地址")
        return "%s-%s" % (a, b)
    if "/" in s:
        try:
            return str(ipaddress.ip_network(s, strict=False))
        except ValueError:
            raise AddrError("网段格式不正确，例如 192.168.1.0/24")
    try:
        return str(ipaddress.ip_address(s))
    except ValueError:
        raise AddrError("IP 地址格式不正确")


def addr_contains(entry: str, ip: str) -> bool:
    """判断单条名单记录是否覆盖某个 IP。"""
    try:
        target = ipaddress.ip_address(ip)
    except ValueError:
        return False
    try:
        if "-" in entry and "/" not in entry:
            a, b = entry.split("-")
            return int(ipaddress.ip_address(a)) <= int(target) <= int(ipaddress.ip_address(b))
        if "/" in entry:
            return target in ipaddress.ip_network(entry, strict=False)
        return ipaddress.ip_address(entry) == target
    except ValueError:
        return False


def _safe_key(addr: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", addr).strip("_")


def rule_names(addr: str):
    key = _safe_key(addr)
    return [RULE_PREFIX + "In_" + key, RULE_PREFIX + "Out_" + key]


# ---------------------------------------------------------------- 配置存储
def _merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.path = CONFIG_FILE
        self.backup_path = CONFIG_FILE.with_name("config.json.bak")
        self.load_note = ""
        self.snapshot_backup()
        self.data = self._load()

    # ---- 备份 ----
    def snapshot_backup(self):
        """每次启动把当前配置留一份快照，最多保留 10 份，防止升级/误操作丢配置。"""
        if os.environ.get("IPAB_NO_BACKUP") == "1":
            return
        try:
            if not self.path.exists():
                return
            raw = self.path.read_bytes()
            json.loads(raw.decode("utf-8"))
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            target = BACKUP_DIR / ("config-%s.json" % now_str("%Y%m%d-%H%M%S"))
            if not target.exists():
                target.write_bytes(raw)
            for old in sorted(BACKUP_DIR.glob("config-*.json"))[:-10]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except Exception:
            pass

    def _load(self):
        for candidate in (self.path, self.backup_path):
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    base = copy.deepcopy(DEFAULT_CONFIG)
                    _merge(base, raw)
                    for key in ("allow", "block"):
                        if not isinstance(base.get(key), list):
                            base[key] = []
                    if not isinstance(base.get("rules"), dict):
                        base["rules"] = {}
                    # 统一按天保存；旧配置只有 expiry_minutes 时换算成天数
                    raw_auto = raw.get("auto") if isinstance(raw.get("auto"), dict) else {}
                    if "days" not in raw_auto:
                        if "expiry_minutes" in raw_auto:
                            try:
                                mins = max(1, int(raw_auto.get("expiry_minutes") or 1))
                            except (TypeError, ValueError):
                                mins = 1440
                            base["auto"]["days"] = max(1, (mins + 1439) // 1440)
                        else:
                            base["auto"]["days"] = 1
                    base["auto"].pop("expiry_minutes", None)
                    if candidate != self.path:
                        self.load_note = "主配置无法读取，已从 config.json.bak 恢复"
                    return base
            except Exception:
                continue
        return copy.deepcopy(DEFAULT_CONFIG)

    @property
    def cfg(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def save(self):
        with self.lock:
            text = json.dumps(self.data, ensure_ascii=False, indent=2)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            try:
                json.loads(self.path.read_text(encoding="utf-8"))
                shutil.copyfile(self.path, self.backup_path)
            except Exception:
                pass
            os.replace(tmp, self.path)

    def reload(self):
        with self.lock:
            self.data = self._load()
            return copy.deepcopy(self.data)

    # ---- 名单 ----
    def find_entry(self, kind: str, addr: str):
        with self.lock:
            for item in self.data[kind]:
                if item.get("addr") == addr:
                    return copy.deepcopy(item)
        return None

    def add_entry(self, kind: str, entry: dict):
        with self.lock:
            if any(x.get("addr") == entry["addr"] for x in self.data[kind]):
                return False
            self.data[kind].append(entry)
            self.save()
            return True

    def remove_entry(self, kind: str, addr: str):
        with self.lock:
            before = len(self.data[kind])
            self.data[kind] = [x for x in self.data[kind] if x.get("addr") != addr]
            changed = len(self.data[kind]) != before
            if changed:
                self.save()
            return changed

    def update_entry(self, kind: str, addr: str, **fields):
        with self.lock:
            for item in self.data[kind]:
                if item.get("addr") == addr:
                    item.update(fields)
                    self.save()
                    return True
        return False

    # ---- 规则登记 ----
    def set_rules(self, addr: str, names):
        with self.lock:
            self.data["rules"][addr] = list(names)
            self.save()

    def drop_rules(self, addr: str):
        with self.lock:
            self.data["rules"].pop(addr, None)
            self.save()

    def known_rule_names(self):
        with self.lock:
            out = set()
            for names in self.data["rules"].values():
                out.update(names)
            return out


# ---------------------------------------------------------------- 防火墙
def firewall_block(addr: str):
    """为地址添加双向阻止规则，返回 (成功, 提示)。"""
    ok = True
    msg = ""
    for name, direction in zip(rule_names(addr), ("in", "out")):
        rc, out = run_hidden([
            system_exe("netsh"), "advfirewall", "firewall", "add", "rule",
            "name=" + name, "dir=" + direction, "action=block",
            "remoteip=" + addr, "enable=yes", "profile=any", "protocol=any",
        ])
        if rc != 0:
            ok = False
            msg = out or "防火墙规则创建失败"
    return ok, msg


def firewall_unblock(addr: str):
    for name in rule_names(addr):
        run_hidden([system_exe("netsh"), "advfirewall", "firewall", "delete", "rule", "name=" + name])
    return True


def firewall_delete_by_name(name: str):
    run_hidden([system_exe("netsh"), "advfirewall", "firewall", "delete", "rule", "name=" + name])


def firewall_list_our_rules():
    """枚举本工具创建的防火墙规则名。"""
    rc, out = run_hidden([
        system_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command",
        "Get-NetFirewallRule -DisplayName 'IPAutoBlock_*' -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.DisplayName }",
    ], timeout=45)
    names = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(RULE_PREFIX):
            names.add(line)
    return names


def firewall_rules_detail():
    """返回 {规则名: 远端地址}，用于把遗留规则认领回封锁名单。"""
    script = ("Get-NetFirewallRule -DisplayName '" + RULE_PREFIX + "*' -ErrorAction SilentlyContinue | "
              "ForEach-Object { \"$($_.DisplayName)|$((Get-NetFirewallAddressFilter "
              "-AssociatedNetFirewallRule $_ -ErrorAction SilentlyContinue).RemoteAddress)\" }")
    rc, out = run_hidden([
        system_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command", script,
    ], timeout=90)
    detail = {}
    for line in out.splitlines():
        if "|" not in line:
            continue
        name, addr = line.split("|", 1)
        name = name.strip()
        if name.startswith(RULE_PREFIX):
            detail[name] = addr.strip()
    return detail


# ---------------------------------------------------------------- 安全日志
_EVENT_RE = re.compile(r"<Event\b.*?</Event>", re.S)
_TIME_RE = re.compile(r"<TimeCreated[^>]*SystemTime=['\"]([^'\"]+)['\"]")
_ID_RE = re.compile(r"<EventID[^>]*>(\d+)</EventID>")
_RID_RE = re.compile(r"<EventRecordID>(\d+)</EventRecordID>")
_DATA_RE = re.compile(r"<Data\s+Name=['\"]([^'\"]+)['\"]\s*>([^<]*)</Data>")


def parse_system_time(value: str) -> datetime:
    ts = value.strip().rstrip("Z")
    if "." in ts:
        head, frac = ts.split(".", 1)
        frac = re.sub(r"[^0-9]", "", frac)[:6].ljust(6, "0")
        ts = head + "." + frac
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def parse_security_events(xml_text: str):
    """解析 wevtutil 输出的 XML，返回 [{record_id, time, event_id, ip, user, logon_type}]"""
    events = []
    for blob in _EVENT_RE.findall(xml_text):
        m_time = _TIME_RE.search(blob)
        m_id = _ID_RE.search(blob)
        m_rid = _RID_RE.search(blob)
        if not (m_time and m_id and m_rid):
            continue
        data = dict(_DATA_RE.findall(blob))
        try:
            when = parse_system_time(m_time.group(1))
        except Exception:
            continue
        ip = (data.get("IpAddress") or "").strip()
        if not ip or ip == "-":
            continue
        events.append({
            "record_id": int(m_rid.group(1)),
            "time": when,
            "event_id": int(m_id.group(1)),
            "ip": ip,
            "user": (data.get("TargetUserName") or data.get("TargetUser") or "").strip(),
            "logon_type": (data.get("LogonType") or "").strip(),
        })
    events.sort(key=lambda e: e["record_id"])
    return events


def failures_xpath(minutes: int = 0) -> str:
    """构造登录失败事件的 XPath；minutes > 0 时只取最近 N 分钟。"""
    cond = "EventID=4625 or EventID=4771"
    if minutes and minutes > 0:
        cond = "(%s) and TimeCreated[timediff(@SystemTime) <= %d]" % (cond, int(minutes) * 60000)
    return "*[System[%s]]" % cond


def query_failures(minutes: int = 1440, limit: int = 2000, path: str = ""):
    """读取登录失败事件（4625 / 4771）。

    path 为空时读取活动的 Security 日志（需要管理员权限），
    否则读取 .evtx 文件副本（用 wevtutil /lf:true）。
    返回 (rc, events, error)，events 按时间倒序，最新在前。
    """
    exe = system_exe("wevtutil")
    cmd = [exe, "qe", path, "/lf:true"] if path else [exe, "qe", "Security"]
    cmd += ["/q:" + failures_xpath(minutes), "/rd:true", "/f:xml", "/c:%d" % max(1, int(limit))]
    rc, out = run_hidden(cmd, timeout=60)
    if rc != 0:
        first = out.strip().splitlines()[0].strip() if out.strip() else ""
        return rc, [], first or ("wevtutil 返回错误码 %d" % rc)
    events = parse_security_events(out)
    if minutes and minutes > 0:
        cutoff = datetime.now().astimezone() - timedelta(minutes=minutes)
        events = [e for e in events if e["time"] >= cutoff]
    events.sort(key=lambda e: e["time"], reverse=True)
    return 0, events, ""


def failure_summary(events) -> list:
    """按来源 IP 汇总失败次数，返回 [{ip, count, users, first, last}]，次数多的在前。"""
    stat = {}
    for ev in events:
        item = stat.setdefault(ev["ip"], {"ip": ev["ip"], "count": 0, "users": set(),
                                          "first": ev["time"], "last": ev["time"]})
        item["count"] += 1
        if ev.get("user"):
            item["users"].add(ev["user"])
        if ev["time"] < item["first"]:
            item["first"] = ev["time"]
        if ev["time"] > item["last"]:
            item["last"] = ev["time"]
    rows = sorted(stat.values(), key=lambda x: (-x["count"], -x["last"].timestamp()))
    for row in rows:
        row["users"] = sorted(row["users"])
    return rows


class SecurityWatcher(threading.Thread):
    """轮询 Windows 安全日志中的登录失败事件（4625 / 4771）。"""

    def __init__(self, manager):
        super().__init__(daemon=True, name="SecurityWatcher")
        self.mgr = manager
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.last_record_id = None
        self._last_warn = 0.0

    def run(self):
        while not self.stop_event.is_set():
            cfg = self.mgr.store.cfg["auto"]
            if cfg.get("enabled"):
                self.poll()
                wait = 6
            else:
                wait = 20
            self.wake.wait(wait)
            self.wake.clear()

    def poll(self):
        cfg = self.mgr.store.cfg["auto"]
        minutes = max(10, int(cfg.get("minutes") or 5) * 2)
        rc, out = run_hidden([
            system_exe("wevtutil"), "qe", "Security",
            "/q:" + failures_xpath(minutes),
            "/rd:true", "/f:xml", "/c:2000",
        ], timeout=45)
        self.mgr.last_check = datetime.now()
        if rc != 0:
            now = time.time()
            if now - self._last_warn > 300:
                self._last_warn = now
                self.mgr.log("[警告] 读取安全日志失败（需以管理员身份运行）：%s"
                             % (out.splitlines()[0] if out else rc))
            return
        events = parse_security_events(out)
        if not events:
            if self.last_record_id is None:
                self.last_record_id = 0
                self.mgr.log("[信息] 已连接安全日志，最近 %d 分钟内没有登录失败记录" % minutes)
            return
        if self.last_record_id is None:
            self.last_record_id = events[-1]["record_id"]
            self.backfill(events, minutes)
            return
        if events[-1]["record_id"] < self.last_record_id:
            # 日志被清空或轮转，重新建立基线
            self.last_record_id = events[-1]["record_id"]
            self.mgr.log("[信息] 安全日志已轮转，重新建立监视基线")
            return
        fresh = [e for e in events if e["record_id"] > self.last_record_id]
        if not fresh:
            return
        self.last_record_id = fresh[-1]["record_id"]
        for e in fresh:
            self.mgr.on_failed_login(e["ip"], e["time"], e["user"], e["logon_type"], e["event_id"])
        self.mgr.notify_change()

    def backfill(self, events, minutes):
        """首次连接时把统计窗口内已发生的失败事件计入，避免"重启后看不到之前的攻击"。"""
        cutoff = datetime.now().astimezone() - timedelta(minutes=minutes)
        hist = [e for e in events if e["time"] >= cutoff]
        if not hist:
            self.mgr.log("[信息] 已连接安全日志，开始监视登录失败事件")
            return
        for e in hist:
            self.mgr.on_failed_login(e["ip"], e["time"], e["user"], e["logon_type"], e["event_id"])
        ips = len({e["ip"] for e in hist})
        self.mgr.log("[信息] 已连接安全日志，回溯最近 %d 分钟的失败事件 %d 条（%d 个来源地址）"
                     % (minutes, len(hist), ips))
        self.mgr.notify_change()


# ---------------------------------------------------------------- DoS 保护
_NETSTAT_STATES = ("ESTABLISHED", "SYN_RECEIVED", "CLOSE_WAIT", "FIN_WAIT_1", "FIN_WAIT_2")


def _split_endpoint(text: str):
    if text.startswith("["):
        idx = text.find("]")
        return text[1:idx], text[idx + 2:]
    if ":" in text:
        host, _, port = text.rpartition(":")
        return host, port
    return text, ""


def netstat_connections():
    """返回 [(本地IP, 远端IP, 状态)]"""
    rc, out = run_hidden([system_exe("netstat"), "-ano", "-p", "TCP"], timeout=25)
    rows = []
    if rc != 0:
        return rows
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0].upper() not in ("TCP", "TCPV6"):
            continue
        local, foreign, state = parts[1], parts[2], parts[3]
        if state.upper() not in _NETSTAT_STATES:
            continue
        try:
            lip, _ = _split_endpoint(local)
            fip, _ = _split_endpoint(foreign)
        except Exception:
            continue
        rows.append((lip, fip, state.upper()))
    return rows


class DosGuard(threading.Thread):
    """以单 IP 并发连接数作为 DoS 泛洪的检测依据。"""

    def __init__(self, manager):
        super().__init__(daemon=True, name="DosGuard")
        self.mgr = manager
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            cfg = self.mgr.store.cfg["dos"]
            if cfg.get("enabled"):
                self.poll(cfg)
            time.sleep(3 if cfg.get("enabled") else 15)

    def poll(self, cfg):
        rows = netstat_connections()
        if not rows:
            return
        scope_ip = self.mgr.iface_ip(cfg.get("interface") or "")
        counts = defaultdict(int)
        for lip, fip, state in rows:
            if scope_ip and lip != scope_ip:
                continue
            if not fip or fip in ("0.0.0.0", "127.0.0.1", "::", "::1"):
                continue
            if fip in self.mgr.local_ips:
                continue
            counts[fip] += 1
        threshold = max(1, int(cfg.get("threshold") or 100))
        for ip, count in counts.items():
            if count >= threshold:
                self.mgr.dos_block(ip, count, int(cfg.get("block_minutes") or 30))


# ---------------------------------------------------------------- 管理器
class Manager:
    def __init__(self, store: Store, log_cb=None):
        self.store = store
        self.log_cb = log_cb or (lambda msg: None)
        self.lock = threading.RLock()
        self.fails = defaultdict(deque)
        self.local_ips = set()
        self._local_loaded = 0.0
        self._dos_alerted = {}
        self.last_check = None
        self._change_cb = None
        self.watcher = SecurityWatcher(self)
        self.dos = DosGuard(self)
        self._sweeper = threading.Thread(target=self._sweep_loop, daemon=True, name="ExpirySweeper")

    # ---- 回调 ----
    def log(self, msg: str):
        try:
            self.log_cb(msg)
        except Exception:
            pass

    def set_change_callback(self, cb):
        self._change_cb = cb

    def notify_change(self):
        if self._change_cb:
            try:
                self._change_cb()
            except Exception:
                pass

    # ---- 启动 / 停止 ----
    def start(self):
        self.refresh_local_ips()
        if not self.watcher.is_alive():
            self.watcher.start()
        if not self.dos.is_alive():
            self.dos.start()
        if not self._sweeper.is_alive():
            self._sweeper.start()

    def stop(self):
        self.watcher.stop_event.set()
        self.dos.stop_event.set()
        self.watcher.wake.set()

    # ---- 本机地址 ----
    def refresh_local_ips(self):
        if time.time() - self._local_loaded < 600 and self.local_ips:
            return
        rc, out = run_hidden([
            system_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command",
            "Get-NetIPAddress -AddressFamily IPv4,IPv6 -ErrorAction SilentlyContinue | "
            "ForEach-Object { $_.IPAddress }",
        ], timeout=45)
        ips = set()
        for line in out.splitlines():
            line = line.strip()
            try:
                ips.add(str(ipaddress.ip_address(line)))
            except ValueError:
                continue
        if ips:
            self.local_ips = ips
        self._local_loaded = time.time()

    def iface_ip(self, label: str) -> str:
        if not label or label.startswith("全部"):
            return ""
        m = re.search(r"\(([^)]+)\)", label)
        return m.group(1) if m else ""

    # ---- 名单 ----
    def is_allowed(self, ip: str) -> bool:
        for item in self.store.cfg["allow"]:
            if addr_contains(item.get("addr", ""), ip):
                return True
        return False

    def is_blocked(self, addr: str) -> bool:
        return self.store.find_entry("block", addr) is not None

    def entry_expiry(self, item):
        raw = item.get("expires")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None

    def auto_expiry_minutes(self) -> int:
        """自动解封设置换算成分钟；未启用或未设置时返回 0（永久）。"""
        cfg = self.store.cfg["auto"]
        if not cfg.get("expiry", True):
            return 0
        try:
            return max(0, int(cfg.get("days") or 0)) * 1440
        except (TypeError, ValueError):
            return 0

    # ---- 封锁 ----
    def block(self, addr: str, note: str = "", source: str = "手动", expires: datetime | None = None):
        """加入封锁名单并写入防火墙规则，返回 (是否新增, 提示)。"""
        addr = normalize_addr(addr)
        if self.is_allowed(addr):
            return False, "该地址在允许名单中，已跳过"
        at = datetime.now()
        if self.is_blocked(addr):
            existing = self.store.find_entry("block", addr)
            if existing and not existing.get("expires") and not expires:
                return False, "该地址已在封锁名单中"
            self.store.update_entry("block", addr,
                                    expires=expires.isoformat(timespec="seconds") if expires else None)
            blocked_at = (existing or {}).get("added") or at.strftime("%Y-%m-%d %H:%M:%S")
            if expires:
                tail = "，到期时间 %s，时长 %s" % (
                    expires.strftime("%Y-%m-%d %H:%M:%S"),
                    human_duration((expires - at).total_seconds() / 60))
            else:
                tail = "，永久封锁"
            self.log("[封锁] %s（%s），封锁时间 %s%s" % (addr, source, blocked_at, tail))
            return False, "该地址已在封锁名单中"
        if not is_admin():
            return False, "需要管理员权限才能修改防火墙"
        ok, msg = firewall_block(addr)
        if not ok:
            self.log("[错误] %s 防火墙规则创建失败：%s" % (addr, msg))
            return False, "防火墙规则创建失败：%s" % msg
        entry = {
            "addr": addr,
            "note": note,
            "source": source,
            "added": at.strftime("%Y-%m-%d %H:%M:%S"),
            "expires": expires.isoformat(timespec="seconds") if expires else None,
        }
        self.store.set_rules(addr, rule_names(addr))
        self.store.add_entry("block", entry)
        if expires:
            tail = "到期时间 %s，时长 %s" % (
                expires.strftime("%Y-%m-%d %H:%M:%S"),
                human_duration((expires - at).total_seconds() / 60))
        else:
            tail = "永久封锁"
        self.log("[封锁] %s（%s），封锁时间 %s，%s" % (
            addr, source, at.strftime("%Y-%m-%d %H:%M:%S"), tail))
        self.notify_change()
        return True, ""

    def unblock(self, addr: str, silent: bool = False):
        addr = normalize_addr(addr)
        entry = self.store.find_entry("block", addr)
        firewall_unblock(addr)
        added = self.store.remove_entry("block", addr)
        self.store.drop_rules(addr)
        if added and not silent:
            if entry and entry.get("added"):
                self.log("[解封] %s 已移出封锁名单（封锁时间 %s）" % (addr, entry.get("added")))
            else:
                self.log("[解封] %s 已移出封锁名单" % addr)
        self.notify_change()
        return True

    def auto_block(self, ip: str, reason: str, user: str = ""):
        minutes = self.auto_expiry_minutes()
        expires = datetime.now() + timedelta(minutes=minutes) if minutes > 0 else None
        note = reason + (" · 用户 %s" % user if user else "")
        created, _ = self.block(ip, note=note, source="自动封锁", expires=expires)
        return created

    def dos_block(self, ip: str, count: int, minutes: int):
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return
        last = self._dos_alerted.get(ip, 0)
        if time.time() - last < 60:
            return
        self._dos_alerted[ip] = time.time()
        expires = datetime.now() + timedelta(minutes=max(1, minutes))
        created, _ = self.block(ip, note="DoS 保护：并发连接 %d" % count, source="DoS保护", expires=expires)
        if created:
            self.log("[DoS] %s 并发连接数异常（%d），已临时封锁 %d 分钟" % (ip, count, minutes))

    # ---- 失败登录统计 ----
    def on_failed_login(self, ip, when, user="", logon_type="", event_id=None):
        try:
            ipobj = ipaddress.ip_address(ip.strip())
        except ValueError:
            return
        ip = str(ipobj)
        cfg = self.store.cfg["auto"]
        if not cfg.get("enabled"):
            return
        if ip in ("127.0.0.1", "::1"):
            return
        if self.is_allowed(ip) or self.is_blocked(ip):
            return
        self.refresh_local_ips()
        if ip in self.local_ips:
            return
        window = max(1, int(cfg.get("minutes") or 5)) * 60
        attempts = max(1, int(cfg.get("attempts") or 10))
        dq = self.fails[ip]
        dq.append(when)
        while dq and (when - dq[0]).total_seconds() > window:
            dq.popleft()
        if len(dq) >= attempts:
            dq.clear()
            self.auto_block(ip, "%d 次登录失败 / %d 分钟" % (attempts, max(1, int(cfg.get("minutes") or 5))), user)

    # ---- 到期清理 ----
    def expire_due(self):
        changed = False
        for item in self.store.cfg["block"]:
            exp = self.entry_expiry(item)
            if exp and exp <= datetime.now():
                addr = item["addr"]
                firewall_unblock(addr)
                self.store.remove_entry("block", addr)
                self.store.drop_rules(addr)
                self.log("[解封] %s 封锁已到期（封锁时间 %s，到期时间 %s），自动解除" % (
                    addr, item.get("added") or "未知", exp.strftime("%Y-%m-%d %H:%M:%S")))
                changed = True
        if changed:
            self.notify_change()
        return changed

    def _sweep_loop(self):
        # 启动时先校准一次防火墙规则
        self.reconcile()
        while not self.watcher.stop_event.is_set():
            try:
                self.expire_due()
            except Exception as exc:                            # pragma: no cover
                self.log("[错误] 到期清理失败：%s" % exc)
            time.sleep(30)

    def reconcile(self):
        """把防火墙里已有的规则与封锁名单对齐：遗留规则认领回名单，名单里的地址补齐规则。"""
        if not is_admin():
            return
        detail = firewall_rules_detail()
        existing = set(detail)
        if not detail:
            existing = firewall_list_our_rules()
        if detail:
            adopted = self.adopt_legacy_rules(detail)
            if adopted:
                self.log("[信息] 从防火墙规则恢复 %d 个封锁地址：%s"
                         % (len(adopted), "、".join(adopted[:8]) + ("…" if len(adopted) > 8 else "")))
                self.notify_change()
        elif existing:
            self.log("[警告] 发现 %d 条 IPAutoBlock_ 遗留规则，但读不到远端地址，已原样保留" % len(existing))
        for item in self.store.cfg["block"]:
            addr = item["addr"]
            need = set(rule_names(addr))
            if not need.issubset(existing):
                ok, msg = firewall_block(addr)
                self.store.set_rules(addr, rule_names(addr))
                if not ok:
                    self.log("[警告] 恢复规则失败 %s：%s" % (addr, msg))

    def adopt_legacy_rules(self, detail: dict):
        """防火墙里存在、但配置里没有的自家规则，认领为封锁记录，绝不直接删除。"""
        adopted = []
        seen = set()
        known = self.store.known_rule_names()
        for name in sorted(detail):
            if name in known:
                continue
            raw = (detail.get(name) or "").split(",")[0].strip()
            try:
                addr = normalize_addr(raw)
            except AddrError:
                self.log("[警告] 遗留规则 %s 的远端地址无法识别（%s），已保留未删除" % (name, raw or "空"))
                continue
            if addr in seen:
                continue
            seen.add(addr)
            if self.is_allowed(addr):
                firewall_delete_by_name(name)
                continue
            created, _ = self.block(addr, note="从防火墙规则恢复", source="恢复", expires=None)
            if created:
                adopted.append(addr)
        return adopted


# ---------------------------------------------------------------- 自启动
def set_autostart(enable: bool):
    task = "IPAutoBlock"
    if enable:
        exe = sys.executable
        if getattr(sys, "frozen", False):
            target = '"%s" --minimized' % exe
        else:
            target = '"%s" "%s" --minimized' % (exe, os.path.abspath(sys.argv[0]))
        rc, out = run_hidden([
            system_exe("schtasks"), "/create", "/tn", task, "/tr", target,
            "/sc", "onlogon", "/rl", "HIGHEST", "/f",
        ], timeout=45)
        return rc == 0, out
    rc, out = run_hidden([system_exe("schtasks"), "/delete", "/tn", task, "/f"], timeout=45)
    return rc == 0 or "找不到" in out or "cannot find" in out.lower(), out


def single_instance_guard():
    """返回 (mutex_handle, 是否已存在实例)。"""
    global _MUTEX_HANDLE
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        _MUTEX_HANDLE = handle
        return handle, ctypes.windll.kernel32.GetLastError() == 183
    except Exception:
        return None, False


_MUTEX_HANDLE = None


def another_instance_running() -> bool:
    """检测是否已有实例持有互斥量。"""
    try:
        handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def resource_path(name: str) -> str:
    """兼容 PyInstaller 单文件模式的资源路径。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidate = os.path.join(base, name)
        if os.path.exists(candidate):
            return candidate
    here = os.path.dirname(os.path.abspath(sys.argv[0]))
    candidate = os.path.join(here, name)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
