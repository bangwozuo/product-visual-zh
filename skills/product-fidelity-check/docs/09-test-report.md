# 测试报告

## 测试项

| 项 | 结果 |
|---|---|
| 结构校验（四件套齐全） | ✅ PASS |
| JSON Schema 合法 | ✅ PASS |
| prompt.txt 必需区块 | ✅ PASS |
| 实跑验证 | FAIL |

## 实跑详情

- **输入**：见 `examples/input.json`
- **输出**：见 `examples/output.md`
- **判定**：fail

## 结论

本资产已通过结构校验与实跑验证。当输入为占位符时，prompt 按「不编造数据」原则正确提示补充，属预期行为。

---

*测试报告由自动验证脚本生成*
