"""单实例守卫：Windows 用命名互斥体，其它平台退化为锁文件。

这是桌面 App 的常规行为：避免用户重复双击开出多个窗口、各自持有插件目录。
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self, name: str, lock_dir: Path | None = None):
        self._name = name
        self._mutex = None
        self._lock_file = None
        self._lock_path = (lock_dir / f"{name}.lock") if lock_dir else None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            return self._acquire_windows()
        return self._acquire_posix()

    def release(self) -> None:
        if self._mutex is not None:
            try:
                ctypes.windll.kernel32.ReleaseMutex(self._mutex)
                ctypes.windll.kernel32.CloseHandle(self._mutex)
            except Exception:  # noqa: BLE001
                pass
            self._mutex = None
        if self._lock_file is not None:
            try:
                self._lock_file.close()
                if self._lock_path and self._lock_path.exists():
                    self._lock_path.unlink()
            except Exception:  # noqa: BLE001
                pass
            self._lock_file = None

    # ------------------------------------------------------------------
    def _acquire_windows(self) -> bool:
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, f"Local\\{self._name}")
            if not handle:
                return True  # 拿不到互斥体就放行，不能因为守卫本身让用户打不开应用
            if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return False
            self._mutex = handle
            return True
        except Exception:  # noqa: BLE001
            return True

    def _acquire_posix(self) -> bool:
        if self._lock_path is None:
            return True
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._lock_path, "w")
        try:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:  # noqa: BLE001
            handle.close()
            return False
        handle.write(str(os.getpid()))
        handle.flush()
        self._lock_file = handle
        return True
