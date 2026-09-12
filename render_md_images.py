# -*- coding: utf-8 -*-
"""把 使用教程/*.md 渲染成高清 PNG（每张图 = 一个文件），输出到 使用教程_图片/"""
import os, re, glob
from PIL import Image, ImageDraw, ImageFont

SCALE = 2
W = 1100 * SCALE          # 画布宽（高清 2x）
MX = 64 * SCALE           # 左右边距
CW = W - MX * 2           # 内容宽
TOP = 72 * SCALE
BOTTOM = 72 * SCALE

BG = (255, 255, 255)
TEXT = (34, 34, 34)
BRAND = (75, 63, 227)
BRAND_DARK = (26, 23, 89)
CODE_BG = (246, 246, 248)
CODE_FILL = (150, 50, 70)
TBL_HEAD_BG = (242, 247, 255)
TBL_BORDER = (222, 222, 228)
DIVIDER = (230, 230, 236)

FONT_DIR = r"C:\Windows\Fonts"


def F(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size * SCALE)


F_BODY = F("msyh.ttc", 26)
F_BODY_B = F("msyhbd.ttc", 26)
F_H1 = F("msyhbd.ttc", 46)
F_H2 = F("msyhbd.ttc", 34)
F_TBL = F("msyh.ttc", 24)
F_TBL_B = F("msyhbd.ttc", 24)
F_CODE = F("consola.ttf", 24)

LH = 44 * SCALE          # 正文行高
TBL_LH = 36 * SCALE      # 表格行内行高
TBL_RH = 16 * SCALE      # 表格单元格上下留白

TOKEN_RE = re.compile(r'(\*\*.+?\*\*|`[^`]+`)')


def is_ascii(s):
    return all(ord(c) < 128 for c in s)


def split_tokens(text):
    toks = []
    for part in TOKEN_RE.split(text):
        if not part:
            continue
        if part.startswith('**') and part.endswith('**') and len(part) > 4:
            toks.append(('b', part[2:-2]))
        elif part.startswith('`') and part.endswith('`') and len(part) > 2:
            toks.append(('c', part[1:-1]))
        else:
            toks.append(('n', part))
    return toks


def tok_font(tok, font, bold_font):
    kind, s = tok
    if kind == 'c':
        return F_CODE if is_ascii(s) else font
    return bold_font if kind == 'b' else font


def tok_fill(tok):
    kind, s = tok
    if kind == 'c':
        return CODE_FILL
    return BRAND_DARK if kind == 'b' else TEXT


def token_w(d, tok, font, bold_font):
    return d.textlength(tok[1], font=tok_font(tok, font, bold_font))


def wrap_tokens(d, toks, font, bold_font, max_w):
    """把 token 列表按 max_w 折行；超宽 token 按字符硬切，返回折行后的行列表"""
    lines, cur, curw = [], [], 0
    for t in toks:
        w = token_w(d, t, font, bold_font)
        if w > max_w:                       # 单 token 超宽 → 逐字符切
            for ch in t[1]:
                ct = (t[0], ch)
                cw = token_w(d, ct, font, bold_font)
                if cur and curw + cw > max_w:
                    lines.append(cur)
                    cur, curw = [], 0
                cur.append(ct)
                curw += cw
            continue
        if cur and curw + w > max_w:
            lines.append(cur)
            cur, curw = [], 0
        cur.append(t)
        curw += w
    if cur:
        lines.append(cur)
    return lines if lines else [[]]


def draw_tok_line(d, x, y, toks, font, bold_font):
    cx = x
    for t in toks:
        kind, s = t
        f = tok_font(t, font, bold_font)
        fill = tok_fill(t)
        if kind == 'c':
            w = d.textlength(s, font=f)
            d.rounded_rectangle([cx - 6 * SCALE, y - 4 * SCALE,
                                 cx + w + 6 * SCALE, y + 30 * SCALE],
                                radius=6 * SCALE, fill=CODE_BG)
            d.text((cx, y), s, font=f, fill=fill)
            cx += w
        else:
            d.text((cx, y), s, font=f, fill=fill)
            cx += d.textlength(s, font=f)
    return cx


