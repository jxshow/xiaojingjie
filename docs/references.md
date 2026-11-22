# 旧报告兼容与设计参考

## 旧报告导入

小鲸洁可以读取卡兹克的 storage-analyzer 分析 JSON。已有报告的用户可在启动时传入 `--report`。小鲸洁通过 `generated_at` 和 `top5` 展示带日期的历史排行，通过 `yellow` 和 `red` 展示需要复核的项目。当前余量和可清理缓存均在本机重新测量。[报告格式来源](https://github.com/KKKKhazix/khazix-skills/tree/76fc0f8e8245b40a809d8eed89b27f04cbcf81bb/storage-analyzer)

## 设计参考

设计工作台时，我们参考了 storage-analyzer 按风险解释清理建议的做法、MangoDisk 逐项选择和查看操作记录的交互，以及 BleachBit 先预览再执行的流程。[storage-analyzer](https://github.com/KKKKhazix/khazix-skills/tree/main/storage-analyzer) · [MangoDisk](https://github.com/harry0703/MangoDisk) · [BleachBit](https://docs.bleachbit.org/doc/general-usage/)
