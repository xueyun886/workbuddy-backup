#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
page/gen_csv_skeleton.py —— 从规整化 html / janus.data.json 提炼「安全编辑面」骨架

定位：
    把 html 里"可被安全修改的内容单元"抽成一张表，作为 html 的"安全编辑面"：
    让 AI / 人通过改这张表来改 html，而不直接动 html 源码，从而保证 html 结构稳定。
    这张编辑面的托管形态是资料库的 Database：
        - 后端**不支持**直接导入 csv 文件建表；
        - 因此本脚本 `--emit db` 模式直接产出 create-database 所需的 schema + 写记录负载，
          由 database/create_database.py 建表（固定 6 字段）、database/add_database_record.py 逐行写入。
    建表后"改内容"= 改该 Database 的记录（database/update_database_record.py），再按 anchor_id=pnid 回填 html。
    `--emit csv` 模式仅用于产出一份本地可读的 csv 预览，不参与建表链路。

anchor_id 的来源（关键设计 —— 复用平台 pnid，不自己注入 data-anchor）：
    html 上传到资料库后，服务端规整化时会解析为扁平节点表并生成 janus.data.json，
    给每个节点分配一个 page-node-id（即 pnid，22 位标准 ID）：
        - 元素节点：渲染回的 html 上是属性  data-page-node-id="<pnid>"
        - 文本/注释/directive 节点：html 里以注释  <!--pnid:<pnid>-->  前缀标记
    本脚本直接把这个 page-node-id 当作 csv 的 anchor_id —— 它天然与 html 双向绑定，
    无需再额外注入锚点。回填时系统按 anchor_id(=page-node-id) 定位节点写回内容。

csv 列契约：
    契约列（只读，AI/人不可改、不可增删行 —— V1）：
        anchor_id  : 内容单元锚点 = page-node-id (pnid)
        type       : 内容类型（heading / paragraph / bullet / quote / table_cell / image / notes / other）
        label      : 人类可读语义描述（便于 AI 理解"在改什么"）
                     WBP 演示（--format presentation）结构下，label 带 slide 分组前缀 [sid/layout/zone]
        editable   : 是否允许编辑（结构性 / 空白文本为 false）
    内容列（可改）：
        value      : 实际内容（文本 / 图片 src / 逐字稿正文）
        unit       : 数值单位等（默认空，留给后续按需填）

WBP 演示结构识别（--format presentation 产物）：
    当 html / janus 含 <section data-wbp-slide data-slide-id=... data-layout=... data-zone=...> 时，
    本脚本沿父链识别每个内容单元所属的 slide，label 前缀标注 [sid/layout/zone]，便于按幻灯片维度编辑；
    逐字稿 <aside data-wbp-notes> 内文本提取为 type=notes、editable=true，可经 database 修改演讲者逐字稿。
    非 WBP 结构（普通汇报长页）不加前缀，向后兼容。

输入（二选一，至少给一个；两者都给时以 janus 为 pnid 权威源、html 兜底）：
    --janus <path>  janus.data.json 路径（NodeMap 序列化，最权威）
    --html  <path>  规整化后的 html 路径（含 data-page-node-id 与 <!--pnid:--> 标记）

输出（--emit 决定形态，默认 db）：
    --emit db   输出 create-database 负载 JSON：{"schema":{...}, "records":[...]}
                schema.properties 为固定 6 字段（anchor_id/type/label/editable/value/unit），
                records 为每行的 PropertyValue map，直接喂给 create_database / add_database_record。
                成功标记：KS_DB_SKELETON_OK <JSON>（{rows,editable_rows,out}）
    --emit csv  输出本地可读 csv 预览（不参与建表）。成功标记：KS_CSV_SKELETON_OK <JSON>
    --out <path>    可选，写出文件路径；缺省时 stdout 输出正文（db 模式为 payload JSON，csv 模式为 csv 文本）
    失败 → stdout 一行 {"error":"<msg>"} 后 exit 0

纯本地运行，不依赖网络 / token。仅处理用户显式给出的本地路径。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from html.parser import HTMLParser

_ID_ATTR = "data-page-node-id"
_PNID_COMMENT_RE = re.compile(r"^\s*pnid:([A-Za-z0-9]{22})\s*$")

