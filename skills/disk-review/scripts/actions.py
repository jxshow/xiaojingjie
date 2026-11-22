"""Execute only handles and destinations derived from the server-side scan."""
import ctypes
import msvcrt
import os
from ctypes import wintypes
from pathlib import Path
from catalog import identity, intersects, ordinary

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
create = kernel.CreateFileW
create.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
create.restype = wintypes.HANDLE
final_path = kernel.GetFinalPathNameByHandleW
final_path.argtypes = [wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
dispose = kernel.SetFileInformationByHandle
dispose.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
close = kernel.CloseHandle
close.argtypes = [wintypes.HANDLE]

def clean(file, root, limits):
    p = file.path
    if root not in p.parents or any(intersects(p, other) for other in limits) or not ordinary(p):
        raise ValueError("路径已改变或受保护")
    handle = create(str(p), 0x10000 | 0x80, 0, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except OSError:
        close(handle)
        raise
    try:
        buf = ctypes.create_unicode_buffer(32768)
        length = final_path(handle, buf, len(buf), 0)
        if not 0 < length < len(buf) or Path(buf.value.removeprefix("\\\\?\\")) != p:
            raise ValueError("文件位置已改变")
        if identity(os.fstat(fd)) != file.identity or file.identity[-1] != 1:
            raise ValueError("文件内容或链接已改变")
        flag = ctypes.c_ubyte(1)
        if not dispose(handle, 4, ctypes.byref(flag), ctypes.sizeof(flag)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        os.close(fd)

def act(row, action, home, limits):
    p = row.path
    if action not in row.actions or any(intersects(p, other) for other in limits) or not ordinary(p):
        raise ValueError("此项操作不可用")
    if action == "locate":
        # Only open directories, including when a report refers to an executable.
        os.startfile(str(p if p.is_dir() else p.parent))
    elif action == "storage":
        os.startfile("ms-settings:storagesense")
    elif action == "apps":
        os.startfile("ms-settings:appsfeatures")
    else:
        downloads = home/"Downloads"
        hold = downloads/".disk-review-hold"
        if action not in ("hold","restore") or p.suffix.lower() not in (".exe",".msi"):
            raise ValueError("操作不可用")
        source, dest = (downloads,hold) if action == "hold" else (hold,downloads)
        target = dest/p.name
        if p.parent != source or any(intersects(target, other) for other in limits):
            raise ValueError("目标受保护")
        if identity(p.lstat()) != row.files[0].identity:
            raise ValueError("文件已变化，请重新扫描")
        dest.mkdir(exist_ok=True)
        if not ordinary(dest):
            raise ValueError("目录已变化")
        p.rename(target)  # Windows refuses to overwrite an existing destination.
