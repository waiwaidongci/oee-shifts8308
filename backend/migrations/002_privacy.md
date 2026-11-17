# 002 差分隐私查询

新增两张业务表，SQLAlchemy 启动自动创建：

- `privacy_budgets`：每份已复核报告一行（`run_id` 唯一）。`total` 为报告总预算 ε=8，`spent` 只增不减、不可重置；同一报告的预算跨账号共享。报告复核通过时建立，存量已复核报告在首次隐私查询时惰性建立（唯一约束防并发重复）。
- `privacy_queries`：隐私查询台账。`dedupe_key`（报告+日期集+设备集+ε 的 SHA256）唯一约束支撑相同条件幂等重试——命中即返回原结果，不重复扣减。`status` 为 `completed`（已计费并保存噪声结果）或 `rejected`（预算不足，`reason` 记录拒绝原因，不扣减）。

扣减采用条件化原子更新 `UPDATE privacy_budgets SET spent=spent+ε WHERE spent+ε<=total`，与结果行同一事务提交：并发不超支，扣减后中断不留未计费结果。
