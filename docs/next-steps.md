# 下一步：已经有的、正在做的、还缺什么

这一页是**待办清单**，不是设计文档。设计理由在各自专题页里：心理与提醒见
`psychosocial-support.md`，血糖记录见 `glucose-data-format.md`，部署见 `release.md`。

分四类：产品能力（不需要外部授权就能做）、需要外部授权、研究方法、工程债。
每条都写清「现在到哪了」，避免下次接手的人从零猜。

## 一、产品能力

### 1. 每周联系次数：已经能按人定，还差手机上的入口

- 后端已完成：四象限给出默认剂量（`api/src/antang_api/psychosocial/support.py`
  的 `DOSAGE_BY_QUADRANT`），患者还可以自己覆盖成 1–7 次
  （`proactive_care_settings.weekly_contact_limit`），执行闸门在
  `api/src/antang_api/proactive_care/quota.py` 的 `weekly_quota()`，
  满额时任务推到「额度腾出来的那一刻」，不是静默丢弃。
- 还缺：`apps/mobile` 的设置页没有这个数字的控件。现在只有 `GET`/`PUT
  /api/v1/proactive-care/settings` 接口，手机端要加一个 1–7 的步进器，
  并把 `weekly_contact_limit_source` 显示成「你定的 / 按评估结果」。
- 判断做完了没有：改完之后在手机上改一次数字，锁屏提醒的时间跟着变。

### 2. 固定整点问候：已完成

- `proactive_care_settings.check_in_hour`（迁移 `o4d5e6f7a8b9`），
  `_snap_to_local_hour()` 把任务对齐到患者本地的整点，改小时会立刻重排。
- 为什么固定而不随机：随机的关心把「检查血糖」这件事外包给系统，反而强化
  反复确认。见 `psychosocial-support.md` 第五节。

### 3. 话题冷却：还没做

同一件事（比如连续三天都在劝「睡前加餐」）现在没有任何冷却机制，只有总次数
上限。需要的是「同一个话题 N 天内不重复」：在 `proactive_care_tasks` 上按
话题留痕，起草前查一次。做之前要先定「话题」怎么标——现在 `task.kind` 只有
问候/健康事件两大类，粒度不够，可能要引入 `topic` 字段。

### 4. 行为信号做触发：还没做（设计已清楚）

反复问血糖、回避运动、夜里反复确认，这三类行为在数据里都能看到，但没有任何
地方把它们变成主动关怀的**触发条件**。现状是所有主动联系都走定时任务。

- 可用的信号（都已经在库里）：`glucose_readings` 的查询/记录频率、
  `meal_logs` 与运动记录的缺失、`fear_behavior_logs` 的 `kind`
  （`bedtime_snack` / `skip_exercise` / …）、消息时间戳集中在夜间。
- 阈值不能拍脑袋：先在 `docs/` 里写清「什么算反复确认」，再写代码；否则就是
  又一套关键词规则。
- 与 alarm fatigue 的关系：行为触发会显著增加推送总量，**必须先有话题冷却与
  次数闸门**，所以排在 3 之后。

### 5. 「用你的话问你的血糖」：只做了第一层

- 现在能做的：固定参数的工具（`read_glucose_readings` 取 N 天、`read_meals`、
  `read_medications`），模型自己决定调用哪个。回答不了「我上周三晚饭前那次
  多少」这种带任意约束的问法——工具参数里没有「周三晚饭前」。
- 缺的是把自然语言约束解析成查询（时间表达式、餐次、上下限），再拼成一次
  结构化查询并返回**原始行**，让模型基于行造句而不是自己算。
- 灵感来源：Chen & Bunescu, *Context Dependent Semantic Parsing over
  Temporally Structured Data*（NAACL 2019, pp. 3576–3585,
  <https://aclanthology.org/N19-1360/>）。论文报告的 sequence-level accuracy
  是 88.7%（人工构造数据）/ 74.8%（真实数据），这个数字提醒我们：**做之前先
  定义评测集**，否则无法判断有没有做对。

### 6. 题库升级：框架在，题是人家的

- 现在：`instrument` 字段区分题库，题面与计分都在服务端（
  `psychosocial/instrument.py`），换题库不需要重装 App。
- 已接入：自编 6 题 + Gold 1 题（`antang-behavior-v1`）、WHO-5（`who5`，
  免费、需注明出处，作为**附加块**搭在同一次评估里，不替代恐惧分量表）。
- 还缺：WHO-5 的手机端渲染（现在后端接口可用，`PsychosocialSection.tsx`
  只画主量表）；拿到授权后替换 HFS-II 题面（表结构与接口不用动）。

## 二、需要外部授权（不能自己动手解决）

| 量表 | 状态 | 要做的事 |
|---|---|---|
| HFS-II / HFS-B / HFS-S / CHFS / PHFS-II / HFS-98 | 版权在 Gonder-Frederick 团队，**未授权** | 发授权询问（谁申请、什么用途、多少患者、是否商业化）；答复前界面只能写「自编行为清单」 |
| PAID（Problem Areas In Diabetes） | Mapi Research Trust / ePROVIDE 管理，**需申请** | 走 ePROVIDE 线上申请，通常要研究方案摘要、用途、样本量、是否要中文翻译 |
| WHO-5 | 免费（WHO 区域办公室发布，署名即可） | 已在用；文档与界面注明出处与「不是诊断」 |
| Gold score / Clarke | 论文公开发表，引用原文即可 | 已在用（Gold 1–7 计分法）；引用 Gold 1994 |

**PAID 要不要签**：产品内部用不需要它——四象限只依赖恐惧程度与察觉能力。要用
的是「想对外声称我们在测糖尿病相关痛苦」这件事；一旦署名 PAID，就必须按授权
条款使用官方题目与官方译法，不能自己改写。签不签取决于是否要发表或申报。

## 三、研究方法（CASE 与 Think Twice）

这两条来自另一份文档里的研究分析（LMc 组方向），**目前代码里是 0%**。已有的
近似实现：`behavioral/service.py` 的 `_judge_discrepancy()`（问卷说一套、行为
记录另一套时给出比对），以及报告数字的「模板解析 / 两遍读数对账」（提示词层面
禁止编数字）。要真正落地，需要先把下面两件事定清楚：

1. **认知图与情感图怎么存**：先在库里定两张图的最小字段（节点=事件/念头/
   情境，边=因果/回避/安抚），否则 Talk 生出来的图无法复盘。
2. **两阶段生成怎么审计**：第一稿给内容与结构，第二稿只允许改措辞、不允许改
   数字与事实；需要一个自动比对（两稿的数字集合必须相同）作为回归测试，
   不能只写在提示词里。

建议顺序：先做「两稿数字一致」的自动比对（一天内能做完、立刻有回归价值），
再做图存储。

## 四、工程债

- `apps/mobile`：每周次数控件、WHO-5 渲染块、心理页与血糖页的新截图。
- 部署：`aya/proactive-weekly-quota` 分支上的提交（每周额度、固定整点、迁移
  修复）已合进 `team/master` 并经生产验证；再往后每次改迁移，**先跑的必须是
  宽的那条 CHECK**（见 `project-state.md` 2026-11-01 那节）。
- gitee 镜像：`origin/main` 停在 `8926435`，本机没有 gitee 凭据。要同步只有
  三条路：私人令牌 / 手动登一次凭据管理器 / 在 gitee 侧「从 GitHub 导入」。
- 旧安装包兼容：响应字段**只能加不能改名**（`below_70_count` 那次教训）。
