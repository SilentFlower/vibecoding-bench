# Frontend Development Guidelines

> Best practices for frontend development in this project.

---

## Overview

本项目前端是 **`webui/{index.html, app.js, style.css}` 三个静态文件**,由 FastAPI 的 `StaticFiles` 在 `/` 下托管。**零构建**(无 npm / 无 framework / 无 TypeScript / 无 bundler / 无 lint),通过 hash 路由 + 全局 `state` 对象 + 模板字符串渲染管 4 个 tab 的 UI。

视觉上是 "Terminal Lab" 终端实验室皮肤(暗色主 + `[data-theme=light]` 明亮变体)。

所有规范文件:
- **诚实描述代码实际是什么样**,不假装这是个 React/TS 项目
- 模板里给出的 hook / state-management / type-safety 等概念**在本栈下不直接存在**,本目录对应文件改为说明"等价物是什么、如何在原生 JS 下解决相同问题"
- **中文撰写**,代码示例保留原文
- 配套 `webui/` 当前提交;若实现风格偏离需更新本目录

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | 三文件结构 + app.js 节顺序 + 命名约定 | Filled |
| [Component Guidelines](./component-guidelines.md) | `<template>` + render 函数对 + modal 收口模式 | Filled |
| [Hook Guidelines](./hook-guidelines.md) | 无 React;`setup* / attach* / end*` 函数对 | Filled |
| [State Management](./state-management.md) | 单 `state` 对象 + 直接赋值 + 显式 render 触发 | Filled |
| [Quality Guidelines](./quality-guidelines.md) | 零构建保活、跨主题、`escapeHTML`、Review 清单 | Filled |
| [Type Safety](./type-safety.md) | 无 TS;后端 Pydantic + 前端 `escapeHTML` + 约定 | Filled |

> 鉴权登录页 / cookie session 前端配套 / paste-helper 模式,跨层契约写在 [deploy/auth-design.md](../deploy/auth-design.md);本目录只覆盖前端实现风格。

---

## How to Use These Guidelines

1. **写代码前**:看对应 spec 文件 + `webui/app.js` 同类代码,贴着现有风格写
2. **改代码后**:对照 Code Review Checklist(quality-guidelines.md 末尾)逐项过一遍
3. **发现偏差**:如果代码现实和 spec 描述不一致,**先确认哪个是真相**(通常代码是真相),然后更新 spec(走 `trellis-update-spec`),不要默默改代码迎合过时 spec

每个文件结尾都有"Common Mistakes"表,**新人优先看这里**。

---

**Language**: Spec 主体使用 **中文**;表标题、字段名、模式名保留英文以贴合代码;示例代码不翻译。
