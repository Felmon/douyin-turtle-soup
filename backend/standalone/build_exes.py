"""
构建独立 EXE
用法: python build_exes.py [--clean]
"""
import os
import shutil
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)  # backend/ 目录
_DIST = os.path.join(_HERE, "dist")

SCRIPTS = [
    ("admin_console.py", "haiyutang-console.exe"),
]


def _build_license_pyd():
    """编译 license.py 为 .pyd（出错时仅警告，不阻塞）"""
    try:
        import Cython  # noqa: F401
    except ImportError:
        print("  [SKIP] Cython 未安装，跳过 license.py 编译")
        return
    try:
        from build_license_pyd import build_pyd
        build_pyd()
    except Exception as e:
        print(f"  [WARN] license.py 编译失败: {e}")


def _force_rmtree(path: str, retries: int = 5, delay: float = 2.0):
    """递归删除目录，遇到锁定时重试。"""
    if not os.path.isdir(path):
        return
    for attempt in range(retries):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt < retries - 1:
                print(f"  [RETRY] 删除 {path} 被锁定，{delay}秒后重试 ({attempt+1}/{retries})")
                time.sleep(delay)
            else:
                # 最后一次尝试：逐个删除文件
                for root, dirs, files in os.walk(path, topdown=False):
                    for name in files:
                        fp = os.path.join(root, name)
                        for r in range(3):
                            try:
                                os.chmod(fp, 0o777)
                                os.remove(fp)
                                break
                            except PermissionError:
                                if r < 2:
                                    time.sleep(delay)
                try:
                    os.rmdir(path)
                except PermissionError:
                    print(f"  [WARN] 无法删除 {path}（被其他进程占用），跳过")


def build():
    if "--clean" in sys.argv and os.path.isdir(_DIST):
        _force_rmtree(_DIST)
        for f in ["admin_console.spec"]:
            p = os.path.join(_HERE, f)
            if os.path.isfile(p):
                os.remove(p)

    os.makedirs(_DIST, exist_ok=True)

    # ── 编译 license.py → .pyd（加固授权核心） ──
    _build_license_pyd()

    for script, out_name in SCRIPTS:
        script_path = os.path.join(_HERE, script)

        print(f"\n{'='*50}")
        print(f"Building: {script} -> {out_name}")
        print(f"{'='*50}")

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--name", os.path.splitext(out_name)[0],
            "--distpath", _DIST,
            "--workpath", os.path.join(_HERE, "build"),
            "--specpath", _HERE,
            # 将 admin.py 和 overlay.py 作为数据文件打包，EXE 运行时从 _MEIPASS 读取
            "--add-data", f"{os.path.join(_PARENT, 'admin.py')}{os.pathsep}.",
            "--add-data", f"{os.path.join(_PARENT, 'overlay.py')}{os.pathsep}.",
            # PyWebView 动态导入 + 平台 COM 组件
            "--hidden-import", "webview",
            "--hidden-import", "webview.platforms.win32",
            "--hidden-import", "webview.platforms.winforms",
            "--hidden-import", "bottle",
            "--hidden-import", "cryptography",
            "--noconfirm",
            script_path,
        ]

        subprocess.check_call(cmd, cwd=_HERE)

        # rename output
        built_exe = os.path.join(_DIST, f"{os.path.splitext(out_name)[0]}.exe")
        expected = os.path.join(_DIST, out_name)
        if os.path.isfile(built_exe) and built_exe != expected:
            os.replace(built_exe, expected)

        # cleanup
        for ext in [".spec"]:
            f = os.path.join(_HERE, f"{os.path.splitext(script)[0]}{ext}")
            if os.path.isfile(f):
                os.remove(f)

        build_dir = os.path.join(_HERE, "build")
        if os.path.isdir(build_dir):
            _force_rmtree(build_dir)

        size_mb = os.path.getsize(expected) / (1024 * 1024) if os.path.isfile(expected) else 0
        print(f"  [OK] {out_name}  ({size_mb:.1f} MB)")

    print(f"\n{'='*50}")
    print(f"  Build complete! Output: {_DIST}")
    print(f"  - Console EXE")
    print(f"{'='*50}")


if __name__ == "__main__":
    build()
