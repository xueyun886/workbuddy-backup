#!/usr/bin/env bash
#
# SessionStart / UserPromptSubmit hook（仅 CLOUD_AGENT）—
# 云端沙箱休眠会释放计算资源（pm2 daemon + node 进程被杀），唤醒后磁盘保留但
# initShellCommand 不会重跑，本地 sheetagent-mcp（:39800）因此处于停止状态。
# 本轮真正用到 MCP 之前先探活，必要时按 init 同样的方式重新拉起并阻塞到就绪。
#
# 设计要点：
#   - server.ts 是无状态 streamable-HTTP（每请求独立 transport），host 侧等价于
#     每次工具调用一个独立 HTTP POST，因此只要拉起进程，下一个 POST 即可命中。
#   - 探活打非 /mcp 路径（server.ts 对其直接返回 404），TCP 通即视为存活，
#     且不会每次探活都白建一个 MCP server 实例。
#   - 始终 exit 0：拉起失败也不应阻塞用户本轮提交，让后续工具调用自行报错即可。
#
set -uo pipefail

cat >/dev/null 2>&1 || true   # 吃掉 hook 传入的 stdin（JSON），避免管道悬挂

# 把 reference 目录软链到固定路径 ~/.sheet-references/：prompt（含 system prompt
# 下发形态）里写死该路径，不依赖运行时替换 ${CODEBUDDY_PLUGIN_ROOT}——system prompt
# 通道没有任何占位符替换。ln -sfn 幂等，插件升级换目录后下一轮自动指向新位置。
if [ -n "${CODEBUDDY_PLUGIN_ROOT:-}" ] && [ -d "${CODEBUDDY_PLUGIN_ROOT}/prompt/sheet-references" ]; then
  ln -sfn "${CODEBUDDY_PLUGIN_ROOT}/prompt/sheet-references" "$HOME/.sheet-references" 2>/dev/null || true
fi

PROBE="http://127.0.0.1:39800/healthz"   # 任意非 /mcp 路径 → 404 快速返回
is_up() { curl -s -o /dev/null --max-time 2 "$PROBE"; }   # 退出 0=有响应(活)，非 0=拒绝(死)

if ! is_up; then
  cd "$HOME/sheet-agent-mcp" 2>/dev/null || exit 0
  # daemon 可能已随休眠消失：restart 找不到进程时回落到 start（与 initShellCommand 一致）
  pm2 restart sheetagent-mcp >/dev/null 2>&1 \
    || pm2 start start.mjs --interpreter=node --name sheetagent-mcp >/dev/null 2>&1 \
    || true
  i=0
  while [ "$i" -lt 30 ]; do   # 最多等 ~15s 直到监听就绪
    is_up && break
    sleep 0.5
    i=$((i + 1))
  done
fi

exit 0
