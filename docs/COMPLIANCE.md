# Compliance Mapping — AuditSeed v0.0.1

> 诚实声明：下表映射的是 AuditSeed **提供的能力**与各框架**控制项**的关系，
> 不构成"通过认证"的声明。合规结论取决于组织整体控制体系与审计师判断。

## SOC 2 (Trust Services Criteria)

| TSC | 控制意图 | AuditSeed 提供的支持 |
| --- | --- | --- |
| CC8.1 (Change Management) | 变更授权、测试与批准 | `task_open`（含 reason = 变更依据声明）、`task_close`（结果确认）、`verify` 回执 |
| CC7.2 (System Monitoring / Anomalies) | 检测异常配置与未授权变更 | git 对账的 `unlogged` 清单 + `gate` 非零退出码可作 CI 异常告警 |
| CC7.3 (Incident Evaluation) | 事后评估事件 | 哈希链提供不可变时间线（`seq/ts/hash`）供事后取证 |

## ISO/IEC 27001:2022

| Annex A | 控制意图 | AuditSeed 提供的支持 |
| --- | --- | --- |
| A.8.15 Logging | 记录事件日志 | 追加式 JSONL 行为链（谁/何时/什么/为什么） |
| A.8.16 Monitoring Activities | 监控异常 | 覆盖率与 unlogged 变更报告；CI gate |
| A.8.9 Configuration Management | 配置基线保护 | 对 `infra/` 等目录的 policy 规则（0.1 路线） |

## EU AI Act (Regulation 2024/1689)

| 条款 | 要求 | AuditSeed 提供的支持 |
| --- | --- | --- |
| Art. 12 Record-keeping | 高风险系统自动记录事件日志（确保可追溯） | 自动捕获的行为链（hook 硬采集 + 哈希链完整性）；本地存储 |
| Art. 14 Human Oversight | 人类监督（覆盖/干预能力） | 声明仪式强制人类可读的"why"；`audit_status` 覆盖率报告 |

## 当前缺口（对应 THREAT-MODEL 与 ROADMAP）

- 无 hook 客户端的覆盖缺口依赖 git 对账兜底（覆盖率如实报告，非 100% 保证）；
- 本机哈希链尚未外锚（0.1：链头哈希导出 / CI artifact 锚定）；
- 报告签名与审计员只读验证（1.0 路线）；
- 脱敏规则（0.1 路线）。