def render_tokens(d, x, y, toks, font, bold_font, max_w, lh):
    for line in wrap_tokens(d, toks, font, bold_font, max_w):
        draw_tok_line(d, x, y, line, font, bold_font)
        y += lh
    return y


def table_layout(d, rows, max_w):
    """计算表格布局：列宽、列起点、每行高度、每个单元格的折行内容。measure 与 render 共用，保证一致"""
    ncol = max(len(r) for r in rows)
    widths = [0] * ncol
    for r in rows:
        for i in range(ncol):
            cell = r[i] if i < len(r) else ""
            for t in split_tokens(cell):
                widths[i] = max(widths[i], token_w(d, t, F_TBL, F_TBL_B))
    pad = 16 * SCALE
    total = sum(widths) + pad * 2 * ncol
    if total > max_w:
        widths = [int(w * (max_w - pad * 2 * ncol) / sum(widths)) for w in widths]
    col_x = []
    cx = MX
    for i in range(ncol):
        col_x.append(cx)
        cx += widths[i] + pad * 2
    # 每个单元格折行，行高 = 该行最多行数
    wrapped = []
    row_h = []
    for r in rows:
        lines_per_cell = []
        for i in range(ncol):
            cell = r[i] if i < len(r) else ""
            toks = split_tokens(cell)
            lines = wrap_tokens(d, toks, F_TBL, F_TBL_B, widths[i])
            lines_per_cell.append(lines)
        wrapped.append(lines_per_cell)
        row_h.append(max(len(l) for l in lines_per_cell) * TBL_LH + TBL_RH * 2)
    return col_x, widths, wrapped, row_h


def render_table(d, y, rows, max_w):
    col_x, widths, wrapped, row_h = table_layout(d, rows, max_w)
    ncol = len(widths)
    for ri, r in enumerate(rows):
        rh = row_h[ri]
        for i in range(ncol):
            x0, x1 = col_x[i], col_x[i] + widths[i] + 32 * SCALE
            y0, y1 = y + ri * rh, y + (ri + 1) * rh
            if ri == 0:
                d.rectangle([x0, y0, x1, y1], fill=TBL_HEAD_BG)
            d.rectangle([x0, y0, x1, y1], outline=TBL_BORDER, width=1 * SCALE)
            ty = y0 + TBL_RH
            for line in wrapped[ri][i]:
                draw_tok_line(d, x0 + 16 * SCALE, ty, line, F_TBL, F_TBL_B)
                ty += TBL_LH
    return y + sum(row_h) + 28 * SCALE


