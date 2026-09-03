# AuditSeed — 技术设计

> **防篡改的 AI 编码行为审计插件**。Agent Plugins 1.0.0 规范插件：
> Skill（声明仪式）+ 客户端 hook（硬采集）+ MCP 引擎（哈希链存储 / 对账 / 合规导出）。
> 同系列：AgentSeed 管 agent 不说谎，AuditSeed 管**改动可追溯、可问责、可提交给审计师**。

## 1. 问题定义

AI 编码 agent 的一切自我汇报都不可信（这是 AgentSeed 的前提），但即便代码本身被验证通过，
企业仍然缺一层：**"这些变更是谁、在什么时候、基于什么理由、经过什么验证后落盘的？"**

- 上下文窗口是易失的：压缩、会话结束、换机器后，"为什么这么改"不复存在。
- 模型的自我陈述不能作为审计证据（利益冲突方兼任记录员）。
- 企业合规（SOC2 变更管理、ISO 27001 A.8.15/A.8.16、EU AI Act 第 12 条）要求
  机器生成、不可篡改、可查询的行为日志——今天所有 coding agent 都没有提供。

**AuditSeed 的边界（诚实声明）**：它记录**行为层**（文件变更 / 命令 / 声明 / 验证回执），
不记录模型内部推理与完整对话流（规范没有暴露通道，见 §6 威胁模型）。

## 2. 三层闭环（为什么缺一层就废）

```
      ┌────────────────────────────────────────────────────────┐
      │                AI coding agent (LLM)                   │
      │   唯一被信任提供的东西：动手前的结构化声明(task_id, 理由)     │
      └──────┬───────────────────────────────┬─────────────────┘
             │(软)按 SKILL 约定调用            │(硬)客户端 hook 触发
             ▼                               ▼
   ┌───────────────────┐          ┌───────────────────────────┐
   │ MCP server 工具族   │          │ hooks/posttooluse.py      │
   │  audit_begin       │          │ 观察每次 Write/Edit/Bash   │
   │  audit_finish      │          │ 模型无法绕过、无法不触发      │
   │  audit_status      │          └──────────┬────────────────┘
   │  audit_export      │                     │ 归一化事件
   │  audit_verify      │                     ▼
   └─────────┬──────────┘          ┌───────────────────────────┐
             │                     │ engine/chainstore.py      │
             ▼                     │ JSONL 哈希链（追加写）        │
   ┌───────────────────┐          │ seq/ts/type/payload/prev   │
   │ git 对账 reconcile │◀────────▶│ SHA-256 链式哈希 + fsync    │
   │ 漏记录改动检测       │          └───────────────────────────┘
   └───────────────────┘
```

| 层 | 单独存在时的缺陷 | 本插件中的角色 |
| --- | --- | --- |
| Skill（软） | 无执行体，模型可跳过 | 声明仪式：动手前 `audit_begin(task, reason)`，收尾 `audit_finish(outcome)` |
| hook（硬） | 采集到事件但没有"为什么"，也没有存储语义 | 无条件捕获每次 Write/Edit/Bash，**模型无法绕过** |
| MCP 引擎（确定性） | 无人调用就是死代码 | 哈希链存储、链校验、git 对账、覆盖率、报告导出、CI 门禁 |

纯 MCP 做不到"强制捕获"（服务器只有被调用才运行）；纯 skill 做不到"独立观察点"；
纯 hook 做不到"可信存储与查询"。**三层合体才是产品**——这正是 Agent Plugins 1.0.0
作为"打包规范"的独特组合能力。

## 3. 目录结构

