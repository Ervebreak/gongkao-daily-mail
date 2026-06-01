# Policy Coordinate Integration Report

## 1. 新增或修改了哪些文件
- `config.py`
- `knowledge_base_loader.py`
- `policy_coordinate_matcher.py`
- `policy_coordinate_usage_history.py`
- `policy_coordinate_quality.py`
- `email_renderer.py`
- `main.py`
- `scripts/check_knowledge_base_loader.py`
- `scripts/check_policy_coordinate_matcher.py`
- `scripts/check_policy_coordinate_usage_history.py`
- `scripts/run_policy_coordinate_trials.py`
- `docs/POLICY_COORDINATE_INTEGRATION_REPORT.md`
- `knowledge_base/policy_corpus/policy_statements_core.jsonl`
- `knowledge_base/policy_corpus/policy_statements.jsonl`
- `knowledge_base/topic_knowledge/article_index.jsonl`
- `knowledge_base/topic_knowledge/article_chunks.jsonl`
- `knowledge_base/topic_knowledge/authoritative_quotes_core.jsonl`
- `knowledge_base/topic_knowledge/authoritative_quotes_candidates.jsonl`
- `knowledge_base/topic_knowledge/topic_frameworks.jsonl`

## 2. 读取了哪些知识库文件
- `knowledge_base/policy_corpus/policy_statements_core.jsonl`
- `knowledge_base/policy_corpus/policy_statements.jsonl`
- `knowledge_base/topic_knowledge/article_index.jsonl`
- `knowledge_base/topic_knowledge/article_chunks.jsonl`
- `knowledge_base/topic_knowledge/authoritative_quotes_core.jsonl`
- `knowledge_base/topic_knowledge/authoritative_quotes_candidates.jsonl`
- `knowledge_base/topic_knowledge/topic_frameworks.jsonl`
- `data/policy_coordinate_usage_history.jsonl`

## 3. 新增了哪些字段
- `policy_coordinate.theme`
- `policy_coordinate.policy_quote` / `policy_source` / `policy_source_type` / `policy_translation`
- `policy_coordinate.authoritative_quote` / `authoritative_source`
- `policy_coordinate.article_connection` / `exam_transfer` / `answer_angles`
- `policy_coordinate.matched_policy_id` / `matched_qiushi_quote_id` / `matched_qiushi_article_id` / `matched_framework_id` / `matched_chunk_ids`
- `policy_coordinate.display_evidence_type` / `display_evidence_label` / `display_evidence_quote` / `display_evidence_source` / `evidence_selection_reason`
- `policy_coordinate.source_type`
- `quote_status` / `display_priority` / `theme_confidence` / `display_ready` / `usage_tier` / `freshness`（语料清洗字段）
- `data/policy_coordinate_usage_history.jsonl` 的 `date` / `theme` / `matched_*` / `policy_quote` / `authoritative_quote`

## 4. 渲染位置在哪里
- `email_renderer.py` 将“今日政策坐标”放在“今日精读”之后、“今日一题”之前。
- HTML 和 plain_text 同步渲染；`brief` 本体不写栏目标题，只写结构化 `policy_coordinate` 数据。

## 5. 质检规则有哪些
- 展示 `policy` 时必须同时具备 `policy_quote` 与 `policy_source`；展示 `qiushi` 时必须同时具备 `authoritative_quote` 与 `authoritative_source`；展示 `both` 时两者都要通过检查。
- `policy_quote` 不超过 90 字；`authoritative_quote` 如存在不超过 120 字。
- 不得把《求是》论述写成政策原文，也不得出现“某领导人指出”但没有具体来源。
- `matched_policy_id` 必须能在政策库中找到；`matched_qiushi_quote_id` 如存在必须能在《求是》表达库中找到。
- 不得出现半截句、空泛转译、与今日精读/今日可带走/今日一题大段重复；双依据同时展示时不得高度重复。
- 《求是》权威论述不合格时自动删除；政策原文不合格时尝试重匹配，仍失败则隐藏整个模块。
- 高危政策坐标错误已并入 P0 门禁，命中关键 code 会阻断正式发送。

