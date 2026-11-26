# IP 自动封锁（Windows 版）

复刻群晖 DSM「自动封锁 / 拒绝服务（DoS）保护」模块的 Windows 工具。监视 Windows 安全日志中的登录失败事件，在设定时间内失败次数超阈值的来源 IP 会被自动写入 Windows 防火墙阻止规则，并按设定时长自动解封。

界面按群晖 DSM 的设置面板与「允许 / 封锁名单」弹窗复刻：折叠分组、蓝色标题、勾选式开关、下划线页签、搜索与导出。

## 运行要求

- Windows 7 SP1 / Server 2008 R2 及以上（x64），推荐 Windows 10 / Server 2016 及以上；需要管理员权限（读写安全日志、修改防火墙规则）。
- 单文件 exe：`IPAutoBlock.exe`，双击后由 UAC 提权启动。
- 未提权时程序仍可打开，但只能查看，顶部会提示「以管理员身份重新启动」。
- 已把 `MSVCP140.dll` / `VCRUNTIME140.dll` 等 VC++ 运行库打进 exe，目标电脑无需单独安装；Server 2012 R2 等旧系统建议补装 `vc_redist.x64.exe` 与 UCRT 补丁 KB2999226。

## Windows Server 兼容性（QtCore DLL 加载失败修复）

- 旧版本用 Qt 6（PySide6），`Qt6Core.dll` 会加载 Windows 系统 ICU（`icuuc.dll` / `icuin.dll` / `icu.dll`）。这些 DLL 是 Windows 10 1703 才引入的，**Server 2016（1607）及更早系统没有**，于是报：

  ```
  Failed to execute script 'main' due to unhandled exception:
  DLL load failed while importing QtCore: 找不到指定的模块。
  ```

- 当前版本改用 **Qt 5.15（PyQt5）**：`Qt5Core.dll` 只依赖 VC++ 运行库和系统 UCRT，不依赖 ICU、不依赖 WinRT，Server 2016 / 2019 / 2022 可直接运行。
- exe 内已打包 `MSVCP140.dll` / `MSVCP140_1.dll` / `VCRUNTIME140.dll` / `VCRUNTIME140_1.dll`，避免服务器没装 VC++ 运行库导致二次加载失败。
- 打包入口改为 `launcher.py`：启动时若仍缺系统组件，不再弹 PyInstaller 的英文异常框，而是弹出中文提示（系统版本 / VC++ 运行库 / UCRT 补丁 / 先把 exe 复制到本地磁盘），并把完整 traceback 追加到 `%APPDATA%\IPAutoBlock\logs\startup.log`，方便把日志发回来定位。
- 如果目标服务器是 **Server 2012 R2 / 2008 R2**，请先安装 `vc_redist.x64.exe`（Visual C++ 2015-2022）和 UCRT 补丁 KB2999226；Server Core（无桌面体验）没有托盘，关闭窗口会直接退出，后台常驻需配合计划任务或 `--minimized`。

## 功能

| 模块 | 说明 |
| --- | --- |
| 自动封锁 | 开关、尝试登录次数、统计窗口（分钟）、封锁过期开关、封锁时长（天，默认 1 天）；自动封锁按该天数解封。设置项改动后立即写入配置，无需再点“应用” |
| 最近登录失败记录 | 按 1 小时 / 6 小时 / 24 小时 / 7 天读取历史失败事件，可多选后一键封锁，可导入 `.evtx` 副本 |
| 允许 / 封锁名单 | 双页签、新增（IP/网段/地址范围）、删除、导出 CSV、搜索、批量导入文本；封锁页签显示「封锁 IP / 原因 / 封锁时间 / 到期时间 / 来源」，IP 列按 `255.255.255.255` 宽度固定，剩余宽度留给原因（悬停显示完整原因），永久封锁的到期时间显示为「永久」 |
| 手动封锁时长 | 默认勾选「永久封锁」；取消「永久封锁」后可按天填写时长，默认沿用设置页的天数（例如 1、3） |
| 拒绝服务（DoS）保护 | 网络界面选择、启用开关、单 IP 并发连接阈值、临时封锁分钟 |
| 运行日志 | 时间戳日志、写入 `%APPDATA%\IPAutoBlock\logs\app.log`；每条 `[封锁]` 记录都带「封锁时间 + 到期时间 + 时长（如 30 分钟 / 6 小时 / 30 天）」，解封与到期解除也带原封锁时间 |
| 系统托盘 | 关闭窗口收进托盘继续后台监视；托盘菜单打开主界面 / 立即检查 / 打开日志目录 / 退出；双击图标恢复窗口 |
| 封锁通知 | 每次封锁弹出气泡（IP、来源、原因、到期），短时间连续封锁只弹首条，完整记录见日志 |
| 开机自启动 | 勾选后通过计划任务（ONLOGON + 最高权限 + `--minimized`）注册，开机直接静默驻留托盘，避免弹 UAC 和主窗口 |

