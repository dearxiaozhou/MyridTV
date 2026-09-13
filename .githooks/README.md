# 提交门禁（本地 CI）

项目只在本地 git 里（没有远端），所以“CI”的等价物是**提交前自动跑自检**：

- 钩子文件：`.githooks/pre-commit` → 调 `tests/verify.ps1`
  （Python 语法 40+ 文件 / 前端 JS `node --check` 26 文件 / i18n 键校验 / `tests/test_*.py`）
- 启用：`git config core.hooksPath .githooks`（本仓库已设置）
- 临时跳过：`git commit --no-verify`
- 手动全量跑：`powershell -File tests/verify.ps1`

改完代码先跑一遍；红了就别提交、别交付。
