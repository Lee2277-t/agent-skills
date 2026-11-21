---
name: js-module-split-verification
description: "在 JavaScript 单文件拆模块或拆分后排查跨模块漏引时，验证接口、依赖和实际行为。适用于 ReferenceError、ESM/CommonJS 不匹配及拆分后的回归，不用于无关架构重写。"
metadata:
  locally_curated: true
---

# JavaScript 拆模块与回归

## 先建立基线

读取模块系统、入口、调用方和现有测试，记录需要保持的导出与关键行为。已有 Git 或其他可恢复版本时复用，不强制另建备份副本。分出基础依赖、业务模块和聚合入口，只调整本次拆分涉及的文件。

## 拆分时保持契约

- 显式导入共享常量与函数，检查遗漏和重名导出；Object.assign 合并导出会覆盖同名项。
- 检查循环依赖对初始化顺序的影响，避免把“能加载”当作行为等价。
- 常量、闭包状态、this 绑定、同步返回值和异步错误均属于对外行为，不只比较函数名称。

## 验证两层

1. 使用项目已有 ESLint、类型检查或 AST 工具查未定义引用。正则扫描只能作线索，不能正确解析所有模板字符串、作用域与动态导入。
2. 根据入口与风险选择代表性行为冒烟，包括重要边界和会改变执行分支的配置。使用隔离存储和测试替身，避免枚举所有导出后盲目调用会写数据的函数。

异步测试必须等待结果并传播失败，例如：

```js
async function runCases(cases) {
  const results = await Promise.allSettled(cases.map(run => Promise.resolve().then(run)));
  const failures = results.filter(result => result.status === 'rejected');
  if (failures.length) throw new AggregateError(failures.map(result => result.reason));
}
```

以上仅演示等待与失败传播；具体断言由业务预期确定。替身通过只说明对应范围的逻辑，不代表真机、数据库或网络集成已通过。

## ESM / CommonJS

先检查最近的 package.json、文件扩展名和真实运行环境。CommonJS 测试入口可用 .cjs，ESM 使用 import；.cjs 入口不会自动把依赖的 .js 改成 CommonJS。不要为通过测试修改主工程模块声明或全局劫持 Node 私有加载器；必要时在隔离夹具或目标宿主运行。

## 完成标准

导出兼容、关键行为及相关分支回归通过，并运行项目已有语法/构建检查。只更新已有且受本次改动影响的模块文档；不自动增加多份 README、入门手册或审计报告。
