# 小鲸洁 · 磁盘清理助手

小鲸洁是一个 Windows 版 Codex Skill。打开本地工作台，就能看到各盘还剩多少空间、哪些缓存值得先清，以及清完后系统盘预计能多出多少空间。

## 安装到 Codex

在 Codex 中发送下面这句话：

> 安装 https://github.com/jxshow/xiaojingjie 里的 skills/disk-review 技能。

安装后新开一个对话，输入 `$disk-review`，或说「用小鲸洁扫一下电脑」。需要 Windows 和 Python 3.11 或更高版本，运行时只使用 Python 标准库。

## 先用样本体验

在 PowerShell 中运行以下命令。浏览器会打开工作台，并用临时目录里的两组缓存和一个安装包演示清理、跳过、暂存和还原。

```powershell
git clone https://github.com/jxshow/xiaojingjie.git
Set-Location xiaojingjie
$session = Join-Path ([IO.Path]::GetTempPath()) ("xiaojingjie-" + [guid]::NewGuid())
python -B .\skills\disk-review\scripts\desk.py --sample --session-dir "$session"
```

要扫描本机，请结束样本服务，重新生成一个会话目录，并在启动命令中去掉 `--sample`。

## 从分析到清理

1. **看总览。** 首页显示各盘余量、占用排行，以及系统盘缓存候选中占比最大的一项。导入卡兹克 storage-analyzer 报告时，历史排行会标明原报告时间。
2. **逐项选择。** 可清理的缓存支持勾选或跳过。安装包可以暂存和还原，系统管理项可以打开相应的 Windows 设置。暂存在同一磁盘内移动文件，本身不会腾出空间。
3. **预览并确认。** 预览列出所选操作、路径与预计清除量。确认后，进度球显示实际处理进度，执行记录列出成功、跳过及卷可用空间变化。确认清除的缓存会永久删除。

首次启动只读扫描。服务仅监听本机回环地址，每次启动使用独立访问凭据。可通过 `--protect` 指定要保留的目录或文件。更多参数见[技能说明](skills/disk-review/SKILL.md)。