# 文本所在父标签 → 内容类型
# 注意：aside **不**在此通配为 notes —— 只有带 data-wbp-notes 标记的 aside 才算逐字稿，
# 由 _is_notes_attrs() 按属性判定（见 _units_from_janus / _PnidExtractor），
# 普通 aside（侧栏/补充说明）文本归 other，避免误标成逐字稿混入编辑面。
_TAG_TYPE = {
    "h1": "heading", "h2": "heading", "h3": "heading",
    "h4": "heading", "h5": "heading", "h6": "heading",
    "p": "paragraph", "li": "bullet", "blockquote": "quote",
    "td": "table_cell", "th": "table_cell", "figcaption": "image",
    "a": "link", "code": "code", "strong": "paragraph", "em": "paragraph",
}

# 不作为可编辑文本抽取的父标签（其文本属脚本 / 样式）
_NON_TEXT_PARENTS = {"script", "style", "title"}


def _is_notes_attrs(attrs: dict) -> bool:
    """判断一个 aside 是否为 WBP 逐字稿容器。

    对齐 WBP 契约 §7 的逐字稿选择器：data-wbp-notes / data-notes / class~=slide-notes。
    仅这些 aside 内文本才提取为 type=notes；普通 aside 归 other。
    """
    if not isinstance(attrs, dict):
        return False
    if "data-wbp-notes" in attrs or "data-notes" in attrs:
        return True
    cls = attrs.get("class") or ""
    return "slide-notes" in cls.split()


def _fail(msg: str) -> None:
    sys.stdout.write(json.dumps({"error": msg}, ensure_ascii=False) + "\n")
    sys.exit(0)


def _slide_prefix(ctx: dict | None) -> str:
    """WBP slide 分组前缀，如 '[s2/kpi/data] '。非 WBP 结构（ctx 为空）返回空串。"""
    if not ctx:
        return ""
    parts = [p for p in (ctx.get("sid", ""), ctx.get("layout", ""), ctx.get("zone", "")) if p]
    return "[" + "/".join(parts) + "] " if parts else ""


def _label_for(type_: str, value: str) -> str:
    """生成人类可读 label：类型中文名 + 内容摘要（截断）。"""
    cn = {
        "heading": "标题", "paragraph": "正文", "bullet": "要点",
        "quote": "引用", "table_cell": "表格单元", "image": "图片",
        "link": "链接", "code": "代码", "notes": "逐字稿", "other": "内容",
    }.get(type_, "内容")
    snippet = re.sub(r"\s+", " ", value).strip()
    if len(snippet) > 18:
        snippet = snippet[:18] + "…"
    return f"{cn}: {snippet}" if snippet else cn