```
AuditSeed/
├── plugin.json                  # 1.0.0 规范清单
├── mcp.json                     # MCP server 声明（stdio: server/mcp_server.py）
├── skills/
│   └── audit/
│       ├── SKILL.md             # 声明仪式（frontmatter 符合 1.0.0）
│       └── references/
│           └── REFERENCE.md     # 字段语义 / 反模式 / 与 AgentSeed 回执的联动
├── hooks/
│   ├── hooks.json               # Claude Code 系 hook 注册（PostToolUse 观察模式）
│   └── posttooluse.py           # 事件归一化 → 入链（崩溃安全、单写者）
├── server/
│   ├── mcp_server.py            # 零依赖 stdio JSON-RPC（newline-delimited）
│   └── engine/
│       ├── canon.py             # 规范化 JSON + SHA-256 工具
│       ├── chainstore.py        # 哈希链追加写 / 校验 / 锁 / 崩溃安全
│       ├── reconcile.py         # git status/diff vs 链上事件 → 漏记录 + 覆盖率
│       └── report.py            # per-task changeset 报告（markdown/JSON）
├── bin/
│   └── auditseed.py             # CLI：gate / export / verify / status / begin / finish
├── tests/                       # 全链路测试（见 §7）
├── docs/
│   ├── DESIGN.md                # 本文档
│   ├── COMPLIANCE.md            # SOC2 / ISO 27001 / EU AI Act 条款映射（不夸大）
│   └── THREAT-MODEL.md          # 防什么、不防什么（诚实边界）
├── .github/workflows/ci.yml     # 语法检查 + 链篡改实验 + 全测试
├── pyproject.toml               # 仅 dev 依赖（pytest）；运行时零依赖
├── README.md / CHANGELOG.md / LICENSE
```

## 4. 核心数据结构

### 4.1 链条条目（chain entry）

```json
{
  "v": 1,
  "seq": 7,
  "ts": "2026-09-03T06:12:44.108Z",
  "repo": "a1b2c3d4e5f60718",
  "task": "feat-login",
  "type": "file_change",
  "payload": {
    "path": "src/auth/login.py",
    "op": "modify",
    "tool": "Edit",
    "diff_stat": {"insertions": 12, "deletions": 3}
  },
  "prev": "9f86d0…",
  "hash": "2c26b4…"
}
```

- `hash = sha256(canon(条目去掉 hash 字段) + prev)`；`canon` = UTF-8、
  `sort_keys=True`、`separateors=(',',':')`、`ensure_ascii=False`。
- 创世条目 `seq=0`、`prev = 64 个 0`、`type=genesis`，绑定 repo 绝对路径哈希。
- 任何历史字节的改动都会使该条目 `hash` 与后续所有 `prev` 断裂——`audit_verify` 全链重算即发现。

### 4.2 事件类型（v0.0.1 全集）

| type | 产生者 | 关键 payload |
| --- | --- | --- |
| `genesis` | 引擎自动 | repo 根路径指纹、引擎版本 |
| `task_open` | 模型经 MCP（技能强制） | task_id、reason（为什么）、agent 声明的 scope |
| `file_change` | hook（硬） | path、op(add/modify/delete)、tool、diff_stat |
| `cmd` | hook（硬） | command、cwd、exit_code、duration_ms |
| `note` | 模型经 MCP | 结构化补充说明 |
| `verify` | AgentSeed 回执（可选联动） | verify 工具名、结论、时间 |
| `task_close` | 模型经 MCP | outcome(merged/reverted/partial)、summary |
| `anchor` | 用户/CI | 链头哈希外锚（粘贴进 PR/CI artifact/邮件） |

### 4.3 存储

- 位置：`~/.auditseed/chains/<repo_id>/chain.jsonl`（本地优先，不上传任何内容）。
  `repo_id = sha256(仓库绝对路径)[:16]`，路径不进链（隐私）。
- 单写者：`chain.jsonl.lock`（O_CREAT|O_EXCL + 陈旧检测：>120s 且无持有进程则回收）。
- 每次追加 `flush + fsync` 后才返回成功；崩溃最多丢"正在写的那半行"，校验器按行解析时跳过并标记截断。

## 5. 重要功能点（0.0.1 承诺清单）

