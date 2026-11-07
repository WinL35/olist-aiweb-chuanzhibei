#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成演示视频二维码（评审核用）。

用法：
    python scripts/make_qr.py --url "https://www.bilibili.com/video/BVxxxx"
    python scripts/make_qr.py            # 只看当前状态

生成：提交材料/qr_video.png（随后运行 build_submission.py 会自动嵌入 PDF）

注意：链接必须**无需登录即可打开**。若设置了访问权限，评委扫码打不开，
按大赛规则后果由选手承担——所以这里会检查一次链接可达性。
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "_vendor"))

OUT = ROOT / "提交材料" / "qr_video.png"


def reachable(url: str) -> tuple[bool, str]:
    """宽松探测：能拿到任何 HTTP 响应就算可达（不少平台不接受 HEAD）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return True, f"HTTP {r.status}"
    except Exception as e:
        code = getattr(e, "code", None)
        if code:
            return True, f"HTTP {code}（有响应，可能需登录，请人工确认）"
        return False, f"{type(e).__name__}: {e}"


def make(url: str) -> Path:
    import qrcode
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=12, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    return OUT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="", help="演示视频链接")
    ap.add_argument("--no-check", action="store_true", help="跳过可达性检查")
    a = ap.parse_args()

    if not a.url:
        if OUT.is_file():
            print(f"已存在二维码：{OUT.relative_to(ROOT)}")
            print("如需替换：python scripts/make_qr.py --url <新链接>")
        else:
            print("还没有二维码。请运行：python scripts/make_qr.py --url <视频链接>")
        return 0

    if not a.url.startswith(("http://", "https://")):
        print("链接需以 http(s):// 开头")
        return 2

    ok, msg = (True, "已跳过检查") if a.no_check else reachable(a.url)
    print(f"可达性：{'OK' if ok else '失败'} — {msg}")
    if not ok:
        print("⚠️ 链接打不开，评委扫码会失败。确认后再加 --no-check 强制生成。")
        return 1

    p = make(a.url)
    print(f"✅ 二维码已生成：{p.relative_to(ROOT)}（{p.stat().st_size / 1024:.1f} KB）")
    print("提示：重新运行 python scripts/build_submission.py 即会嵌入 PDF。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())