## 工作方式

1. 后台线程每 6 秒执行一次：

   ```
   wevtutil qe Security "/q:*[System[(EventID=4625 or EventID=4771) and TimeCreated[timediff(@SystemTime) <= N]]]" /rd:true /f:xml /c:2000
   ```

   只取最近 `max(10, 2 × 统计分钟)` 分钟内的事件（按时间过滤，避免被其他类型事件挤掉），
   解析 4625（登录失败）与 4771（Kerberos 预认证失败）中的 `IpAddress`，按 IP 统计失败次数。

   **启动回溯**：程序启动时会把这个窗口内已经发生的失败事件一并计入，所以"重启前的攻击"同样能被识别和封锁，不再像早期版本那样把历史当成基线丢弃。

2. 达到阈值（且不在允许名单、不是本机 IP、未被封锁）时，调用：

   ```
   netsh advfirewall firewall add rule name=IPAutoBlock_In_<IP> dir=in action=block remoteip=<IP> ...
   netsh advfirewall firewall add rule name=IPAutoBlock_Out_<IP> dir=out action=block remoteip=<IP> ...
   ```

   入站与出站各一条规则，规则名统一以 `IPAutoBlock_` 开头，不会影响系统或其他软件的防火墙规则。

3. 每条封锁记录同时保存「封锁时间」（`added`，精确到秒）和「到期时间」（`expires`，永久封锁为空）；运行日志会写成 `[封锁] IP（来源），封锁时间 2026-11-25 14:00:00，到期时间 2026-11-25 14:30:00，时长 30 分钟`，永久封锁则显示 `永久封锁`。后台每 30 秒检查一次，到期自动删除规则并移出封锁名单，解封日志也会带原封锁时间。

4. DoS 保护：每 3 秒采样 `netstat -ano -p TCP`，统计单个远端 IP 的并发 TCP 连接数，超过阈值即临时封锁。Windows 防火墙没有 DSM 的 SYN 泛洪计数接口，故用并发连接数近似。

5. 安全护栏：`127.0.0.1`、`::1`、本机网卡地址、允许名单内的地址永远不会被自动封锁，避免把自己锁在门外。

## 后台运行与托盘

