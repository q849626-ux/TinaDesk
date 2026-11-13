# -*- coding: utf-8 -*-
"""遥控桌面小窗（供你或脚本调用）：
    python ctl.py refresh          # 立刻刷新
    python ctl.py theme 墨色       # 换色：墨色 / 藏青 / 暖棕 / 原白
小窗每 2 秒检查一次 control.json，变化即生效。
"""
import json, os, sys, time

DATA_DIR = os.environ.get("TINA_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(DATA_DIR, "control.json")
THEMES = ("墨色", "藏青", "暖棕", "原白")


def main(argv):
    try:
        with open(PATH, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
    except Exception:
        d = {}
    if len(argv) >= 1 and argv[0] == "refresh":
        d["refresh"] = str(time.time())
    elif len(argv) >= 2 and argv[0] == "theme" and argv[1] in THEMES:
        d["theme"] = argv[1]
    else:
        print(__doc__)
        return 1
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    print("ok", d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