| # | 功能点 | 验收标准 |
| --- | --- | --- |
| F1 | 哈希链追加写 | 乱序/断链/改历史任一，`audit_verify` 必须报错并定位行号 |
| F2 | 篡改实验 | 翻转链文件任意字节 → 校验失败；恢复后重新通过 |
| F3 | 崩溃安全 | 追加到一半被杀 → 合法条目数不变，截断行被标记不传播 |
| F4 | hook 采集 | Write/Edit/Bash 事件全部入链，模型不可绕过（hook 由客户端触发） |
| F5 | 声明闭环 | task_open 必须先于该任务 file_change 事件，否则 reconcile 报 unassigned |
| F6 | git 对账 | 工作区改动 vs 链上事件 → 漏记录清单 + 覆盖率百分比 |
| F7 | 合规导出 | 按任务导出 markdown/JSON 报告：谁/何时/改了什么/为什么/验证回执/结果 |
| F8 | 链头锚点 | 输出链头哈希，可粘贴到 PR/CI 作存在性证明（外锚） |
| F9 | CI 门禁 | `auditseed gate`：链校验失败/覆盖率低于阈值/任务未闭合 → 非零退出码 |
| F10 | 零依赖 | 运行时仅 Python 3.9+ 标准库（git 需在 PATH，仅 reconcile/gate 用） |

### 5.1 CLI 一览

```
auditseed begin  --repo PATH --task ID --reason "..."     # 声明仪式（等同 MCP audit_begin）
auditseed finish --repo PATH --task ID --outcome merged   # 任务闭合
auditseed status --repo PATH                              # 覆盖率 / 漏记录 / 当前任务
auditseed verify --repo PATH                              # 全链重算校验
auditseed export --repo PATH --task ID [--format md|json] # 合规报告
auditseed gate   --repo PATH --task ID --min-coverage 100 # CI 门禁（0/1/2 退出码）
```

MCP 工具与 CLI 一一对应，命名 `audit_begin / audit_finish / audit_status / audit_verify /
audit_export`（MCP 侧不提供 gate——门禁属于 CI/人，不属于模型）。

## 6. 威胁模型（不夸大）

**防得住**：事后篡改/删除历史记录（哈希链断裂必被发现）；模型谎报"没改过某文件"
（hook 硬采集 + git 对账双重兜底）；"为什么改"丢失（声明入链）。

**防不住（v0.0.1 边界，见 THREAT-MODEL.md 全表）**：
- 不支持 hook 的客户端只能靠 git 对账兜底，覆盖率报告会如实反映缺口；
- 本地磁盘攻击者可以整文件删除（v0.1 起提供链头外锚 + 定期 anchor 到 CI/远端）；
- 模型把代码"讲"出去的通道（对话本身）不在采集范围；
- 记录者（本机引擎）与行为者的物理同机性——信任根是本机用户，不是云端第三方。

## 7. 测试策略

- 引擎层：篡改/断链/截断/乱序/锁竞争/空仓/非 git 目录，全部真实临时目录 + 真实 `git init`；
- hook 层：stdin JSON 各形态（含畸形输入）→ 归一化 → 入链断言；
- MCP 层：initialize / tools/list / tools/call / 未知方法 / 畸形 JSON 的协议矩阵；
- 对账层：记录后改动、未记录改动、链外新文件、删除事件 四象限；
- 门禁层：阈值边界（99/100）、任务未闭合、链被篡改三种失败路径。

## 8. 版本路线

- **0.0.1（本版）**：F1–F10 全部落地，真实 hook 覆盖 Claude Code 系客户端，其余客户端 git 兜底。
- 0.1：policy 规则（目录级强制声明）、链头定期外锚（CI artifact）、AgentSeed verify 回执自动入链。
- 0.2：多仓库聚合视图、团队级（远端只读镜像）审计、报告自定义模板。
- 1.0：审计员模式（只读验证工具 + 报告签名），COMPLIANCE 映射升级为经样本审计验证。
