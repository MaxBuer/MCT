#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCT 打包脚本 - Build / Package Script

交互式（或命令行参数）打包：

  1) 是否打包 Python 运行环境（用 PyInstaller 生成独立 .exe）？
     - 是 → 再选：
         · 单文件版   (onefile)：一个 MCT.exe，携带全部依赖
         · 多文件集版 (onedir) ：dist/MCT/ 文件夹（exe + 依赖文件）
     - 否 → 生成「源码包」zip（不含 Python，需本机已安装 Python，
             解压后用 启动汉化助手.bat 运行）

用法：
  python build.py                     # 交互式选择
  python build.py --mode onefile      # 直接生成单文件 exe
  python build.py --mode onedir       # 直接生成多文件集 exe
  python build.py --mode source       # 直接生成源码包 zip
  python build.py --skip-install      # 不自动安装 PyInstaller（配合 --mode onefile/onedir 使用）
"""

import os
import shutil
import subprocess
import sys
import zipfile

APP_NAME = "MCT"
ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_ICO = os.path.join(ROOT, "logo", "logo.ico")
ICON_PNG = os.path.join(ROOT, "logo", "logo.png")
BAT_NAME = "启动汉化助手.bat"


# ---------------------------------------------------------------------------
# 交互输入
# ---------------------------------------------------------------------------
def ask_yes_no(prompt: str, default: str = "y") -> bool:
    while True:
        r = input(prompt).strip().lower()
        if not r:
            r = default
        if r in ("y", "yes", "是", "1"):
            return True
        if r in ("n", "no", "否", "0"):
            return False
        print("  请输入 y / n")


def ask_choice(prompt: str, options: dict, default: str = "1") -> str:
    print(prompt)
    for k, v in options.items():
        mark = "（默认）" if k == default else ""
        print(f"  [{k}] {v}{mark}")
    while True:
        r = input("请输入编号: ").strip() or default
        if r in options:
            return r
        print("  请输入有效编号")


# ---------------------------------------------------------------------------
# PyInstaller
# ---------------------------------------------------------------------------
def check_pyinstaller() -> bool:
    try:
        import PyInstaller
        print(f"✓ 已安装 PyInstaller {PyInstaller.__version__}")
        return True
    except ImportError:
        return False


def ensure_pyinstaller(skip_install: bool = False) -> bool:
    if check_pyinstaller():
        return True
    if skip_install:
        print("✗ 未安装 PyInstaller（已跳过自动安装）。请先执行：pip install pyinstaller")
        return False
    print("未检测到 PyInstaller，尝试自动安装（pip install pyinstaller）...")
    try:
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    except Exception as e:
        print(f"✗ 自动安装失败: {e}")
        return False
    if rc != 0:
        print("✗ PyInstaller 安装失败，请手动执行：pip install pyinstaller")
        return False
    return check_pyinstaller()


def build_exe(mode: str) -> bool:
    """mode: onefile | onedir"""
    for d in ("dist", "build"):
        p = os.path.join(ROOT, d)
        if os.path.exists(p):
            shutil.rmtree(p)
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
    ]
    # 图标（.ico 用于 Windows 可执行文件图标）
    if os.path.exists(ICON_ICO):
        cmd += ["--icon", ICON_ICO]
    else:
        print("提示: 未找到 logo/logo.ico，将不使用 exe 图标")
    cmd += [
        "--name", APP_NAME,
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", ROOT,
        # 附带 logo 资源（软件图标/详情卡片兜底图）
        "--add-data", "logo" + os.pathsep + "logo",
        "main.py",
    ]
    cmd.append("--onefile" if mode == "onefile" else "--onedir")

    print("开始构建（这可能耗时几分钟）...")
    print("> " + " ".join(cmd))
    try:
        rc = subprocess.call(cmd, cwd=ROOT)
    except Exception as e:
        print(f"✗ 构建异常: {e}")
        return False
    if rc != 0:
        print(f"✗ 构建失败（退出码 {rc}），详见上方 PyInstaller 输出")
        return False

    if mode == "onefile":
        exe = os.path.join(ROOT, "dist", APP_NAME + (".exe" if os.name == "nt" else ""))
        if os.path.exists(exe):
            print(f"\n✓ 单文件版生成成功: {exe}")
            return True
        print("✗ 未找到输出文件，构建可能失败")
        return False

    folder = os.path.join(ROOT, "dist", APP_NAME)
    if os.path.isdir(folder):
        print(f"\n✓ 多文件集版生成成功: {folder}")
        print(f"  主程序: {os.path.join(folder, APP_NAME + ('.exe' if os.name == 'nt' else ''))}")
        print("  提示: 分发时请保留整个文件夹")
        return True
    print("✗ 未找到输出文件夹，构建可能失败")
    return False


# ---------------------------------------------------------------------------
# 源码包（不打包 Python）
# ---------------------------------------------------------------------------
def collect_source_files() -> list:
    """收集源码包需要的文件（排除 __pycache__、测试、日志、构建产物）"""
    files = []
    for name in ("main.py", "README.md", "requirements.txt", BAT_NAME, "build.py"):
        if os.path.exists(os.path.join(ROOT, name)):
            files.append(name)
    for sub in ("utils", "workers"):
        base = os.path.join(ROOT, sub)
        if not os.path.isdir(base):
            continue
        for root, _, fs in os.walk(base):
            if "__pycache__" in root:
                continue
            for f in fs:
                if f.endswith(".py"):
                    files.append(os.path.relpath(os.path.join(root, f), ROOT))
    for root, _, fs in os.walk(os.path.join(ROOT, "logo")):
        for f in fs:
            files.append(os.path.relpath(os.path.join(root, f), ROOT))
    return sorted(set(files))


def build_source_zip() -> bool:
    files = collect_source_files()
    if not files:
        print("✗ 未收集到任何源码文件")
        return False
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    zip_path = os.path.join(ROOT, "dist", f"{APP_NAME}_源码包.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(os.path.join(ROOT, rel), rel)
    print(f"\n✓ 源码包生成成功: {zip_path}")
    print(f"  共 {len(files)} 个文件，不含 Python 运行环境")
    print(f"  使用: 解压后双击 {BAT_NAME}（需本机已安装 Python 3.11+）")
    return True


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="MCT 打包脚本")
    parser.add_argument("--mode", choices=["onefile", "onedir", "source"],
                        help="直接指定打包方式（跳过交互）：onefile=单文件 / onedir=多文件集 / source=源码包")
    parser.add_argument("--skip-install", action="store_true",
                        help="不自动安装 PyInstaller")
    args = parser.parse_args()

    print("=" * 56)
    print("  MCT · Minecraft 汉化助手 打包脚本")
    print("=" * 56)

    mode = args.mode
    if mode is None:
        bundle = ask_yes_no("是否打包 Python 运行环境（生成独立 .exe）？[Y/n] ", "y")
        if bundle:
            choice = ask_choice("选择打包类型：", {
                "1": "单文件版 (onefile) —— 单个 MCT.exe",
                "2": "多文件集版 (onedir) —— dist/MCT/ 文件夹",
            }, default="1")
            mode = "onefile" if choice == "1" else "onedir"
        else:
            mode = "source"

    if mode in ("onefile", "onedir"):
        if not ensure_pyinstaller(args.skip_install):
            return 1
        ok = build_exe(mode)
    else:
        ok = build_source_zip()

    print("=" * 56)
    print("完成 ✅" if ok else "失败 ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
