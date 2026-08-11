#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smh/upload_smh_file.py —— 上传本地文件到资料库，按 uploadType 自动适配 COS / SMH 直传。

链路（用法与参数见 smh/entry.md）：
    1. get-upload-credential 申请凭证，响应 uploadType 决定通道：
         cos   —— md/csv/html/htm/zip 等，返回 cosKey，走 COS 预签名
         drive —— 其余扩展名，返回 headers + confirmKey，走 SMH 直传
    2. PUT 文件二进制：cos 直传 uploadUrl（无 header）；drive 带响应 headers
    3. import-local-file 落节点：cos 传 cosKey；drive 传 confirmKey(+taskId)
    4. 成功 → `KS_SMH_UPLOAD_OK <json>`(node_block_id/file_name/ext/url)；
       失败 → `{"error":...}` 后 exit 0（不暴露 token / 中间响应）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 复用 library/_common.py 的 token / HTTP / 脱敏 / 失败出口约定。
_LIB_DIR = Path(__file__).resolve().parents[1]
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import _common  # noqa: E402
from _common import (  # noqa: E402
    HttpError,
    error_exit,
    http_request,
    read_token_from_stdin,
    safe_print,
    unwrap_data,
)

_PATH_GET_UPLOAD_CREDENTIAL = "/space/api/agent/v1/get-upload-credential"
_PATH_IMPORT_LOCAL_FILE = "/space/api/agent/v1/import-local-file"

# 上传类型（get-upload-credential 响应 uploadType 字段取值）。
_UPLOAD_TYPE_COS = "cos"
_UPLOAD_TYPE_DRIVE = "drive"

# 单次允许上传的最大文件大小（字节）。客户端裸 PUT 大文件不稳，给一个稳妥上限；
# 超出直接静默退出，避免长时阻塞与超大请求体。
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MiB

# PUT 上传超时（秒）；与本地网络条件相关，给一个相对宽松的值。
PUT_TIMEOUT = 120


def _file_meta(path: str) -> tuple:
    """读取文件内容并返回 (content, size)；任何异常 → (b"", 0) 由调用方按失败处理。"""
    try:
        with open(path, "rb") as f:
            content = f.read(MAX_UPLOAD_BYTES + 1)
    except (OSError, IOError):
        return b"", 0
    size = len(content)
    if size == 0 or size > MAX_UPLOAD_BYTES:
        return b"", 0
    return content, size


def _put_to_cos(upload_url: str, body: bytes) -> bool:
    """COS 预签名上传：直接 PUT 到 uploadUrl，无需额外 header；2xx 视为成功。"""
    return _put(upload_url, body, headers=None)


def _put_with_headers(upload_url: str, body: bytes, headers: dict) -> bool:
    """SMH 直传：PUT 到 uploadUrl 并携带服务端给出的 headers（Authorization 等）；2xx 视为成功。"""
    return _put(upload_url, body, headers=headers)


