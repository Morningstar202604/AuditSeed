# Changelog

遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；语义化版本。

## [0.0.1] - 2026-09-03

首个可用版本：三层闭环（Skill 声明 / hook 硬采集 / MCP 引擎）全链路落地。

### Added

- **哈希链存储** `server/engine/chainstore.py`：JSONL 单文件、严格 `O_APPEND`
  （无任何原地改写代码路径）、逐条 `flush + fsync`、`seq/prev/hash` 链式完整性、
  单写者 O_EXCL 锁（含陈旧锁回收与有界重试，修复 Windows 句柄语义下的回收死锁）、
  崩溃撕裂行的"debris vs tampering"分类（链接续接 → 信息性 debris；断链 → 致命）；
- **声明仪式** `audit_begin/finish/note`：动手前强制声明任务与理由，`task_id`
  白名单校验，`outcome` 枚举校验，闭合后清理活动任务；
- **git 对账** `server/engine/reconcile.py`：工作区 porcelain v1 vs 链上事件 →
  covered / unlogged / phantom / 覆盖率；非 git 目录如实降级；
- **合规报告** `server/engine/report.py`：按任务导出 markdown / JSON
  （声明、时间线、文件表、命令、验证回执、完整性、覆盖率）——纯函数返回字符串，
  stdout-first，插件内不出现任何"写用户文件"的代码路径；
- **MCP 服务器** `server/mcp_server.py`：零依赖 stdio JSON-RPC 2.0
  （initialize / tools/list / tools/call / 通知语义 / -32700/-32601/-32602 错误矩阵），
  六个审计工具；**故意不暴露**任何修改证据或绕过门禁的工具；
- **客户端 hook** `hooks/posttooluse.py` + `hooks/hooks.json`：Write/Edit/MultiEdit/
  Bash 事件归一化入链；永不阻塞客户端（异常吞掉 → 覆盖率报告揭示缺口，而非隐藏）；
- **CLI** `bin/auditseed.py`：begin / finish / status / verify / export / gate
  （gate 退出码 0/1/2：链校验失败、任务未闭合、覆盖率低于阈值）；
- **技能** `skills/audit/SKILL.md`：声明仪式 + 反模式清单（含 `reverted` 是好条目
  的价值观声明）；
- **文档**：DESIGN.md（完整架构）、THREAT-MODEL.md（防什么/不防什么）、
  COMPLIANCE.md（SOC2 / ISO 27001 / EU AI Act 映射，不夸大）；
- **测试 ×36**：分类器全分支（内存法，含 debris/致命边界）、锁竞争与陈旧锁回收
  （含 Windows 句柄语义死锁回归）、对账四象限、MCP 协议矩阵、hook 归一化与
  畸形输入、门禁决策分支；全部真实临时 git 仓库 + 隔离存储根。
