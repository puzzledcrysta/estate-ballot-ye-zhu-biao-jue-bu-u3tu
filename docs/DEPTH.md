# 业主表决簿业务与测试登记

- 规模：中型
- 使用者：住宅小区业委会计票员
- 核心规则：同一所有权主体跨房合并为一票，按共有比例计算面积；参与和赞成均同时满足面积及人数门槛。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 送审票册 | 检查编码、字段宽度和来源行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 产权字段 | 归一修订、业务键和偏移时间 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 冲突票夹 | 定位重复、被替代与矛盾来源 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 份额计票 | 按规则复算并追溯证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 公示勾稽 | 核对独立清单和各类差异 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 议案记录 | 打开历史批次并对原文件复跑 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 计票底稿 | 登记复核结论并下载证据 | `POST /api/review/{run_id}` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 产权更正 | 录入原票与两份互斥更正，三路各算面积人数并分别对账 | `POST /api/corrections` | `app/modules/corrections/service.py` | `tests/test_corrections.py` |

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-01 | GB18030 来源文件 | legacy.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_gb18030` |
| TRAP-02 | BOM 前缀 | shift.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 备注含引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 分段重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不足 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 缺测哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 前导零的单号 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时刻 UTC 归一 | shift.csv | `app/modules/domain/values.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 同版业务字段冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-16 | 末行引号截断 | truncated.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_truncated_rejected` |
| TRAP-17 | 旧版列名映射 | legacy.csv | `app/modules/contract/schema.py` | `tests/test_contract.py::test_legacy_aliased` |
| TRAP-18 | 空文件、空白文件与仅表头 | 测试构造 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核版本拒绝 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-27 | 互斥更正翻转议案结论 | 测试构造 | `app/modules/corrections/service.py` | `tests/test_corrections.py::test_flip_is_held_for_verification` |
| TRAP-28 | 更正重跑不得新增确认记录 | 测试构造 | `app/modules/corrections/decisions.py` | `tests/test_corrections.py::test_signed_pack_grows_no_new_confirmation_on_rerun` |
| TRAP-106 | only area | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_only_area` |

## 对账

输入 = 计入 + 隔离 + 重传及版本替换 + 空白记录 + 重复表头。按业务键全外连接，缺失一侧与数值为零分别登记。逐笔差值与总差一致。

## 产权更正（M8）

同一议案收到两份互斥产权更正时，计票员在「产权更正」录入原票与两份更正（议案类别、产权单元、表决票）。三路各自独立复算产权/参与/赞成的面积与人数及双门槛结论，再各自与外部账全外连接对账。

- 三路结论一致且无隔离 → `结论不变`，复核可直接「确认」。
- 任一路无法计票（隔离）或更正使双门槛结论翻转（如由通过变为未通过）→ `待核实`，只允许「留待核实」且必须填写意见。
- 更正包按规则版本、规范载荷与外部账摘要做内容寻址；同样两份更正重跑返回同一批次，已登记的确认/留待记录不新增。
- 原票、产权更正一、产权更正二的录入字段、计票依据（proof）与逐路对账结果均保留，可通过 `/api/corrections/{id}/export` 下载。
