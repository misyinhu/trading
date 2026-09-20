#!/usr/bin/env python3
"""add_simnow_secrets.py — 将 SimNow 凭证安全写入 secrets.toml

用法:
    python add_simnow_secrets.py
    # 交互式输入账号密码

    # 或直接传参:
    python add_simnow_secrets.py --user misyinhu --password xxx --flag sim
"""

import sys
import os
import argparse
from pathlib import Path


def get_secrets_path() -> Path:
    """查找 secrets.toml 路径"""
    candidates = [
        Path(__file__).parent.parent / ".streamlit" / "secrets.toml",
        Path(__file__).parent.parent / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    for p in candidates:
        if p.exists():
            return p
    # 不存在就创建第一个候选
    p = candidates[0]
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_secrets(path: Path) -> dict[str, str]:
    """解析现有 secrets.toml"""
    data = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def write_secrets(path: Path, data: dict[str, str]):
    """写回 secrets.toml"""
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    # 找出非空最后一行
    if lines and lines[-1].strip():
        lines.append("")  # 末尾加空行

    lines.append("# === SimNow 凭证 ===")
    for key, val in sorted(data.items()):
        # 避免重复键
        if any(line.strip().startswith(f"{key} =") for line in lines):
            continue
        lines.append(f'{key} = "{val}"')

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] 写入 {path}")


def main():
    parser = argparse.ArgumentParser(description="配置 SimNow 凭证")
    parser.add_argument("--user", help="SimNow 账号")
    parser.add_argument("--password", help="SimNow 密码")
    parser.add_argument(
        "--flag",
        default="sim",
        choices=["sim", "live"],
        help="sim=模拟盘, live=实盘",
    )
    args = parser.parse_args()

    path = get_secrets_path()
    print(f"secrets 路径: {path}")

    data = read_secrets(path)
    prefix = "SIMNOW_SIM" if args.flag == "sim" else "SIMNOW_LIVE"

    user = args.user or input(f"{prefix}_USER（账号）: ").strip()
    password = args.password or input(f"{prefix}_PASSWORD（密码）: ").strip()

    if not user or not password:
        print("[ABORT] 账号和密码不能为空")
        sys.exit(1)

    data[f"{prefix}_USER"] = user
    data[f"{prefix}_PASSWORD"] = password

    write_secrets(path, data)
    print(f"[DONE] SimNow {args.flag} 凭证已保存（密码已写入 secrets.toml）")


if __name__ == "__main__":
    main()
