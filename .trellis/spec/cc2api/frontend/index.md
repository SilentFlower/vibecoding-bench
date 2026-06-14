# cc2api Frontend Code-Spec Index

> 本层覆盖 `cc2api/web/` Vue 3 + TypeScript + Vite 管理后台。后端 API 和 settings 规则见 `backend/`。

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Frontend Guidelines](./frontend-guidelines.md) | Vue Router、API client、settings UI、类型同步和构建规则 | Filled |

---

## Pre-Development Checklist

修改 `cc2api/web/` 前必须：

1. 读取 [Frontend Guidelines](./frontend-guidelines.md)。
2. 搜索 `web/src/api.ts` 和目标组件，确认字段名、接口路径和现有控件模式。
3. 涉及设置项时，同时读取 [backend Settings & Database](../backend/settings-database.md)。
4. 涉及账号、token、usage、telemetry 显示时，确认敏感字段是否脱敏。

## Quality Check

```bash
cd cc2api/web
npm run build
```

---

**Language**: 中文撰写；组件名、接口路径、TypeScript 字段名保留原文。
