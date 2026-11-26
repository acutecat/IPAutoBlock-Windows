# 分支与发布流程

本项目从 `v1.0.0` 起采用两条长期分支：

| 分支 | 定位 | 允许的操作 |
| --- | --- | --- |
| `dev` | 开发分支，日常改动都先落这里 | 直接提交、频繁推送 |
| `main` | 稳定分支，只放经过验证的代码 | 只接受 `dev` 的 PR；合并即发版 |

## 日常开发

1. 在 `dev` 上修改代码，提交前改 `version.py`（如果需要升版本）。
2. 推送到 `dev`，GitHub Actions 自动运行 `CI`：
   - Windows + PyQt5 环境；
   - 安装 `requirements.txt`；
   - 执行 `tools/functional_test.py`，全部 PASS 才算通过。
3. 本地至少再跑一遍：

   ```powershell
   python tools\functional_test.py
   ```

4. CI 通过且本地冒烟无问题后，从 `dev` 向 `main` 开 Pull Request。
5. PR 的 CI 也必须通过，才允许合并到 `main`。

## 稳定分支准入（基础 bug 检查）

合并到 `main` 前，下面这些基础项必须逐项确认：

- [ ] 程序能正常启动，无 Qt / DLL 加载错误；
- [ ] 设置项改动后立即保存，不需要“应用”按钮；
- [ ] 自动封锁按“封锁时长（天）”生成到期时间，旧配置能正确迁移；
- [ ] 手动封锁默认永久，取消永久后能按天封锁；
- [ ] 允许名单、封锁名单、搜索、CSV 导出正常；
- [ ] 托盘、关于窗口、版本号显示正常；
- [ ] 配置损坏回退、旧防火墙规则认领正常；
- [ ] `tools/functional_test.py` 全部 PASS。

任何一项不通过，都留在 `dev` 修，不合并到 `main`。

## 发版

- `main` 合并后，`Release` 工作流自动执行：
  1. 再跑一遍完整测试（不通过不构建）；
  2. 用 PyInstaller 构建单文件 `IPAutoBlock.exe`；
  3. 上传构建产物；
  4. 以 `version.py` 的版本号创建 GitHub Release，例如 `v1.0.0`；
  5. 把 `IPAutoBlock-v1.0.0.exe` 挂到 Release，并写入 SHA256。
- 版本号只有一个来源：`version.py` 的 `APP_VERSION`。改版本只改这一处。
- 已经存在的同版本 Release 会覆盖 exe 资产并更新说明，不会重复创建。

## 紧急修复

- 从 `main` 拉 `hotfix/<问题>`，修完先向 `main` 开 PR；
- 合并发版后，再把 `main` 合回 `dev`，避免两条分支漂移。
