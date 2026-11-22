"""Read-only discovery. Only built-in cache rules can create a destructive capability."""
import ctypes
import os
import shutil
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class File:
    path: Path
    identity: tuple

    @property
    def size(self):
        return self.identity[2]

def identity(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink)

def ordinary(path):
    """Reject links and other reparse points, including ancestors."""
    for part in (path, *path.parents):
        s = part.lstat()
        if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
            return False
    return True

def fixed(path):
    return (path.is_absolute() and len(path.drive) == 2
            and ctypes.windll.kernel32.GetDriveTypeW(path.anchor) == 3
            and ":" not in str(path)[2:] and ".." not in path.parts)

def intersects(a, b):
    return a == b or a in b.parents or b in a.parents

@dataclass
class Row:
    key: str
    name: str
    path: Path
    kind: str
    detail: str
    actions: tuple
    files: list = field(default_factory=list)
    size: int = 0
    estimate: str = ""
    errors: int = 0

    def public(self):
        return dict(id=self.key, name=self.name, path=str(self.path), kind=self.kind,
                    detail=self.detail, actions=self.actions, size=self.size,
                    estimate=self.estimate, count=len(self.files), errors=self.errors)

def cache_files(root, limits):
    result = []
    errors = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            if not ordinary(directory):
                continue
            if (directory/".git").exists():
                errors += 1
                continue
            with os.scandir(directory) as stream:
                for entry in stream:
                    try:
                        path = Path(entry.path)
                        s = entry.stat(follow_symlinks=False)
                        if getattr(s, "st_file_attributes", 0) & (0x400 | 0x1000):
                            continue
                        if any(intersects(path, limit) for limit in limits):
                            continue
                        if stat.S_ISDIR(s.st_mode):
                            pending.append(path)
                        elif stat.S_ISREG(s.st_mode):
                            # DirEntry.stat on Windows may omit inode and link count.
                            s = path.lstat()
                            if s.st_nlink == 1 and s.st_ino and not (s.st_file_attributes & 0x400):
                                result.append(File(path, identity(s)))
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return result, errors

def volumes():
    records = []
    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(char + ":/")
        if fixed(root):
            try:
                used = shutil.disk_usage(root)
                records.append(dict(name=root.drive, free=used.free, total=used.total))
            except OSError:
                continue
    return records

def bounded_directory_size(root):
    pending = [root]
    total = 0
    partial = False
    deadline = time.monotonic() + 2
    while pending:
        try:
            current = pending.pop()
            if not ordinary(current):
                continue
            with os.scandir(current) as stream:
                for entry in stream:
                    if time.monotonic() >= deadline:
                        return total, True
                    s = entry.stat(follow_symlinks=False)
                    if s.st_file_attributes & (0x400 | 0x1000):
                        continue
                    if stat.S_ISDIR(s.st_mode):
                        pending.append(Path(entry.path))
                    elif stat.S_ISREG(s.st_mode):
                        total += s.st_size
        except OSError:
            partial = True
    return total, partial

