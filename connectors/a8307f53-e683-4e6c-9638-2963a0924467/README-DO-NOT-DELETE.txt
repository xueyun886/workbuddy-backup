WorkBuddy Connector Credentials
================================

本目录包含 WorkBuddy 连接器（QQ 邮箱 / 腾讯文档 / 微云等）的本地凭据。

请不要单独删除以下隐藏文件：
  .credentials.v3.json       加密后的 OAuth 令牌
  .credentials.json          旧版本明文凭据（保留作为回滚兜底，不会再被写入）
  connector-states.v3.json   加密后的连接器状态（含注入用 token / API Key）
  .master.key                本地加密密钥（误删将导致所有连接器需要重新授权）

如需重置某个连接器，请通过 WorkBuddy 客户端 → 连接器中心 → 解绑 操作；
彻底清理时请整目录删除，不要只删某一个文件。

This directory contains WorkBuddy connector credentials.
Do NOT delete individual hidden files. Use WorkBuddy → Connector → Unbind
to reset, or remove the whole directory if you want a clean state.
