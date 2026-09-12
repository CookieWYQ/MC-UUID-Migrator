# -*- coding: utf-8 -*-
"""UUID 玩家数据迁移工具：把来源UUID(A)的数据整体迁移为 目标UUID(B)。

范围：
  1. 根目录下所有文件名/目录名含 A 的 → 改名替换为 B
  2. 文件内容（文本/二进制/原始NBT）中的 A → 原位替换为 B（等长，安全）
     - UUID 字符串 4 种写法：小写/大写 × 带横线/去横线
     - UUID 二进制 16 字节形式（NBT 的 IntArray[4]/LongArray[2]/byte[] 等）
  3. gzip 压缩 NBT 文件（playerdata/*.dat、模组 .dat 等）：解压 → 替换 → 重新压缩
  4. .mca 区块文件（region/entities/poi）：逐区块解压 → 替换 → 安全重建文件
     （覆盖车万女仆等把所属/主人 UUID 以二进制形式存在区块实体里的情况）
  5. 迁移前自动备份：所有涉及文件复制到 uuid_backup_时间戳_UUID对/（保留相对路径，可整体还原）
     uuid_backup_* 目录在后续扫描中自动排除，多次迁移互不混入

适用于 playerdata/stats/advancements、车万女仆、各类模组以 UUID 为键存放的数据等。

另有独立功能「Xaero 地图转移」页（与 UUID 无关）：
  Xaero 路径点/已探索地图存在客户端、按"客户端+世界或服务器容器"保存，文件里不含 UUID。
  该页把某容器（如单机世界）的路径点与已探索地图，合并到另一容器（如该服务器），
  即"把单机世界的路径点搬到服务器上"。

用法：
  图形界面：  python uuid_transfer_tool.py
  命令行：    python uuid_transfer_tool.py --root 根目录 --a 来源UUID --b 目标UUID [--scan]
   Xaero：    python uuid_transfer_tool.py --xaero-root 客户端目录 --xaero-src 源容器 --xaero-dst 目标容器
"""
import os
import re
import sys
import glob
import json
import gzip
import zlib
import struct
import shutil
import argparse
import datetime
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont


# ---- 打包资源定位（教程 md 打进 exe，运行时从临时解包目录读取）----

def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def tutorial_files():
    d = resource_path("使用教程")
    if not os.path.isdir(d):
        return []
    return sorted(glob.glob(os.path.join(d, "*.md")))


def render_md_rich(txt, md):
    """把教程 md 渲染成富文本（标题/表格/列表/代码/粗体）写入 Text 控件"""
    txt.configure(state="normal")
    txt.delete("1.0", "end")

    fam = "Microsoft YaHei"
    f_body = tkfont.Font(family=fam, size=11)
    f_body_b = tkfont.Font(family=fam, size=11, weight="bold")
    f_mono = tkfont.Font(family="Consolas", size=10)
    f_mono_b = tkfont.Font(family="Consolas", size=10, weight="bold")

    txt.tag_configure("h1", font=tkfont.Font(family=fam, size=16, weight="bold"),
                      foreground="#4B3FE3", spacing1=10, spacing3=10)
    txt.tag_configure("h2", font=tkfont.Font(family=fam, size=13, weight="bold"),
                      foreground="#1A1759", spacing1=14, spacing3=6)
    txt.tag_configure("body", font=f_body, spacing3=5, lmargin1=10, lmargin2=10, rmargin=12)
    txt.tag_configure("li", font=f_body, spacing3=4, lmargin1=24, lmargin2=42, rmargin=12)
    txt.tag_configure("bold", font=f_body_b)
    txt.tag_configure("code", font=f_mono, background="#F1F1F5", foreground="#9C2A45")

    def ins(text, *tags):
        txt.insert("end", text, tags)

    def inline(s, base):
        """插入带 **粗体** 与 `代码` 的行内内容"""
        for part in re.split(r"(\*\*.+?\*\*|`[^`]+`)", s):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                ins(part[2:-2], base, "bold")
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                ins(part[1:-1], base, "code")
            else:
                ins(part, base)

    lines = md.splitlines()
    i, n = 0, len(lines)
    while i < n:
        t = lines[i].strip()
        if not t:
            i += 1
            continue
        # 标题
        if t.startswith("#"):
            lv = len(t) - len(t.lstrip("#"))
            ins(t.lstrip("#").strip() + "\n", "h1" if lv == 1 else "h2")
            i += 1
            continue
        # 表格：用等宽字体 + 像素制表位对齐，表头带底色
        if t.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if cells and set("".join(cells)) <= set("-: "):
                    i += 1
                    continue
                rows.append(cells)
                i += 1
            if rows:
                ncol = max(len(r) for r in rows)
                widths = [0] * ncol
                for ri, r in enumerate(rows):
                    f = f_mono_b if ri == 0 else f_mono
                    for c in range(ncol):
                        widths[c] = max(widths[c], f.measure(r[c] if c < len(r) else ""))
                stops, x = [], 0
                for w in widths:
                    x += w + 22
                    stops.append(x)
                txt.tag_configure("tblh", font=f_mono_b, background="#EAF0FF",
                                  foreground="#1A1759", lmargin1=12, lmargin2=12,
                                  spacing1=3, spacing3=3, tabs=tuple(stops))
                txt.tag_configure("tbl", font=f_mono, lmargin1=12, lmargin2=12,
                                  spacing1=2, spacing3=2, tabs=tuple(stops))
                for ri, r in enumerate(rows):
                    line = "\t".join((r[c] if c < len(r) else "") for c in range(ncol))
                    ins(line.replace("**", "").replace("`", "") + "\n",
                        "tblh" if ri == 0 else "tbl")
            continue
        # 列表（- 或 1.）
        m = re.match(r"^(\d+)[\.、]\s*(.*)$", t)
        if t.startswith("- ") or m:
            if m:
                marker, rest = m.group(1) + ". ", m.group(2)
            else:
                marker, rest = "• ", t[2:]
            ins(marker, "li")
            inline(rest, "li")
            ins("\n", "li")
            i += 1
            continue
        # 普通段落（合并连续行）
        para = [t]
        i += 1
        while i < n:
            t2 = lines[i].strip()
            if (not t2 or t2.startswith("#") or t2.startswith("|")
                    or t2.startswith("- ") or re.match(r"^\d+[\.、]", t2)):
                break
            para.append(t2)
            i += 1
        inline(" ".join(para), "body")
        ins("\n", "body")

    txt.configure(state="disabled")
    txt.see("1.0")