def discover(local, home, report, limits, notify, sample=False):
    rows = []
    seen = set()
    warnings = []
    def add(name, path, kind, detail, actions, measured=False, estimate=""):
        path = Path(path)
        if not fixed(path) or not path.exists() or (path in seen and not estimate):
            return
        if not ordinary(path):
            warnings.append("跳过链接或重解析位置 · " + str(path))
            return
        seen.add(path)
        protected = any(intersects(path, other) for other in limits)
        if protected:
            kind, actions = "protected", ()
        row = Row(str(len(rows) + 1), name, path, kind, detail, actions, estimate=estimate)
        if measured and not protected:
            row.files, row.errors = cache_files(path, limits)
            row.size = sum(f.size for f in row.files)
            if not row.files:
                if row.errors:
                    warnings.append("无法完整读取 · " + str(path))
                return
        rows.append(row)
    for name, base in (("Chrome", local/"Google/Chrome/User Data"),
                       ("Edge", local/"Microsoft/Edge/User Data")):
        notify(name + " 浏览器缓存")
        if base.is_dir() and fixed(base) and ordinary(base):
            for profile in sorted(base.iterdir()):
                if profile.name == "Default" or profile.name.startswith("Profile ") and profile.name[8:].isdigit():
                    add(name+" · "+profile.name, profile/"Cache", "safe",
                        "网页资源可以重新下载。执行时跳过已变化及占用中的文件。", ("clean",), True)
                    add(name+" 编译缓存 · "+profile.name, profile/"Code Cache", "safe",
                        "浏览器可重新编译这些脚本。首次访问相关网页时可能稍慢。", ("clean",), True)
    for name, folder, desc in (
        ("DirectX 着色器缓存", "NVIDIA/DXCache", "清理后游戏或图形应用可能需要重新编译着色器。"),
        ("pip 下载缓存", "pip/cache/http-v2", "包索引和下载响应可重新获取，离线安装可能需要重新联网。"),
    ):
        notify(name)
        add(name, local/folder, "safe", desc, ("clean",), True)
    downloads = home/"Downloads"
    notify("下载目录与安装包")
    if downloads.is_dir() and fixed(downloads) and ordinary(downloads):
        for p in sorted(downloads.iterdir()):
            if p.suffix.lower() in (".exe", ".msi") and p.is_file():
                add("下载的安装包 · "+p.name, p, "review",
                    "可能用于离线安装。暂存会把文件移入下载目录的 .disk-review-hold，下次扫描可以还原。", ("hold","locate"))
                if rows and rows[-1].path == p:
                    s = p.lstat()
                    rows[-1].size = s.st_size
                    rows[-1].files = [File(p, identity(s))]
            elif p.is_file() and ordinary(p) and p.stat().st_size >= 256*1024**2:
                add("大文件 · "+p.name,p,"review","下载的文件可能是唯一副本。请先查看文件位置和备份。",("locate",))
                if rows and rows[-1].path == p:
                    rows[-1].size = p.stat().st_size
        held = downloads/".disk-review-hold"
        if held.is_dir() and ordinary(held):
            for p in sorted(held.iterdir()):
                if p.suffix.lower() in (".exe", ".msi") and p.is_file():
                    add("已暂存 · "+p.name, p, "review","还原到下载目录。同名文件存在时跳过。", ("restore","locate"))
                    if rows and rows[-1].path == p:
                        s = p.lstat()
                        rows[-1].files = [File(p, identity(s))]
                        rows[-1].size = s.st_size
    if sample:
        return rows,warnings
    if report:
        for tier in ("yellow","red"):
            for item in report.get(tier, []):
                p = Path(item["path"])
                note = " ".join(str(item.get(k, "")) for k in ("content_profile","why_manual","disposal","risk","why_keep","indirect_release") if item.get(k))
                ops = ("apps","locate") if tier == "red" else ("locate",)
                if p == Path(os.environ["SystemRoot"])/"SoftwareDistribution/Download":
                    ops = ("storage","locate")
                add(item["name"], p, "review", "上次报告记录，"+note, ops, estimate=item.get("size",""))
    for name,p,desc,actions in (
        ("模型下载目录", home/".cache/huggingface/hub","可能含离线使用的模型，先核对模型版本和依赖。",("locate",)),
        ("Windows 更新暂存", Path(os.environ["SystemRoot"])/"SoftwareDistribution/Download","由 Windows 判断可回收的更新文件。",("storage","locate")),
        ("Codex 运行环境", home/".cache/codex-runtimes","当前运行时和回滚版本共用此目录，先核对版本。",("locate",)),
        ("npm 包缓存", local/"npm-cache/_cacache","包索引与内容有配套关系。可先通过 npm cache verify 做完整性检查。",("locate",)),
    ):
        if p in seen:
            continue
        notify(name)
        add(name,p,"review",desc,actions)
        if rows and rows[-1].path == p and rows[-1].kind == "review":
            row = rows[-1]
            row.size, partial = bounded_directory_size(p)
            if partial:
                row.name += "（部分统计）"
    return rows,warnings
