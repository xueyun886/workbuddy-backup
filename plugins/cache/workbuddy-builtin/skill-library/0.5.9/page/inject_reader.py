#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
page/inject_reader.py —— 给规整化 html 注入「database 动态读取脚本」（保留内容做锚点载体）

定位（md→html 安全编辑面链路 · 铁序 ⑤ 的收尾步骤）：
    gen_csv_skeleton.py 已把 html 里"可编辑内容单元"提炼成 database 记录（anchor_id=pnid，value=内容），
    create_database.py / add_database_record.py 已把这些记录写入资料库 Database。
    核心：html 元素渲染的数据在运行时**从 database 动态读取**（这是安全编辑面的本质）。
    本脚本**不剥空成空壳**——保留 html 里的真实文本与 img src，但保留它们只是为了
    「保住 pnid 锚点不被服务端裁剪 + 无 SDK 时兜底」，**不是**把数据写死当静态展示值：

        · 结构标签、<!--pnid:ID--> 文本锚点注释、文本内容、img src —— **全部原样保留**（锚点载体 + 兜底）；
        · 注入的**只读** __SMART_PAGE__.database 脚本在 html 每次加载时按 anchor_id(=pnid)
          从 database 拉最新 value 渲染进对应节点（幂等：先清空槽位再写唯一一份），
          database 是显示数据的唯一真相源——平台环境下用户看到的就是 database 动态读取的值；
        · 若运行环境无 __SMART_PAGE__ SDK（脱离平台 sandbox），脚本静默返回，
          保留的内容原样显示，**绝不空白**。

    => 产出 html：显示数据动态来自 database（SDK 在则按最新 value 渲染）+ 永不空白（无 SDK 兜底）。
       这份 html 即铁序 ⑥ import_html.py 重导入的唯一对象。

为什么不剥空成空壳：
    一旦把内容剥到空，服务端重规整化会裁剪掉"无内容的空节点"，脚本依赖的 pnid 锚点随之消失 → 整页空白。
    所以保留真实内容是为了保住锚点与兜底渲染，但显示数据依旧动态来自 database，二者不矛盾。

输入：
    --html <path>          规整化 html 路径（含 data-page-node-id 与 <!--pnid:--> 标记），必填
    --database-id <id>     create_database.py 返回的 database_id，硬编码进注入脚本，必填
    --out <path>           可选，写出注入后的 html；缺省 stdout 输出 html 正文

输出：
    成功 → 写出/打印注入后的 html，并在 stdout 末行打 KS_INJECT_OK <JSON>（{injected,out}）
    失败 → stdout 一行 {"error":"<msg>"} 后 exit 0

