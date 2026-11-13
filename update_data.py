# -*- coding: utf-8 -*-
"""每日数据更新（不依赖 AI，只用 Python 标准库）。

    python update_data.py prices   # 只更新行情 -> prices.json
    python update_data.py tasks    # 只更新任务 -> econ_news.json / english_words.json / deals.json
    python update_data.py all      # 全部（默认）
    python update_data.py all --check   # 在控制台逐项打印每个数据源成功与否，用来排错

原则：任何数据源失败都不会清空旧数据，会沿用上一次的值；失败原因写进 update.log。
"""
import html
import json
import os
import random
import re
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# 数据目录：环境变量 TINA_DATA_DIR > 程序（或 exe）所在目录
DATA_DIR = os.environ.get("TINA_DATA_DIR") or os.path.dirname(
    sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))

CN = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
CHECK = "--check" in sys.argv


def P(name):
    return os.path.join(DATA_DIR, name)


def log(msg):
    line = f"{datetime.now(CN):%Y-%m-%d %H:%M:%S}  {msg}"
    if CHECK:
        print(line)
    try:
        lp = P("update.log")
        lines = []
        if os.path.exists(lp):
            with open(lp, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()[-300:]
        lines.append(line)
        with open(lp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


def http_get(url, headers=None, encoding="utf-8", timeout=20):
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(encoding, errors="replace")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def fnum(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def pct(now, prev):
    if now is None or not prev:
        return None
    return round((now / prev - 1) * 100, 2)


# ═════════════════════════ 行情 ═════════════════════════
# 首次打开使用下面这份默认清单；用户在小窗里右键增删后，写入 watchlist.json。
WATCHLIST_FILE = "watchlist.json"
WATCHLIST_PATH = os.path.join(DATA_DIR, WATCHLIST_FILE)

DEFAULT_CRYPTO = [
    {"name": "比特币", "geckoid": "bitcoin", "okx": "BTC-USDT"},
    {"name": "以太坊", "geckoid": "ethereum", "okx": "ETH-USDT"},
    {"name": "狗狗币", "geckoid": "dogecoin", "okx": "DOGE-USDT"},
    {"name": "波场(TRON)", "geckoid": "tron", "okx": "TRX-USDT"},
    {"name": "门罗币", "geckoid": "monero", "okx": "XMR-USDT"},
    {"name": "BNB", "geckoid": "binancecoin", "okx": "BNB-USDT"},
]
DEFAULT_STOCKS = [
    {"name": "上证指数", "code": "sh000001"},
    {"name": "贵州茅台", "code": "sh600519"},
    {"name": "中国石油", "code": "sh601857"},
    {"name": "宇树科技", "code": "sh688836"},
    {"name": "长鑫科技", "code": "sh688825"},
    {"name": "英伟达", "code": "usNVDA"},
    {"name": "特斯拉", "code": "usTSLA"},
    {"name": "英特尔", "code": "usINTC"},
    {"name": "闪迪", "code": "usSNDK"},
]
DEFAULT_FX = [
    {"code": "USD", "label": "美元"},
    {"code": "EUR", "label": "欧元"},
    {"code": "AUD", "label": "澳元"},
    {"code": "JPY", "label": "日元"},
]
DEFAULT_OIL = [
    {"city": "西安", "adcode": "610100", "grades": ["92", "95"]},
]

# 常用币种别名，添加时先在这里匹配，找不到再去 CoinGecko 搜索
EXTRA_CRYPTO = [
    {"name": "索拉纳", "geckoid": "solana", "okx": "SOL-USDT", "aliases": ["sol", "solana"]},
    {"name": "瑞波币", "geckoid": "ripple", "okx": "XRP-USDT", "aliases": ["xrp", "ripple"]},
    {"name": "艾达币", "geckoid": "cardano", "okx": "ADA-USDT", "aliases": ["ada", "cardano"]},
    {"name": "雪崩", "geckoid": "avalanche-2", "okx": "AVAX-USDT", "aliases": ["avax", "avalanche"]},
    {"name": "波卡", "geckoid": "polkadot", "okx": "DOT-USDT", "aliases": ["dot", "polkadot"]},
    {"name": "Chainlink", "geckoid": "chainlink", "okx": "LINK-USDT", "aliases": ["link", "chainlink"]},
    {"name": "Polygon", "geckoid": "matic-network", "okx": "MATIC-USDT", "aliases": ["matic", "polygon", "pol"]},
    {"name": "TON", "geckoid": "the-open-network", "okx": "TON-USDT", "aliases": ["ton", "toncoin"]},
    {"name": "Sui", "geckoid": "sui", "okx": "SUI-USDT", "aliases": ["sui"]},
    {"name": "莱特币", "geckoid": "litecoin", "okx": "LTC-USDT", "aliases": ["ltc", "litecoin"]},
    {"name": "比特币现金", "geckoid": "bitcoin-cash", "okx": "BCH-USDT", "aliases": ["bch"]},
    {"name": "Uniswap", "geckoid": "uniswap", "okx": "UNI-USDT", "aliases": ["uni"]},
    {"name": "Shiba Inu", "geckoid": "shiba-inu", "okx": "SHIB-USDT", "aliases": ["shib"]},
    {"name": "Pepe", "geckoid": "pepe", "okx": "PEPE-USDT", "aliases": ["pepe"]},
    {"name": "Aptos", "geckoid": "aptos", "okx": "APT-USDT", "aliases": ["apt"]},
    {"name": "Filecoin", "geckoid": "filecoin", "okx": "FIL-USDT", "aliases": ["fil"]},
    {"name": "NEAR", "geckoid": "near", "okx": "NEAR-USDT", "aliases": ["near"]},
    {"name": "以太经典", "geckoid": "ethereum-classic", "okx": "ETC-USDT", "aliases": ["etc"]},
    {"name": "宇宙", "geckoid": "cosmos", "okx": "ATOM-USDT", "aliases": ["atom", "cosmos"]},
]

FX_CURRENCIES = [
    ("USD", "美元"), ("EUR", "欧元"), ("JPY", "日元"), ("GBP", "英镑"),
    ("HKD", "港元"), ("AUD", "澳元"), ("CAD", "加元"), ("SGD", "新加坡元"),
    ("CHF", "瑞士法郎"), ("NZD", "新西兰元"), ("KRW", "韩元"), ("THB", "泰铢"),
    ("MYR", "林吉特"), ("RUB", "卢布"), ("MOP", "澳门元"), ("DKK", "丹麦克朗"),
    ("SEK", "瑞典克朗"), ("NOK", "挪威克朗"), ("ZAR", "南非兰特"),
    ("AED", "阿联酋迪拉姆"), ("SAR", "沙特里亚尔"), ("HUF", "匈牙利福林"),
    ("PLN", "波兰兹罗提"), ("TRY", "土耳其里拉"), ("MXN", "墨西哥比索"),
]
FX_PER100 = {"JPY", "KRW"}
FX_CN_ALIAS = {"港币": "港元", "美金": "美元", "日币": "日元", "韩币": "韩元", "韩圆": "韩元"}

# 汽车之家油价页用的城市行政区划代码
OIL_CITIES = [
    ("北京", "110100"), ("天津", "120100"), ("上海", "310100"), ("重庆", "500100"),
    ("石家庄", "130100"), ("唐山", "130200"), ("秦皇岛", "130300"), ("邯郸", "130400"),
    ("保定", "130600"), ("张家口", "130700"), ("承德", "130800"), ("廊坊", "131000"),
    ("太原", "140100"), ("大同", "140200"),
    ("呼和浩特", "150100"), ("包头", "150200"), ("鄂尔多斯", "150600"),
    ("沈阳", "210100"), ("大连", "210200"), ("长春", "220100"), ("哈尔滨", "230100"),
    ("南京", "320100"), ("无锡", "320200"), ("徐州", "320300"), ("常州", "320400"),
    ("苏州", "320500"), ("南通", "320600"), ("扬州", "321000"),
    ("杭州", "330100"), ("宁波", "330200"), ("温州", "330300"), ("嘉兴", "330400"),
    ("湖州", "330500"), ("绍兴", "330600"), ("金华", "330700"), ("台州", "331000"),
    ("合肥", "340100"), ("芜湖", "340200"),
    ("福州", "350100"), ("厦门", "350200"), ("泉州", "350500"), ("南昌", "360100"),
    ("济南", "370100"), ("青岛", "370200"), ("淄博", "370300"), ("烟台", "370600"),
    ("潍坊", "370700"), ("济宁", "370800"), ("威海", "371000"), ("临沂", "371300"),
    ("郑州", "410100"), ("洛阳", "410300"),
    ("武汉", "420100"), ("宜昌", "420500"), ("长沙", "430100"),
    ("广州", "440100"), ("深圳", "440300"), ("珠海", "440400"), ("汕头", "440500"),
    ("佛山", "440600"), ("江门", "440700"), ("湛江", "440800"), ("茂名", "440900"),
    ("惠州", "441300"), ("东莞", "441900"), ("中山", "442000"),
    ("南宁", "450100"), ("柳州", "450200"), ("桂林", "450300"),
    ("海口", "460100"), ("三亚", "460200"),
    ("成都", "510100"), ("绵阳", "510700"), ("贵阳", "520100"), ("昆明", "530100"),
    ("拉萨", "540100"),
    ("西安", "610100"), ("宝鸡", "610300"), ("咸阳", "610400"), ("延安", "610600"),
    ("榆林", "610800"),
    ("兰州", "620100"), ("西宁", "630100"), ("银川", "640100"), ("乌鲁木齐", "650100"),
]
GRADE_INFO = {
    "92": {"page": "92号汽油", "label": "92#汽油", "col": 1},
    "95": {"page": "95号汽油", "label": "95#汽油", "col": 2},
    "98": {"page": "98号汽油", "label": "98#汽油", "col": 3},
    "0": {"page": "0号柴油", "label": "0#柴油", "col": 4},
}
OIL_GRADE_ORDER = ["92", "95", "98", "0"]


def default_watchlist():
    return {
        "crypto": [dict(x) for x in DEFAULT_CRYPTO],
        "oil": [dict(x, grades=list(x["grades"])) for x in DEFAULT_OIL],
        "shares": [dict(x) for x in DEFAULT_STOCKS],
        "fx": [dict(x) for x in DEFAULT_FX],
    }


def load_watchlist():
    d = read_json(WATCHLIST_PATH, None)
    base = default_watchlist()
    if not isinstance(d, dict):
        return base
    for key in base:
        if isinstance(d.get(key), list):
            base[key] = d[key]
    return base


def save_watchlist(data):
    write_json(WATCHLIST_PATH, {
        "crypto": data.get("crypto") or [],
        "oil": data.get("oil") or [],
        "shares": data.get("shares") or [],
        "fx": data.get("fx") or [],
    })
    return True


def placeholder_items(cid):
    """本地还没有行情时，先用关注列表里的名称占位。"""
    wl = load_watchlist()
    if cid == "crypto":
        return [{"name": x.get("name") or "", "display": "—"} for x in wl.get("crypto") or []]
    if cid == "oil":
        out = []
        for e in wl.get("oil") or []:
            city = e.get("city") or ""
            for g in e.get("grades") or ["92", "95"]:
                label = (GRADE_INFO.get(g) or {}).get("label") or g
                out.append({"name": f"{city} {label}".strip(), "display": "—"})
        return out
    if cid == "shares":
        return [{"name": x.get("name") or x.get("code") or "", "display": "—"} for x in wl.get("shares") or []]
    if cid == "fx":
        return [{"name": f"汇率 {x.get('label') or x.get('code') or ''}".strip(), "display": "—"}
                for x in wl.get("fx") or []]
    if cid == "gold":
        return [{"name": "国内金价", "display": "—"}]
    return []


def _crypto_keys(item):
    keys = {str(item.get("name") or "").lower(), str(item.get("geckoid") or "").lower()}
    okx = str(item.get("okx") or "")
    if "-" in okx:
        keys.add(okx.split("-", 1)[0].lower())
    for a in item.get("aliases") or []:
        keys.add(str(a).lower())
    keys.discard("")
    return keys


def resolve_crypto(query):
    q = (query or "").strip()
    if not q:
        return None, "请输入币种名称或代码，例如 BTC、以太坊"
    ql = q.lower().lstrip("$")
    if ql.endswith("-usdt"):
        ql = ql[:-5]
    elif ql.endswith("usdt"):
        ql = ql[:-4]
    pool = list(DEFAULT_CRYPTO) + list(EXTRA_CRYPTO) + list(load_watchlist().get("crypto") or [])
    for it in pool:
        if ql in _crypto_keys(it) or q == it.get("name"):
            return {"name": it["name"], "geckoid": it["geckoid"], "okx": it["okx"]}, None
    try:
        d = json.loads(http_get("https://api.coingecko.com/api/v3/search?query=" + quote(q)))
        coins = d.get("coins") or []
    except Exception as e:
        return None, f"查找币种失败：{e}"
    if not coins:
        return None, f"没找到「{q}」，试试英文代码，例如 SOL、BTC"
    pick = next((c for c in coins
                 if str(c.get("symbol") or "").lower() == ql or str(c.get("id") or "").lower() == ql), None)
    if pick is None:
        pick = coins[0]
    symbol = str(pick.get("symbol") or "XXX").upper()
    name = q if any("\u4e00" <= ch <= "\u9fff" for ch in q) else (pick.get("name") or symbol)
    return {"name": name, "geckoid": pick["id"], "okx": f"{symbol}-USDT"}, None


def normalize_stock_code(q):
    s = (q or "").strip()
    if not s:
        return None
    sl = s.lower().replace(".", "").replace(" ", "")
    if sl.startswith("us") and len(sl) > 2 and sl[2:].isalpha():
        return "us" + sl[2:].upper()
    if re.fullmatch(r"hk\d{1,5}", sl):
        return "hk" + sl[2:].zfill(5)
    if re.fullmatch(r"(sh|sz|bj)\d{6}", sl):
        return sl
    if re.fullmatch(r"\d{6}", sl):
        if sl[0] in "569":
            return "sh" + sl
        if sl[0] in "0123":
            return "sz" + sl
        if sl[0] in "48":
            return "bj" + sl
        return "sh" + sl
    if re.fullmatch(r"\d{1,5}", sl):
        return "hk" + sl.zfill(5)
    if re.fullmatch(r"[a-z]{1,5}", sl):
        return "us" + sl.upper()
    return None


def resolve_stock(query):
    q = (query or "").strip()
    code = normalize_stock_code(q)
    if code is None:
        for it in list(DEFAULT_STOCKS) + list(load_watchlist().get("shares") or []):
            if it.get("name") == q:
                code = it.get("code")
                break
    if code is None:
        return None, "请输入股票代码，例如 600519、sz000001、AAPL、00700"
    try:
        txt = http_get("https://qt.gtimg.cn/q=" + code, encoding="gbk")
    except Exception as e:
        return None, f"查询失败：{e}"
    m = re.search(r'v_(\w+)="([^"]*)"', txt)
    if not m or not m.group(2):
        return None, f"没找到代码 {code}，请核对后重试"
    f = m.group(2).split("~")
    if len(f) < 4 or not fnum(f[3]):
        return None, f"没找到代码 {code}，请核对后重试"
    return {"name": f[1] or q, "code": code}, None


def resolve_fx(query):
    q = (query or "").strip()
    if not q:
        return None, "请输入货币名称或代码，例如 英镑、HKD、欧元"
    cleaned = q.replace("人民币", "").replace("兑", "").replace("/", "").replace("汇率", "").strip()
    cleaned = FX_CN_ALIAS.get(cleaned, cleaned)
    u = cleaned.upper()
    for code, label in FX_CURRENCIES:
        if u == code or cleaned == label or q == label:
            return {"code": code, "label": label}, None
    return None, "请输入货币名称或代码，例如 英镑、HKD、欧元"


def find_oil_city(query):
    q = (query or "").strip()
    if not q:
        return None, "请输入城市名，例如 北京、杭州、深圳"
    if re.fullmatch(r"\d{6}", q):
        for name, code in OIL_CITIES:
            if code == q:
                return (name, code), None
        return None, f"还没有收录代码 {q}，试试直接写城市名"
    if q.endswith("市") and len(q) > 1:
        q = q[:-1]
    for name, code in OIL_CITIES:
        if name == q:
            return (name, code), None
    hits = [(n, c) for n, c in OIL_CITIES if n.startswith(q) or q in n]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, "找到多个城市：" + "、".join(n for n, _ in hits[:8]) + "，请写全称"
    return None, f"还没有收录「{q}」，试试 北京、杭州、深圳 这样的城市名"


def _grade_short(g):
    return "0#柴油" if g == "0" else f"{g}#"


def watchlist_labels(kind):
    wl = load_watchlist()
    if kind == "crypto":
        return [x.get("name") or "" for x in wl.get("crypto") or []]
    if kind == "shares":
        return [f"{x.get('name') or ''}  {x.get('code') or ''}".strip() for x in wl.get("shares") or []]
    if kind == "fx":
        return [f"{x.get('label') or ''}  {x.get('code') or ''}".strip() for x in wl.get("fx") or []]
    if kind == "oil":
        out = []
        for x in wl.get("oil") or []:
            gs = "、".join(_grade_short(g) for g in (x.get("grades") or []))
            out.append(f"{x.get('city') or ''}  {gs}".strip())
        return out
    return []


def watchlist_add(kind, query, grades=None):
    wl = load_watchlist()
    if kind == "crypto":
        item, err = resolve_crypto(query)
        if err:
            return False, err
        if any(x.get("geckoid") == item["geckoid"] or x.get("name") == item["name"] for x in wl["crypto"]):
            return False, f"「{item['name']}」已经在列表里了"
        wl["crypto"].append(item)
        save_watchlist(wl)
        return True, f"已添加 {item['name']}"
    if kind == "shares":
        item, err = resolve_stock(query)
        if err:
            return False, err
        if any(x.get("code") == item["code"] for x in wl["shares"]):
            return False, f"「{item['name']}」已经在列表里了"
        wl["shares"].append(item)
        save_watchlist(wl)
        return True, f"已添加 {item['name']}（{item['code']}）"
    if kind == "fx":
        item, err = resolve_fx(query)
        if err:
            return False, err
        if any(x.get("code") == item["code"] for x in wl["fx"]):
            return False, f"「{item['label']}」已经在列表里了"
        wl["fx"].append(item)
        save_watchlist(wl)
        return True, f"已添加 {item['label']}"
    if kind == "oil":
        found, err = find_oil_city(query)
        if err:
            return False, err
        city, adcode = found
        want = [g for g in (grades or ["92", "95"]) if g in GRADE_INFO]
        if not want:
            return False, "请至少选一种油号（92 / 95 / 98 / 0号柴油）"
        for e in wl["oil"]:
            if e.get("adcode") == adcode or e.get("city") == city:
                have = e.get("grades") or []
                added = [g for g in want if g not in have]
                if not added:
                    return False, f"「{city}」的这些油号已经在列表里了"
                e["grades"] = [g for g in OIL_GRADE_ORDER if g in have + added]
                save_watchlist(wl)
                return True, f"已为{city}添加 " + "、".join(_grade_short(g) for g in added)
        wl["oil"].append({"city": city, "adcode": adcode, "grades": [g for g in OIL_GRADE_ORDER if g in want]})
        save_watchlist(wl)
        return True, f"已添加{city} " + "、".join(_grade_short(g) for g in want)
    return False, "未知栏目"


def watchlist_remove_at(kind, index):
    wl = load_watchlist()
    key = {"crypto": "crypto", "shares": "shares", "fx": "fx", "oil": "oil"}.get(kind)
    if not key or not (0 <= index < len(wl.get(key) or [])):
        return False, "没找到这一项"
    wl[key].pop(index)
    save_watchlist(wl)
    return True, "已删除"


def watchlist_remove_by_label(kind, label):
    """按小窗上正在显示的名称，删掉关注列表里对应的一项。"""
    wl = load_watchlist()
    label = (label or "").strip()
    if kind == "crypto":
        nxt = [x for x in wl["crypto"] if x.get("name") != label]
    elif kind == "shares":
        nxt = [x for x in wl["shares"] if x.get("name") != label]
    elif kind == "fx":
        lab = label.replace("汇率", "").strip()
        nxt = [x for x in wl["fx"] if x.get("label") != lab]
    elif kind == "oil":
        changed = False
        for e in wl["oil"]:
            city = e.get("city") or ""
            prefix = city + " "
            if not label.startswith(prefix):
                continue
            rest = label[len(prefix):]
            g = "0" if rest.startswith("0#") else (re.match(r"(\d+)#", rest).group(1) if re.match(r"(\d+)#", rest) else None)
            if g and g in (e.get("grades") or []):
                e["grades"] = [x for x in e["grades"] if x != g]
                changed = True
        if not changed:
            return False, "没找到这一项"
        wl["oil"] = [e for e in wl["oil"] if e.get("grades")]
        save_watchlist(wl)
        return True, "已删除"
    else:
        return False, "未知栏目"
    if kind in ("crypto", "shares", "fx"):
        if len(nxt) == len(wl[kind]):
            return False, "没找到这一项"
        wl[kind] = nxt
        save_watchlist(wl)
        return True, "已删除"
    return False, "没找到这一项"


def fetch_crypto():
    coins = load_watchlist().get("crypto") or []
    if not coins:
        return []
    got = {}
    try:
        ids = ",".join(c["geckoid"] for c in coins if c.get("geckoid"))
        d = json.loads(http_get("https://api.coingecko.com/api/v3/simple/price?ids=" + ids +
                                "&vs_currencies=usd&include_24hr_change=true"))
        for c in coins:
            cid = c.get("geckoid")
            if cid in d and d[cid].get("usd") is not None:
                ch = d[cid].get("usd_24h_change")
                got[c["name"]] = (float(d[cid]["usd"]), None if ch is None else round(float(ch), 2))
        log(f"crypto: CoinGecko 得到 {len(got)}/{len(coins)}")
    except Exception as e:
        log(f"crypto: CoinGecko 失败 {e!r}")
    for c in coins:
        name, inst = c.get("name"), c.get("okx")
        if name in got or not inst:
            continue
        try:
            d = json.loads(http_get("https://www.okx.com/api/v5/market/ticker?instId=" + inst))
            t = d["data"][0]
            last, op = float(t["last"]), float(t["open24h"])
            got[name] = (last, pct(last, op))
        except Exception as e:
            log(f"crypto: OKX {inst} 失败 {e!r}")
    items = [{"name": c["name"], "price": got[c["name"]][0], "change_pct": got[c["name"]][1]}
             for c in coins if c.get("name") in got]
    return items if items or not coins else None


def fetch_stocks():
    """腾讯行情接口；休市时返回的就是最近一次收盘价。"""
    stocks = load_watchlist().get("shares") or []
    if not stocks:
        return []
    try:
        txt = http_get("https://qt.gtimg.cn/q=" + ",".join(c["code"] for c in stocks if c.get("code")), encoding="gbk")
    except Exception as e:
        log(f"shares: 请求失败 {e!r}")
        return None
    data = {}
    for m in re.finditer(r'v_(\w+)="([^"]*)"', txt):
        f = m.group(2).split("~")
        if len(f) > 32:
            data[m.group(1)] = f
    items = []
    for it in stocks:
        name, code = it.get("name") or "", it.get("code") or ""
        f = data.get(code)
        price = fnum(f[3]) if f else None
        if not price:
            log(f"shares: {name}({code}) 无数据")
            continue
        ch = fnum(f[32])
        if ch is None:
            ch = pct(price, fnum(f[4]))
        items.append({"name": f[1] if f and f[1] else name, "price": price, "change_pct": ch, "code": code})
    log(f"shares: 得到 {len(items)}/{len(stocks)}")
    return items if items or not stocks else None


def fetch_gold():
    """上海黄金交易所 Au99.99（沪金99），元/克。新浪行情，需要 Referer。"""
    try:
        txt = http_get("https://hq.sinajs.cn/list=gds_AU9999",
                       headers={"Referer": "https://finance.sina.com.cn/"}, encoding="gbk")
        body = re.search(r'="([^"]*)"', txt).group(1).split(",")
        price = fnum(body[0])
        prev = fnum(body[7]) if len(body) > 7 else None
        if not price:
            raise ValueError("price empty: " + txt[:80])
        log(f"gold: {price} 昨收 {prev}")
        return [{"name": "国内金价", "price": price, "change_pct": pct(price, prev)}]
    except Exception as e:
        log(f"gold: 失败 {e!r}")
        return None


def fetch_fx():
    """中国外汇交易中心公布的人民币汇率中间价（最近一次已公布值）。"""
    wanted = load_watchlist().get("fx") or []
    if not wanted:
        return []
    try:
        d = json.loads(http_get(
            "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/ccpr.json",
            headers={"Referer": "https://www.chinamoney.com.cn/chinese/bkccpr/"}))
        recs = d.get("records", [])
    except Exception as e:
        log(f"fx: 失败 {e!r}")
        return None
    items = []
    for it in wanted:
        cur, label = it.get("code") or "", it.get("label") or it.get("code") or ""
        rec = next((r for r in recs if cur in str(r.get("vrtEName", "")).upper()), None)
        if not rec:
            log(f"fx: 没找到 {cur}")
            continue
        price = fnum(rec.get("price"))
        if price is None:
            continue
        bp = fnum(rec.get("bpDouble"))
        if bp is None:
            bp = fnum(rec.get("bp")) or 0.0
        if cur in FX_PER100:
            if price < 0.2:
                price *= 100
            disp = f"100{label} = {price:.4f} 元"
        else:
            disp = f"1{label} = {price:.4f} 元"
        if bp > 0:
            ct = f"较上日上调 {abs(bp):.0f} 个基点"
        elif bp < 0:
            ct = f"较上日下调 {abs(bp):.0f} 个基点"
        else:
            ct = "较上日持平"
        items.append({"name": f"汇率 {label}", "price": price, "display": disp, "change_text": ct})
    log(f"fx: 得到 {len(items)}/{len(wanted)}")
    return items if items or not wanted else None

MANUAL_FILE = "手动数据.txt"
MANUAL_PATH = os.path.join(DATA_DIR, MANUAL_FILE)

MANUAL_TEMPLATE = """# ══════════════════════════════════════════════════════════════
#  Tina 桌面小窗 · 手动数据（唯一需要你手动改的文件）
#
#  怎么用：改完按 Ctrl+S 保存即可。程序会在下一次自动更新时读取；
#          想马上生效：在小窗上右键 →「立即更新数据」。
#  规则：以 # 开头的行是说明，会被忽略；[方括号] 里的分组名不要改。
# ══════════════════════════════════════════════════════════════

[汽油]
# 默认【自动获取】（汽车之家的「西安油价」页面），一般不用填，也不用管。
# 只有自动获取失败（比如断网、对方网页改版）时，程序才会改用这里的值当后备。
# 格式：92 = 现价 , 变动      现价单位是元/升，数字后面不要带「元」字
#   变动 = 相对上一次调价涨了多少：涨写正数，降写负数，没变写 0
#   例：92 = 8.76 , +0.27        例：95 = 9.32 , -0.15
@@92@@
@@95@@

[羊毛]
# 今日羊毛：每天展示 10 条——前 5 条是外卖优惠券，后 5 条是 Token / AI 额度类；小窗每页 5 条、自动翻页。
# 这里只填写消费类标题，最多取前 5 条；额度类由程序自动更新，一般不用填。
# 直接写文字，不要自己加序号（程序会自动编成 1. 2. 3.）。
# 标题太长会被截成「…」，建议写在 18 个字以内。
# 想换内容就整行改掉或删掉；消费类一条都不写，就改用自动订阅的消费源。
# 例：瑞幸 9.9 元咖啡券（今日可领）


[订阅源]
# 可选：额外的消费类 RSS 地址，每行一个，会和默认消费源一起读。
# 额度类有单独的默认源，不用写在这里。不填也没关系。
# 例：https://你的RSSHub域名/路由


[单词]
# 额外的英文单词（可以不填）。会并入程序内置的 60 个词库里轮换。
# 格式：单词 | 音标 | 中文意思 | 英文例句       四项之间用竖线 | 隔开
# 例：resilient | rɪˈzɪliənt | 有韧性的 | She stays resilient under pressure.

"""

_FULL = str.maketrans({"＝": "=", "，": ",", "＋": "+", "－": "-", "−": "-", "｜": "|", "［": "[", "］": "]", "：": ":"})


def _read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def _oil_line(key, oil):
    r = (oil or {}).get(key) or {}
    p = fnum(r.get("price"))
    if p is None:
        return f"{key} = "
    c = fnum(r.get("change")) or 0.0
    return f"{key} = {p:g} , {c:+g}" if c else f"{key} = {p:g} , 0"


def load_manual():
    """读取并解析 手动数据.txt，返回 {"oil": {...}, "deals": [...], "words": [...]}。
    文件不存在就生成模板（并把旧版 oil_manual.json 里的油价搬进来）。"""
    if not os.path.exists(MANUAL_PATH):
        oil = read_json(P("oil_manual.json")) or {}
        text = MANUAL_TEMPLATE.replace("@@92@@", _oil_line("92", oil)).replace("@@95@@", _oil_line("95", oil))
        with open(MANUAL_PATH, "w", encoding="utf-8-sig") as f:
            f.write(text)
        log(f"已生成 {MANUAL_FILE}")
    try:
        text = _read_text(MANUAL_PATH)
    except Exception as e:
        log(f"读取 {MANUAL_FILE} 失败 {e!r}")
        return {}
    oil, deals, words, feeds, section = {}, [], [], [], ""
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line[0] in "#＃":
            continue
        m = re.match(r"^\[(.+?)\]$", line.translate(_FULL))
        if m:
            section = m.group(1).strip()
            continue
        if "汽油" in section:
            t = line.translate(_FULL)
            m = re.match(r"^(92|95)\s*#?\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(?:,\s*([+-]?[0-9]+(?:\.[0-9]+)?))?\s*$", t)
            if m:
                oil[m.group(1)] = {"price": float(m.group(2)), "change": float(m.group(3) or 0)}
            elif "=" in t and t.split("=", 1)[1].strip():
                log(f"{MANUAL_FILE} [汽油] 看不懂这一行：{line}")
        elif "订阅" in section:
            if line.lower().startswith("http"):
                feeds.append(line)
        elif "羊毛" in section:
            deals.append(line)
        elif "单词" in section:
            parts = [x.strip() for x in line.translate(_FULL).split("|")]
            if len(parts) >= 3 and parts[0]:
                words.append({"word": parts[0], "ipa": parts[1].strip("/ "), "zh": parts[2],
                              "example": parts[3] if len(parts) > 3 else ""})
            else:
                log(f"{MANUAL_FILE} [单词] 看不懂这一行：{line}")
    return {"oil": oil, "deals": deals, "words": words, "feeds": feeds}


OIL_URL = "https://www.autohome.com.cn/oil/610100.html"   # 汽车之家油价页，城市用行政区划代码，西安是 610100


def parse_autohome_oil(raw, old_items=None, city="西安", grades=None):
    """从汽车之家油价页解析指定油号：现价取页面摘要，变动 = 现价 − 上一次不同的价格（走势表）。"""
    grades = [g for g in (grades or ["92", "95"]) if g in GRADE_INFO]
    cur = {}
    for g, info in GRADE_INFO.items():
        m = re.search(info["page"] + r"为\s*([0-9.]+)\s*元", raw)
        if not m:
            continue
        v = float(m.group(1))
        if 2 < v < 30:
            cur[g] = v
    if not any(g in cur for g in grades):
        raise ValueError(f"{city} 没找到油价")
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\s+", " ", text)
    rows = re.findall(r"(\d{2}-\d{2}) ([0-9.]+) ([0-9.]+) ([0-9.]+) ([0-9.]+)", text)
    old = {it.get("name"): it for it in (old_items or [])}
    items = []
    for g in grades:
        info = GRADE_INFO[g]
        if g not in cur:
            log(f"oil: {city} 没有 {info['label']}")
            continue
        name = f"{city} {info['label']}"
        change = None
        col = info["col"]
        for r in rows:
            if abs(float(r[col]) - cur[g]) > 1e-9:
                change = round(cur[g] - float(r[col]), 2)
                break
        if change is None:
            o = old.get(name) or {}
            op = fnum(o.get("price"))
            if op is not None and abs(op - cur[g]) > 1e-9:
                change = round(cur[g] - op, 2)
            else:
                ct = str(o.get("change_text") or "")
                change = fnum(ct.replace("元", "").strip()) if ct else 0.0
        items.append({"name": name, "price": cur[g], "display": f"{cur[g]:.2f} 元/升",
                      "change_text": f"{change:+.2f} 元" if change else "0.00 元",
                      "city": city, "grade": g})
    return items


def fetch_oil():
    """各地汽油 / 柴油挂牌价：按关注列表请求汽车之家；失败才用 手动数据.txt 的 [汽油] 给西安当后备。"""
    entries = load_watchlist().get("oil") or []
    if not entries:
        return []
    old = (read_json(P("prices.json"), {}) or {}).get("columns", [])
    old_items = next((c.get("items", []) for c in old if isinstance(c, dict) and c.get("id") == "oil"), [])
    items, failed = [], []
    for e in entries:
        city = e.get("city") or "西安"
        adcode = e.get("adcode") or "610100"
        grades = e.get("grades") or ["92", "95"]
        url = f"https://www.autohome.com.cn/oil/{adcode}.html"
        try:
            raw = http_get(url, headers={"Referer": "https://www.autohome.com.cn/oil"})
            part = parse_autohome_oil(raw, old_items, city=city, grades=grades)
            items.extend(part)
            log(f"oil: {city} 自动获取成功 {[(i['name'], i['display'], i['change_text']) for i in part]}")
        except Exception as ex:
            log(f"oil: {city} 自动获取失败 {ex!r}")
            failed.append((city, grades))
    if failed:
        d = load_manual().get("oil") or {}
        have = {it.get("name") for it in items}
        for city, grades in failed:
            if city != "西安":
                continue
            for key in grades:
                if key not in ("92", "95"):
                    continue
                name = f"{city} {GRADE_INFO[key]['label']}"
                if name in have:
                    continue
                r = d.get(key) or {}
                p = fnum(r.get("price"))
                if p is None:
                    continue
                c = fnum(r.get("change")) or 0.0
                items.append({"name": name, "price": p, "display": f"{p:.2f} 元/升",
                              "change_text": f"{c:+.2f} 元" if c else "0.00 元",
                              "city": city, "grade": key})
    return items if items or not entries else None


def update_prices():
    path = P("prices.json")
    old = read_json(path, {}) or {}
    if os.path.exists(path) and not os.path.exists(path + ".bak"):
        shutil.copy(path, path + ".bak")   # 第一次覆盖前，备份你原来的文件
    old_cols = {c.get("id"): c for c in old.get("columns", []) if isinstance(c, dict)}
    spec = [("crypto", "加密货币", fetch_crypto), ("oil", "汽油", fetch_oil),
            ("shares", "股票指数", fetch_stocks), ("gold", "国内金价", fetch_gold),
            ("fx", "汇率", fetch_fx)]
    cols, fresh = [], 0
    for cid, cname, fn in spec:
        try:
            got = fn()
        except Exception as e:
            log(f"{cid}: 异常 {e!r}")
            got = None
        if got is None:
            items = (old_cols.get(cid) or {}).get("items", [])   # 失败就沿用旧数据
        else:
            items = got
            fresh += 1
        cols.append({"id": cid, "name": cname, "items": items})
    now = datetime.now(CN)
    write_json(path, {"updated_at": now.isoformat(timespec="seconds"), "date": f"{now:%Y-%m-%d}",
                      "rotate_seconds": old.get("rotate_seconds", 5), "columns": cols})
    log(f"prices.json 已写入（{fresh}/5 栏为新数据）")
    return fresh



# ═════════════════════════ 任务 ═════════════════════════
# 想换新闻源就改这两个列表（RSS 地址）。能不能访问取决于你的网络。
FEEDS_ECON = ["https://www.chinanews.com.cn/rss/finance.xml",
              "http://www.people.com.cn/rss/finance.xml"]  # 备用人民日报财经（BBC 中文源已 404）
FEEDS_DEALS = ["http://feed.smzdm.com"]  # 备用商品好价 RSS，消费栏现在默认不走这条
COUPON_LIST_URL = "https://h5.smzdm.com/user/coupon/coupon_list"  # 什么值得买优惠券频道（外卖 / 闪购）
FEEDS_DEALS_AI = ["https://www.llmabacus.com/feed.xml"]  # Token / AI 额度：大模型价格变动（降价 / 涨价 / 新发布）


def rss_titles(url):
    return [t for t, _d, _u in rss_items(url)]


def rss_items(url):
    """返回 [(标题, 纯文本摘要, 链接), ...]。"""
    txt = http_get(url)
    root = ET.fromstring(txt.encode("utf-8"))
    out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"):
            continue
        title, desc, link = "", "", ""
        for ch in it:
            tag = ch.tag.split("}")[-1]
            if tag == "title" and ch.text:
                title = re.sub(r"\s+", " ", html.unescape(ch.text)).strip()
            elif tag in ("description", "summary") and ch.text:
                raw = re.sub(r"<[^>]+>", " ", ch.text)
                desc = re.sub(r"\s+", " ", html.unescape(raw)).strip()
            elif tag == "link":
                href = ((ch.get("href") or "").strip() or (ch.text or "").strip())
                if href:
                    link = href
            elif tag == "guid" and not link and ch.text:
                g = ch.text.strip()
                if g.startswith("http"):
                    link = g
        if title:
            out.append((title, desc, link))
    return out


def collect(feeds, n=10):
    """交错合并多个源，返回 [{"title", "url"}, ...]。"""
    lists = []
    for u in feeds:
        try:
            items = []
            for title, _desc, link in rss_items(u):
                items.append({"title": title, "url": link})
            lists.append(items)
            log(f"rss ok {u} ({len(items)})")
        except Exception as e:
            log(f"rss 失败 {u} {e!r}")
    out, seen, i = [], set(), 0
    while len(out) < n and any(i < len(l) for l in lists):
        for l in lists:
            if i < len(l) and len(out) < n:
                title = l[i]["title"]
                if title not in seen:
                    seen.add(title)
                    out.append(l[i])
        i += 1
    return out



def _ai_title(title, desc):
    title = (title or "").strip()
    if not title:
        return ""
    if any(x in title for x in ("%", "¥", "$", "降价", "涨价", "折", "便宜")):
        return title
    if not desc:
        return title
    sent = re.split(r"[。；;\n]", desc, 1)[0].strip(" ：:")
    if len(sent) > 36:
        sent = sent[:36] + "…"
    if sent and sent not in title:
        return f"{title}：{sent}"
    return title


def collect_ai_deals(n=5):
    """从额度源取 n 条，优先降价 / 涨价，其次新发布。"""
    preferred, rest = [], []
    seen = set()
    for u in FEEDS_DEALS_AI:
        try:
            items = rss_items(u)
            log(f"rss ok {u} ({len(items)})")
        except Exception as e:
            log(f"rss 失败 {u} {e!r}")
            continue
        for title, desc, link in items:
            t = _ai_title(title, desc)
            if not t or t in seen:
                continue
            seen.add(t)
            if "弃用" in t:
                continue
            item = {"title": t, "url": link}
            if ("降价" in t) or ("涨价" in t):
                preferred.append(item)
            else:
                rest.append(item)
    return (preferred + rest)[:n]


def _html_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
           .replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", s).strip()


def _is_waimai_coupon(tag, text=""):
    blob = f"{tag} {text}"
    if any(k in blob for k in ("到店", "堂食")):
        return False
    if tag in ("美团外卖", "淘宝闪购", "饿了么", "京东外卖", "美团闪购"):
        return True
    return any(k in blob for k in ("外卖", "闪购", "饿了么"))


def _shorten_waimai(tag, short, title):
    text = " ".join(x for x in (short, title) if x)
    text = re.sub(r"^(?:每日可领|必领神券|必领红包|今日必买)[:：]?\s*", "", text)
    offers = re.findall(r"满?\d+[-减]\d+元?", text)
    seen, uniq = set(), []
    for o in offers:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    platform = tag or "外卖"
    if uniq:
        return f"{platform} {'/'.join(uniq[:2])}"
    m = re.search(r"返\d+(?:/\d+)?淘金币", text)
    if m:
        return f"{platform} {m.group(0)}"
    short = re.sub(r"^(?:每日可领|必领神券|必领红包|今日必买)[:：]?\s*", "", text)
    short = re.sub(r"^(?:美团外卖|淘宝闪购|美团闪购|饿了么|京东外卖)\s*", "", short)
    if short.endswith("专"):
        short += "场"
    if len(short) > 14:
        short = short[:14]
    return f"{platform} {short}".strip()


def collect_waimai_coupons(n=5):
    """从什么值得买优惠券频道里挑外卖 / 闪购。"""
    try:
        html = http_get(COUPON_LIST_URL)
    except Exception as e:
        log(f"优惠券频道读取失败：{e}")
        return []
    if not html:
        return []
    out, seen = [], set()
    for m in re.finditer(r'<a href="(https://m\.smzdm\.com/p/\d+/)"[^>]*>(.*?)</a>', html, re.S):
        url, block = m.group(1), m.group(2)
        tag_m = re.search(r'class="tag"[^>]*>([^<]+)', block)
        short_m = re.search(r'class="content[^"]*"[^>]*>(.*?)</span>', block, re.S)
        title_m = re.search(r'class="title"[^>]*>.*?<span[^>]*>(.*?)</span>', block, re.S)
        tag = _html_text(tag_m.group(1) if tag_m else "")
        short = _html_text(short_m.group(1) if short_m else "")
        title = _html_text(title_m.group(1) if title_m else "")
        if not _is_waimai_coupon(tag, f"{short} {title}"):
            continue
        tt = _shorten_waimai(tag, short, title)
        if tt and tt not in seen:
            seen.add(tt)
            out.append({"title": tt, "url": url})
        if len(out) >= n:
            break
    log(f"优惠券频道：外卖/闪购 {len(out)} 条")
    return out[:n]


def _shorten_consumer(title, max_name=14):
    """把消费类长标题收成「关键词 + 价格」，方便小窗一行看完。"""
    t = (title or "").strip()
    if not t:
        return t
    t = re.sub(r"^今日好券\s*[|｜]\s*", "", t)
    t = re.sub(r"\d{1,2}\.\d{1,2}上新[:：]?", "", t)
    t = re.sub(r"周[一二三四五六日天][^，。！!,、]*[，。！!]", "", t)
    t = re.sub(r"^(?:\d+)?VIP[:：]", "", t)
    t = re.sub(r"^(?:百亿)?补贴[:：]", "", t)
    t = re.sub(r"日本直邮", " ", t)
    couponish = ("券" in t) or ("红包" in t) or ("领" in t and "元" in t)
    if couponish and ("、" in t or t.count("领") >= 2 or "今日好券" in (title or "")):
        t = re.sub(r"等[~～]*", "、", t)
        parts = [p.strip() for p in re.split(r"[、，,]", t) if p.strip()]
        bits, leftover = [], []
        for p in parts:
            p = re.sub(r"\d{1,2}\.\d{1,2}上新[:：]?", "", p)
            p = re.sub(r"周[一二三四五六日天]好券速领[！!]?", "", p)
            p = p.replace("领", "")
            p = re.sub(r"\d+(?:\.\d+)?元", "", p)
            p = p.strip(" ：:，,、~|｜")
            if not p:
                continue
            leftover.append(p)
            if p in bits:
                continue
            if bits and p[:2] == bits[0][:2]:
                continue
            bits.append(p)
            if len(bits) >= 2:
                break
        if len(bits) < 2:
            for p in leftover:
                if p not in bits:
                    bits.append(p)
                if len(bits) >= 2:
                    break
        name = " ".join(bits) if bits else t
        return name[:18] if len(name) > 18 else name

    prices = re.findall(r"\d+(?:\.\d+)?元", t)
    price = prices[-1] if prices else ""
    t = re.sub(r"（[^）]*）", "", t)
    t = re.sub(r"\([^)]*\)", "", t)
    if price:
        t = t.replace(price, "")
    t = re.sub(r"等[~～]*.*$", "", t)
    t = re.sub(r"\d{5,}", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" ：:，,、~-|/")

    skip_re = re.compile(
        r"^(?:乳?白色?|米白|米色?|黑色?|红色?|蓝色?|绿色?|灰色?|粉色?|黄色?|紫色?|橙色?|"
        r"卡其|藏青|深蓝|浅蓝|咖啡|棕色?|杏色|大号|小号|中号|加大|均码|"
        r"(?:XXL|XL|XS|[SML])|\d{2,3}码)$"
    )
    spec_re = re.compile(r"^(?:\d+(?:\.\d+)?\s*(?:w|W|孔|米|cm|mm|kg|g|L|l|英寸|寸|斤)|总控|需用券)$")
    nouns = ("打印机", "洗衣液", "床头柜", "洗脸盆", "台下盆", "路由器", "置物架", "挂篮",
             "插排", "插座", "开衫", "卫衣", "衬衫", "T恤", "登山鞋", "跑鞋", "耳机", "充电宝",
             "数据线", "键盘", "鼠标", "显示器", "洗衣机", "冰箱", "空调", "电动牙刷",
             "洗发水", "沐浴露", "纸巾", "垃圾袋", "挂钩", "收纳", "网关", "净水器",
             "风扇", "平板", "台盆", "面盆", "斗柜", "巧克力", "黑巧", "纸尿裤",
             "水龙头", "拖把池", "浴霸", "冲锋衣", "枕头")

    def first_product(s):
        hits = []
        for n in nouns:
            i = s.find(n)
            if i >= 0:
                hits.append((i, n))
        if not hits:
            return None
        hits.sort(key=lambda x: (x[0], -len(x[1])))
        i, n = hits[0]
        if i <= 2:
            return s[: i + len(n)]
        i, n = max(hits, key=lambda x: (x[0] + len(x[1]), len(x[1])))
        m = re.match(r"[A-Za-z][A-Za-z0-9\-]{1,7}", s)
        return (m.group(0) + n) if m else n

    tokens = []
    for x in t.split(" "):
        if (not x or skip_re.match(x) or spec_re.match(x) or x.endswith("面料")
                or re.search(r"\d+\s*(?:w|W|孔|米|cm|mm|kg|英寸)", x)
                or re.search(r"(?:大号|小号|中号|加宽|升级).*(?:色|黑|白|灰)?$", x)):
            continue
        tokens.append(x)

    if not tokens:
        name = first_product(t) or t[:max_name]
    elif len(tokens) == 1:
        s = tokens[0]
        name = s if len(s) <= max_name else (first_product(s) or s[:max_name])
    else:
        brand = tokens[0]
        prod = None
        for x in reversed(tokens[1:]):
            got = first_product(x)
            if got:
                prod = got
                break
        mid = []
        for x in tokens[1:]:
            if "平板" in x and len(x) <= 10:
                mid = [x]
                break
        if not mid:
            for x in tokens[1:]:
                if first_product(x):
                    continue
                if re.match(r"^[A-Za-z][A-Za-z0-9\-]{2,9}$", x) or re.match(r"^[A-Za-z0-9]{3,10}$", x):
                    mid = [x]
                    break
        parts = [brand]
        parts += mid
        if prod and all(prod not in p for p in parts):
            parts.append(prod)
        name = " ".join(parts)

    if " " not in name and len(name) > max_name:
        name = first_product(name) or name[:max_name]
    if len(name) > 16:
        parts = name.split()
        name = " ".join([parts[0], parts[-1]]) if len(parts) >= 3 else name[:16]
    if price:
        return f"{name} {price}".strip()
    return name or title[:max_name]



def _norm_deal(x, kind=None):
    """把标题或 {title, url, kind} 收成统一的字典。"""
    if isinstance(x, dict):
        t = str(x.get("title") or "").strip()
        url = str(x.get("url") or x.get("link") or "").strip()
        k = x.get("kind") or x.get("type") or x.get("cat") or kind
    else:
        t = str(x or "").strip()
        url = ""
        k = kind
    if t.startswith("消费：") or t.startswith("额度："):
        if k is None:
            k = "coupon" if t.startswith("消费：") else "token"
        t = t[3:].strip()
    if not t:
        return None
    d = {"title": t}
    if k:
        d["kind"] = k
    if url:
        d["url"] = url
    return d


def _deal_titles(items):
    out = []
    for x in items or []:
        d = _norm_deal(x)
        if d:
            out.append(d)
    return out


def _split_old_deals(items):
    consumer, ai = [], []
    for it in items or []:
        d = _norm_deal(it)
        if not d:
            continue
        k = str(d.get("kind") or "").strip().lower()
        if k in ("token", "额度", "ai", "tokens"):
            ai.append(d)
        else:
            consumer.append(d)
    return consumer, ai


# 内置词库（每天按日期轮换 10 个）。想加词：在 word_bank.json 里放同样字段的列表即可。
WORD_BANK = [
    ("commute", "kəˈmjuːt", "通勤", "I commute to work by subway."),
    ("budget", "ˈbʌdʒɪt", "预算", "We need to stick to our budget."),
    ("negotiate", "nɪˈɡoʊʃieɪt", "谈判", "They negotiated a better price."),
    ("inflation", "ɪnˈfleɪʃn", "通货膨胀", "Inflation has slowed this year."),
    ("invest", "ɪnˈvest", "投资", "She invested in index funds."),
    ("deadline", "ˈdedlaɪn", "截止日期", "The deadline is next Friday."),
    ("efficient", "ɪˈfɪʃnt", "高效的", "This is an efficient way to work."),
    ("recipe", "ˈresəpi", "食谱", "This recipe is easy to follow."),
    ("schedule", "ˈskedʒuːl", "日程", "My schedule is full today."),
    ("reliable", "rɪˈlaɪəbl", "可靠的", "He is a reliable friend."),
    ("improve", "ɪmˈpruːv", "改进", "I want to improve my English."),
    ("challenge", "ˈtʃælɪndʒ", "挑战", "Learning to code is a challenge."),
    ("consume", "kənˈsuːm", "消耗；消费", "Old cars consume a lot of fuel."),
    ("demand", "dɪˈmænd", "需求", "Demand for chips keeps rising."),
    ("supply", "səˈplaɪ", "供应", "Supply could not meet demand."),
    ("profit", "ˈprɑːfɪt", "利润", "The firm made a small profit."),
    ("trend", "trend", "趋势", "Remote work is a growing trend."),
    ("growth", "ɡroʊθ", "增长", "The economy showed steady growth."),
    ("tariff", "ˈtærɪf", "关税", "A new tariff raised the price."),
    ("currency", "ˈkɜːrənsi", "货币", "The local currency lost value."),
    ("discount", "ˈdɪskaʊnt", "折扣", "Students get a ten percent discount."),
    ("refund", "ˈriːfʌnd", "退款", "I asked for a refund."),
    ("subscribe", "səbˈskraɪb", "订阅", "Subscribe to get daily updates."),
    ("convenient", "kənˈviːniənt", "方便的", "The store is convenient to reach."),
    ("ingredient", "ɪnˈɡriːdiənt", "配料", "Fresh ginger is the key ingredient."),
    ("appointment", "əˈpɔɪntmənt", "预约", "I have a doctor's appointment."),
    ("forecast", "ˈfɔːrkæst", "预测", "The forecast says it will rain."),
    ("priority", "praɪˈɔːrəti", "优先事项", "Safety is our top priority."),
    ("maintain", "meɪnˈteɪn", "维持；保养", "Maintain a regular sleep schedule."),
    ("estimate", "ˈestɪmeɪt", "估计", "Can you estimate the cost?"),
    ("temporary", "ˈtempəreri", "临时的", "This is only a temporary fix."),
    ("essential", "ɪˈsenʃl", "必不可少的", "Water is essential for life."),
    ("compare", "kəmˈper", "比较", "Compare prices before you buy."),
    ("achieve", "əˈtʃiːv", "实现", "She achieved her goal."),
    ("adapt", "əˈdæpt", "适应", "It takes time to adapt to a new city."),
    ("curious", "ˈkjʊriəs", "好奇的", "Kids are naturally curious."),
    ("familiar", "fəˈmɪliər", "熟悉的", "This song sounds familiar."),
    ("generate", "ˈdʒenəreɪt", "产生", "Solar panels generate electricity."),
    ("impact", "ˈɪmpækt", "影响", "The news had a big impact."),
    ("recover", "rɪˈkʌvər", "恢复", "Markets began to recover."),
    ("stable", "ˈsteɪbl", "稳定的", "Prices have stayed stable."),
    ("volatile", "ˈvɑːlətl", "波动剧烈的", "Oil prices are volatile."),
    ("shortage", "ˈʃɔːrtɪdʒ", "短缺", "There is a shortage of workers."),
    ("regulate", "ˈreɡjuleɪt", "监管", "Banks are tightly regulated."),
    ("launch", "lɔːntʃ", "发布", "The company will launch a new phone."),
    ("competitor", "kəmˈpetɪtər", "竞争对手", "Our competitor cut its prices."),
    ("average", "ˈævərɪdʒ", "平均的", "The average rent has gone up."),
    ("reduce", "rɪˈduːs", "减少", "Try to reduce your spending."),
    ("expand", "ɪkˈspænd", "扩大", "They plan to expand overseas."),
    ("sustainable", "səˈsteɪnəbl", "可持续的", "We need a sustainable plan."),
    ("reputation", "ˌrepjuˈteɪʃn", "声誉", "The shop has a good reputation."),
    ("workload", "ˈwɜːrkloʊd", "工作量", "My workload doubled this month."),
    ("overtime", "ˈoʊvərtaɪm", "加班", "He worked overtime all week."),
    ("retire", "rɪˈtaɪər", "退休", "She plans to retire at sixty."),
    ("shipment", "ˈʃɪpmənt", "发运的货物", "The shipment arrives on Monday."),
    ("persuade", "pərˈsweɪd", "说服", "I tried to persuade him to stay."),
    ("flexible", "ˈfleksəbl", "灵活的", "We offer flexible hours."),
    ("postpone", "poʊstˈpoʊn", "推迟", "The meeting was postponed."),
    ("neighborhood", "ˈneɪbərhʊd", "社区", "It is a quiet neighborhood."),
    ("grocery", "ˈɡroʊsəri", "食品杂货", "I do my grocery shopping on Sunday."),
]


def pick_words(n=10, randomize=False, exclude=None):
    bank = [dict(word=w, ipa=i, zh=z, example=e) for w, i, z, e in WORD_BANK]
    extra = load_manual().get("words") or []
    bank += [x for x in extra if isinstance(x, dict) and x.get("word")]
    if not bank:
        return []
    n = min(n, len(bank))
    if randomize:
        pool = list(bank)
        if exclude:
            seen = {str(x.get("word", "")).strip().lower() for x in exclude if isinstance(x, dict)}
            reduced = [w for w in pool if str(w.get("word", "")).strip().lower() not in seen]
            if len(reduced) >= n:
                pool = reduced
        return random.sample(pool, n)
    start = (datetime.now(CN).date().toordinal() * n) % len(bank)
    return [bank[(start + k) % len(bank)] for k in range(n)]


def replace_english_words(n=10, exclude=None):
    items = pick_words(n=n, randomize=True, exclude=exclude)
    now = datetime.now(CN)
    stamp = {"updated_at": now.isoformat(timespec="seconds"), "date": f"{now:%Y-%m-%d}"}
    write_json(P("english_words.json"), {**stamp, "items": items})
    log(f"english_words.json 已随机更换 {len(items)} 个单词")
    return items


def update_tasks():
    now = datetime.now(CN)
    stamp = {"updated_at": now.isoformat(timespec="seconds"), "date": f"{now:%Y-%m-%d}"}

    ok = False
    econ = collect(FEEDS_ECON)
    if econ:
        write_json(P("econ_news.json"), {**stamp, "items": econ})
        log(f"econ_news.json 已写入 {len(econ)} 条")
        ok = True
    else:
        log("econ_news: 全部失败，保留旧文件")

    write_json(P("english_words.json"), {**stamp, "items": pick_words()})
    log("english_words.json 已写入")

    manual = load_manual()
    old_cons, old_ai = _split_old_deals((read_json(P("deals.json"), {}) or {}).get("items"))

    consumer = _deal_titles(manual.get("deals"))
    need = 5 - len(consumer)
    if need > 0:
        consumer += collect_waimai_coupons(n=need)
    consumer = consumer[:5]
    if not consumer:
        consumer = [d for d in old_cons if _is_waimai_coupon("", d.get("title", ""))][:5]

    ai = collect_ai_deals(n=5)
    if not ai:
        ai = old_ai[:5]

    items = ([_norm_deal(x, "coupon") for x in consumer]
             + [_norm_deal(x, "token") for x in ai])
    items = [x for x in items if x]
    if items:
        write_json(P("deals.json"), {**stamp, "items": items})
        deals = items
        log(f"deals.json 已写入 消费 {len(consumer)} 条、额度 {len(ai)} 条")
        if consumer or ai:
            ok = True
    else:
        log("deals: 消费源和额度源都没有取到，保留旧文件")
    return ok


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    what = args[0] if args else "all"
    if what in ("prices", "all"):
        update_prices()
    if what in ("tasks", "all"):
        update_tasks()