def parse_md(text):
    lines = text.splitlines()
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue
        if s == '---':
            blocks.append(('hr',))
            i += 1
        elif line.lstrip().startswith('#'):
            lv = len(line) - len(line.lstrip('#'))
            blocks.append(('h', lv, s.lstrip('#')))
            i += 1
        elif re.match(r'^\d+[\.、]', s) or s.startswith('- '):
            items = []
            while i < n:
                raw = lines[i].rstrip()
                t = raw.strip()
                if re.match(r'^\d+[\.、]', t) or t.startswith('- '):
                    indent = len(raw) - len(raw.lstrip())
                    if t.startswith('- '):
                        items.append((indent // 2, t[2:]))
                    else:
                        m = re.match(r'^(\d+)[\.、]\s*(.*)$', t)
                        items.append((indent // 2, (m.group(1) + '. ' + m.group(2)).strip()))
                    i += 1
                else:
                    break
            blocks.append(('ul', items))
        elif s.startswith('|'):
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                row = lines[i].strip().strip('|')
                cells = [c.strip() for c in row.split('|')]
                if cells and set(''.join(cells)) <= set('-: '):
                    i += 1
                    continue
                rows.append(cells)
                i += 1
            blocks.append(('table', rows))
        elif line.startswith(('   ', '\t')):
            code = []
            while i < n and (lines[i].startswith(('   ', '\t'))):
                code.append(lines[i].strip())
                i += 1
            blocks.append(('code', code))
        else:
            para = []
            while i < n:
                l2 = lines[i].rstrip()
                t2 = l2.strip()
                if not t2 or t2 == '---' or t2.startswith('#'):
                    break
                if l2.startswith(('   ', '\t')) or re.match(r'^\d+[\.、]', t2) or t2.startswith(('- ', '|')):
                    break
                para.append(t2)
                i += 1
            blocks.append(('p', ' '.join(para)))
    return blocks


def layout(d, blocks):
    y = TOP
    for b in blocks:
        kind = b[0]
        if kind == 'h':
            lv = b[1]
            y += (30 if lv == 1 else 20) * SCALE          # 标题上方间距
            y += (72 if lv == 1 else 52) * SCALE          # 标题占高
            y += (28 if lv == 1 else 14) * SCALE          # 标题下方间距（H1 含分割线间隔）
        elif kind == 'p':
            y = render_tokens(d, MX, y, split_tokens(b[1]), F_BODY, F_BODY_B, CW, LH)
        elif kind == 'ul':
            for indent, item in b[1]:
                off = indent * 22 * SCALE
                y = render_tokens(d, MX + off, y, [('n', '•  ')] + split_tokens(item),
                                  F_BODY, F_BODY_B, CW - off, LH)
        elif kind == 'table':
            col_x, widths, wrapped, row_h = table_layout(d, b[1], CW)
            y += sum(row_h) + 28 * SCALE
        elif kind == 'code':
            y += 10 * SCALE
            y += len(b[1]) * 40 * SCALE + 20 * SCALE
    return y + BOTTOM


def render(blocks, img_h):
    img = Image.new("RGB", (W, img_h), BG)
    d = ImageDraw.Draw(img)
    y = TOP
    for b in blocks:
        kind = b[0]
        if kind == 'h':
            lv, txt = b[1], b[2]
            y += (30 if lv == 1 else 20) * SCALE
            d.text((MX, y), txt, font=F_H1 if lv == 1 else F_H2, fill=BRAND if lv == 1 else BRAND_DARK)
            y += (72 if lv == 1 else 52) * SCALE
            if lv == 1:
                d.rectangle([MX, y - 14 * SCALE, W - MX, y - 14 * SCALE + 2 * SCALE], fill=DIVIDER)
            y += (28 if lv == 1 else 14) * SCALE
        elif kind == 'p':
            y = render_tokens(d, MX, y, split_tokens(b[1]), F_BODY, F_BODY_B, CW, LH)
        elif kind == 'ul':
            for indent, item in b[1]:
                off = indent * 22 * SCALE
                y = render_tokens(d, MX + off, y, [('n', '•  ')] + split_tokens(item),
                                  F_BODY, F_BODY_B, CW - off, LH)
        elif kind == 'table':
            y = render_table(d, y, b[1], CW)
        elif kind == 'code':
            y += 10 * SCALE
            bh = len(b[1]) * 40 * SCALE + 20 * SCALE
            d.rounded_rectangle([MX, y, W - MX, y + bh], radius=10 * SCALE, fill=CODE_BG)
            cy = y + 12 * SCALE
            for c in b[1]:
                f = F_CODE if is_ascii(c) else F_BODY
                d.text((MX + 14 * SCALE, cy), c, font=f, fill=CODE_FILL if is_ascii(c) else TEXT)
                cy += 40 * SCALE
            y += bh
    return img


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(base, "使用教程")
    out_dir = os.path.join(base, "使用教程_图片")
    os.makedirs(out_dir, exist_ok=True)
    probe = Image.new("RGB", (10, 10))
    pd = ImageDraw.Draw(probe)
    for path in sorted(glob.glob(os.path.join(src_dir, "*.md"))):
        text = open(path, "r", encoding="utf-8").read().replace("☑", "√")
        blocks = parse_md(text)
        h = layout(pd, blocks)
        img = render(blocks, h)
        name = os.path.splitext(os.path.basename(path))[0] + ".png"
        img.save(os.path.join(out_dir, name))
        print(f"{name}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()