安全：
    纯本地运行，不触网、不读 token；仅处理用户显式给出的本地路径。
    database_id 仅允许 [A-Za-z0-9_-]，并以 JSON 字面量安全嵌入 JS（防脚本注入）；
    注入脚本**只读**（仅 db.query），绝不写库；回填只用 createTextNode/setAttribute，不用 innerHTML。
    注入脚本**幂等**：每个 pnid 槽位先清空再写一份，平台编辑回写 html / 重规整出新 pnid 后重复加载也不累加重复值。
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# 与 gen_csv_skeleton.py 对齐的 pnid 约定
_PNID = r"[A-Za-z0-9]{22}"
# 合法 database_id 字符集
_DB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 注入的只读动态覆盖脚本模板（ES5，兼容 sandbox）。__DATABASE_ID_LITERAL__ 由本脚本替换为 JSON 字面量。
_READER_SCRIPT = """<script>
  // ===== Database 安全编辑面 · 运行时从 database 动态读取渲染数据（由 md→html 链路 inject_reader.py 注入） =====
  // database 是 html 元素显示数据的唯一真相源：本脚本每次加载都按 anchor_id(=pnid) 从 database 拉最新 value 渲染进对应节点。
  // html 里保留的真实内容只是「锚点载体 + 无 SDK 兜底」，不是静态展示值——有 SDK 时一律以 database 的值为准。
  // 编辑应走 database 改 value（安全编辑面），下次加载本脚本即覆盖为最新值。
  // 幂等保证：每个 pnid 槽位"先清空再写一份"，即便平台把编辑值回写进 html、重规整出新 pnid，
  // 重复加载也不会累加重复值（修复"编辑后展示异常 / 出现重复值"）。
  (function () {
    // 先收集所有 <!--pnid:ID--> 文本锚点注释
    var commentByPnid = {};
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT, null, false);
    var c, m;
    while ((c = walker.nextNode())) {
      m = /^\\s*pnid:([A-Za-z0-9]{22})\\s*$/.exec(c.nodeValue || '');
      if (m) { commentByPnid[m[1]] = c; }
    }

    var db = window.__SMART_PAGE__ && window.__SMART_PAGE__.database;
    if (!db) {
      // 无 SDK 环境（脱离平台 sandbox）：保留的内容原样显示，不覆盖、不抛错、不空白
      return;
    }
    var DATABASE_ID = __DATABASE_ID_LITERAL__;  // 硬编码 create_database 返回的 database_id

    // 分页拉全编辑面记录（内容单元可能 > 单页）
    var all = [];
    (function loadPage(cursor) {
      db.query({ databaseId: DATABASE_ID, pageSize: 200, startCursor: cursor || undefined })
        .then(function (res) {
          all = all.concat((res && res.results) || []);
          if (res && res.hasMore && res.nextCursor) { loadPage(res.nextCursor); }
          else { applyAll(all); }
        })
        .catch(function (err) { console.error('[md2html-edit] 读取编辑面失败:', err); });
    })();

    // 清空 <!--pnid:ID--> 锚点之后、到下一个边界之前的所有内容（幂等覆盖的关键）。
    //   边界 = 元素节点(nodeType 1) | 另一个仍在 DB 中的 pnid 注释 | 父节点结束。
    //   被清除对象 = 快照文本节点 + "孤儿 pnid 注释"(不在 DB 中，多为编辑回写/服务端重规整遗留) + 其它注释。
    // 平台编辑是产物级的：会把"运行时覆盖的值"一并回写进 html 再重规整出新 pnid；
    // 若不先清空、只 insert，就会一轮一轮累加重复值。先清后写 → 槽位永远只保留 DB 的唯一一份。
    function clearSlot(cm, dbPnids) {
      var n = cm.nextSibling;
      while (n) {
        if (n.nodeType === 1) { break; }          // 元素边界：属于其它结构单元，不动
        if (n.nodeType === 8) {                   // 注释
          var mm = /^\\s*pnid:([A-Za-z0-9]{22})\\s*$/.exec(n.nodeValue || '');
          if (mm && dbPnids[mm[1]]) { break; }    // 命中另一受管槽位 → 停在它前面，互不干扰
        }
        var toRemove = n;
        n = n.nextSibling;
        toRemove.parentNode.removeChild(toRemove); // 快照文本 / 孤儿 pnid 注释 / 其它注释 → 清掉
      }
    }

    // 按 anchor_id(=pnid) 用 DB 最新 value 幂等覆盖对应节点（先清空槽位、再写唯一一份）
    function applyAll(rows) {
      var i;
      // 先建 DB pnid 集合：clearSlot 用它界定"受管槽位"边界，相邻槽位之间不互相清除
      var dbPnids = {};
      for (i = 0; i < rows.length; i++) {
        if (rows[i] && rows[i]['anchor_id']) { dbPnids[rows[i]['anchor_id']] = true; }
      }
      for (i = 0; i < rows.length; i++) {
        var row = rows[i];
        var pnid = row['anchor_id'];
        var value = row['value'];
        if (!pnid || value == null) { continue; }
        if (row['type'] === 'image') {            // 图片：元素节点带 data-page-node-id，setAttribute 本就幂等
          var img = document.querySelector('[data-page-node-id="' + pnid + '"]');
          if (img) { img.setAttribute('src', value); img.setAttribute('data-sp-bindable', 'database'); }
          continue;
        }
        var cm = commentByPnid[pnid];              // 文本：锚点在 <!--pnid:ID--> 注释
        if (!cm || !cm.parentNode) { continue; }
        clearSlot(cm, dbPnids);                    // ① 幂等清空本槽位（含快照文本 / 编辑回写 / 重规整产物）
        cm.parentNode.insertBefore(document.createTextNode(value), cm.nextSibling);  // ② 写入 DB 唯一一份
        if (cm.parentNode.setAttribute) {
          cm.parentNode.setAttribute('data-sp-bindable', 'database');
        }
      }
    }
  })();
</script>"""


def _fail(msg: str) -> None:
    sys.stdout.write(json.dumps({"error": msg}, ensure_ascii=False) + "\n")
    sys.exit(0)


def _inject_reader(html: str, database_id: str) -> tuple[str, bool]:
    """在最后一个 </body> 前注入只读动态覆盖脚本（硬编码 database_id）。"""
    script = _READER_SCRIPT.replace(
        "__DATABASE_ID_LITERAL__", json.dumps(database_id, ensure_ascii=False)
    )
    idx = html.lower().rfind("</body>")
    if idx == -1:
        return html + "\n" + script + "\n", True   # 无 </body> 则追加到末尾
    return html[:idx] + script + "\n" + html[idx:], True


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--html", dest="html", default="")
    parser.add_argument("--database-id", dest="database_id", default="")
    parser.add_argument("--out", dest="out", default="")
    try:
        args, _unknown = parser.parse_known_args()
    except SystemExit:
        _fail("参数解析失败")

    html_path = (args.html or "").strip()
    database_id = (args.database_id or "").strip()
    out_path = (args.out or "").strip()

    if not html_path:
        _fail("需提供 --html（规整化 html 路径）")
    if not database_id:
        _fail("需提供 --database-id（create_database 返回的 database_id）")
    if not _DB_ID_RE.match(database_id):
        _fail("database_id 含非法字符（仅允许 A-Za-z0-9_-）")

    try:
        with open(html_path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
    except (OSError, IOError):
        _fail("html 读取失败")

    if "pnid:" not in html and "data-page-node-id" not in html:
        _fail("html 不含 pnid 标记，疑似未规整化的本地原始 html（禁止注入）")

    html, injected = _inject_reader(html, database_id)

    ok = json.dumps(
        {"injected": injected, "out": out_path or ""},
        ensure_ascii=False, separators=(",", ":"),
    )

    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                f.write(html)
        except (OSError, IOError):
            _fail("html 写入失败")
        sys.stdout.write("KS_INJECT_OK " + ok + "\n")
    else:
        sys.stdout.write(html)
        if not html.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.write("KS_INJECT_OK " + ok + "\n")


if __name__ == "__main__":
    main()