def _put(upload_url: str, body: bytes, headers: dict | None) -> bool:
    """裸 urllib PUT 文件二进制到给定 URL。

    不走 _common.http_request：后者会强制注入 WorkBuddy 的 Authorization 与
    Content-Type: application/json，而这里直传的是文件本体、且要么无 header（COS
    预签名）要么带 SMH 自己的 header。2xx 视为成功；任何异常返回 False。
    """
    if not upload_url or not body:
        return False
    req = urllib.request.Request(
        url=upload_url,
        data=body,
        method="PUT",
    )
    if headers:
        for k, v in headers.items():
            if k and v is not None:
                req.add_header(str(k), str(v))
    try:
        with urllib.request.urlopen(req, timeout=PUT_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        return False
    except Exception:  # noqa: BLE001 - 任何意外都静默
        return False


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--token-stdin", dest="token_stdin", action="store_true")
    parser.add_argument("path", nargs="?", default="")
    parser.add_argument("--file-name", dest="file_name", default="")
    parser.add_argument("--space-id", dest="space_id", default="")
    parser.add_argument("--parent-id", dest="parent_id", default="")
    try:
        args, _unknown = parser.parse_known_args()
    except SystemExit:
        error_exit("参数解析失败")

    # 读取 token（必须在读 stdin 之前，因为 --token-stdin 从 stdin 读首行）
    token = ""
    if args.token_stdin:
        token = read_token_from_stdin()
    if not token and not _common.is_sandbox():
        error_exit("token 缺失或无效")

    path = (args.path or "").strip()
    if not path or not os.path.isfile(path):
        error_exit("文件路径无效或文件不存在")

    content, size = _file_meta(path)
    if size == 0:
        error_exit("文件为空或超出大小上限")

    file_name = (args.file_name or os.path.basename(path)).strip()
    if not file_name:
        error_exit("文件名为空")

    # ext：去前导点、转小写；仅用于回执输出，落地品类由服务端按扩展名判定。
    ext = os.path.splitext(file_name)[1].lstrip(".").lower()

    target_space_id = (args.space_id or "").strip()
    target_parent_id = (args.parent_id or "").strip()

    # ---- Step 1: 获取上传凭证 ----
    cred_body: dict = {
        "fileName": file_name,
        "fileSize": size,
    }
    if target_parent_id:
        # 后端据 parentId 解析 spaceID；不传则默认 workbuddy 空间。
        cred_body["parentId"] = target_parent_id
    try:
        cred_data = unwrap_data(
            http_request(
                "POST",
                _common.build_url(_PATH_GET_UPLOAD_CREDENTIAL),
                token,
                body=cred_body,
                timeout=8.0,
            )
        )
    except HttpError as e:
        error_exit(f"获取上传凭证失败: {e}")

    upload_url = (cred_data.get("uploadUrl") or "").strip()
    upload_type = (cred_data.get("uploadType") or "").strip().lower()
    cos_key = (cred_data.get("cosKey") or "").strip()
    confirm_key = (cred_data.get("confirmKey") or "").strip()
    task_id = (cred_data.get("taskId") or "").strip()
    headers = cred_data.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}

    if not upload_url:
        error_exit("上传凭证响应缺少 uploadUrl")

    # ---- Step 2 + 3: 按 uploadType 分流（PUT 上传 + 构造导入请求体）----
    import_body: dict = {"fileName": file_name}

    if upload_type == _UPLOAD_TYPE_COS:
        if not cos_key:
            error_exit("COS 模式上传凭证缺少 cosKey")
        if not _put_to_cos(upload_url, content):
            error_exit("文件上传到 COS 失败")
        import_body["cosKey"] = cos_key
    elif upload_type == _UPLOAD_TYPE_DRIVE:
        if not confirm_key:
            error_exit("SMH 直传上传凭证缺少 confirmKey")
        if not _put_with_headers(upload_url, content, headers):
            error_exit("文件直传到 SMH 失败")
        import_body["confirmKey"] = confirm_key
        if task_id:
            import_body["taskId"] = task_id
    else:
        error_exit(f"未知上传类型: {upload_type or '(空)'}")

    # ---- Step 4: 触发导入（落成文件节点） ----
    if target_space_id:
        import_body["spaceId"] = target_space_id
    if target_parent_id:
        import_body["parentId"] = target_parent_id

    # 可选 title：默认用文件名去掉扩展名（与 drive/import_csv 一致；文件节点的展示标题）
    title = os.path.splitext(file_name)[0].strip()
    if title:
        import_body["title"] = title

    try:
        import_data = unwrap_data(
            http_request(
                "POST",
                _common.build_url(_PATH_IMPORT_LOCAL_FILE),
                token,
                body=import_body,
                timeout=30.0,
            )
        )
    except HttpError as e:
        error_exit(f"导入文件请求失败: {e}")

    node_block_id = (import_data.get("nodeBlockId") or "").strip()
    if not node_block_id:
        error_exit("服务端返回的 nodeBlockId 为空")

    url = (import_data.get("url") or "").strip()

    output = {
        "node_block_id": node_block_id,
        "file_name": file_name,
        "ext": ext,
        "url": url,
    }
    safe_print(
        "KS_SMH_UPLOAD_OK "
        + json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    )

    # 成品回执行：Agent 直接原样透传给用户；url 是节点访问地址，可回显，禁止自拼。
    if url:
        reply = f"文件「{file_name}」已上传到资料库，点击查看：{url}"
    else:
        reply = f"文件「{file_name}」已上传到资料库。"
    safe_print(f"KS_USER_REPLY\t{reply}")


if __name__ == "__main__":
    main()