## 6. 三个试跑样例的 policy_coordinate 内容
### 基层治理 / 新就业群体 / 城市治理
- 主题：`基层治理`
- 展示类型：`both`
- 证据选择原因：政策原文和权威论述都高度贴切且不重复，policy_score=145.0，qiushi_score=136.0。
- 政策原文：国务院关于推行常住地提供基本公共服务的实施意见提出，“将基层就业公共服务融入以党建引领基层治理范畴，在乡镇（街道）履行职责事项清单中落实。”。
- 权威论述：《求是》2024年第9期文章《组织动员亿万职工积极投身强国建设、民族复兴的伟大事业》。强调，“要健全已有的组织基础，持续推进新经济组织、新社会组织、新就业群体建会入会工作，扩大工会组织覆盖面。”。
- 文章落点：本文以《“小哥议事厅”让骑手成为社区治理新力量》中的具体案例，呈现了基层治理从政策要求到基层场景的落点：一些城市通过议事厅、骑手驿站、随手拍上报等机制，把新就业群体纳入城市治理链条，让他们既能被服务，也能反哺治理。
- 考场迁移：遇到申论对策可从建平台、畅诉求、强协同、促闭环四步展开，体现多元共治和基层精细化治理；面试综合分析可强调把新就业群体从被管理对象转化为治理共同体成员，增强城市治理的感知力和响应力；申论对策题类题目，可从政策目标、现实堵点、协同机制和闭环落实四个层面展开。
- 答题角度：夯实基层基础；整合治理资源；提升服务能力；把群体吸纳进来：依托骑手驿站、议事厅和网格联络员；把问题收集上来：通过随手拍、微建议、线上工单等方；建平台入口：依托驿站和议事厅设置稳定参与渠道。
### 高质量发展 / 新质生产力
- 主题：`新质生产力`
- 展示类型：`qiushi`
- 证据选择原因：两条依据都可用，但权威论述贴合度明显更高，policy_score=164.0，qiushi_score=177.0。
- 政策原文：本样例前台未展示政策原文。
- 权威论述：《求是》2023年第15期文章《加强基础研究 实现高水平科技自立自强》。强调，“应对国际科技竞争、实现高水平科技自立自强，推动构建新发展格局、实现高质量发展，迫切需要我们加强基础研究，从源头和底层解决关键技术问题。”。
- 文章落点：本文以《让科技成果加速转化为看得见的新质生产力》中的具体案例，呈现了新质生产力从政策要求到基层场景的落点：一些地方围绕成果转化、中试验证、金融支持和人才集聚联动发力，让创新成果更快进入产业化场景，推动传统产业升级和未来产业培育同步突破。
- 考场迁移：遇到申论可从强创新平台、补转化环节、育应用场景、优要素配置四个角度展开；面试可强调发展新质生产力既要向前布局未来产业，也要向内改造传统产业，形成新旧动能接续转换；申论对策题类题目，可从政策目标、现实堵点、协同机制和闭环落实四个层面展开。
- 答题角度：强化科技创新；培育产业动能；推动成果转化；做强创新平台：统筹实验室、产业研究院和技术转移中；打通转化堵点：围绕中试验证、知识产权运用和标准衔；强平台支撑：提升实验室和转移中心承接能力。
### 民生保障 / 就业
- 主题：`民生保障`
- 展示类型：`both`
- 证据选择原因：政策原文和权威论述都高度贴切且不重复，policy_score=137.0，qiushi_score=136.0。
- 政策原文：数字中国建设整体布局规划提出，“促进数字公共服务普惠化，大力实施国家教育数字化战略行动，完善国家智慧教育平台，发展数字健康”。
- 权威论述：《求是》2024年第21期文章《促进高质量充分就业》。强调，“各级党委和政府要把就业当作民生头等大事来抓，加强组织领导，健全制度机制，增强工作合力。”。
- 文章落点：本文以《公共就业服务要从“有人管”走向“更好用”》中的具体案例，呈现了民生保障从政策要求到基层场景的落点：一些地方把就业服务站建到园区、社区和商圈，结合岗位归集、技能培训、重点群体帮扶和数字匹配，让求职服务更下沉、更精准、更有温度。
- 考场迁移：遇到申论对策可从服务下沉、精准匹配、培训赋能、兜底帮扶四个角度展开；面试可强调就业优先要落到服务可及性和政策精准度上，让群众在家门口找到机会、获得帮助；申论对策题类题目，可从政策目标、现实堵点、协同机制和闭环落实四个层面展开。
- 答题角度：补齐民生短板；提高保障水平；回应群众关切；服务站点下沉：把就业服务站布局到社区、园区、商圈；岗位培训衔接：同步归集岗位信息和培训资源，围绕企；下沉服务站点：把服务触角延伸到社区园区商圈。