- 点窗口右上角关闭（X）不会退出程序，而是收进系统托盘，后台线程继续读日志、写防火墙规则、清理到期封锁；首次收起会弹一次说明气泡。
- 托盘图标：双击或单击恢复主窗口；右键菜单为「打开主界面 / 立即检查 / 打开日志目录 / 关于本程序 / 退出」。
- 「关于本程序」显示软件名、`Copyright © 2025-当前年份 GK.2`、使用限制（禁止商业项目 / 批量部署 / 二次打包分发、禁止逆向篡改）与权利声明，是独立弹窗，不占主界面空间。
- 托盘悬停提示会显示当前已封锁地址数量，非管理员时附带「权限不足」。
- 真正退出只有两条路：托盘菜单「退出」，或任务管理器结束进程。退出时会保存配置并停止监视线程。
- 每次封锁（自动封锁 / 手动封锁 / DoS 保护）都会弹气泡通知；2.5 秒内连续封锁只弹第一条，避免刷屏，完整记录写进运行日志。
- 图标统一：exe 文件图标、窗口/任务栏图标、托盘图标、主界面左上角图标、关于窗口图标全部来自同一张 `app_icon.png` 母版（`build\app_icon.ico` 由它导出 16–256 多尺寸），不再出现「矢量盾牌」与「位图盾牌」两套造型；母版去掉了原先右上角极小的「IP」字样，避免 16/32 px 下糊成一个白点。
- 开机自启动任务带 `--minimized` 参数：登录后不弹主窗口，直接静默驻留托盘（托盘不可用的环境下仍会正常显示窗口）。
- 也可以用命令行 `IPAutoBlock.exe --minimized` 手动以最小化方式启动。

## 配置与升级（不会因为换 exe 丢数据）

- 配置独立于程序存放：`%APPDATA%\IPAutoBlock\config.json`。**替换 / 升级 / 挪动 exe 路径都不影响配置和名单**，新版本读的是同一份文件。
- 封锁过期统一按天保存；旧版配置里的 `auto.expiry_minutes` 会向上换算成 `auto.days`，例如 43200 分钟升级后为 30 天；旧封锁记录里的封锁/到期时间原样保留。
- 每次启动会把当前配置快照到 `%APPDATA%\IPAutoBlock\backups\config-<时间>.json`，保留最近 10 份；每次保存前还会留一份 `config.json.bak`。
- 主配置损坏（JSON 读不出）时自动回退到 `config.json.bak`，运行日志里会提示已从备份恢复。
- 更关键的一层保护：如果配置里的封锁名单为空、但防火墙里仍有 `IPAutoBlock_*` 规则（例如旧版本遗留、配置被误删），新版会把它们**认领回封锁名单**（来源标记为「恢复」，永久生效），而不是像旧版那样当成孤儿规则删掉。可在「允许 / 封锁名单 → 封锁名单」里看到并手动解除。
- 想彻底重置：先删规则，再删配置目录，否则下次启动会按照规则把名单认领回来：

  ```powershell
  Get-NetFirewallRule -DisplayName 'IPAutoBlock_*' | Remove-NetFirewallRule
  Remove-Item "$env:APPDATA\IPAutoBlock" -Recurse -Force
  ```

## 文件位置

- 配置：`%APPDATA%\IPAutoBlock\config.json`
- 配置备份：`%APPDATA%\IPAutoBlock\backups\config-*.json`（最近 10 份）、`config.json.bak`
- 日志：`%APPDATA%\IPAutoBlock\logs\app.log`
- 防火墙规则：`IPAutoBlock_In_*` / `IPAutoBlock_Out_*`

完全清理（管理员 PowerShell）：

```powershell
Get-NetFirewallRule -DisplayName 'IPAutoBlock_*' | Remove-NetFirewallRule
Remove-Item "$env:APPDATA\IPAutoBlock" -Recurse -Force
```

## 源码结构

```
IPAutoBlock/
├─ launcher.py       打包入口：捕获 Qt 加载失败并给出中文提示 / 写 startup.log
├─ main.py           主界面、设置与名单逻辑
├─ qtui.py           DSM 风格控件、允许 / 封锁名单窗口、关于窗口
├─ core.py           配置存储、防火墙、安全日志监视、DoS 检测
├─ app_icon.png      应用图标母版（512×512，exe/窗口/托盘/关于统一使用）
├─ build\app_icon.ico 由母版导出的多尺寸图标（16/24/32/48/64/128/256）
├─ build.ps1         一键打包脚本
└─ tools/            开发辅助（界面截图、功能自测、图标生成）
```

## 自行打包

需要 Python 3.10+（含 PyQt5 与 PyInstaller）：