class TutorialWindow(tk.Toplevel):
    """内置使用教程查看器（内容来自打包进 exe 的 md）"""

    def __init__(self, master):
        super().__init__(master)
        self.title("使用教程")
        self.geometry("860x620")
        self.files = tutorial_files()

        left = tk.Frame(self)
        left.pack(side="left", fill="y")
        self.lb = tk.Listbox(left, width=26)
        self.lb.pack(side="left", fill="y", expand=True)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.lb.yview)
        sb.pack(side="right", fill="y")
        self.lb.configure(yscrollcommand=sb.set)

        right = tk.Frame(self)
        right.pack(side="right", fill="both", expand=True)
        self.txt = tk.Text(right, wrap="word", padx=10, pady=8)
        tsb = ttk.Scrollbar(right, orient="vertical", command=self.txt.yview)
        tsb.pack(side="right", fill="y")
        self.txt.configure(yscrollcommand=tsb.set)
        self.txt.pack(side="left", fill="both", expand=True)

        for f in self.files:
            self.lb.insert("end", os.path.splitext(os.path.basename(f))[0])
        self.lb.bind("<<ListboxSelect>>", self._show)
        if self.files:
            self.lb.selection_set(0)
            self._show()

    def _show(self, _evt=None):
        sel = self.lb.curselection()
        if not sel:
            return
        try:
            with open(self.files[sel[0]], "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError as e:
            content = "# 读取失败\n\n%s" % e
        render_md_rich(self.txt, content)

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def valid_uuid(s):
    return bool(s and UUID_RE.match(s))


def offline_uuid(name):
    """计算关闭正版验证（online-mode=false）服务器对某用户名使用的离线 UUID。
    规则与 Minecraft 一致：MD5("OfflinePlayer:" + 用户名)，v3 版本位 + RFC4122 变体位。"""
    import hashlib
    import uuid as _uuid
    h = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    h[6] = (h[6] & 0x0F) | 0x30          # version 3
    h[8] = (h[8] & 0x3F) | 0x80          # RFC 4122 variant
    return str(_uuid.UUID(bytes=bytes(h)))


def online_uuid_from_cache(root, name):
    """从根目录 usercache.json / usernamecache.json 解析用户名对应的正版 UUID，找不到返回 None"""
    import json
    if not root:
        return None
    for fname in ("usercache.json", "usernamecache.json"):
        p = os.path.join(root, fname)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if isinstance(data, dict):        # usernamecache: {"name": "uuid"}
            u = data.get(name)
            if u:
                return str(u)
        elif isinstance(data, list):      # usercache: [{"name":..., "uuid":...}]
            for item in data:
                if isinstance(item, dict) and item.get("name") == name and item.get("uuid"):
                    return str(item["uuid"])
    return None


def online_uuid_from_mojang(name):
    """通过 Mojang 官方 API 获取正版 UUID（失败返回 None）"""
    import urllib.request
    import urllib.parse
    import json
    try:
        url = "https://api.mojang.com/users/profiles/minecraft/" + urllib.parse.quote(name)
        req = urllib.request.Request(url, headers={"User-Agent": "uuid-migrate/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            uid = json.loads(resp.read().decode("utf-8")).get("id")
        if uid:
            return uid[:8] + "-" + uid[8:12] + "-" + uid[12:16] + "-" + uid[16:20] + "-" + uid[20:]
    except Exception:
        return None
    return None


# ---- 本地配置持久化（SFTP 服务器信息）----

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".uuid_transfer_tool_config.json")
_XOR_KEY = bytes([0x5A, 0x3C, 0x91, 0x27, 0x6E, 0x44, 0x0F, 0xB2])   # 简单混淆，非加密


def _obfuscate(s):
    import base64
    data = s.encode("utf-8")
    data = bytes(b ^ _XOR_KEY[i % len(_XOR_KEY)] for i, b in enumerate(data))
    return base64.b64encode(data).decode("ascii")


def _deobfuscate(s):
    import base64
    data = base64.b64decode(s.encode("ascii"))
    return bytes(b ^ _XOR_KEY[i % len(_XOR_KEY)] for i, b in enumerate(data)).decode("utf-8")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def ci_replace(s, old, new):
    """大小写不敏感地替换子串（UUID 在旧版本/部分模组中可能为大写存储）"""
    return re.sub(re.escape(old), new, s, flags=re.IGNORECASE)


def scan_matches(root, uuid_a):
    """返回 (文件名/目录名命中列表, 全部文件列表)。文件名匹配大小写不敏感。"""
    name_hits, all_files = [], []
    la = uuid_a.lower()
    for dirpath, dirnames, filenames in os.walk(root):
        # 排除本工具生成的备份目录，避免多次迁移时旧备份被再次扫描/混入
        dirnames[:] = [d for d in dirnames if not d.lower().startswith("uuid_backup_")]
        for d in dirnames:
            if la in d.lower():
                name_hits.append(os.path.join(dirpath, d))
        for f in filenames:
            p = os.path.join(dirpath, f)
            if la in f.lower():
                name_hits.append(p)
            all_files.append(p)
    return name_hits, all_files


def uuid_forms(uuid_a):
    """UUID 字符串的 4 种写法：小写/大写 × 带横线/去横线（去重）"""
    a = uuid_a.lower()
    return list(dict.fromkeys([a, a.upper(), a.replace("-", ""), a.replace("-", "").upper()]))


def uuid_patterns(uuid_a):
    """扫描用：文件内容中要匹配的各种 UUID 写法（字节，含 16 字节二进制形式）"""
    a = uuid_a.lower()
    pats = [s.encode("ascii") for s in uuid_forms(uuid_a)]
    pats.append(bytes.fromhex(a.replace("-", "")))
    return list(dict.fromkeys(pats))


def uuid_pairs(uuid_a, uuid_b):
    """替换用：(原字节, 替换字节) 对。同形式等长替换：字符串→字符串，16字节→16字节"""
    a = uuid_a.lower()
    b = uuid_b.lower()
    forms = [
        (a, b),
        (a.upper(), b),
        (a.replace("-", ""), b.replace("-", "")),
        (a.replace("-", "").upper(), b.replace("-", "")),
    ]
    seen, out = set(), []
    for f, t in forms:
        if f not in seen:
            seen.add(f)
            out.append((f.encode("ascii"), t.encode("ascii")))
    out.append((bytes.fromhex(a.replace("-", "")), bytes.fromhex(b.replace("-", ""))))
    return out


def edit_bytes(data, pairs):
    """把字节内容中出现的各 pat 原位替换（等长）。返回 (新数据, 是否改动)"""
    changed = False
    for pat, repl in pairs:
        if pat in data:
            data = data.replace(pat, repl)
            changed = True
    return data, changed


def file_contains(path, pats, chunk=1 << 20):
    """分块检测文件原始字节是否含任一 pat"""
    pats = list(pats)
    try:
        with open(path, "rb") as fh:
            tail = b""
            keep = max(len(p) for p in pats) - 1
            while True:
                data = fh.read(chunk)
                if not data:
                    return False
                buf = tail + data
                for pat in pats:
                    if pat in buf:
                        return True
                tail = buf[-keep:] if keep else b""
    except OSError:
        return False
    return False


def replace_in_file(path, pairs):
    """把文件原始字节内容替换（等长）"""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return False
    new, changed = edit_bytes(data, pairs)
    if not changed:
        return False
    try:
        with open(path, "wb") as fh:
            fh.write(new)
        return True
    except OSError:
        return False


# ---- gzip 压缩 NBT 文件（playerdata/*.dat 等）----

def is_gzip_file(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def gzip_decompress(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        return gzip.decompress(raw)
    except Exception:
        return None


def gzip_contains(path, patterns):
    dec = gzip_decompress(path)
    if dec is None:
        return False
    return any(p in dec for p in patterns)


def gzip_nbt_edit(path, pairs):
    """gzip NBT：解压 → 替换 → 重新压缩写回"""
    dec = gzip_decompress(path)
    if dec is None:
        return False
    new, changed = edit_bytes(dec, pairs)
    if not changed:
        return False
    try:
        with open(path, "wb") as fh:
            fh.write(gzip.compress(new, compresslevel=5))
        return True
    except OSError:
        return False


# ---- .mca 区块文件（region/entities/poi）----

def is_mca_file(path):
    return path.lower().endswith(".mca")


def mca_chunks(path):
    """读取 region 文件，返回 (块列表, 原始字节)。
    每块: (index, ctype, 压缩数据, 解压后的数据或 None, 原始块字节或 None)
    无法解压/结构异常的块用 raw 原样保留，重打包时绝不丢失。"""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return [], b""
    if len(raw) < 8192:
        return [], b""
    chunks = []
    for i in range(1024):
        b4 = raw[i * 4:i * 4 + 4]
        offset = (b4[0] << 16) | (b4[1] << 8) | b4[2]
        count = b4[3]
        if offset == 0 or count == 0:
            continue
        cstart = offset * 4096
        cend = cstart + count * 4096
        if cend > len(raw) or cstart + 5 > len(raw):
            continue                        # 扇区越界，无法读取（极端损坏，跳过）
        block = raw[cstart:cend]
        dlen = struct.unpack_from(">I", block, 0)[0]
        if dlen + 5 > len(block):
            # 声明长度超出扇区分配：整体原样保留该块
            chunks.append((i, 0, b"", None, block))
            continue
        ctype = block[4]
        cdata = block[5:5 + dlen]
        dec = None
        try:
            if ctype == 1:
                dec = gzip.decompress(cdata)
            elif ctype == 2:
                dec = zlib.decompress(cdata)
        except Exception:
            dec = None
        chunks.append((i, ctype, cdata, dec, None))
    return chunks, raw


def mca_contains(path, patterns):
    try:
        chunks, _ = mca_chunks(path)
    except Exception:
        return False
    for _, _, _, dec, _raw in chunks:
        if dec is not None and any(p in dec for p in patterns):
            return True
    return False


def mca_edit(path, pairs):
    """.mca：逐块解压替换；改动后整体重建文件（保留时间戳，无法解析的块原样保留，安全重打包）"""
    try:
        chunks, raw = mca_chunks(path)
    except Exception:
        return False
    new_chunks = []          # (index, 完整块字节)
    changed_any = False
    for idx, ctype, cdata, dec, rawblock in chunks:
        if rawblock is not None:
            # 结构异常：整体原样保留
            new_chunks.append((idx, rawblock))
            continue
        if dec is None:
            new_chunks.append((idx, struct.pack(">I", len(cdata)) + bytes([ctype]) + cdata))
            continue
        new_dec, changed = edit_bytes(dec, pairs)
        if not changed:
            new_chunks.append((idx, struct.pack(">I", len(cdata)) + bytes([ctype]) + cdata))
            continue
        changed_any = True
        try:
            if ctype == 1:
                nc = gzip.compress(new_dec, compresslevel=5)
            else:
                nc = zlib.compress(new_dec, 5)
        except Exception:
            new_chunks.append((idx, struct.pack(">I", len(cdata)) + bytes([ctype]) + cdata))
            continue
        new_chunks.append((idx, struct.pack(">I", len(nc)) + bytes([ctype]) + nc))
    if not changed_any:
        return False
    header = bytearray(8192)
    header[4096:8192] = raw[4096:8192]          # 保留原时间戳表
    body = bytearray()
    sector = 2
    table = {}
    for idx, chunk in new_chunks:
        need = (len(chunk) + 4095) // 4096
        if sector + need > 0xFFFFFF:
            return False
        table[idx] = (sector, need)
        body += chunk
        body += b"\x00" * (need * 4096 - len(chunk))
        sector += need
    for idx, (sec, cnt) in table.items():
        header[idx * 4:idx * 4 + 4] = struct.pack(">I", (sec << 8) | cnt)
    try:
        with open(path, "wb") as fh:
            fh.write(bytes(header) + bytes(body))
        return True
    except OSError:
        return False


# ---- Xaero 小地图/世界地图：容器间转移（路径点 + 已探索地图）----
# 事实依据（Xaero's Minimap 1.21.1 / 26.4.2 反编译常量）：
#   * 客户端路径点：<客户端>/xaero/minimap/<容器>/dim%<维度>/<集合>.txt
#     行格式 waypoint:name:initials:x:y:z:color:disabled:type:set:rotate_on_tp:tp_yaw:visibility_type:destination
#     文件里不含任何 UUID/玩家名 —— 路径点属于"客户端 + 容器"，不属于账号
#   * 客户端已探索地图：<客户端>/xaero/world-map/<容器>/<null|DIM-1|DIM1>/...
#   * 服务端 <world>/xaeromap.txt 只有一行 id:<多世界ID>，不是玩家路径点
# 所以"把一个人的路径点转给另一个人"= 客户端容器间拷贝（单机世界容器 → 该服务器容器）

XAERO_MINIMAP = "minimap"
XAERO_WORLDMAP = "world-map"


def xaero_root(client_root):
    """返回客户端 xaero 目录（兼容传入 <root>/xaero 或 <root> 本身）"""
    p = os.path.join(client_root, "xaero")
    if os.path.isdir(p):
        return p
    if os.path.basename(client_root.rstrip("\\/")).lower() == "xaero":
        return client_root
    return p


def xaero_containers(client_root):
    """列出容器（单机世界名 / Multiplayer_服务器地址），来自 minimap 目录"""
    d = os.path.join(xaero_root(client_root), XAERO_MINIMAP)
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d)
                  if os.path.isdir(os.path.join(d, n)) and n.lower() != "backup")


def _walk_files(d):
    for root, _dirs, files in os.walk(d):
        for f in files:
            yield os.path.join(root, f)


def _read_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def _waypoint_lines(path):
    """取出文件里所有 waypoint: 行（跳过 # 注释与 sets:/set: 元数据）"""
    return [l for l in _read_lines(path) if l.startswith("waypoint:")]


def _pick_target_wp_file(dim_dir):
    """目标维度目录里该写入哪个 txt：优先 waypoints.txt，其次 mw$*.txt"""
    if not os.path.isdir(dim_dir):
        return None
    txts = [f for f in sorted(os.listdir(dim_dir)) if f.lower().endswith(".txt")]
    if not txts:
        return None
    if "waypoints.txt" in txts:
        return os.path.join(dim_dir, "waypoints.txt")
    mw = [f for f in txts if f.startswith("mw$")]
    return os.path.join(dim_dir, mw[0] if mw else txts[0])


def _target_wp_name(mini_dst):
    """目标容器惯用的路径点文件名（如 mw$123_1.txt）；找不到则 None"""
    if not os.path.isdir(mini_dst):
        return None
    for d in sorted(os.listdir(mini_dst)):
        p = _pick_target_wp_file(os.path.join(mini_dst, d))
        if p:
            return os.path.basename(p)
    return None


def _target_wm_subdir(wm_dim_dir):
    """目标世界地图维度目录里，若存在唯一 mw$<id> 子目录则返回它（多人服务器用多世界子目录）"""
    if not os.path.isdir(wm_dim_dir):
        return ""
    subs = [x for x in sorted(os.listdir(wm_dim_dir))
            if x.startswith("mw$") and os.path.isdir(os.path.join(wm_dim_dir, x))]
    return subs[0] if len(subs) == 1 else ""


def xaero_preview(client_root, src, dst):
    """预览：返回 (路径点条数{维度:条数}, 地图文件数{维度:文件数})"""
    xr = xaero_root(client_root)
    mini_src = os.path.join(xr, XAERO_MINIMAP, src)
    wm_src = os.path.join(xr, XAERO_WORLDMAP, src)
    wp, mp = {}, {}
    if os.path.isdir(mini_src):
        for dim in sorted(os.listdir(mini_src)):
            d = os.path.join(mini_src, dim)
            if not os.path.isdir(d):
                continue
            n = 0
            for f in os.listdir(d):
                if f.lower().endswith(".txt"):
                    n += len(_waypoint_lines(os.path.join(d, f)))
            if n:
                wp[dim] = n
    if os.path.isdir(wm_src):
        for dim in sorted(os.listdir(wm_src)):
            d = os.path.join(wm_src, dim)
            if not os.path.isdir(d):
                continue
            mp[dim] = sum(1 for f in _walk_files(d) if not f.endswith(".lock"))
    return wp, mp


def read_world_multiworld_id(world_dir):
    """从本地 <世界目录>/xaeromap.txt 读取 id:<数字>（Xaero 多世界ID）"""
    for name in ("xaeromap.txt", "xaeroworldmap.txt"):
        p = os.path.join(world_dir, name)
        if os.path.isfile(p):
            for line in _read_lines(p):
                m = re.match(r"^\s*id\s*:\s*(-?\d+)\s*$", line)
                if m:
                    return m.group(1)
    return None


def sftp_read_multiworld_id(ssh, world_dir):
    """从 SFTP 远端 <世界目录>/xaeromap.txt 读取 id:<数字>"""
    sftp = ssh.open_sftp()
    try:
        for name in ("xaeromap.txt", "xaeroworldmap.txt"):
            try:
                with sftp.open(posix_join(world_dir, name), "r") as fh:
                    data = fh.read(4096)
            except IOError:
                continue
            if isinstance(data, bytes):
                data = data.decode("utf-8", "replace")
            for line in data.splitlines():
                m = re.match(r"^\s*id\s*:\s*(-?\d+)\s*$", line)
                if m:
                    return m.group(1)
    finally:
        sftp.close()
    return None


def xaero_align_id(client_root, container, new_id, report=None):
    """把容器内 mw$<旧ID>_1.txt（小地图）与 mw$<旧ID>（世界地图目录）统一改成 new_id。
    被改名的文件先备份，重命名映射写入 改名记录.txt（可据此还原）。返回 (改动数量, 备份目录)。"""
    xr = xaero_root(client_root)
    backup_dir = os.path.join(client_root, "xaero_backup_%s_%s_align_to_%s" % (
        datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
        container.replace("/", "_"), new_id))
    renamed = []

    def _do(old, new, label):
        if os.path.isfile(old):
            bp = os.path.join(backup_dir, os.path.relpath(old, client_root))
            os.makedirs(os.path.dirname(bp), exist_ok=True)
            shutil.copy2(old, bp)
        os.replace(old, new)
        renamed.append((os.path.relpath(old, client_root), os.path.relpath(new, client_root)))
        if report:
            report("[对齐] %s → %s" % (label, os.path.basename(new)))

    n = 0
    mini = os.path.join(xr, XAERO_MINIMAP, container)
    if os.path.isdir(mini):
        for dim in sorted(os.listdir(mini)):
            d = os.path.join(mini, dim)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                m = re.match(r"^mw\$(\d+)(.*)$", f)
                if not m or m.group(1) == new_id:
                    continue
                newf = "mw$%s%s" % (new_id, m.group(2))
                if os.path.exists(os.path.join(d, newf)):
                    if report:
                        report("[对齐] 跳过（已存在 %s）" % newf)
                    continue
                _do(os.path.join(d, f), os.path.join(d, newf), f)
                n += 1
    wm = os.path.join(xr, XAERO_WORLDMAP, container)
    if os.path.isdir(wm):
        for dim in sorted(os.listdir(wm)):
            d = os.path.join(wm, dim)
            if not os.path.isdir(d):
                continue
            for sub in sorted(os.listdir(d)):
                m = re.match(r"^mw\$(\d+)$", sub)
                if not m or m.group(1) == new_id:
                    continue
                newsub = "mw$%s" % new_id
                if os.path.exists(os.path.join(d, newsub)):
                    if report:
                        report("[对齐] 跳过（已存在 %s）" % newsub)
                    continue
                _do(os.path.join(d, sub), os.path.join(d, newsub), sub)
                n += 1

    if renamed:
        with open(os.path.join(backup_dir, "改名记录.txt"), "w", encoding="utf-8") as fh:
            fh.write("目录改名可逆：把下列右列改回左列即可还原\n\n")
            for a, b in renamed:
                fh.write("%s  ->  %s\n" % (a, b))
    return n, (backup_dir if renamed else None)


def xaero_transfer(client_root, src, dst, do_waypoints=True, do_map=True,
                   report=None, progress=None, cancel=None, multi_id=None):
    """把 Xaero 客户端数据从容器 src 合并到容器 dst（不破坏目标已有数据）。
    返回 (结果描述字符串, 备份目录)。"""
    xr = xaero_root(client_root)
    mini_src = os.path.join(xr, XAERO_MINIMAP, src)
    mini_dst = os.path.join(xr, XAERO_MINIMAP, dst)
    wm_src = os.path.join(xr, XAERO_WORLDMAP, src)
    wm_dst = os.path.join(xr, XAERO_WORLDMAP, dst)
    if not os.path.isdir(mini_src) and not os.path.isdir(wm_src):
        return "源容器没有 xaero 数据（%s）" % src, None

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(client_root, "xaero_backup_%s_%s_to_%s"
                              % (stamp, src.replace("/", "_"), dst.replace("/", "_")))
    os.makedirs(backup_dir, exist_ok=True)

    def _backup(path):
        rel = os.path.relpath(path, client_root)
        bp = os.path.join(backup_dir, rel)
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        if not os.path.exists(bp):
            shutil.copy2(path, bp)

    n_wp, n_map = 0, 0
    # 1) 路径点：按维度合并到目标容器
    if do_waypoints and os.path.isdir(mini_src):
        dst_name = _target_wp_name(mini_dst)
        for dim in sorted(os.listdir(mini_src)):
            if cancel and cancel.is_set():
                return "已取消", backup_dir
            sdir = os.path.join(mini_src, dim)
            if not os.path.isdir(sdir):
                continue
            src_lines = []
            for f in sorted(os.listdir(sdir)):
                if f.lower().endswith(".txt"):
                    src_lines += _waypoint_lines(os.path.join(sdir, f))
            if not src_lines:
                continue
            ddir = os.path.join(mini_dst, dim)
            os.makedirs(ddir, exist_ok=True)
            if multi_id:
                tgt = os.path.join(ddir, "mw$%s_1.txt" % multi_id)
            else:
                tgt = _pick_target_wp_file(ddir) or os.path.join(ddir, dst_name or "waypoints.txt")
            if os.path.isfile(tgt):
                _backup(tgt)
            exist = set(_waypoint_lines(tgt))
            add = [l for l in src_lines if l not in exist]
            if not add:
                if report:
                    report(f"[Xaero路径点] {dim}: 目标已有全部 {len(src_lines)} 条，跳过")
                continue
            content = _read_lines(tgt)
            if not content:
                content = ["#", "#waypoint:name:initials:x:y:z:color:disabled:type:"
                           "set:rotate_on_tp:tp_yaw:visibility_type:destination", "#"]
            content += add
            with open(tgt, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(content) + "\n")
            n_wp += len(add)
            if report:
                report(f"[Xaero路径点] {dim}: 合并 {len(add)} 条 → {os.path.relpath(tgt, client_root)}")

    # 2) 已探索地图：补充目标容器缺失的区块文件（不覆盖已有）
    if do_map and os.path.isdir(wm_src):
        for dim in sorted(os.listdir(wm_src)):
            if cancel and cancel.is_set():
                return "已取消", backup_dir
            sdir = os.path.join(wm_src, dim)
            if not os.path.isdir(sdir):
                continue
            ddir = os.path.join(wm_dst, dim)
            sub = _target_wm_subdir(ddir)
            if not sub and multi_id:
                sub = "mw$%s" % multi_id
            dst_root = os.path.join(ddir, sub) if sub else ddir
            cnt = 0
            for srcf in _walk_files(sdir):
                rel = os.path.relpath(srcf, sdir)
                if rel.endswith(".lock"):
                    continue
                df = os.path.join(dst_root, rel)
                if os.path.exists(df):
                    continue
                os.makedirs(os.path.dirname(df), exist_ok=True)
                shutil.copy2(srcf, df)
                cnt += 1
            if cnt:
                n_map += cnt
                if report:
                    report(f"[Xaero地图] {dim}: 补充 {cnt} 个已探索区块文件 → "
                           f"{os.path.relpath(dst_root, client_root)}")
        # 容器根部的 XaeroPlus 数据（标记/传送门/新区块）
        for f in sorted(os.listdir(wm_src)):
            srcf = os.path.join(wm_src, f)
            if not os.path.isfile(srcf) or f.lower() in ("server_config.txt", "config.txt"):
                continue
            df = os.path.join(wm_dst, f)
            if os.path.exists(df):
                continue
            os.makedirs(wm_dst, exist_ok=True)
            shutil.copy2(srcf, df)
            n_map += 1
            if report:
                report(f"[Xaero地图] 复制 {f}")

    msg = "完成：合并路径点 %d 条，补充地图文件 %d 个" % (n_wp, n_map)
    return msg, backup_dir


def scan_contents(all_files, patterns, progress=None, cancel=None):
    """扫描文件内容，返回 [(路径, 类型)]，类型: raw / gzip / mca"""
    hits = []
    total = len(all_files)
    for i, p in enumerate(all_files):
        if cancel and cancel.is_set():
            break
        if file_contains(p, patterns):
            hits.append((p, "raw"))
        elif is_gzip_file(p) and gzip_contains(p, patterns):
            hits.append((p, "gzip"))
        elif is_mca_file(p) and mca_contains(p, patterns):
            hits.append((p, "mca"))
        if progress:
            progress(i + 1, total)
    return hits


def transfer(root, uuid_a, uuid_b, report=None, progress=None, cancel=None,
             on_changed=None, on_renamed=None):
    """执行迁移：备份 → 内容替换（文本/原始NBT/gzipNBT/mca/Xaero）→ 文件名/目录名替换。
    on_changed(p): 内容被修改的本地路径；on_renamed(old, new): 被改名的路径。"""
    patterns = uuid_patterns(uuid_a)
    pairs = uuid_pairs(uuid_a, uuid_b)
    name_hits, all_files = scan_matches(root, uuid_a)

    if report:
        report("扫描内容...")
    content_hits = scan_contents(all_files, patterns, progress=progress, cancel=cancel)

    if report:
        report(f"文件名命中 {len(name_hits)} 项 | 内容命中 {len(content_hits)} 项")

    # 1) 备份：改动前把所有涉及文件复制到 uuid_backup_时间戳_UUID对/（保留相对路径，可整体还原）
    backup_dir = os.path.join(
        root,
        "uuid_backup_%s_%s_to_%s" % (
            datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
            uuid_a.lower()[:8],
            uuid_b.lower()[:8],
        ),
    )
    targets = set(name_hits) | {p for p, _ in content_hits}
    for p in name_hits:                      # 改名目标已存在的 B 旧数据一并备份
        newp = ci_replace(p, uuid_a, uuid_b)
        if os.path.exists(newp):
            targets.add(newp)
    os.makedirs(backup_dir, exist_ok=True)
    for p in sorted(targets):
        dst = os.path.join(backup_dir, os.path.relpath(p, root))
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(p):
                shutil.copytree(p, dst)
            else:
                shutil.copy2(p, dst)
            if report:
                report(f"[备份] {p}")
        except OSError as e:
            if report:
                report(f"[备份失败] {p}: {e}")

    if cancel and cancel.is_set():
        if report:
            report("已取消")
        return

    # 2) 内容替换：raw / gzip / mca
    for p, kind in content_hits:
        ok = False
        if kind == "gzip":
            ok = gzip_nbt_edit(p, pairs)
            tag = "gzipNBT"
        elif kind == "mca":
            ok = mca_edit(p, pairs)
            tag = "区块"
        else:
            ok = replace_in_file(p, pairs)
            tag = "内容"
        if ok:
            if on_changed:
                on_changed(p)
            if report:
                report(f"[{tag}] {p}")

    # 3) 文件名/目录名替换（目标同名文件已备份，直接覆盖）
    for p in name_hits:
        newp = ci_replace(p, uuid_a, uuid_b)
        try:
            os.replace(p, newp)
            if on_renamed:
                on_renamed(p, newp)
            if report:
                report(f"[改名] {p} -> {newp}")
        except OSError as e:
            if report:
                report(f"[失败] {p}: {e}")

    if report:
        report(f"备份目录: {backup_dir}")
        report("迁移完成")


# ---- SFTP 多人服务器模式 ----

def posix_join(base, rel):
    base = base.rstrip("/")
    return (base + "/" + rel) if rel else base


def sftp_connect(host, port, user, passwd, report=None):
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, int(port), username=user, password=passwd or None, timeout=30)
    if ssh.get_transport():
        ssh.get_transport().set_keepalive(30)
    if report:
        report(f"SFTP 连接成功：{host}:{port}")
    return ssh


def _set_sftp_timeout(sftp, seconds=60):
    """给 SFTP 通道设超时，避免单个操作（列目录/下载/上传）无限挂起"""
    try:
        ch = sftp.get_channel()
        ch.settimeout(seconds)
    except Exception:
        pass


def sftp_list_all(sftp, remote_root, report=None, cancel=None):
    """递归列出远程所有文件路径（相对 remote_root），带 180s 硬超时看门狗防卡死。
    传入已打开的 SFTP 通道（单通道复用，避免重复 open_sftp 在部分服务器上挂起）。"""
    box = {}

    def _inner():
        return _sftp_walk(sftp, remote_root, report, cancel)

    t = threading.Thread(target=lambda: box.update(r=_inner()), daemon=True)
    t.start()
    t.join(timeout=180)
    if t.is_alive():
        if report:
            report("[超时] 远程目录扫描超过 180 秒未完成，已中断。请检查网络后重试。")
        return None
    return box.get("r")


def _sftp_walk(sftp, remote_root, report, cancel):
    import stat as stat_mod
    files = []
    stack = [remote_root.rstrip("/")]
    seen = set()
    dirs_done = 0
    while stack:
        if cancel and cancel.is_set():
            return None
        d = stack.pop()
        if d in seen:
            continue
        seen.add(d)
        try:
            attrs = sftp.listdir_attr(d)
        except Exception as e:
            if report:
                report(f"[跳过] 无法列出 {d}：{e}")
            continue
        for a in attrs:
            full = (d + "/" + a.filename) if d else a.filename
            if stat_mod.S_ISDIR(a.st_mode):
                stack.append(full)
            else:
                files.append(full)
        dirs_done += 1
        if report and (dirs_done % 20 == 0 or len(files) % 500 == 0):
            report(f"扫描中... 已遍历 {dirs_done} 个目录 / {len(files)} 个文件")
    root = remote_root.rstrip("/")
    out = []
    for f in files:
        if f.startswith(root + "/"):
            rel = f[len(root) + 1:]
        elif f == root:
            continue
        else:
            rel = f
        out.append(rel)
    return out


def sftp_ensure_dirs(sftp, remote_root, reldir):
    if not reldir:
        return
    cur = remote_root.rstrip("/")
    for part in reldir.split("/"):
        cur += "/" + part
        try:
            sftp.stat(cur)
        except IOError:
            try:
                sftp.mkdir(cur)
            except IOError:
                pass


def sftp_transfer(ssh, remote_root, uuid_a, uuid_b, report=None, progress=None, cancel=None):
    """SFTP 迁移：下载远端镜像 → 本地迁移 → 只回传改动文件；原文件备份到本地。
    返回 (本地备份目录, 镜像目录)。"""
    import tempfile
    sftp = ssh.open_sftp()
    _set_sftp_timeout(sftp)
    remote_root = remote_root.rstrip("/")
    if report:
        report("扫描远程文件列表...")
    files = sftp_list_all(sftp, remote_root, report=report, cancel=cancel)
    if files is None:
        sftp.close()
        if report:
            report("已取消")
        return None, mirror
    if report:
        report(f"远程文件 {len(files)} 个，下载镜像...")

    mirror = tempfile.mkdtemp(prefix="uuid_mirror_")
    total = len(files)
    for i, rel in enumerate(files):
        if cancel and cancel.is_set():
            sftp.close()
            if report:
                report("已取消")
            return None, mirror
        local = os.path.join(mirror, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        try:
            sftp.get(posix_join(remote_root, rel), local)
        except Exception as e:
            if report:
                report(f"[下载失败] {rel}: {e}")
        if progress:
            progress(i + 1, total)

    renames = []          # (old, new)
    content_set = set()   # 内容被修改的本地路径（改名前的旧路径）

    def _changed(p):
        content_set.add(p)

    def _renamed(old, new):
        renames.append((old, new))

    if report:
        report("镜像完成，开始本地迁移...")
    transfer(mirror, uuid_a, uuid_b, report=report, cancel=cancel,
             on_changed=_changed, on_renamed=_renamed)

    # 备份目录移到持久位置（镜像可能被临时清理）
    saved_backup = None
    for d in os.listdir(mirror):
        if d.lower().startswith("uuid_backup_"):
            src = os.path.join(mirror, d)
            dst = os.path.join(os.getcwd(), d)
            if os.path.exists(dst):
                dst += "_" + datetime.datetime.now().strftime("%H%M%S")
            try:
                shutil.move(src, dst)
                saved_backup = dst
                if report:
                    report(f"本地备份: {dst}")
            except OSError as e:
                if report:
                    report(f"[备份移动失败] {e}")
            break

    # 计算需要回传的文件（内容改动映射到改名后路径 + 改名目录下的所有文件）
    def map_path(p):
        best = None
        for old, new in renames:
            if p == old or p.startswith(old + os.sep):
                if best is None or len(old) > len(best[0]):
                    best = (old, new)
        if best is None:
            return p
        return best[1] + p[len(best[0]):]

    upload = set()
    for p in content_set:
        upload.add(map_path(p))
    for old, new in renames:
        if os.path.isdir(new):
            for dp, _, fns in os.walk(new):
                for fn in fns:
                    upload.add(os.path.join(dp, fn))
        else:
            upload.add(new)

    # 回传
    if report:
        report(f"回传 {len(upload)} 个文件...")
    n = len(upload)
    for i, lp in enumerate(sorted(upload)):
        if cancel and cancel.is_set():
            break
        if not os.path.isfile(lp):
            continue
        rel = os.path.relpath(lp, mirror).replace(os.sep, "/")
        if rel.lower().startswith("uuid_backup_"):
            continue
        rp = posix_join(remote_root, rel)
        try:
            sftp_ensure_dirs(sftp, remote_root, os.path.dirname(rel))
            sftp.put(lp, rp)
            if report:
                report(f"[上传] {rel}")
        except Exception as e:
            if report:
                report(f"[上传失败] {rel}: {e}")
        if progress:
            progress(i + 1, max(n, 1))

    # 删除远端被改名消失的旧路径
    mirror_rels = set()
    for dp, _, fns in os.walk(mirror):
        for fn in fns:
            lp = os.path.join(dp, fn)
            rel = os.path.relpath(lp, mirror).replace(os.sep, "/")
            if not rel.lower().startswith("uuid_backup_"):
                mirror_rels.add(rel)
    for rel in files:
        if rel in mirror_rels:
            continue
        try:
            sftp.remove(posix_join(remote_root, rel))
            if report:
                report(f"[删除旧文件] {rel}")
        except Exception:
            pass

    sftp.close()
    if report:
        report("SFTP 迁移完成")
    return saved_backup, mirror


class App:
    def __init__(self, master):
        self.master = master
        master.title("UUID 玩家数据迁移")
        master.geometry("720x560")
        self.q = queue.Queue()
        self.cancel = threading.Event()

        frm = ttk.Frame(master, padding=8)
        frm.pack(fill="both", expand=True)

        # ---- 用户名一键替换（正版↔离线）----
        top = ttk.Frame(frm)
        top.grid(row=0, column=0, columnspan=3, sticky="we")
        ttk.Label(top, text="用户名:").pack(side="left")
        self.name_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.name_var, width=16).pack(side="left", padx=4)
        self.dir_var = tk.StringVar(value="正版→离线")
        ttk.Combobox(top, textvariable=self.dir_var,
                     values=("正版→离线", "离线→正版"),
                     width=9, state="readonly").pack(side="left", padx=4)
        self.auto_btn = ttk.Button(top, text="一键替换", command=self.auto_replace)
        self.auto_btn.pack(side="left", padx=4)
        ttk.Label(top, text="（自动算正版/离线 UUID 填入当前页并执行替换）").pack(side="left")
        ttk.Button(top, text="使用教程", command=self.show_tutorial).pack(side="right", padx=4)

        nb = ttk.Notebook(frm)
        nb.grid(row=1, column=0, columnspan=3, sticky="nsew")

        # ---- 单人存档页 ----
        t1 = ttk.Frame(nb, padding=8)
        nb.add(t1, text="单人存档")
        ttk.Label(t1, text="存档根目录:").grid(row=0, column=0, sticky="w")
        self.root_var = tk.StringVar()
        ttk.Entry(t1, textvariable=self.root_var).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(t1, text="浏览", command=self.browse).grid(row=0, column=2)
        ttk.Label(t1, text="来源UUID(A):").grid(row=1, column=0, sticky="w")
        self.a_var = tk.StringVar()
        ttk.Entry(t1, textvariable=self.a_var).grid(row=1, column=1, columnspan=2, sticky="we", padx=4)
        ttk.Label(t1, text="目标UUID(B):").grid(row=2, column=0, sticky="w")
        self.b_var = tk.StringVar()
        ttk.Entry(t1, textvariable=self.b_var).grid(row=2, column=1, columnspan=2, sticky="we", padx=4)
        t1.columnconfigure(1, weight=1)

        # ---- 多人服务器页 ----
        t2 = ttk.Frame(nb, padding=8)
        nb.add(t2, text="多人服务器")
        ttk.Label(t2, text="SFTP地址:").grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar()
        ttk.Entry(t2, textvariable=self.host_var).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Label(t2, text="端口:").grid(row=0, column=2, sticky="e")
        self.port_var = tk.StringVar(value="22")
        ttk.Entry(t2, textvariable=self.port_var, width=7).grid(row=0, column=3)
        ttk.Label(t2, text="用户名:").grid(row=1, column=0, sticky="w")
        self.user_var = tk.StringVar()
        ttk.Entry(t2, textvariable=self.user_var).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Label(t2, text="密码:").grid(row=1, column=2, sticky="e")
        self.pass_var = tk.StringVar()
        ttk.Entry(t2, textvariable=self.pass_var, show="*").grid(row=1, column=3)
        self.remember_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(t2, text="记住密码", variable=self.remember_var).grid(row=1, column=4, sticky="w")
        ttk.Label(t2, text="远端世界根目录:").grid(row=2, column=0, sticky="w")
        self.ftp_root_var = tk.StringVar(value="/")
        ttk.Entry(t2, textvariable=self.ftp_root_var).grid(row=2, column=1, columnspan=3, sticky="we", padx=4)
        ttk.Label(t2, text="来源UUID(A):").grid(row=3, column=0, sticky="w")
        self.a2_var = tk.StringVar()
        ttk.Entry(t2, textvariable=self.a2_var).grid(row=3, column=1, columnspan=3, sticky="we", padx=4)
        ttk.Label(t2, text="目标UUID(B):").grid(row=4, column=0, sticky="w")
        self.b2_var = tk.StringVar()
        ttk.Entry(t2, textvariable=self.b2_var).grid(row=4, column=1, columnspan=3, sticky="we", padx=4)
        ttk.Button(t2, text="测试连接", command=self.test_connection).grid(row=5, column=0, columnspan=4, sticky="w", pady=4)
        t2.columnconfigure(1, weight=1)

        # ---- Xaero 地图转移页 ----
        t3 = ttk.Frame(nb, padding=8)
        nb.add(t3, text="Xaero 地图转移")
        ttk.Label(t3, text="客户端目录(含 xaero):").grid(row=0, column=0, sticky="w")
        self.xa_root_var = tk.StringVar()
        ttk.Entry(t3, textvariable=self.xa_root_var).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(t3, text="浏览", command=self.browse_xaero).grid(row=0, column=2)
        ttk.Label(t3, text="源容器(要搬走的):").grid(row=1, column=0, sticky="w")
        self.xa_src_var = tk.StringVar()
        self.xa_src_box = ttk.Combobox(t3, textvariable=self.xa_src_var, values=(), width=36)
        self.xa_src_box.grid(row=1, column=1, columnspan=2, sticky="we", padx=4)
        ttk.Label(t3, text="目标容器(要搬到的):").grid(row=2, column=0, sticky="w")
        self.xa_dst_var = tk.StringVar()
        self.xa_dst_box = ttk.Combobox(t3, textvariable=self.xa_dst_var, values=(), width=36)
        self.xa_dst_box.grid(row=2, column=1, columnspan=2, sticky="we", padx=4)
        ttk.Label(t3, text="服务器世界目录(可选):").grid(row=3, column=0, sticky="w")
        self.xa_world_var = tk.StringVar()
        ttk.Entry(t3, textvariable=self.xa_world_var).grid(row=3, column=1, sticky="we", padx=4)
        ttk.Button(t3, text="读取多世界ID", command=self.xaero_read_id).grid(row=3, column=2)
        ttk.Label(t3, text="多世界ID(可选):").grid(row=4, column=0, sticky="w")
        self.xa_mwid_var = tk.StringVar()
        ttk.Entry(t3, textvariable=self.xa_mwid_var, width=18).grid(row=4, column=1, sticky="w", padx=4)
        ttk.Button(t3, text="对齐到目标容器", command=self.xaero_align).grid(row=4, column=2, sticky="w")
        xa_opt = ttk.Frame(t3)
        xa_opt.grid(row=5, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Button(xa_opt, text="刷新容器列表", command=self.xaero_refresh).pack(side="left", padx=4)
        self.xa_wp_var = tk.BooleanVar(value=True)
        self.xa_map_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(xa_opt, text="路径点", variable=self.xa_wp_var).pack(side="left", padx=4)
        ttk.Checkbutton(xa_opt, text="已探索地图", variable=self.xa_map_var).pack(side="left", padx=4)
        xa_btns = ttk.Frame(t3)
        xa_btns.grid(row=6, column=0, columnspan=3, sticky="w", pady=4)
        self.xa_scan_btn = ttk.Button(xa_btns, text="扫描预览", command=self.xaero_scan)
        self.xa_scan_btn.pack(side="left", padx=4)
        self.xa_go_btn = ttk.Button(xa_btns, text="开始转移", command=self.xaero_go)
        self.xa_go_btn.pack(side="left", padx=4)
        ttk.Label(t3, text="用途：把单机世界的路径点 / 已探索地图，合并到该服务器的容器（反向亦可）。").grid(
            row=7, column=0, columnspan=3, sticky="w")
        ttk.Label(t3, text="说明：容器 = xaero 里区分世界/服务器的文件夹；“服务器世界目录”填 world 文件夹可自动读取多世界ID，"
                           "让文件名对齐服务器。").grid(row=8, column=0, columnspan=3, sticky="w")
        ttk.Label(t3, text="注意：路径点与地图属于客户端，与 UUID 无关；执行前请先退出游戏。").grid(
            row=9, column=0, columnspan=3, sticky="w")
        t3.columnconfigure(1, weight=1)

        # ---- 共用按钮 / 日志 / 进度 ----
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=3, pady=4)
        self.scan_btn = ttk.Button(btns, text="扫描", command=self.scan)
        self.scan_btn.pack(side="left", padx=4)
        self.go_btn = ttk.Button(btns, text="开始迁移", command=self.go)
        self.go_btn.pack(side="left", padx=4)
        self.cancel_btn = ttk.Button(btns, text="取消", command=lambda: self.cancel.set(), state="disabled")
        self.cancel_btn.pack(side="left", padx=4)

        lb_frame = ttk.Frame(frm)
        lb_frame.grid(row=3, column=0, columnspan=3, sticky="nsew")
        self.listbox = tk.Listbox(lb_frame, height=13)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lb_frame, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)

        self.prog = ttk.Progressbar(frm, maximum=100)
        self.prog.grid(row=4, column=0, columnspan=3, sticky="we", pady=6)

        self.status = tk.StringVar(value="就绪：单人页填存档目录 / 多人页填 SFTP 信息；或用用户名一键替换（正版→离线）")
        ttk.Label(frm, textvariable=self.status).grid(row=5, column=0, columnspan=3, sticky="w")

        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(3, weight=1)

        # 加载已保存的服务器配置
        self._load_server_config()
        master.protocol("WM_DELETE_WINDOW", self._on_close)
        master.after(100, self.poll)

    def _load_server_config(self):
        cfg = load_config()
        if not cfg:
            return
        if cfg.get("host"):
            self.host_var.set(cfg["host"])
        if cfg.get("port"):
            self.port_var.set(str(cfg["port"]))
        if cfg.get("user"):
            self.user_var.set(cfg["user"])
        if cfg.get("root"):
            self.ftp_root_var.set(cfg["root"])
        if cfg.get("remember_pw") and cfg.get("pw"):
            try:
                self.pass_var.set(_deobfuscate(cfg["pw"]))
                self.remember_var.set(True)
            except Exception:
                pass

    def _save_server_config(self):
        cfg = {
            "host": self.host_var.get().strip(),
            "port": self.port_var.get().strip() or "22",
            "user": self.user_var.get().strip(),
            "root": self.ftp_root_var.get().strip() or "/",
            "remember_pw": bool(self.remember_var.get()),
        }
        if self.remember_var.get() and self.pass_var.get():
            cfg["pw"] = _obfuscate(self.pass_var.get())
        save_config(cfg)

    def _on_close(self):
        self._save_server_config()
        self.master.destroy()

    def auto_replace(self):
        """按用户名一键替换：根据方向把 正版/离线 UUID 填为 A/B 并执行迁移"""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("错误", "请先输入用户名")
            return
        to_offline = self.dir_var.get().startswith("正版")
        offline = offline_uuid(name)
        if self._current_mode() == "single":
            root = self.root_var.get().strip()
            online = online_uuid_from_cache(root, name) or online_uuid_from_mojang(name)
            if not online:
                self.a_var.set("")
                self.b_var.set(offline)
                messagebox.showerror("错误",
                                     f"无法获取 {name} 的正版 UUID（Mojang API 与 usercache 均未命中）。\n"
                                     f"离线 UUID：{offline}\n请手动填写 A/B 后再迁移。")
                return
            self.a_var.set(online if to_offline else offline)
            self.b_var.set(offline if to_offline else online)
            self.listbox.delete(0, "end")
            self.listbox.insert("end", f"正版 UUID = {online}")
            self.listbox.insert("end", f"离线 UUID = {offline}")
            self.listbox.insert("end", "方向：" + ("正版→离线" if to_offline else "离线→正版"))
            self.go()
        else:
            online = online_uuid_from_mojang(name)
            if not online:
                self.a2_var.set("")
                self.b2_var.set(offline)
                messagebox.showerror("错误",
                                     f"无法获取 {name} 的正版 UUID（Mojang API 未命中）。\n"
                                     f"离线 UUID：{offline}\n请手动填写 A/B 后再迁移。")
                return
            self.a2_var.set(online if to_offline else offline)
            self.b2_var.set(offline if to_offline else online)
            self.listbox.delete(0, "end")
            self.listbox.insert("end", f"正版 UUID = {online}")
            self.listbox.insert("end", f"离线 UUID = {offline}")
            self.listbox.insert("end", "方向：" + ("正版→离线" if to_offline else "离线→正版"))
            self.go()

    def test_connection(self):
        """测试 SFTP 连通性（可留空密码）"""
        if self._current_mode() != "ftp":
            messagebox.showinfo("提示", "请先在“多人服务器”页填写 SFTP 信息")
            return
        host = self.host_var.get().strip()
        port = self.port_var.get().strip() or "22"
        user = self.user_var.get().strip()
        passwd = self.pass_var.get()
        froot = self.ftp_root_var.get().strip() or "/"
        if not host:
            messagebox.showerror("错误", "请先填写 SFTP 地址")
            return
        self._busy(True)
        self.status.set("正在测试连接...")
        threading.Thread(target=self._worker_test, args=(host, port, user, passwd, froot), daemon=True).start()

    def _worker_test(self, host, port, user, passwd, froot):
        try:
            ssh = sftp_connect(host, port, user, passwd or None, report=lambda m: self.q.put(("msg", m)))
            sftp = ssh.open_sftp()
            _set_sftp_timeout(sftp, 30)
            attrs = sftp.listdir_attr(froot)
            n = len(attrs) if attrs else 0
            sftp.close()
            ssh.close()
            self.q.put(("msg", f"[连接测试] 成功：{host}:{port}，根目录 {froot} 可访问（{n} 个条目）"))
        except Exception as e:
            self.q.put(("msg", f"[连接测试] 失败：{host}:{port} -> {e}"))
        self.q.put(("done",))

    def _current_mode(self):
        # 通过 Notebook 当前选中页判断
        nb = None
        for w in self.master.winfo_children():
            for c in w.winfo_children():
                if isinstance(c, ttk.Notebook):
                    nb = c
        if nb is None:
            return "single"
        try:
            idx = nb.index(nb.select())
        except Exception:
            return "single"
        return ("single", "ftp", "xaero")[idx] if 0 <= idx < 3 else "single"

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.root_var.set(d)

    def show_tutorial(self):
        if not tutorial_files():
            messagebox.showinfo("提示", "未找到教程资源（开发模式下请把 md 放在 使用教程/ 目录）")
            return
        TutorialWindow(self.master)

    def browse_xaero(self):
        d = filedialog.askdirectory(title="选择客户端目录（含 xaero 文件夹）")
        if d:
            self.xa_root_var.set(d)
            self.xaero_refresh()

    def xaero_refresh(self):
        root = self.xa_root_var.get().strip()
        if not root:
            messagebox.showerror("错误", "请先选择客户端目录")
            return
        cs = xaero_containers(root)
        self.xa_src_box["values"] = cs
        self.xa_dst_box["values"] = cs
        self.listbox.insert("end", "[Xaero] 发现 %d 个容器：%s" % (len(cs), ", ".join(cs) if cs else "无"))
        self.listbox.see("end")
        if cs:
            if self.xa_src_var.get() not in cs:
                self.xa_src_var.set(cs[0])
            if self.xa_dst_var.get() not in cs:
                self.xa_dst_var.set(cs[1] if len(cs) > 1 else cs[0])

    def xaero_read_id(self):
        """读取服务器多世界ID：优先用“服务器世界目录”，否则用多人页的 SFTP 信息"""
        world = self.xa_world_var.get().strip()
        mwid = None
        if world:
            if not os.path.isdir(world):
                messagebox.showerror("错误", "服务器世界目录不存在（应填 world 文件夹）")
                return
            mwid = read_world_multiworld_id(world)
            if not mwid:
                messagebox.showerror("错误", "该目录下没有 xaeromap.txt（或其中没有 id: 行）")
                return
        else:
            host = self.host_var.get().strip()
            if not host:
                messagebox.showerror("错误", "请填“服务器世界目录”，或先在“多人服务器”页填 SFTP 信息")
                return
            port = self.port_var.get().strip() or "22"
            user = self.user_var.get().strip()
            passwd = self.pass_var.get()
            froot = self.ftp_root_var.get().strip() or "/"
            self.status.set("读取远端多世界ID...")
            self.listbox.insert("end", f"[Xaero] 从 SFTP {host}:{port}{froot} 读取 id...")
            try:
                ssh = sftp_connect(host, port, user, passwd or None)
                try:
                    mwid = sftp_read_multiworld_id(ssh, froot)
                finally:
                    ssh.close()
            except Exception as e:
                messagebox.showerror("错误", f"SFTP 读取失败：{e}")
                return
            if not mwid:
                messagebox.showerror("错误", f"远端 {froot}/xaeromap.txt 中没有 id: 行")
                return
        self.xa_mwid_var.set(mwid)
        self.listbox.insert("end", f"[Xaero] 多世界ID = {mwid}")
        self.listbox.see("end")

    def xaero_align(self):
        """把目标容器内的 mw$<旧ID> 统一改为当前多世界ID"""
        root = self.xa_root_var.get().strip()
        dst = self.xa_dst_var.get().strip()
        mwid = self.xa_mwid_var.get().strip()
        if not root or not os.path.isdir(root) or not os.path.isdir(xaero_root(root)):
            messagebox.showerror("错误", "客户端目录无效（应为含 xaero 文件夹的目录）")
            return
        if not dst:
            messagebox.showerror("错误", "请填写/选择目标容器")
            return
        if not mwid.isdigit():
            messagebox.showerror("错误", "请先“读取多世界ID”或手动填写（纯数字）")
            return
        try:
            n = xaero_align_id(root, dst, mwid,
                               report=lambda m: self.q.put(("msg", m)))
            self.q.put(("msg", f"[Xaero] 对齐完成，改动 {n} 处（{dst} → id {mwid}）"))
        except Exception as e:
            self.q.put(("msg", f"[Xaero错误] {e}"))
        self.q.put(("done",))

    def _xaero_inputs(self):
        root = self.xa_root_var.get().strip()
        src = self.xa_src_var.get().strip()
        dst = self.xa_dst_var.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showerror("错误", "客户端目录无效（应为含 xaero 文件夹的目录）")
            return None
        if not os.path.isdir(xaero_root(root)):
            messagebox.showerror("错误", "该目录下没有 xaero 文件夹")
            return None
        if not src or not dst:
            messagebox.showerror("错误", "请选择源容器与目标容器")
            return None
        if src == dst:
            messagebox.showerror("错误", "源容器与目标容器不能相同")
            return None
        return root, src, dst

    def xaero_scan(self):
        inp = self._xaero_inputs()
        if not inp:
            return
        root, src, dst = inp
        self.listbox.delete(0, "end")
        self.status.set("Xaero 扫描中...")
        threading.Thread(target=self._worker_xaero_scan, args=(root, src, dst), daemon=True).start()

    def _worker_xaero_scan(self, root, src, dst):
        try:
            wp, mp = xaero_preview(root, src, dst)
            self.q.put(("msg", f"[Xaero] {src} → {dst}"))
            for dim, n in wp.items():
                self.q.put(("msg", f"  路径点 {dim}: {n} 条"))
            for dim, n in mp.items():
                self.q.put(("msg", f"  已探索地图 {dim}: {n} 个文件"))
            if not wp and not mp:
                self.q.put(("msg", "  （源容器没有可转移的数据）"))
            self.q.put(("msg", "点“开始转移”执行（会自动备份目标文件）"))
        except Exception as e:
            self.q.put(("msg", f"[Xaero错误] {e}"))
        self.q.put(("done",))

    def xaero_go(self):
        inp = self._xaero_inputs()
        if not inp:
            return
        root, src, dst = inp
        if not (self.xa_wp_var.get() or self.xa_map_var.get()):
            messagebox.showerror("错误", "请至少勾选“路径点”或“已探索地图”")
            return
        self.cancel.clear()
        self._busy(True)
        self.listbox.delete(0, "end")
        self.prog.configure(value=0)
        mwid = self.xa_mwid_var.get().strip() or None
        threading.Thread(target=self._worker_xaero_go,
                         args=(root, src, dst, self.xa_wp_var.get(), self.xa_map_var.get(), mwid),
                         daemon=True).start()

    def _worker_xaero_go(self, root, src, dst, do_wp, do_map, multi_id=None):
        try:
            msg, bk = xaero_transfer(root, src, dst, do_waypoints=do_wp, do_map=do_map,
                                     report=lambda m: self.q.put(("msg", m)),
                                     progress=self._prog, cancel=self.cancel,
                                     multi_id=multi_id)
            self.q.put(("msg", msg))
            if bk:
                self.q.put(("msg", "备份目录: " + bk))
        except Exception as e:
            self.q.put(("msg", f"[Xaero错误] {e}"))
        self.q.put(("done",))

    def _valid_ab(self, a, b):
        if not valid_uuid(a) or not valid_uuid(b):
            messagebox.showerror("错误", "UUID 格式错误（应为 xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx）")
            return False
        return True

    def get_inputs(self):
        if self._current_mode() == "single":
            root = self.root_var.get().strip()
            a = self.a_var.get().strip().lower()
            b = self.b_var.get().strip().lower()
            if not root or not os.path.isdir(root):
                messagebox.showerror("错误", "存档根目录无效")
                return None
            if not self._valid_ab(a, b):
                return None
            return ("single", root, a, b)
        host = self.host_var.get().strip()
        port = self.port_var.get().strip() or "22"
        user = self.user_var.get().strip()
        passwd = self.pass_var.get()
        froot = self.ftp_root_var.get().strip() or "/"
        a = self.a2_var.get().strip().lower()
        b = self.b2_var.get().strip().lower()
        if not host:
            messagebox.showerror("错误", "SFTP 地址不能为空")
            return None
        if not self._valid_ab(a, b):
            return None
        return ("ftp", (host, port, user, passwd, froot), a, b)

    def _busy(self, flag):
        st = "disabled" if flag else "normal"
        self.scan_btn.configure(state=st)
        self.go_btn.configure(state=st)
        self.xa_scan_btn.configure(state=st)
        self.xa_go_btn.configure(state=st)
        self.cancel_btn.configure(state="normal" if flag else "disabled")

    def _prog(self, i, total):
        self.q.put(("prog", i * 100 // max(total, 1)))

    def scan(self):
        inp = self.get_inputs()
        if not inp:
            return
        mode, loc, a, _ = inp
        self._busy(True)
        self.status.set("扫描中...")
        self.cancel.clear()
        threading.Thread(target=self._worker_scan, args=(mode, loc, a), daemon=True).start()

    def _worker_scan(self, mode, loc, a):
        if mode == "single":
            root = loc
            name_hits, all_files = scan_matches(root, a)
            content = [p for p, _ in scan_contents(all_files, uuid_patterns(a), progress=self._prog, cancel=self.cancel)]
            self.q.put(("scan_done", name_hits, content))
            return
        host, port, user, passwd, froot = loc

        def stat(m):
            self.q.put(("scan_stat", m))

        try:
            ssh = sftp_connect(host, port, user, passwd, report=lambda m: self.q.put(("msg", m)))
            sftp = ssh.open_sftp()
            files = sftp_list_all(sftp, froot, report=stat, cancel=self.cancel)
            sftp.close()
            ssh.close()
        except Exception as e:
            self.q.put(("msg", f"[SFTP错误] {e}"))
            self.q.put(("done",))
            return
        if files is None:
            self.q.put(("done",))
            return
        name_hits = [f for f in files if a in os.path.basename(f).lower()]
        self.q.put(("scan_done", name_hits, []))
        self.q.put(("msg", f"远程共 {len(files)} 个文件；内容命中需迁移时检测"))

    def go(self):
        inp = self.get_inputs()
        if not inp:
            return
        mode, loc, a, b = inp
        self.cancel.clear()
        self._busy(True)
        self.listbox.delete(0, "end")
        self.prog.configure(value=0)
        threading.Thread(target=self._worker_go, args=(mode, loc, a, b), daemon=True).start()

    def _worker_go(self, mode, loc, a, b):
        if mode == "single":
            transfer(loc, a, b,
                     report=lambda m: self.q.put(("msg", m)),
                     progress=self._prog,
                     cancel=self.cancel)
        else:
            host, port, user, passwd, froot = loc
            try:
                ssh = sftp_connect(host, port, user, passwd, report=lambda m: self.q.put(("msg", m)))
                sftp_transfer(ssh, froot, a, b,
                              report=lambda m: self.q.put(("msg", m)),
                              progress=self._prog,
                              cancel=self.cancel)
                try:
                    ssh.close()
                except Exception:
                    pass
            except Exception as e:
                self.q.put(("msg", f"[SFTP错误] {e}"))
        self.q.put(("done",))

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "msg":
                    self.status.set(item[1])
                    self.listbox.insert("end", item[1])
                    self.listbox.see("end")
                elif kind == "scan_stat":
                    self.status.set(item[1])
                elif kind == "prog":
                    self.prog.configure(value=item[1])
                elif kind == "scan_done":
                    name_hits, content = item[1], item[2]
                    self.status.set("文件名命中 %d 项 | 内容命中 %d 项（点“开始迁移”执行）"
                                    % (len(name_hits), len(content)))
                    self.listbox.delete(0, "end")
                    for p in name_hits:
                        self.listbox.insert("end", "[文件名] " + p)
                    for p in content:
                        self.listbox.insert("end", "[内容] " + p)
                    self._busy(False)
                elif kind == "done":
                    self.status.set("完成")
                    self._busy(False)
                    messagebox.showinfo("完成", "操作完成")
        except queue.Empty:
            pass
        self.master.after(100, self.poll)


def main_cli():
    ap = argparse.ArgumentParser(description="UUID 玩家数据迁移（命令行版）")
    ap.add_argument("--root", help="本地存档/服务器根目录")
    ap.add_argument("--a", help="来源 UUID")
    ap.add_argument("--b", help="目标 UUID")
    ap.add_argument("--scan", action="store_true", help="仅扫描预览，不执行迁移")
    ap.add_argument("--sftp-host", help="SFTP 服务器地址（多人服务器模式，提供后走 SFTP）")
    ap.add_argument("--sftp-port", default="22", help="SFTP 端口")
    ap.add_argument("--sftp-user", help="SFTP 用户名")
    ap.add_argument("--sftp-pass", help="SFTP 密码")
    ap.add_argument("--sftp-root", default="/", help="SFTP 远端世界根目录")
    ap.add_argument("--offline-uuid", help="计算关闭正版验证服务器中该用户名的离线 UUID")
    ap.add_argument("--by-username", help="按用户名一键替换：A=正版UUID，B=离线UUID（需配 --root 或 --sftp-host）")
    ap.add_argument("--to-online", action="store_true", help="与 --by-username 搭配：反向替换（A=离线UUID，B=正版UUID）")
    ap.add_argument("--xaero-root", help="Xaero 客户端目录（含 xaero 文件夹）")
    ap.add_argument("--xaero-src", help="Xaero 源容器（要搬走的，如单机世界名）")
    ap.add_argument("--xaero-dst", help="Xaero 目标容器（要搬到的，如 Multiplayer_服务器地址）")
    ap.add_argument("--xaero-scan", action="store_true", help="Xaero 仅预览，不执行")
    ap.add_argument("--xaero-world", help="服务器世界目录（本地或配合 --sftp-* 的远端路径），用于读取多世界ID")
    ap.add_argument("--xaero-id", help="Xaero 多世界ID（直接用该ID命名目标文件）")
    ap.add_argument("--xaero-align", action="store_true", help="只把目标容器文件名对齐到多世界ID")
    args = ap.parse_args()

    if args.offline_uuid:
        print(offline_uuid(args.offline_uuid))
        return

    if args.xaero_root:
        mid = args.xaero_id
        if not mid and args.xaero_world:
            if args.sftp_host:
                ssh0 = sftp_connect(args.sftp_host, args.sftp_port, args.sftp_user,
                                    args.sftp_pass, report=print)
                try:
                    mid = sftp_read_multiworld_id(ssh0, args.xaero_world)
                finally:
                    ssh0.close()
            else:
                mid = read_world_multiworld_id(args.xaero_world)
            print("多世界ID =", mid)
        if args.xaero_align:
            if not args.xaero_dst or not mid:
                sys.exit("对齐需要 --xaero-dst 与可用的 --xaero-id/--xaero-world")
            n, bk = xaero_align_id(args.xaero_root, args.xaero_dst, mid, report=print)
            print("对齐完成，改动 %d 处" % n)
            if bk:
                print("备份目录:", bk)
            return
        if not args.xaero_src or not args.xaero_dst:
            sys.exit("需要 --xaero-src 与 --xaero-dst（可用 --xaero-scan 先看容器列表）")
        if args.xaero_scan:
            wp, mp = xaero_preview(args.xaero_root, args.xaero_src, args.xaero_dst)
            print("容器: %s" % ", ".join(xaero_containers(args.xaero_root)))
            print("源容器 %s → 目标容器 %s" % (args.xaero_src, args.xaero_dst))
            for d, n in wp.items():
                print("  路径点 %s: %d 条" % (d, n))
            for d, n in mp.items():
                print("  已探索地图 %s: %d 个文件" % (d, n))
            return
        msg, bk = xaero_transfer(args.xaero_root, args.xaero_src, args.xaero_dst,
                                 report=print, multi_id=mid)
        print(msg)
        if bk:
            print("备份目录:", bk)
        return

    if args.by_username:
        name = args.by_username
        offline = offline_uuid(name)
        args.b = offline
        args.a = online_uuid_from_cache(args.root, name) if args.root else None
        if not args.a:
            args.a = online_uuid_from_mojang(name)
        if not args.a:
            sys.exit(f"无法获取 {name} 的正版 UUID（Mojang API 与 usercache 均未命中），请手动指定 --a/--b")
        if args.to_online:                      # 反向：离线→正版
            args.a, args.b = args.b, args.a

    if not args.a or not args.b:
        sys.exit("需要 --a 和 --b（或用 --by-username）")
    a, b = args.a.lower(), args.b.lower()
    if not valid_uuid(a) or not valid_uuid(b):
        sys.exit("UUID 格式错误")

    if args.sftp_host:
        ssh = sftp_connect(args.sftp_host, args.sftp_port, args.sftp_user, args.sftp_pass, report=print)
        if args.scan:
            sftp = ssh.open_sftp()
            files = sftp_list_all(sftp, args.sftp_root, report=print)
            sftp.close()
            if files:
                print("远程文件 %d 个:" % len(files))
                for f in files:
                    if a in os.path.basename(f).lower():
                        print("  [文件名] " + f)
            ssh.close()
            return
        sftp_transfer(ssh, args.sftp_root, a, b, report=print)
        try:
            ssh.close()
        except Exception:
            pass
        print("迁移完成")
        return

    if not args.root:
        sys.exit("需要 --root 或 --sftp-host")
    name_hits, all_files = scan_matches(args.root, a)
    content = scan_contents(all_files, uuid_patterns(a))
    print("文件名命中 %d 项:" % len(name_hits))
    for p in name_hits:
        print("  " + p)
    print("内容命中 %d 项:" % len(content))
    for p, kind in content:
        print(f"  [{kind}] " + p)
    if not args.scan:
        transfer(args.root, a, b, report=print)
        print("迁移完成")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main_cli()
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()