# ──────────────────────────────────────────────────────────────────────────
# 路径 A：从 janus.data.json（NodeMap）提炼 —— 最权威
# ──────────────────────────────────────────────────────────────────────────
def _units_from_janus(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            node_map = json.load(f)
    except (OSError, IOError, json.JSONDecodeError):
        _fail("janus.data.json 读取或解析失败")
    if not isinstance(node_map, dict):
        _fail("janus.data.json 结构非预期（应为 page-node-id → node 映射）")

    units: list[dict] = []
    for pnid, node in node_map.items():
        if not isinstance(node, dict):
            continue
        ntype = node.get("type", "")
        # 文本节点：核心可编辑内容单元
        if ntype == "text":
            content = node.get("content") or ""
            parent_node = node_map.get(node.get("parentId", ""))
            parent_tag = (
                (parent_node.get("tag") or "").lower()
                if isinstance(parent_node, dict) else ""
            )
            if parent_tag in _NON_TEXT_PARENTS:
                continue
            if not content.strip():
                continue
            if parent_tag == "aside":
                # 仅带 data-wbp-notes 标记的 aside 才是逐字稿，普通 aside 归 other
                parent_attrs = (
                    parent_node.get("attributes") or {}
                    if isinstance(parent_node, dict) else {}
                )
                ctype = "notes" if _is_notes_attrs(parent_attrs) else "other"
            else:
                ctype = _TAG_TYPE.get(parent_tag, "other")
            ctx = _slide_ctx_of(node_map, node)
            units.append(_mk_unit(pnid, ctype, content.strip(), True, ctx))
        # 图片元素：地址 + 说明
        elif ntype == "element" and node.get("tag", "").lower() == "img":
            attrs = node.get("attributes") or {}
            src = (attrs.get("src") or "").strip()
            alt = (attrs.get("alt") or "").strip()
            if src:
                ctx = _slide_ctx_of(node_map, node)
                u = _mk_unit(pnid, "image", src, True, ctx)
                if alt:
                    u["label"] = _slide_prefix(ctx) + f"图片: {alt[:18]}"
                units.append(u)
    return units


def _slide_ctx_of(node_map: dict, node: dict) -> dict | None:
    """沿 parentId 向上查找最近的 WBP slide section，返回 {sid,layout,zone}。

    非 WBP 结构（找不到 data-wbp-slide / data-slide-id 的 section）返回 None，
    label 不加分组前缀，向后兼容普通汇报长页。
    """
    cur = node
    guard = 0
    while isinstance(cur, dict) and guard < 200:
        guard += 1
        if cur.get("type") == "element" and (cur.get("tag") or "").lower() == "section":
            attrs = cur.get("attributes") or {}
            if "data-wbp-slide" in attrs or "data-slide-id" in attrs:
                return {
                    "sid": (attrs.get("data-slide-id") or "").strip(),
                    "layout": (attrs.get("data-layout") or "").strip(),
                    "zone": (attrs.get("data-zone") or "").strip(),
                }
        pid = cur.get("parentId", "")
        if not pid:
            break
        cur = node_map.get(pid)
    return None


def _mk_unit(anchor_id: str, type_: str, value: str, editable: bool,
             ctx: dict | None = None) -> dict:
    return {
        "anchor_id": anchor_id,
        "type": type_,
        "label": _slide_prefix(ctx) + _label_for(type_, value),
        "editable": "true" if editable else "false",
        "value": value,
        "unit": "",
    }


# ──────────────────────────────────────────────────────────────────────────
# 路径 B：从规整化 html 提炼（解析 data-page-node-id 与 <!--pnid:--> 标记）
# ──────────────────────────────────────────────────────────────────────────
class _PnidExtractor(HTMLParser):
    """提取带 pnid 的文本节点与图片元素。

    规整化 html 约定：
        - 元素：<tag data-page-node-id="ID" ...>
        - 文本节点前置注释：<!--pnid:ID-->文本
    文本节点的 anchor 取其前置注释里的 pnid（更细粒度、与回填一致）。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.units: list[dict] = []
        self._stack: list[str] = []        # 标签栈（小写）
        self._pending_pnid = ""            # 最近一条 <!--pnid:--> 注释携带的 id
        # WBP slide 上下文栈：元素为 (section 所在 _stack 深度索引, ctx)
        self._slide_stack: list[tuple] = []
        # aside 上下文栈：元素为 (aside 所在 _stack 深度索引, is_notes)
        self._aside_stack: list[tuple] = []

    def _cur_ctx(self) -> dict | None:
        return self._slide_stack[-1][1] if self._slide_stack else None

    def _cur_aside_is_notes(self) -> bool:
        return self._aside_stack[-1][1] if self._aside_stack else False

    def handle_comment(self, data: str) -> None:
        m = _PNID_COMMENT_RE.match(data)
        if m:
            self._pending_pnid = m.group(1)

    def handle_starttag(self, tag: str, attrs) -> None:
        tag_l = tag.lower()
        adict = {k.lower(): (v or "") for k, v in attrs}
        # 进入 WBP slide section：记录分组上下文（深度 = 入栈前的 _stack 长度）
        if tag_l == "section" and ("data-wbp-slide" in adict or "data-slide-id" in adict):
            ctx = {
                "sid": adict.get("data-slide-id", "").strip(),
                "layout": adict.get("data-layout", "").strip(),
                "zone": adict.get("data-zone", "").strip(),
            }
            self._slide_stack.append((len(self._stack), ctx))
        if tag_l == "aside":
            self._aside_stack.append((len(self._stack), _is_notes_attrs(adict)))
        if tag_l == "img":
            src = adict.get("src", "").strip()
            alt = adict.get("alt", "").strip()
            pnid = adict.get(_ID_ATTR, "").strip() or self._pending_pnid
            self._pending_pnid = ""
            if src and pnid:
                ctx = self._cur_ctx()
                u = _mk_unit(pnid, "image", src, True, ctx)
                if alt:
                    u["label"] = _slide_prefix(ctx) + f"图片: {alt[:18]}"
                self.units.append(u)
        self._stack.append(tag_l)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack:
            self._stack.pop()
        # 自闭合 section / aside 不应改变上下文栈（其深度对应已弹出的位置）
        if self._slide_stack and self._slide_stack[-1][0] == len(self._stack):
            self._slide_stack.pop()
        if self._aside_stack and self._aside_stack[-1][0] == len(self._stack):
            self._aside_stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if self._stack:
            self._stack.pop()
        # 关闭的若是当前 slide section / aside（深度匹配），弹出对应上下文
        if self._slide_stack and self._slide_stack[-1][0] == len(self._stack):
            self._slide_stack.pop()
        if self._aside_stack and self._aside_stack[-1][0] == len(self._stack):
            self._aside_stack.pop()

    def handle_data(self, data: str) -> None:
        pnid = self._pending_pnid
        self._pending_pnid = ""
        if not data.strip() or not pnid:
            return
        parent = self._stack[-1] if self._stack else ""
        if parent in _NON_TEXT_PARENTS:
            return
        if parent == "aside":
            # 仅带 data-wbp-notes 标记的 aside 才是逐字稿，普通 aside 归 other
            ctype = "notes" if self._cur_aside_is_notes() else "other"
        else:
            ctype = _TAG_TYPE.get(parent, "other")
        self.units.append(_mk_unit(pnid, ctype, data.strip(), True, self._cur_ctx()))


def _units_from_html(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (OSError, IOError):
        _fail("html 读取失败")
    parser = _PnidExtractor()
    try:
        parser.feed(content)
    except Exception:  # noqa: BLE001 - 解析异常视为提炼失败
        _fail("html 解析失败")
    return parser.units


# ──────────────────────────────────────────────────────────────────────────
# 输出 csv
# ──────────────────────────────────────────────────────────────────────────
_COLUMNS = ["anchor_id", "type", "label", "editable", "value", "unit"]

# 「安全编辑面」Database 的固定 schema（6 字段）——供 create_database.py 直接使用。
# properties 为 array 格式 [{name, config:PropertyConfig}]，与 database/create_database.py 对齐。
_DB_SCHEMA_PROPS = [
    {"name": "anchor_id", "config": {"text": ""}},      # 锚点 = page-node-id（pnid），只读语义
    {"name": "type", "config": {"text": ""}},           # 内容类型
    {"name": "label", "config": {"text": ""}},          # 人类可读语义描述
    {"name": "editable", "config": {"checkbox": False}},  # 是否允许编辑
    {"name": "value", "config": {"text": ""}},          # 实际内容（可改）
    {"name": "unit", "config": {"text": ""}},           # 数值单位等（可改）
]


def _to_csv(units: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for u in units:
        writer.writerow(u)
    return buf.getvalue()


def _to_db_payload(units: list[dict]) -> dict:
    """把内容单元转成 create-database 负载：{schema, records}。

    - schema.properties 为固定 6 字段；title 留空，由 agent 在建表前注入「<html标题> · 编辑面」。
    - records 为每行的 PropertyValue map（map<字段名, {类型: 值}>），喂给 add_database_record.py。
    """
    records: list[dict] = []
    for u in units:
        records.append({
            "anchor_id": {"text": u.get("anchor_id", "")},
            "type": {"text": u.get("type", "")},
            "label": {"text": u.get("label", "")},
            "editable": {"checkbox": u.get("editable") == "true"},
            "value": {"text": u.get("value", "")},
            "unit": {"text": u.get("unit", "")},
        })
    return {
        "schema": {"title": "", "properties": _DB_SCHEMA_PROPS},
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--janus", dest="janus", default="")
    parser.add_argument("--html", dest="html", default="")
    parser.add_argument("--out", dest="out", default="")
    parser.add_argument("--emit", dest="emit", default="db", choices=["db", "csv"])
    try:
        args, _unknown = parser.parse_known_args()
    except SystemExit:
        _fail("参数解析失败")

    janus_path = (args.janus or "").strip()
    html_path = (args.html or "").strip()
    if not janus_path and not html_path:
        _fail("需提供 --janus 或 --html 至少其一")

    units: list[dict] = []
    if janus_path:
        if not os.path.isfile(janus_path):
            _fail("janus 路径无效或文件不存在")
        units = _units_from_janus(janus_path)

    # janus 权威、html 兜底：janus 未提炼出内容时，若给了 html 再从 html 提炼
    if not units and html_path:
        if not os.path.isfile(html_path):
            _fail("html 路径无效或文件不存在")
        units = _units_from_html(html_path)

    if not units:
        _fail("未提炼出任何可编辑内容单元")

    editable_rows = sum(1 for u in units if u["editable"] == "true")
    out_path = (args.out or "").strip()
    ok = json.dumps(
        {"rows": len(units), "editable_rows": editable_rows, "out": out_path or ""},
        ensure_ascii=False, separators=(",", ":"),
    )

    if args.emit == "csv":
        body = _to_csv(units)
        marker = "KS_CSV_SKELETON_OK"
    else:  # db（默认）
        body = json.dumps(_to_db_payload(units), ensure_ascii=False)
        marker = "KS_DB_SKELETON_OK"

    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                f.write(body)
        except (OSError, IOError):
            _fail("文件写入失败")
        sys.stdout.write(marker + " " + ok + "\n")
    else:
        sys.stdout.write(body)
        if not body.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.write(marker + " " + ok + "\n")


if __name__ == "__main__":
    main()