```powershell
python -m venv C:\Users\<你>\ipab-qt5
python -m pip --python C:\Users\<你>\ipab-qt5\Scripts\python.exe install "PyQt5==5.15.11" "PyQt5-Qt5>=5.15.2,<5.16" pyinstaller pillow
python tools\make_ico_from_png.py   # 从 app_icon.png 生成 build\app_icon.ico
.\build.ps1
```

或直接执行（注意 icon / add-data 用绝对路径，PyInstaller 会按 specpath 解析相对路径）：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
  --name IPAutoBlock --icon "<项目>\build\app_icon.ico" ^
  --add-data "<项目>\app_icon.png;." --add-data "<项目>\build\app_icon.ico;." ^
  launcher.py
```

产物：`dist\IPAutoBlock.exe`（约 38 MB，单文件，无需安装 Python）。

## 读不到历史失败记录时

按下面顺序排查（本机实测过前两条）：

1. **没有以管理员身份运行**。`C:\Windows\System32\winevt\Logs\Security.evtx` 的 ACL 只允许 SYSTEM / Administrators 读取，普通用户执行 `wevtutil qe Security` 直接返回 `Access is denied`。界面右上角会显示「以管理员身份重新启动」，点它提权重开即可。
2. **没有开启登录失败审核**。用管理员 PowerShell 执行：

   ```powershell
   auditpol /get /subcategory:"登录"
   ```

   若「失败」为「无」，在 `secpol.msc` → 本地策略 → 审核策略 →「审核登录事件」勾选「失败」，或执行 `auditpol /set /subcategory:"登录" /failure:enable`。策略生效后需要产生新的失败登录才会写日志，旧的空档补不回来。
3. **事件里没有来源 IP**。控制台本地登录失败、部分服务账户登录的 `IpAddress` 为 `-`，这类事件没有可封锁对象，程序会跳过（日志里不会出现对应记录）。
4. **日志被其他事件挤掉**。旧版本固定取最新 300 条，安全日志事件量大时窗口可能只覆盖几秒。现在查询改为按 `timediff` 时间过滤、上限 2000 条，不再受其他事件数量影响。

想核对"到底有没有记录"，可直接在「最近的登录失败记录」里选 24 小时 / 7 天刷新；也可以在管理员 PowerShell 里手工验证：

```powershell
wevtutil qe Security "/q:*[System[(EventID=4625 or EventID=4771) and TimeCreated[timediff(@SystemTime) <= 86400000]]]" /c:20 /rd:true /f:text
```

从**其他电脑**取历史：用管理员把对方的 `Security.evtx` 复制出来（系统目录下的原文件普通用户读不了），在本机点「导入 .evtx」选择该副本即可离线解析，再「封锁选中」。

## 已知限制

- 只统计安全日志中带来源 IP 的失败事件；控制台本地登录失败通常为 `-`，不会触发封锁。
- 读取安全日志依赖「审核登录事件」策略；默认域/本地策略一般已开启登录失败审核，若日志里没有 4625，可在 `secpol.msc` 中开启「审核登录事件 - 失败」。
- DoS 检测基于 `netstat` 采样，属于近似实现，阈值建议结合实际业务压测调整。
- 防火墙规则为「阻止该 IP 的全部入站/出站流量」，与群晖一致；如需只拦某个端口，请改用其他工具。
- 托盘依赖 Windows 资源管理器（Explorer）的通知区域；Server Core / 无桌面的会话里没有托盘，此时关闭窗口会直接退出程序，后台常驻请配合「开机自启动」或 `--minimized`。

## 安全提示

- 首次使用建议先把管理终端的 IP 加入允许名单，再启用自动封锁。
- 程序不会修改非 `IPAutoBlock_` 前缀的规则；但仍建议在服务器上操作前先了解防火墙现状。

## 版权与使用限制

```text
IP 自动封锁工具
Copyright © 2025-当前年份 GK.2
禁止用于商业项目、批量部署、二次打包分发。 禁止逆向、篡改程序。
GK.2 All rights reserved. GK.2保留所有权利.
```