## 7. 试跑检查结果
### 基层治理 / 新就业群体 / 城市治理
- `daily_json_has_policy_coordinate`: pass
- `html_has_policy_coordinate`: pass
- `plain_text_has_policy_coordinate`: pass
- `policy_quote_from_policy_corpus`: pass
- `authoritative_quote_from_topic_knowledge`: pass
- `qiushi_not_rendered_as_policy_quote`: pass
- `article_connection_specific`: pass
- `exam_transfer_specific`: pass
- `no_truncated_sentence`: pass
- `no_obvious_duplication`: pass
- `quality_check_passed`: pass
- `render_title_not_duplicated`: pass
- `takeaway_framework_hidden`: pass
- `all_passed`: pass
### 高质量发展 / 新质生产力
- `daily_json_has_policy_coordinate`: pass
- `html_has_policy_coordinate`: pass
- `plain_text_has_policy_coordinate`: pass
- `policy_quote_from_policy_corpus`: pass
- `authoritative_quote_from_topic_knowledge`: pass
- `qiushi_not_rendered_as_policy_quote`: pass
- `article_connection_specific`: pass
- `exam_transfer_specific`: pass
- `no_truncated_sentence`: pass
- `no_obvious_duplication`: pass
- `quality_check_passed`: pass
- `render_title_not_duplicated`: pass
- `takeaway_framework_hidden`: pass
- `all_passed`: pass
### 民生保障 / 就业
- `daily_json_has_policy_coordinate`: pass
- `html_has_policy_coordinate`: pass
- `plain_text_has_policy_coordinate`: pass
- `policy_quote_from_policy_corpus`: pass
- `authoritative_quote_from_topic_knowledge`: pass
- `qiushi_not_rendered_as_policy_quote`: pass
- `article_connection_specific`: pass
- `exam_transfer_specific`: pass
- `no_truncated_sentence`: pass
- `no_obvious_duplication`: pass
- `quality_check_passed`: pass
- `render_title_not_duplicated`: pass
- `takeaway_framework_hidden`: pass
- `all_passed`: pass

## 8. 前台展示分布
- 展示 `policy` 的样例数：0
- 展示 `qiushi` 的样例数：1
- 展示 `both` 的样例数：2
- 展示 `none` 的样例数：0
- 邮件前台已删除“今日可带走”中的“可迁移框架”展示，但 JSON 中的 `framework` / `exam_use` 等字段仍保留。

## 9. 近 14 天去重逻辑验证
- 试跑使用隔离历史文件：`output\policy_coordinate_trials\policy_coordinate_usage_history.jsonl`。
- 正式三次试跑依次写入临时 usage history，后续样例匹配时 `recent_count` 分别提升为：1 / 1 / 1。
- 额外重复探测主题：`基层治理 / 新就业群体 / 城市治理`。
- 首次命中政策 ID：`POLICY_0312`；重复探测命中政策 ID：`POLICY_0528`。
- 去重调试信息：`selected_repeat_notes={}`。
- nightly candidate 生成不会写正式 usage history；正式晨间发送成功后才会追加 `data/policy_coordinate_usage_history.jsonl`。

## 10. 目前还有哪些风险
- OSS 读取目前只预留了配置项，`KNOWLEDGE_BASE_MODE=oss` 和 `KNOWLEDGE_OSS_PREFIX` 还没有接上真实下载逻辑。
- 真实文章的匹配效果仍需继续观察，当前三组试跑只能证明链路、门禁和渲染可用。
- 后续需要根据真实邮件结果继续微调匹配权重、去重策略和 policy_coordinate prompt。
- 近 14 天去重目前依赖运行时历史文件；正式效果取决于生产环境是否持续保留 `data/policy_coordinate_usage_history.jsonl`。
- 不同主题下《求是》权威论述的可召回性不完全均衡，部分样例可能只展示政策原文而不展示《求是》论述。

## 11. 后续如果切换 OSS，需要怎么配置
- 环境变量层面：设置 `KNOWLEDGE_BASE_MODE=oss`、`KNOWLEDGE_OSS_PREFIX=<你的 OSS 目录前缀>`，并继续保留 `OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`。
- 代码层面：当前 `knowledge_base_loader.py` 仍只读取本地 `KNOWLEDGE_BASE_DIR`，切换 OSS 前需要在加载器里补齐 OSS 下载/缓存逻辑，再让各个 `load_*()` 走统一读取入口。
- 生产部署层面：如果还希望去重历史也跨实例持久化，建议将 `data/policy_coordinate_usage_history.jsonl` 也一并迁移到 OSS 或其他持久化存储。

## 12. 本地试跑产物位置
- `output/policy_coordinate_trials/` 下保存了 3 组 `daily.json`、`email.html`、`plain_text.txt`、`quality.json` 和 `run.log`。
