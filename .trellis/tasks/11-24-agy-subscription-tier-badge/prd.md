# 反重力账号显示真实订阅档位

## 目标

账号卡片及详情标题显示平台观测到的订阅档位。账号的自定义名称可以自由修改。

## 事实

截图对应的账号返回了两种信息。原生 `userTier.name` 和额度快照 `tier` 均为 `Google AI Ultra`，`userTier.id` 为 `g1-ultra-tier`。同一次原生数据的 `planStatus.planInfo.planName` 为 `Pro`。当前 `apps/web/src/components/Accounts.vue` 的 `cardPlan` 只读取 `platform_quota.plan`，因此两个标题都显示 Pro。

## 需求与验收

- AGY 标签按已观测的用户订阅档位显示。原生 `capabilities.provider.userTier` 支持字符串和带 `name` 的对象。历史快照可使用 `platform_quota.tier`。两者缺少有效名称时沿用 `platform_quota.plan`，全部缺失则隐藏标签。
- 用独立的合成名称验证套餐而非按账号名推测。冲突样本 `Google AI Ultra / Pro` 在列表和详情标题都显示 `Ultra`，真实 Pro 显示 `Pro`。详情如展示两项原始观测，分别标明“订阅档位”和“平台计划”，确保语义清楚。
- 同时回归只有旧 plan 的账号、档位为空、所有观测缺失，以及原有 Claude 订阅显示。复用 `deploy/flower2api/verify_agy_accounts_ui.py` 构造样本，运行前端类型检查、构建和浏览器验证。此改动只需展示现有管理 API 数据。
