# Harness Change Log

## 2026-07-01 - Phase 3B weekly PDF training question binding

Reason:

- Weekly PDF manual review showed the training section was still drifting away from the selected material cards and gold-sentence bank, so readers could not clearly see how this week's material should be migrated into actual answers.
- This phase stabilizes the training-question structure and binds each question to reusable weekly materials or expressions without touching daily mail generation or send routing.

Files changed:

- `weekly_material_curator.py`
- `weekly_typst_export.py`
- `tests/test_weekly_pdf_quality.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Weekly enrichment now normalizes `training_questions` with a stable structure:
  - `question_type`
  - `question`
  - `linked_materials`
  - `linked_expressions`
  - `review_key`
  - `answer_outline`
  - `reference_direction`
- The validator keeps backward compatibility with legacy `practice_questions`, but outputs `training_questions` and mirrors them back into `practice_questions` for older readers.
- Each accepted training question must:
  - include a concrete scene/conflict/task stem
  - link to at least one material or expression
  - contain at least 3 keyword-style outline points
- If there are at least 2 material cards, the weekly training set is expected to bind at least 2 questions directly to those material cards.
- The PDF training section now renders around:
  - 可调用素材
  - 审题关键
  - 作答提示
  - 参考迁移方向
- This phase does not change:
  - daily question generation
  - selection quality gate
  - subscriber segmentation
  - weekly send routing
  - OSS delivery logic

## 2026-06-30 - Phase 3A weekly PDF material card structure stabilization

Reason:

- Weekly PDF manual review showed material cards were still structurally inconsistent: some cards had narrow applicability, some only exposed source fields without clear usage, and lite preview could surface a material title without a stable full-card structure behind it.
- This phase stabilizes the reusable material-card schema without changing daily mail generation, weekly send routing, or selection gate behavior.

Files changed:

- `weekly_material_curator.py`
- `weekly_typst_export.py`
- `tests/test_weekly_pdf_quality.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- `material_cards` are normalized toward a stable full-card shape with required fields such as:
  - `title`
  - `source_article`
  - `source_date`
  - `material_type`
  - `usable_themes`
  - `suitable_question_types`
  - `material_summary`
  - `usage_examples`
  - `usage_boundary`
- Each accepted card must provide at least 2 reusable themes and at least 2 usage examples.
- Placeholder copy such as `鏆傛棤` / `鏉愭枡涓嶈冻` / `鍙睍绀篳 / `TODO` / `debug` / `fallback` is filtered from user-visible material-card content.
- Weekly preview material fragments continue to derive from the full material-card list, so preview titles correspond to a real full-card source.
- This phase does not change:
  - daily question generation
  - weekly send logic
  - subscriber segmentation
  - selection quality gate

## 2026-06-30 - Phase 2 selection metadata false P0 fix

Reason:

- Recent candidate runs were blocked by `weak_featured_selection` even when the actual featured article and `final_selection.featured` were valid.
- The root cause was missing `_llm_two_stage.selection.featured` metadata such as empty title/url or `total_score=0`, which was being treated the same as a truly low-scoring featured selection.

Files changed:

- `quality_gate.py`
- `tests/test_selection_quality.py`
- `tests/test_quality_card_final_state.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- `weak_featured_selection` remains as a true P0 only for real low-score featured selections with intact metadata.
- If selection metadata is missing but `final_selection` or `featured_article` still resolves to a valid featured article, the issue is downgraded to `selection_metadata_missing` review instead of a blocking P0.
- If no valid featured article can be resolved at all, `missing_final_selection` remains blocking.
- Quality card copy now reports metadata-missing fallback explicitly instead of claiming `涓荤嚎鏂囩珷閫夐鍒嗚繃浣庯細0`.

## 2026-06-30 - Daily question stability fixes for PR #58

Reason:

- Recent review showed `daily_question` still had unstable type-versus-wording behavior, material-dependent prompts, over-expanded breaking hints, and mobile-unfriendly long answer rendering.
- This patch keeps the existing gate and selection structure, but stabilizes the daily-question module itself so the same issues stop recurring in generation and rendering.

Files changed:

- `question_quality.py`
- `llm_client.py`
- `email_renderer.py`
- `tests/test_daily_question_multi_candidate.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Stabilized `daily_question` question-type and question-wording consistency.
- Cleans material-dependent phrasing such as `鏍规嵁璧勬枡` / `缁欏畾璧勬枡` from standalone prompts.
- Keeps `answer_framework` as a skeleton instead of echoing `candidate_answer`.
- Compresses over-framework-like `breaking_hint` into a single route sentence.
- Splits long `candidate_answer` content into multiple paragraphs in rendered plain text / HTML.

## 2026-06-29 - Harness Phase 5 lightweight candidate selection and token review

Reason:

- The project already tracks LLM traces and harness metrics, but high-risk modules such as `daily_question` and weekly PDF material selection still rely on single-pass generation with limited cost visibility.
- This stage adds lightweight multi-candidate selection only where quality gains are most likely, while keeping the rest of the generation and sending flow unchanged.
- Because this can change formal generation output and token spend, the new behavior is default-off and intended for controlled rollout.

Files changed:

- `config.py`
- `token_economics.py`
- `llm_client.py`
- `main.py`
- `candidate_store.py`
- `harness_metrics.py`
- `weekly_material_curator.py`
- `scripts/weekly_quality_review.py`
- `tests/test_token_economics.py`
- `tests/test_daily_question_multi_candidate.py`
- `tests/test_weekly_material_curator_quality.py`
- `tests/test_weekly_quality_review_reflections.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Added lightweight daily-question multi-candidate selection:
  - generate 2 candidate directions on top of the original result
  - score them with existing question quality checks plus overlap/style heuristics
  - keep fallback to the original single-candidate result if selection fails
- Added weekly material mode candidate selection metadata so each source article can prefer:
  - `case`
  - `mechanism`
  - `expression`
- Added `token_economics.py` and trace summarization for estimated prompt/response tokens by stage.
- Extended harness metrics and weekly review with token/cost visibility:
  - `llm_call_count`
  - `estimated_total_tokens`
  - `selection_tokens`
  - `writing_tokens`
  - `rewrite_tokens`
  - `policy_rerank_tokens`
  - `lite_cta_tokens`
  - `fallback_count`
- Added `Token / Cost Review` to weekly harness review output.
- New environment toggles:
  - `DAILY_QUESTION_MULTI_CANDIDATE_ENABLED`
  - `WEEKLY_MATERIAL_MULTI_CANDIDATE_ENABLED`
- Both toggles are now default-off and must be explicitly enabled by environment variable for production rollout.
- This stage does not change:
  - morning send behavior
  - subscriber plan logic
  - unsubscribe logic
  - referral logic

## 2026-06-29 - Harness Phase 4 regression case runner

Reason:

- `knowledge/quality_issues.jsonl`銆乣good_examples`銆乣bad_examples` already capture historical quality learnings, but they were not yet executable as lightweight regression cases.
- This stage adds a small runnable regression layer so recurring issues can be checked automatically without changing formal generation or sending flow.

Files changed:

- `knowledge/README.md`
- `knowledge/regression_cases/**`
- `scripts/run_regression_cases.py`
- `scripts/weekly_quality_review.py`
- `tests/test_run_regression_cases.py`
- `tests/test_quality_reflections.py`
- `tests/test_weekly_quality_review_reflections.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Added 7 minimal historical regression case categories:
  - `half_sentence`
  - `label_leak`
  - `policy_weak_match`
  - `lite_cta_salesy`
  - `weekly_pdf_path_error`
  - `internal_trace_leak`
  - `daily_question_mismatch`
- Added `scripts/run_regression_cases.py` to traverse `knowledge/regression_cases/`, call existing quality checkers, and write `output/latest_regression_cases.json`.
- `weekly_quality_review.py` now reports regression-case totals, new cases this week, and the latest run pass/fail summary when `latest_regression_cases.json` is available.
- `quality_reflections` remains reflection-only in this stage; new reflections still default to `regression_case=false` until a sample is deliberately promoted into `knowledge/regression_cases/`.
- This phase does not change formal daily generation, rendering, sending, or paid/free/try subscriber behavior.

## 2026-06-27 - Unify daily question answer framework limit to 45 chars

Reason:

- `daily_question.answer_framework` had drifted across prompt sources: some generation prompts still used `35` while the runtime rules, Skill docs, and quality checks were already aligned to `45`.
- This inconsistency increased the risk of generation-side under-specification and made rule audits noisy.

Files changed:

- `prompt_templates.py`
- `llm_client.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- All current generation-side instructions for `daily_question.answer_framework` now use `45` as the per-item upper bound.
- The limit is again aligned across:
  - generation prompts
  - runtime prompt rules
  - Skill/docs
  - quality checks
- This change only unifies rule wording; it does not change rendering logic, send logic, or question quality gate behavior.

## 2026-06-19 - Clarify quality card gate vs residual risk counts

Reason:

- The admin quality card previously displayed `P0/P1/P2` by reusing severity-to-priority mapping, which made ordinary `severity=high` review issues look like blocking P0s even when `quality_gate.p0_count` was 0.
- Recent truncation regressions also needed a stricter distinction between "high risk" and "actually still visible in the final rendered email".

Files changed:

- `admin_report.py`
- `quality_issue_schema.py`
- `main.py`
- `content_quality_reviewer.py`
- `takeaway_quality.py`
- `expression_quality.py`
- `tests/test_quality_card_final_state.py`
- `tests/test_quality_gate_content_quality_sync.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Quality cards now show `闂ㄧP0` from `quality_gate.p0_count` and separate `鍓╀綑椋庨櫓` high/medium/low counts from final issues instead of the old `P0/P1/P2` summary.
- Remaining-risk lines only say `褰卞搷鍙戦€乣 when the issue code is actually present in `quality_gate.p0_issues`; other high issues are labeled `楂橀闄╋紝寤鸿淇`.
- Visible truncation issues such as `text_truncation`, `truncated_takeaway`, and `expression_truncated` are escalated into gate P0 only when their `bad_text` still appears in the final rendered `plain_text` or `html_body`.
- Truncation findings now preserve `field` and `bad_text` metadata more consistently so existing rewrite/repair stages can target them before the final gate decision.

## 2026-06-12 - Policy coordinate stage 4 reranker

Reason:

- Stage 3 already routes authoritative expressions ahead of policy statements, but final selection still depends only on rule scores and can overfit broad thematic overlap.
- This stage adds a lightweight LLM reranker so the module only displays when a candidate really explains the article's core contradiction, while keeping the retrieval layer rule-based.

Files changed:

- `main.py`
- `llm_client.py`
- `policy_coordinate_reranker.py`
- `policy_coordinate_semantic_fit.py`
- `email_renderer.py`
- `tests/test_policy_coordinate_diagnostics.py`
- `tests/test_policy_coordinate_reranker.py`
- `tests/test_policy_coordinate_semantic_fit.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Added `policy_coordinate_reranker.py` to rerank up to 10 authoritative candidates first, then policy-statement candidates only as fallback.
- Reranker inputs are clipped to article title, compact `policy_profile`, summary text, and compact candidate rows to control token use.
- Display thresholds now follow stage 4 routing: authoritative rerank must reach 70, policy-statement rerank must reach 75, otherwise the module stays hidden.
- Logs now include `rerank_input_summary`, `authoritative_rerank_result`, `policy_statement_rerank_result`, `final_display_type`, and `hidden_reason`.
- Added a small semantic-fit override so a specific reranked authoritative explanation is not rejected only because old keyword lists miss it.

## 2026-06-11 - Add policy coordinate diagnostics only

Reason:

- Policy coordinate matching already computes candidate rankings and hide/display reasons, but the run log does not expose enough context to diagnose why a module was shown or suppressed.
- This round is intentionally observability-only: it should help inspect query inputs, top candidates, backend status, semantic-fit status, and disabled reasons without changing match scores, thresholds, or render behavior.

Files:

- `main.py`
- `policy_coordinate_matcher.py`
- `tests/test_policy_coordinate_diagnostics.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added a structured `policy coordinate diagnostics` log event during policy-coordinate build.
- Logs now include compact input previews, topic anchors, matcher top candidates, selected evidence ids, scores, backend status, semantic-fit status, and disabled reason.
- Expanded matcher debug output so `framework_top` also exposes up to 5 items for diagnostics.
- Existing matching results, thresholds, display logic, and final rendering behavior remain unchanged.

## 2026-06-11 - Policy coordinate stage 2 profile input

Reason:

- The current `policy_coordinate` matcher mainly consumes brief summary fields and can miss policy semantics that only appear in the full article body.
- This stage adds full-text-aware `policy_profile` extraction and logging, but keeps the existing policy-coordinate scoring thresholds and display decisions unchanged.

Files changed:

- `policy_profile_builder.py`
- `main.py`
- `tests/test_policy_profile_builder.py`
- `CHANGELOG_HARNESS.md`

Latest behavior:

- Added `policy_profile_builder.py` to build `core_problem`, `governance_logic`, `value_orientation`, `negative_behaviors`, `positive_behaviors`, `fine_anchors`, and `retrieval_queries` from article title, source, and full text with brief fallback.
- `build_policy_coordinate(...)` now accepts `source_articles`, prefers full article text from the original crawl payload, and falls back to `featured_article` text-like fields or brief-composed text when full text is unavailable.
- Policy-coordinate matching now receives the new policy-profile summaries, anchors, and retrieval queries as extra input, but the existing matching thresholds and display/hide logic are unchanged.
- Runtime logs now include a `policy coordinate profile` event with `article_title`, `article_source`, `article_text_source`, `article_text_length`, truncated text preview, full `policy_profile`, and generated `retrieval_queries`.

Follow-ups:

1. This stage only improves input quality and observability; it does not yet make `policy_profile` a hard decision layer for final display.
2. If full-text input later introduces noisy recall, tune query composition and keyword deduplication before changing backend display thresholds.
## 2026-06-27 - Harness Phase 3 rule registry and field impact map

### Changed

- Added `content_harness/rule_registry.md` to separate L1 red lines, L2 module rules, and L3 memory/regression rules.
- Added `content_harness/field_impact_map.json` for high-risk fields, including render targets, quality modules, must-validate checks, and risk level.
- Added `scripts/audit_prompt_rules.py` to audit prompt rule drift across `prompt_templates.py`, `llm_client.py`, `content_harness/*.md`, and `CHANGELOG_HARNESS.md`.
- Added `tests/test_audit_prompt_rules.py` to cover field limit conflicts, duplicate runtime rules, archived rule leakage, and field impact map coverage.
- Updated `content_harness/00_index.md` with a Stage 3 governance entry and the recommended audit command.

### Notes

- This stage only adds rule governance artifacts and auditing; it does not change generation logic or sending logic.
- The audit script now surfaces an existing `answer_framework` limit drift where some sources still say `35` and others say `45`. That normalization should be handled in a later focused PR.

## 2026-06-02 - Add reading guide review checks

Reason:

- The first-stage reading guide module is already generated and rendered in the email body.
- The system now needs a lightweight review layer that can flag empty, generic, catalog-style, or hype-heavy guides for later prompt tuning without changing delivery behavior.

Files:

- `reading_guide_quality.py`
- `main.py`
- `tests/test_reading_guide_quality.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `reading_guide_quality.py` with `evaluate_reading_guide_quality(brief)`.
- Checks now cover missing guide payloads, empty fields, invalid anchor modules, generic wording, module-catalog intros, hype language, overlong fields, and excessive repetition with the email subject.
- `reading_guide` quality is now aggregated into the final quality map for review and logging consistency.
- `build_quality_gate(...)` includes `reading_guide` in the module map, but no reading-guide issue code is promoted into `p0_codes`.
- This round adds monitoring only; it does not block sending or change send logic.

Follow-up:

- `reading_guide` quality is review-only and should be improved through prompt and fallback refinement when recurring issues appear.
- If a later round needs stronger enforcement, it should be introduced deliberately instead of silently escalating these review signals.

## 2026-06-02 - Add dynamic reading guide module

Reason:

- The email subject has already been upgraded to an exam-benefit headline to improve open rate.
- After open, the first screen still needs a lightweight, content-specific guide that tells the reader what is most worth learning today, where to focus, and what they can carry into exam answers.

Files:

- `prompt_templates.py`
- `content_harness/runtime_prompt_rules.md`
- `brief_schema.py`
- `email_renderer.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `reading_guide` to the generation schema with `core_value`, `focus_path`, `learning_outcome`, and `anchor_module`.
- Added runtime prompt rules that define `reading_guide` as a dynamic value guide instead of a static module introduction.
- `ensure_brief_schema(...)` now fills `reading_guide` deterministically when the model omits it or leaves fields empty.
- The renderer now shows `馃搶 浠婂ぉ杩欏皝鎬庝箞鐢╜ below the top theme card and above `浠婃棩 3 浠朵簨` in both HTML and plain text.
- The module shows only the three reader-facing lines and does not expose `anchor_module`.
- This round adds generation, fallback, and rendering only; it does not add P0 blocking or change send logic.

Follow-up:

- `reading_guide` is a front-of-email guidance layer, not a new quality gate.
- If later rounds want to score or review this module, that should be added separately without changing the current send path.

## 2026-06-02 - Add subject quality review checks

Reason:

- The previous two stages already updated prompt guidance and added deterministic subject fallback normalization.
- The system still needs a lightweight way to record whether `email_subject` meets the exam-benefit title standard, so later open-rate tuning and manual review have structured evidence.

Files:

- `subject_quality.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `subject_quality.py` with `evaluate_subject_quality(brief)`.
- Checks now cover duplicate subject prefix, hype words, generic subjects, missing exam-value markers, and overlong subject lines.
- `subject_quality` is aggregated into `quality.final.subject_quality` during normal quality evaluation.
- `build_quality_gate(...)` now includes `subject_quality` in the module map for reporting consistency.
- No `subject_quality` code is added to `p0_codes`; title issues stay as review-only signals and do not block sending.
- Title problems are still expected to be fixed first by `subject_line.py`; remaining issues are recorded for review and later optimization.

Follow-up:

- Subject quality is for monitoring and review, not for delivery blocking.
- The current patch keeps `scripts/validate_daily_brief.py` unchanged to avoid expanding this round into a broader encoding cleanup.

## 2026-06-02 - Add deterministic email subject fallback

Reason:

- The previous stage updated prompt guidance so the model prefers exam-benefit subject lines.
- The generation side can still produce generic, overlong, prefixed, or hype-heavy subjects, so the schema normalization stage now adds a lightweight deterministic fallback.

Files:

- `subject_line.py`
- `brief_schema.py`
- `CHANGELOG_HARNESS.md`

Current behavior:

- Added `subject_line.py` as a dedicated email-subject normalization helper.
- The model can still generate `brief.email_subject` freely, but the program now strips prefixes such as `銆愬叕鑰冩櫒璇汇€慲, `鍏€冩櫒璇籤, and `Re:`.
- Generic subjects, hype-word subjects, empty subjects, and subjects longer than 26 characters are replaced with a stable exam-benefit fallback built from existing brief fields.
- Fallback generation prefers `daily_question.question_type`, `upper_exam_points`, `article_framework_map.exam_tags`, `featured_article.theme`, and related existing fields.
- `brief.email_subject` continues to stay prefix-free; the sending layer still adds the unified `銆愬叕鑰冩櫒璇汇€慲 prefix.

Follow-up:

- This is a normalization fallback only; it is not a new `subject_quality.py` module and does not change the sending pipeline.
- Future title tuning should prefer adjusting `subject_line.py` rules and fallback wording instead of moving prefix logic into generation or delivery.

鏈枃浠惰褰曞叕鑰冩櫒璇婚偖浠堕」鐩殑閲嶈瑙勫垯銆丳rompt銆佽川妫€銆佹覆鏌撳拰閮ㄧ讲鏀瑰姩銆備互鍚?AI Coding / Codex / Cursor / OpenClaw 鎺ユ墜椤圭洰鍓嶏紝蹇呴』鍏堣鏈枃浠讹紝鍐嶈 `AGENTS.md` 鍜?`content_harness/00_index.md`銆?

## 浣跨敤瑙勫垯

1. 姣忔淇敼瑙勫垯銆丳rompt銆佽川妫€銆佹覆鏌撱€佸彂閫侀摼璺€佸綊妗ｉ摼璺垨閮ㄧ讲閰嶇疆鍚庯紝閮借鍦ㄦ湰鏂囦欢鏂板涓€鏉¤褰曘€?
2. 璁板綍瑕佸啓娓呮锛氭敼鍔ㄦ棩鏈熴€佹敼鍔ㄨ寖鍥淬€佹秹鍙婃枃浠躲€佷负浠€涔堟敼銆佹渶鏂扮増琛屼负鏄粈涔堛€佸悗缁娉ㄦ剰浠€涔堛€?
3. 鏈枃浠跺彧璁板綍鈥滈」鐩涓哄彉鍖栤€濆拰鈥滃鏄撳奖鍝嶅悗缁垽鏂殑鍐崇瓥鈥濓紝涓嶈褰曟櫘閫氶敊鍒瓧鍜屾棤琛屼负褰卞搷鐨勫皬鎺掔増銆?
4. 鏂板璁板綍鏀惧湪鈥滄渶鏂版敼鍔ㄢ€濅笅闈紝淇濇寔鍊掑簭銆?
5. 濡傛灉鏌愭鏀瑰姩鍚屾椂褰卞搷 Prompt 鍜岃川妫€锛屽繀椤诲悓鏃惰鏄庣敓鎴愪晶鍜屾嫤鎴晶鍒嗗埆鏀逛簡浠€涔堛€?

## 褰撳墠鏈€鏂扮増鐘舵€?

### 椤圭洰鎺ユ墜闃呰椤哄簭

褰撳墠绾﹀畾锛?

1. 鍏堣 `CHANGELOG_HARNESS.md`锛岀‘璁ゆ渶杩戞敼浜嗕粈涔堛€佸綋鍓嶆渶鏂扮増琛屼负鏄粈涔堛€佽繕鏈夊摢浜涘緟琛ラ」銆?
2. 鍐嶈 `AGENTS.md`锛岀‘璁ら」鐩繍琛岃竟鐣屻€佺姝㈣涓恒€佹牳蹇冩枃浠跺湴鍥惧拰楠岃瘉瑕佹眰銆?
3. 鏈€鍚庢寜淇敼绫诲瀷璇诲彇 `content_harness/00_index.md` 鎸囧悜鐨勮鍒欍€丼kill銆佽川妫€鍜屽伐浣滄祦鏂囨。銆?

### 浠婃棩涓€棰樻ā鍧楄竟鐣?

褰撳墠绾﹀畾锛?

- 瀹￠鍏抽敭锛氱湅娓呴銆傚彧鎷嗛锛岃鏄庨鐩湡姝ｉ棶浠€涔堛€佹秹鍙婂摢浜涘璞°€佹牳蹇冪煕鐩炬槸浠€涔堛€佸摢浜涗綔绛旀柟鍚戜笉鑳芥紡銆備笉寰楀啓瀹屾暣瀵圭瓥璺嚎銆?
- 浣滅瓟涓荤嚎锛氭墦寮€棰樸€傚簳灞傚瓧娈典粛浣跨敤 `breaking_hint`锛屽睍绀鸿涔夋槸鈥滀綔绛斾富绾库€濄€傚彧缁欎竴鍙ユ€昏矾绾匡紝渚嬪鈥滃厛閲婄枒绋抽鏈燂紝鍐嶆函婧愭煡闂锛屾渶鍚庡缓鏈哄埗绠￠暱杩溾€濄€備笉寰楀垪瀹屾暣鍒嗙偣銆?
- 浣滅瓟妗嗘灦锛氬啓鎴愰銆備娇鐢?`answer_framework` / `answer_frame`锛屽彧鍐?3-4 鏉℃寮忓垎鐐归鏋讹紝姣忕偣涓嶈秴杩?45 瀛楋紝鏍煎紡涓衡€滃姩璇嶇煭璇細绠€鐭В閲娿€傗€濄€?
- 鑰冪敓鐗堝弬鑰冪瓟妗堬細瀹屾暣灞曞紑锛岃礋璐ｆ妸浣滅瓟妗嗘灦杞垚鑷劧銆佺ǔ閲嶃€佸彲澶嶈堪鐨勮€冨満琛ㄨ揪銆?

涓€鍙ヨ瘽瑙勫垯锛?

> 瀹￠鍏抽敭鐪嬫竻棰橈紝浣滅瓟涓荤嚎鎵撳紑棰橈紝浣滅瓟妗嗘灦鍐欐垚棰樸€?

## 鏈€鏂版敼鍔?

### 2026-06-02锝滄柊澧炶€冭瘯鏀剁泭鍨嬮偖浠舵爣棰樿鍒?

**鏀瑰姩鍘熷洜**

褰撳墠閭欢鏍囬鍋忊€滄枃绔犱富棰樺瀷鈥濓紝鐢ㄦ埛鍦ㄦ敹浠剁閲岀湅涓嶅嚭浠婂ぉ鑳藉鍒颁粈涔堛€佺粌浠€涔堛€佸甫璧颁粈涔堛€備负鎻愬崌鎵撳紑鍓嶇殑浠峰€兼壙璇烘劅锛屾湰娆℃妸鏍囬瑙勫垯璋冩暣涓衡€滆€冭瘯鏀剁泭鍨嬫爣棰樷€濄€?

**宸叉敼鏂囦欢**

- `prompt_templates.py`
- `content_harness/runtime_prompt_rules.md`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `brief.email_subject` 鏀逛负鈥滀笉甯︺€愬叕鑰冩櫒璇汇€戝墠缂€鐨勮€冭瘯鏀剁泭鍨嬫爣棰樷€濓紝鍓嶇紑浠嶇敱鍙戦€佸眰缁熶竴娣诲姞銆?
- 鏍囬蹇呴』浣撶幇甯歌€冩劅銆佽€冭瘯鏀剁泭鍜屽叿浣撴敹鑾凤紝涓嶈兘鍙啓鏂囩珷涓婚銆?
- 杩愯瑙勫垯涓柊澧?`Email Subject` 灏忚妭锛屾槑纭爣棰樺簲浼樺厛浣撶幇楂橀鑰冪偣銆佸父鑰冨満鏅€佺敵璁虹礌鏉愩€侀潰璇曞父瑙侀銆佹満鍏冲疄鍔￠銆佷粖鏃ュ甫璧般€佺瓟棰樿搴︺€佹斂绛栧潗鏍囩瓑鎵撳紑浠峰€笺€?
- 鏍囬蹇呴』甯﹀叿浣撳璞℃垨鍏蜂綋鑰冪偣锛岀姝娇鐢ㄢ€滃繀鑰冦€佹娂棰樸€佷笂宀搞€佷笉鐪嬪悗鎮斻€佷竴瀹氫細鑰冣€濈瓑澶稿紶钀ラ攢璇嶃€?
- 鏈鍙敼 Prompt 鍜岃鍒欐枃妗ｏ紝涓嶆敼鍙戦€侀€昏緫銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 濡傛灉鍚庣画闇€瑕佸鏍囬鍋氳嚜鍔ㄨ川妫€锛屽簲鍙﹁捣浠诲姟锛屼笉瑕佹妸杩欐鏈€灏?patch 鎵╁睍鎴愭柊鐨勬爣棰樻ā鍧椼€?
2. 鍙戦€佸眰浠嶈礋璐ｇ粺涓€琛?`銆愬叕鑰冩櫒璇汇€慲 鍓嶇紑锛宐rief 鐢熸垚渚т笉瑕侀噸澶嶆坊鍔犮€?

### 2026-05-31锝滄柊澧?policy_coordinate 璐ㄦ涓庨檷绾?

**鏀瑰姩鍘熷洜**

鈥滀粖鏃ユ斂绛栧潗鏍団€濆凡杩涘叆 JSON 鍜岄偖浠舵覆鏌擄紝闇€瑕佸湪鏈€缁堣川閲忓妫€涓牎楠屾斂绛栧師鏂囥€佹潵婧愩€佽浆璇戙€佹枃绔犺惤鐐广€佽€冨満杩佺Щ鍜屻€婃眰鏄€嬫潈濞佽杩帮紝閬垮厤閿欒鏀跨瓥寮曠敤鎴栫┖娉涜〃杈剧洿鎺ュ睍绀恒€?

**宸叉敼鏂囦欢**

- `policy_coordinate_quality.py`
- `main.py`
- `admin_report.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増鏈涓?*

- 鏂板 `evaluate_policy_coordinate_quality(...)`锛屾鏌ユ斂绛栧師鏂囥€佹斂绛栨潵婧愩€佹斂绛栬浆璇戙€佹枃绔犺惤鐐广€佽€冨満杩佺Щ銆佸尮閰?ID銆佸崐鎴彞銆佺┖娉涜〃杈俱€佽法妯″潡閲嶅鍜屾覆鏌撹鏀俱€?
- 鏈€缁?`evaluate_all_quality(...)` 宸叉帴鍏?`policy_coordinate` 璐ㄦ锛宍quality_payload["final"]` 鍜岃川閲忓崱浼氬睍绀烘渶缁堝墿浣欓棶棰樸€?
- 娓叉煋鍓嶄細纭繚 `brief["policy_coordinate"]` 宸茬敓鎴愶紝淇姝ゅ墠鈥滃瓧娈靛啓鍏ユ櫄浜庢覆鏌撯€濈殑鏃跺簭闂銆?
- 濡傛灉銆婃眰鏄€嬫潈濞佽杩颁笉鍚堟牸锛屼細鍒犻櫎鏉冨▉璁鸿堪锛屼粎淇濈暀鏀跨瓥鍘熸枃銆佹枃绔犺惤鐐广€佽€冨満杩佺Щ銆?
- 濡傛灉鏀跨瓥鍘熸枃鎴栨潵婧愪笉鍚堟牸锛屼細灏濊瘯閲嶆柊鍖归厤锛涗粛涓嶅悎鏍煎垯闅愯棌鏀跨瓥鍧愭爣妯″潡锛屽苟鍦ㄨ川閲忕粨鏋滀腑璁板綍闄嶇骇鍘熷洜銆?
- `policy_coordinate` 璐ㄦ涓嶈繘鍏?P0 闃绘柇鐮侊紝涓嶄細鍥犱负璇ユā鍧楀奖鍝嶅叾浠栨ā鍧楁甯哥敓鎴愭垨鍙戦€併€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 鍚庣画濡傞渶鎶婃斂绛栧潗鏍囬棶棰樺崌绾т负鍙戦€侀樆鏂紝搴斿崟鐙瘎浼拌浼ょ巼鍚庡啀鍔犲叆 P0 code銆?
2. 褰撳墠 `quality_card` 灞曠ず鐨勬槸淇/闄嶇骇鍚庣殑鏈€缁堝墿浣欓棶棰橈紝涓嶅睍绀哄凡鍒犻櫎鐨勬潈濞佽杩伴棶棰樸€?

### 2026-05-31锝滄覆鏌撲粖鏃ユ斂绛栧潗鏍囨ā鍧?

**鏀瑰姩鍘熷洜**

鍦ㄤ换鍔?4 宸插啓鍏?`brief["policy_coordinate"]` 鐨勫熀纭€涓婏紝鎶娾€滀粖鏃ユ斂绛栧潗鏍団€濆睍绀哄埌閭欢姝ｆ枃锛屼綅缃斁鍦ㄢ€滀粖鏃ョ簿璇烩€濅箣鍚庛€佲€滀粖鏃ヤ竴棰樷€濅箣鍓嶃€?

**宸叉敼鏂囦欢**

- `email_renderer.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増鏈涓?*

- HTML 鍜?plain_text 鍚屾娓叉煋 `policy_coordinate`銆?
- `policy_coordinate` 缂哄皯 `policy_source` 鎴?`policy_quote` 鏃讹紝鏁翠釜妯″潡涓嶅睍绀恒€?
- 鏉冨▉璁鸿堪鍙湁鍦?`authoritative_quote` 鍜?`authoritative_source` 鍚屾椂瀛樺湪鏃舵墠灞曠ず锛屼笉浼氭畫鐣欑┖鏍囬銆?
- 鏀跨瓥鍘熸枃琛屽彧浣跨敤鏀跨瓥璇簱瀛楁锛歚policy_source` + `policy_quote`銆?
- 銆婃眰鏄€嬭杩板彧灞曠ず鍦ㄢ€滄潈濞佽杩扳€濊锛屼笉浼氬啓鎴愨€滄斂绛栧師鏂団€濄€?
- 鏈涓嶄慨鏀瑰彂閫侀€昏緫銆佷笉淇敼 `quality_gate`锛屼篃涓嶆妸鈥滀粖鏃ユ斂绛栧潗鏍団€濇爣棰樺啓鍏?brief 瀛楁銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 鍚庣画鍙熀浜庡疄闄呴偖浠舵牱寮忓井璋冩斂绛栧潗鏍囧崱鐗囬厤鑹插拰闂磋窛銆?
2. 濡傝鎶婃斂绛栧潗鏍囩撼鍏ヨ川閲忛棬绂侊紝搴斿彟璧蜂换鍔″崟鐙璁℃鏌ラ」銆?

### 2026-05-31锝渄aily JSON 鍐欏叆 policy_coordinate 瀛楁

**鏀瑰姩鍘熷洜**

鍦ㄤ笉鏀归偖浠?HTML銆佸彂閫侀€昏緫鍜岃川閲忛棬绂佺殑鍓嶆彁涓嬶紝鎶婃斂绛栧潗鏍囧尮閰嶇粨鏋滃啓鍏ユ瘡鏃?brief JSON锛屼负鍚庣画娓叉煋鈥滀粖鏃ユ斂绛栧潗鏍団€濇ā鍧楀仛鏁版嵁鍑嗗銆?

**宸叉敼鏂囦欢**

- `main.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増鏈涓?*

- 鍦ㄦ渶缁堜繚瀛?`latest_brief.json` 鍜屽€欓€?payload 鍓嶏紝涓?`brief` 鏂板 `policy_coordinate` 瀛楁銆?
- `policy_quote` 鍙潵鑷斂绛栬搴擄紝浼樺厛浣跨敤 `short_quote`锛屼笉鍚堥€傛椂浣跨敤 `policy_quote`锛屼笖鎺у埗鍦?90 瀛椾互鍐呫€?
- `policy_source` 浣跨敤鏀跨瓥鏉＄洰鐨?`source_title`锛宍policy_source_type` 浣跨敤 `source_type`銆?
- `authoritative_quote` 鍙潵鑷€婃眰鏄€嬫潈濞佽杩板簱锛屽彲涓虹┖锛涘瓨鍦ㄦ椂蹇呴』鍚屾椂鐢熸垚 `authoritative_source`銆?
- `authoritative_source` 浼樺厛浣跨敤 `speech_date + speech_event`锛屽惁鍒欏洖閫€鍒般€婃眰鏄€嬫湡鍒婃枃绔犳爣棰樸€?
- `article_connection` 鍜?`exam_transfer` 鐢辨渶缁堢簿閫夋枃绔犮€佹斂绛栬В閲婂拰鑰冭瘯鍦烘櫙鐢熸垚锛屽彧鍐欏叆 JSON锛屼笉杩涘叆姝ｆ枃娓叉煋銆?
- `brief` 涓笉鍐欏叆鈥滀粖鏃ユ斂绛栧潗鏍団€濇爣棰橈紝淇濇寔瀛楁鍙瓨缁撴瀯鍖栨鏂囨暟鎹€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 涓嬩竴姝ヨ嫢鎺ュ叆 HTML renderer锛屽簲鍙鍙?`brief["policy_coordinate"]`锛屼笉瑕侀噸鏂板湪娓叉煋灞傚仛鍖归厤銆?
2. 娓叉煋鍓嶅缓璁厛浜哄伐妫€鏌ュ嚑澶?`latest_brief.json` 涓?`policy_coordinate` 鐨勫尮閰嶈川閲忋€?
3. 鏈樁娈垫病鏈変慨鏀?`quality_gate`锛屽洜姝ゆ斂绛栧潗鏍囧瓧娈垫殏涓嶅弬涓庢嫤鎴€?

### 2026-05-31锝滄斂绛栧潗鏍囧尮閰嶅櫒棰勬帴鍏?

**鏀瑰姩鍘熷洜**

涓哄悗缁妸鈥滀粖鏃ユ斂绛栧潗鏍団€濇帴鍏ラ偖浠舵鏂囷紝鍏堟柊澧炵嫭绔嬪尮閰嶅櫒锛屼粠鏀跨瓥鍘熸枃搴撳拰銆婃眰鏄€嬩笓棰樼煡璇嗗簱涓彫鍥炲綋澶╂枃绔犲彲鐢ㄧ殑鏀跨瓥鍘熸枃銆佹潈濞佽杩般€佺浉鍏崇墖娈靛拰涓撻妗嗘灦銆傛湰闃舵鍙繑鍥炲€欓€夊璞★紝涓嶅啓鍏?daily JSON銆佷笉淇敼 HTML銆佷笉淇敼鍙戦€侀€昏緫銆?

**宸叉敼鏂囦欢**

- `policy_coordinate_matcher.py`
- `scripts/check_policy_coordinate_matcher.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増鏈涓?*

- 鏂板 `match_policy_coordinate_candidates(...)`锛岃緭鍏ユ爣棰樸€佹憳瑕?姝ｆ枃銆佷富棰樸€佸叧閿瘝鍜岃€冭瘯鍦烘櫙锛岃緭鍑?`matched_policy_coordinate_candidates`銆?
- 鏀跨瓥鍘熸枃浼樺厛鍖归厤 `policy_statements_core.jsonl`锛涙牳蹇冨簱鏃犺涔夊懡涓椂锛屽啀浠庢墿灞曞簱涓瓫閫?`quote_status=clean`銆乣display_ready=true`銆乣theme_confidence=high`銆乣usage_tier` 闈?`disabled/background` 鐨勬潯鐩€?
- 銆婃眰鏄€嬫潈濞佽杩颁紭鍏堝尮閰?`authoritative_quotes_core.jsonl`锛屽€欓€夊簱鍙湪鏍稿績搴撴棤缁撴灉鏃跺厹搴曘€?
- `article_chunks.jsonl` 鏈€澶氬彫鍥?3 涓墖娈碉紝`topic_frameworks.jsonl` 鏈€澶氳繑鍥?1 涓鏋躲€?
- 鍖归厤鎵撳垎缁煎悎涓婚銆佷簩绾т富棰樸€佸叧閿瘝銆佽€冭瘯鍦烘櫙銆佸睍绀轰紭鍏堢骇銆乣usage_tier` 鍜?`freshness`锛沗historical_framework` 闄嶆潈锛宍disabled` 涓嶄娇鐢紝`background` 涓嶇洿鎺ュ睍绀恒€?
- 褰撳墠涓嶆帴鍏ョ敓鎴愰摼璺紝鑴氭湰 `scripts/check_policy_coordinate_matcher.py` 浠呯敤浜庢湰鍦伴獙璇併€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 涓嬩竴姝ユ帴鍏ラ偖浠剁敓鎴愬墠锛屽簲鍏堢‘璁?`best_policy` 鐨勫睍绀鸿川閲忓拰 `debug_scores` 鏄惁绗﹀悎浜哄伐棰勬湡銆?
2. renderer 鎺ュ叆搴斿崟鐙彁浜わ紝閬垮厤鍖归厤閫昏緫鍜?HTML 灞曠ず閫昏緫娣峰湪涓€璧枫€?
3. 濡傛灉鍚庣画鍒囨崲 OSS 璇诲彇锛岄渶瑕佸厛鎵╁睍 `knowledge_base_loader.py`锛屼笉瑕佺洿鎺ュ湪鍖归厤鍣ㄩ噷鍐?OSS 閫昏緫銆?

### 2026-05-31锝滅煡璇嗗簱 JSONL 鍔犺浇鍣ㄩ鎺ュ叆

**鏀瑰姩鍘熷洜**

涓哄悗缁帴鍏モ€滀粖鏃ユ斂绛栧潗鏍団€濆拰銆婃眰鏄€嬩笓棰樼煡璇嗗簱锛屽厛鎻愪緵鐙珛鐨?JSONL 璇诲彇鑳藉姏銆傛湰闃舵鍙柊澧炲姞杞芥ā鍧楀拰妫€鏌ヨ剼鏈紝涓嶆妸鐭ヨ瘑搴撴帴鍏?daily JSON銆侀偖浠剁敓鎴愩€丠TML 娓叉煋銆佸彂閫佹垨璐ㄩ噺闂ㄧ閫昏緫銆?

**宸叉敼鏂囦欢**

- `knowledge_base_loader.py`
- `scripts/check_knowledge_base_loader.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増鏈涓?*

- 鏂板閫氱敤 `load_jsonl(path)`锛屾敮鎸佽鍙?UTF-8/UTF-8 BOM JSONL銆?
- JSONL 鍗曡瑙ｆ瀽澶辫触鏃惰褰曢敊璇苟璺宠繃鍧忚锛屼笉涓柇涓绘祦绋嬨€?
- 鏂囦欢涓嶅瓨鍦ㄦ椂璁板綍 warning 骞惰繑鍥炵┖鍒楄〃銆?
- 鍚屼竴娆¤繍琛屽唴鎸夌粷瀵硅矾寰勭紦瀛樿鍙栫粨鏋滐紝閬垮厤閲嶅璇诲彇澶ф枃浠躲€?
- 鏂板鍔犺浇鍑芥暟锛歚load_policy_core`銆乣load_policy_all`銆乣load_qiushi_article_index`銆乣load_qiushi_chunks`銆乣load_qiushi_quotes_core`銆乣load_qiushi_quotes_candidates`銆乣load_topic_frameworks`銆?
- 褰撳墠涓嶈鍙?`raw_articles/qiushi/` 鍏ㄦ枃鐩綍銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 姝ｅ紡鎺ュ叆閭欢鍐呭鍓嶏紝搴斾紭鍏堜娇鐢?`load_policy_core()` 浣滀负鈥滀粖鏃ユ斂绛栧潗鏍団€濈殑灞曠ず绾ф斂绛栧師鏂囨潵婧愩€?
2. 鎵╁睍鍊欓€夈€佸垏鐗囧拰鏉冨▉寮曠敤鏆傛椂鍙綔涓哄悗缁绱㈣兘鍔涢鐣欙紝涓嶅簲鍦ㄦ湰闃舵鏀瑰彉閭欢姝ｆ枃銆?
3. OSS 妯″紡鍚庣画鍗曠嫭瀹炵幇锛屽綋鍓嶅姞杞藉櫒璇诲彇鏈湴 `KNOWLEDGE_BASE_DIR`銆?

### 2026-05-31锝滅煡璇嗗簱鐩綍涓庨厤缃鎺ュ叆

**鏀瑰姩鍘熷洜**

涓哄悗缁帴鍏モ€滀粖鏃ユ斂绛栧潗鏍団€濆拰銆婃眰鏄€嬩笓棰樼煡璇嗗簱锛屽厛鎶婂凡鏁寸悊濂界殑鐭ヨ瘑搴撴枃浠舵斁鍏ヤ粨搴擄紝骞堕鐣欐湰鍦?OSS 涓ょ璇诲彇妯″紡銆傛湰闃舵鍙仛鐩綍銆侀厤缃拰鎵撳寘璧勪骇鎺ュ叆锛屼笉鏀瑰彉鐢熸垚銆佹覆鏌撱€佸彂閫佸拰璐ㄩ噺闂ㄧ閫昏緫銆?

**宸叉敼鏂囦欢**

- `config.py`
- `.env.example`
- `README.md`
- `scripts/build_fc_package.ps1`
- `content_harness/deployment_rules.md`
- `knowledge_base/policy_corpus/policy_statements_core.jsonl`
- `knowledge_base/policy_corpus/policy_statements.jsonl`
- `knowledge_base/topic_knowledge/`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鏂板鐜鍙橀噺锛歚KNOWLEDGE_BASE_MODE=local`銆乣KNOWLEDGE_BASE_DIR=knowledge_base`銆乣KNOWLEDGE_OSS_PREFIX=`銆?
- `config.Settings` 鏂板鐭ヨ瘑搴撻厤缃拰璺緞灞炴€э細`knowledge_base_path`銆乣policy_corpus_path`銆乣topic_knowledge_path`銆?
- 浠撳簱鏂板 `knowledge_base/policy_corpus/`锛屽寘鍚斂绛栧師鏂囨牳蹇冨睍绀哄簱鍜屾墿灞曞€欓€夊簱銆?
- 浠撳簱鏂板 `knowledge_base/topic_knowledge/`锛屽寘鍚€婃眰鏄€嬩笓棰樼储寮曘€佸垏鐗囥€佹潈濞佸紩鐢ㄣ€佷笓棰樻鏋跺拰 `raw_articles/qiushi/` 鍘熸枃鐩綍銆?
- FC 鎵撳寘鑴氭湰浼氬鍒?`knowledge_base/`锛屽苟妫€鏌ユ牳蹇冩斂绛栧簱鍜屼笓棰樼储寮曟枃浠跺瓨鍦ㄣ€?
- 鏈樁娈典笉璇诲彇鐭ヨ瘑搴撱€佷笉鍐欏叆 daily JSON銆佷笉鏀?Prompt銆佷笉鏀?renderer銆佷笉鏀瑰彂閫侀€昏緫銆佷笉鏀?quality_gate銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 姝ｅ紡鎺ュ叆鈥滀粖鏃ユ斂绛栧潗鏍団€濇椂锛屼紭鍏堣鍙?`knowledge_base/policy_corpus/policy_statements_core.jsonl`銆?
2. 鍒囨崲 OSS 鏃讹紝灏?`KNOWLEDGE_BASE_MODE` 鏀逛负 `oss`锛屽苟璁剧疆 `KNOWLEDGE_OSS_PREFIX` 涓?bucket 鍐呭璞″墠缂€锛汷SS 閴存潈缁х画澶嶇敤鐜版湁 OSS 閰嶇疆銆?
3. 鎺ュ叆鐢熸垚閫昏緫鍓嶏紝搴斿崟鐙鍔犺鍙栧け璐ュ厹搴曪紝閬垮厤鐭ヨ瘑搴撶己澶卞奖鍝嶅€欓€夐偖浠剁敓鎴愩€?

### 2026-05-28锝滈樁娈?2 鎶藉彇缁熶竴璐ㄩ噺璁＄畻 helper

**鏀瑰姩鍘熷洜**

`main.py` 涓澶勫湪 brief 琚慨澶嶆垨閲嶅啓鍚庨噸澶嶆墽琛屸€滄覆鏌撱€佸悇妯″潡璐ㄦ銆乧ontent quality銆乹uality gate 鏋勯€犫€濋€昏緫銆傞噸澶嶄唬鐮佽秺澶氾紝鍚庣画淇瀛楁鍚屾銆丳0 repair銆乸re-send guard 鏃惰秺瀹规槗鍑虹幇鈥滄煇涓€璺緞婕忚窇鏌愪釜璐ㄦ鈥濈殑闂銆?

**宸叉敼鏂囦欢**

- `main.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鏂板 `render_brief_outputs`锛岀粺涓€浠?brief 鐢熸垚绾枃鏈拰 HTML銆?
- 鏂板 `evaluate_all_quality`锛岀粺涓€璁＄畻浠婃棩涓€棰樸€佹鏋跺浘銆佷粖鏃ュ彲甯﹁蛋銆佹暣灏佹竻娲佸害銆侀€熻銆侀噸澶嶃€佽〃杈捐川鎰熴€佹ā鍧楀啑浣欍€佸唴瀹归闄┿€侀€夋枃璐ㄩ噺銆乧ontent quality 鍜?pre-send cleanliness銆?
- 鏂板 `build_gate_from_quality_map`锛岀粺涓€鎶婅川閲?map 杞垚 `build_quality_gate(...)` 鍙傛暟锛岄伩鍏嶅悇澶勬墜鍐欏弬鏁伴『搴忋€?
- 鏂板 `recompute_after_brief_change`锛岀敤浜?brief 鍙樻洿鍚庣粺涓€鎵ц schema 鏍￠獙銆乁RL 鏍囨敞銆佹渶缁堥€夋枃鎽樿銆佷富棰樺彉鍖栨鏌ャ€乻ubject 閲嶇畻銆佹覆鏌撳拰璐ㄩ噺澶嶇畻銆?
- 鍊欓€変欢澶嶆牳銆乧ontent quality minor fix銆乧ontent issue rewrite銆乸re-send cleanliness guard銆丳0 repair 鍚庣殑閮ㄥ垎閲嶅璐ㄦ浠ｇ爜宸叉敼涓轰娇鐢ㄧ粺涓€ helper銆?
- 鏈樁娈靛彧鎶藉嚱鏁板拰鏇挎崲鏈烘閲嶅鍧楋紝涓嶆媶鏂囦欢銆佷笉鏀逛簨浠舵ā寮忋€佷笉鏀瑰彂閫佸垽鏂€佷笉鏀硅川閲忓瓧娈靛悕銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 鍚庣画缁х画鏇挎崲鍓╀綑璐ㄩ噺閲嶅鍧楁椂锛屽簲浼樺厛浣跨敤 `evaluate_all_quality` 鍜?`recompute_after_brief_change`锛屼笉瑕佺户缁鍒舵暣娈佃川妫€璋冪敤銆?
2. 绗?3 闃舵鎷嗘枃浠跺墠锛屽簲鍏堢‘璁?`quality.final`銆乣quality_gate`銆乣latest_quality.json` 鍜岀鐞嗗憳鎶ュ憡缁撴瀯娌℃湁瀛楁缂哄け銆?

### 2026-05-28锝滈樁娈?1 閮ㄧ讲鏂囨。涓庢墦鍖呭寘鍚嶇粺涓€

**鏀瑰姩鍘熷洜**

浠ｇ爜浼樺寲绗竴闃舵鍏堝鐞嗕綆椋庨櫓鐨勯儴缃插拰浠撳簱鍗敓闂銆傛鍓?README 鍐欎笂浼?`gongkao-morning-mailer.zip`锛孊ash 鎵撳寘鑴氭湰杈撳嚭 `function.zip`锛孭owerShell 鎵撳寘鑴氭湰榛樿杈撳嚭 `_release\gongkao-morning-mailer.zip`锛屽鏄撳鑷存湰鍦般€丟itHub 鍜岄樋閲屼簯 FC 涓婁紶璇存槑涓嶄竴鑷淬€?

**宸叉敼鏂囦欢**

- `README.md`
- `requirements.txt`
- `.gitignore`
- `scripts/build_fc_package.ps1`
- `content_harness/deployment_rules.md`
- `docs/deploy_aliyun_fc.md`
- `docs/architecture.md`
- `docs/code_optimization_execution_plan.md`
- `docs/code_optimization_execution_plan.docx`

**鏈€鏂扮増琛屼负**

- 閮ㄧ讲鍖呯粺涓€鍛藉悕涓?`function.zip`銆?
- PowerShell 鎵撳寘鑴氭湰榛樿鍦ㄤ粨搴撴牴鐩綍鐢熸垚 `function.zip`锛涘鏋滀紶鍏ョ浉瀵硅矾寰勶紝浼氭寜浠撳簱鏍圭洰褰曡В鏋愩€?
- README 鍜岄儴缃茶鍒欐枃妗ｇ粺涓€璇存槑涓婁紶 `function.zip`銆?
- 鏂板闃块噷浜?FC 閮ㄧ讲璇存槑锛屾槑纭湰鍦版鏌ャ€佹墦鍖呫€佷笂浼犮€佽Е鍙戝櫒鍜屽彂甯冨悗楠岃瘉姝ラ銆?
- 鏂板褰撳墠杩愯鏋舵瀯鏂囨。锛岃褰?`main.handler`銆丠TTP 闃绘柇銆乫eedback銆佸闂村€欓€夈€佹棭鏅ㄥ彂閫併€佸懆鎶?PDF 鍜岃川閲忛棬绂佽竟鐣屻€?
- `reportlab` 渚濊禆閿佸畾涓?`reportlab==4.5.1`锛岄伩鍏?FC 鎵撳寘鏃跺畨瑁呬笉鍙鏈熺増鏈€?
- `.gitignore` 琛ュ厖 `chardet/`锛岄槻姝緷璧栫洰褰曡鍏ヤ粨搴撱€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 鏈樁娈典笉鍒犻櫎浠撳簱涓凡璺熻釜鐨?`reportlab/` 鐩綍锛屽悗缁瑕佺Щ闄?vendored 鐩綍锛屽繀椤诲崟鐙獙璇?PDF 鐢熸垚鍜?FC 鎵撳寘銆?
2. 鍚庣画鎷嗗垎 `main.py` 鍓嶏紝搴斿厛瀹屾垚璐ㄩ噺璁＄畻 helper 鎶藉彇锛岄伩鍏嶅湪澶氫釜鏂囦欢涔嬮棿澶嶅埗閲嶅璐ㄦ浠ｇ爜銆?

### 2026-05-27锝滄覆鏌撳眰涓庡彂閫佸墠娓呮礂缁熶竴鍏滃簳鍘婚櫎灞曠ず鏍囩娉勬紡

**鏀瑰姩鍘熷洜**

鐢ㄦ埛缁х画鍙嶉锛屾渶缁?`candidate_email_*.html` 涓粛鍙嶅鍑虹幇鈥滃彲鐢ㄨ〃杈撅細鍙敤琛ㄨ揪锛氣€濃€滃鏋滅偣鍘熸枃锛岄噸鐐圭湅锛氬鏋滅偣鍘熸枃锛岄噸鐐圭湅锛氣€濃€滃棰樺叧閿細瀹￠鍏抽敭锛氣€濃€滀綔绛斾富绾匡細浣滅瓟涓荤嚎锛氣€濈瓑灞曠ず鍨嬪皬鏍囬閲嶅銆傚崟闈犱笂娓哥敓鎴愮害鏉熷拰鏃╂湡娓叉煋鍘婚噸杩樹笉澶燂紝闇€瑕佸湪娓叉煋灞傚拰鍙戦€佸墠娓呮礂灞傚悓鏃跺仛鏇寸ǔ鐨勫厹搴曘€?

**宸叉敼鏂囦欢**

- `email_renderer.py`
- `pre_send_cleanliness.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `email_renderer.py` 鏂板缁熶竴鐨勫睍绀哄墠缂€鍓ョ閫昏緫锛屾渶缁堟覆鏌?HTML / 绾枃鏈椂浼氶噸澶嶅墺绂讳互涓嬪墠缂€锛岀洿鍒板瓧娈垫鏂囨仮澶嶄负绾唴瀹癸細
  - `濡傛灉鐐瑰師鏂囷紝閲嶇偣鐪媊
  - `鍙敤琛ㄨ揪`
  - `浣滅瓟涓荤嚎`
  - `瀹￠鍏抽敭`
  - `鎹㈡垚鑰冨満璇漙
  - `鑰冨満璇漙
- 绾枃鏈拰 HTML 娓叉煋灞傞兘浼氬湪 `original_reading_focus`銆乣rewritable_expression`銆乣exam_focus`銆佸弬鑰冨彞寮忕瓑灞曠ず鍨嬪瓧娈典笂搴旂敤杩欏眰鍏滃簳锛岃€屼笉鏄彧渚濊禆涓婃父 brief 宸茬粡琚慨骞插噣銆?
- `pre_send_cleanliness.py` 琛ラ綈浜?`usable_for_exam` 鍜?`exam_use[*]` 杩欎袱涓瓧娈靛埆鍚嶇殑鍓嶇紑娓呮礂锛岄伩鍏嶈川妫€鍛戒腑涓€涓瓧娈靛悕銆佹渶缁堟覆鏌撳嵈璧板彟涓€涓瓧娈靛悕锛屽鑷粹€滀慨浜嗕絾閭欢閲岃繕鍦ㄢ€濄€?
- 杩欐鏀瑰姩鍙鐞嗗睍绀烘爣绛炬硠婕忥紝涓嶆敼妯″潡缁撴瀯銆佷笉鏀瑰瓧娈靛惈涔夈€佷笉閲嶅啓姝ｆ枃鍐呭銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 濡傛灉鍚庣画鏂板鏂扮殑鈥滄爣棰?+ 姝ｆ枃鈥濆睍绀烘ā鍧楋紝涓旀鏂囧€间篃鍙兘鑷甫鍚屽悕灏忔爣棰橈紝蹇呴』鍚屾鍔犲叆娓叉煋灞備笌 `pre_send_cleanliness.py` 鐨勫墠缂€鍓ョ鍚嶅崟銆?
2. 鐢熸垚渚т粛搴斿敖閲忛伩鍏嶈緭鍑鸿繖浜涘墠缂€锛涘綋鍓嶄慨澶嶆槸灞曠ず灞傚厹搴曪紝涓嶄唬琛ㄥ彲浠ユ斁鏉句笂娓?Prompt 绾︽潫銆?

### 2026-05-26锝滀慨澶?rewrite 鍚庡€欓€変欢銆丠TML銆佺函鏂囨湰涓庤川閲忓崱涓嶄竴鑷?

**鏀瑰姩鍘熷洜**

鐢ㄦ埛鍙嶉 `latest_quality_card.md` 鐨勨€滆嚜鍔ㄤ慨澶嶆憳瑕佲€濇樉绀烘煇浜涘瓧娈靛凡缁忎慨濂斤紝浣嗘渶缁?`latest.json`銆乣candidate_email_*.html`銆乣plain_text` 閲屼粛娈嬬暀鍗婃埅鍙ャ€佸皬鏍囬鍓嶇紑鎴栧垎鍙风粨灏撅紱鍚屾椂璐ㄩ噺鍗￠噷鍚屼竴鏉′慨澶嶆憳瑕佷細閲嶅鍑虹幇銆傞棶棰樻湰璐ㄦ槸 rewrite 鍚庡啓鍥炪€佸妫€銆佸啀娓叉煋鍜岃川閲忓崱鎽樿鍘婚噸娌℃湁瀹屽叏鎵撻€氥€?

**宸叉敼鏂囦欢**

- `main.py`
- `pre_send_cleanliness.py`
- `admin_report.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `content_issue_rewrite` 鎴?`p0 repair` 涔嬪悗锛屼細閲嶆柊鍚屾锛?
  - `brief`
  - `plain_text`
  - `html_body`
  - `content_quality`
  - `quality_gate`
  淇濊瘉鏈€缁堝€欓€変欢閲屼繚瀛樼殑鏄慨澶嶅悗鐨勬渶缁堜骇鐗╋紝鑰屼笉鏄€滄憳瑕佽淇簡锛屼絾姝ｆ枃杩樻病鎹⑩€濄€?
- 濡傛灉 `content_issue_rewrite` 瀵艰嚧鍐呭璐ㄩ噺鍒嗘暟鏄庢樉涓嬮檷锛屼細鏁磋疆鍥炴粴锛屽苟鎶婅杞?rewrite 鏍囪涓?`rolled_back`锛涜鍥炴粴鐨?rewrite 涓嶅啀缁х画姹℃煋鏈€缁堣川閲忓崱鍜屽€欓€変欢鎽樿銆?
- `merge_rewrite_results` 浼氳烦杩囧凡鍥炴粴杞锛宍admin_report.py` 浼氬鑷姩淇鎽樿鍘婚噸锛岄伩鍏嶅悓涓€鏉′慨澶嶅湪璐ㄩ噺鍗￠噷閲嶅灞曠ず涓ゆ銆?
- `pre_send_cleanliness.py` 琛ュ厖浜嗗瓧娈电骇鍏滃簳锛?
  - `today_takeaway.framework` 绾冲叆姝ｆ枃鍨嬪瓧娈垫竻娲佽寖鍥?
  - `daily_question.thirty_second_answer`
  - `daily_question.output_sentence_template`
  濡傛灉鍙墿鏈熬鍒嗗彿锛屼細鐩存帴瀛楁绾ф敼鎴愬彞鍙凤紝鑰屼笉鏄负杩欎竴涓爣鐐归棶棰橀噸鍐欐暣涓?`daily_question`
- `main.py` 鍦ㄥ彂閫佸墠娓呮磥搴﹀畧鍗箣鍚庝篃浼氶噸鏂拌瘎浼?`content_quality`锛岄伩鍏嶈川閲忛棬绂佷粛娌跨敤娓呮磥鍓嶇殑鏃х粨鏋溿€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 浠ュ悗鍑℃槸鏂板鈥滆嚜鍔ㄤ慨澶嶄絾涓嶄竴瀹氶噸鍐欏叏鏂団€濈殑瀛楁绾ф竻娲侀€昏緫锛岄兘瑕佺‘璁?`latest.json`銆乣plain_text`銆乣html_body`銆乣quality_card` 鍥涗唤浜х墿鏄惁鍚屾鏇存柊銆?
2. 濡傛灉鍚庣画鍐嶅嚭鐜扳€滆川閲忓崱璇翠慨浜嗭紝浣嗛偖浠堕噷娌′慨鈥濈殑闂锛屼紭鍏堟帓鏌ュ啓鍥為『搴忋€佸洖婊氭爣璁板拰鎽樿鍘婚噸锛岃€屼笉鏄厛鎬€鐤戝崟鏉?Prompt銆?

### 2026-05-25锝滄柊澧炴鏂囧瀷瀛楁鍙ユ湯鏍囩偣瀹堝崼涓庡崐鎴彞灏炬娴?

**鏀瑰姩鍘熷洜**

鐢ㄦ埛鍙嶉鐢熸垚閭欢閲岀粡甯稿嚭鐜扳€滃儚瀛楁鎷兼帴缁撴灉鈥濈殑姝ｆ枃锛氭湁浜涘睍绀哄瀷鍐呭缂哄彞鍙凤紝鏈変簺鍙ュ瓙鍋滃湪鈥滃彲钀藉湴鈥濃€滄湁鍔╀簬鈥濃€滃叧閿湪浜庘€濃€滀粠鑰屸€濈瓑鏄庢樉鍗婃埅灏惧反涓婏紝杩樻湁涓埆 30 绉掑弬鑰冨彞寮忓彧鍓╀竴涓垎鍙风粨灏俱€傞渶瑕佸湪鍙戦€佸墠澧炲姞纭畾鎬х殑姝ｆ枃鏀跺彛瑙勫垯锛屽厛鎶婃垚鍝佹劅鍜屾埅鏂闄╃ǔ浣忋€?

**宸叉敼鏂囦欢**

- `pre_send_cleanliness.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鍙戦€佸墠娓呮磥搴﹀畧鍗細瀵逛互涓嬫鏂囧瀷瀛楁鑷姩琛ヤ腑鏂囧彞鍙凤細鍙瀛楁缁撳熬涓嶆槸 `銆傦紒锛燂紱.!?銆嶃€忥級銆戙€媊锛屽氨琛ユ垚瀹屾暣鍙ワ紝瑕嗙洊鑼冨洿鍖呮嫭锛?
  - `today_focus`
  - `must_remember_sentence`
  - `featured_article.one_sentence`
  - `original_reading_focus`
  - `three_useful_points`
  - `exam_use / usable_for_exam`
  - `rewritable_expression`
  - `daily_question.exam_focus`
  - `daily_question.breaking_hint`
  - `daily_question.candidate_answer`
  - `daily_question.output_sentence_template`
  - `daily_question.thirty_second_answer`
  - `today_takeaway.framework`
  - `today_takeaway.common_knowledge_points`
  - `today_takeaway.golden_sentences[*].sentence`
  - `quick_reads[*].one_sentence`
  - `quick_reads[*].exam_value`
- 濡傛灉姝ｆ枃鍨嬪瓧娈典互鈥滃彲钀藉湴銆佸彲浠ョ敤浜庛€侀€傚悎杞寲涓恒€佹湁鍔╀簬銆佷綋鐜板嚭銆佸叧閿湪浜庛€佷富瑕佸寘鎷€佷粠鑰屻€佽繘鑰屻€佸悓鏃躲€佸苟涓斺€濈瓑楂橀闄╁熬宸寸粨鏉燂紝浼氳涓?`suspected_truncated_sentence`锛屽苟杩涘叆璐ㄩ噺闂ㄧ銆?
- 浠婃棩涓€棰樼殑 `thirty_second_answer` / `output_sentence_template` 濡傛灉鍙墿鏈熬鍒嗗彿锛屼細鍦ㄥ瓧娈电骇鐩存帴鏀规垚鍙ュ彿锛岄伩鍏嶅洜涓轰竴涓熬鏍囩偣閲嶅啓鏁翠釜棰樼洰妯″潡銆?
- `main.py` 宸叉妸 `suspected_truncated_sentence` 绾冲叆 `quality_gate` 鐨?P0 闆嗗悎锛岀‘淇濊繖绫绘槑鏄惧崐鎴彞涓嶄細琚斁杩囥€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 杩欏瑙勫垯鍙礋璐ｂ€滄敹灏锯€濆拰鈥滆瘑鍒槑鏄惧崐鎴彞鈥濓紝涓嶄唬鏇垮唴瀹归噸鍐欙紱濡傛灉姝ｆ枃閫昏緫鏈韩涓嶉€氶『锛屼粛瑕佽蛋鍘熸湁 rewrite / 璐ㄩ噺闂ㄧ閾捐矾銆?
2. 鍚庣画濡傛灉鏂板姝ｆ枃鍨嬪瓧娈碉紝闇€瑕佸悓姝ュ姞鍏?`BODY_TEXT_PATHS`锛屽惁鍒欎笉浼氳嚜鍔ㄨˉ鍙ュ彿鎴栬瘑鍒崐鎴熬宸淬€?

### 2026-05-25锝滄柊澧炲熀灞傝韩浠借秺鏉冧綔绛旈闄╄川妫€

**鏀瑰姩鍘熷洜**

鐢ㄦ埛鎸囧嚭锛屼粖鏃ヤ竴棰樺鏋滈骞茶韩浠芥槸鍩哄眰銆佽閬撱€佺ぞ鍖恒€佸競鍦虹洃绠℃墍銆佸煄绠°€佸伐浣滀汉鍛樼瓑锛岀瓟妗堥噷鍗寸洿鎺ュ啓鈥滃埗瀹氳涓氭爣鍑嗏€濃€滀慨鏀瑰寘瑁呪€濃€滄帹琛屽寘瑁呮爣璇嗏€濈敋鑷斥€滄棤鏄庣‘杩濇硶渚濇嵁澶勭綒鏅€氶珮绯栭珮娌归鍝佸晢鎴封€濓紝浼氬舰鎴愭槑鏄捐秺鏉冪敋鑷宠繚娉曡〃杩般€傝繖绫婚棶棰樹笉鑳藉彧褰撴櫘閫氳〃杈剧憰鐤靛鐞嗭紝闇€瑕佸崟鐙嫤鎴€?

**宸叉敼鏂囦欢**

- `question_quality.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `question_quality.py` 鏂板 `grassroots_authority_overreach` 妫€鏌ワ細褰撻骞插懡涓熀灞傝韩浠借澧冩椂锛屼細鑱斿姩鎵弿 `answer_framework` 涓?`candidate_answer`銆?
- 瀵逛互涓嬮珮椋庨櫓琛ㄨ堪鐩存帴鎸夐珮椋庨櫓鎷︽埅锛?
  - `渚濇硶澶勭悊鎸佺画鍞崠鏅€氶珮绯栭珮娌归鍝佸晢鎴穈
  - `鏃犳槑纭繚娉曚緷鎹缃歚
  - `澶勭綒鏅€氶珮绯栭珮娌归鍝乣
  - `鏌ュ鏅€氶珮绯栭珮娌归鍝乣
  - `鍙栫紨鍞崠鏅€氶珮绯栭珮娌归鍝乣
- 瀵逛互涓嬧€滄妸涓婄骇鏉冮檺鍐欐垚鍩哄眰鐩存帴鏉冮檺鈥濈殑琛ㄨ堪鎸変腑椋庨櫓鎻愮ず锛?
  - `鍒跺畾琛屼笟鏍囧噯`
  - `淇敼鍖呰`
  - `鎺ㄨ鍖呰鏍囪瘑`
  - `缁熶竴鍖呰鏍囪瘑`
  - `寮哄埗鍖呰鏍囪瘑`
  - `瑕佹眰鍟嗘埛淇敼鍖呰`
- 濡傛灉杩欎簺琛ㄨ堪鍓嶉潰鏄庣‘鍐欎簡鈥滃缓璁笂绾?/ 鎶ヨ涓婄骇 / 鎺ㄥ姩瀹屽杽 / 涓婃姤鈥濈瓑闄愬畾璇紝瑙勫垯浼氬敖閲忚瘑鍒负鈥滃缓璁笂绾у仛鈥濓紝涓嶈浼ゃ€?
- `main.py` 宸叉妸 `grassroots_authority_overreach` 绾冲叆 `quality_gate` 鐨?P0 闆嗗悎銆傚浜庡熀灞傝韩浠介锛岃繖绫昏秺鏉冪瓟妗堜笉鑳界洿鎺ユ斁琛屻€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 杩欐潯瑙勫垯鐨勬牳蹇冧笉鏄€滆秺淇濆畧瓒婂ソ鈥濓紝鑰屾槸鏄庣‘鍖哄垎涓夊眰鏉冮檺锛氬熀灞傚彲鐩存帴鍋氥€佸缓璁笂绾у仛銆佸彧鏈夋槑纭繚娉曟椂鎵嶄緷娉曟煡澶勩€?
2. 濡傛灉鍚庣画鎵╁睍鍒版暀鑲层€佷綇寤恒€佸競鍦虹洃绠＄瓑鏇村韬唤棰樺瀷锛屽簲缁х画琛ュ厖瓒婃潈鍏抽敭璇嶅拰鍚堟硶闄愬畾璇紝鑰屼笉鏄彧闈犵幇鏈夊嚑涓ず渚嬭瘝銆?

### 2026-05-22锝滃懆鏈€欓€変欢鏀逛负鍙敓鎴愬懆 PDF 姹囩紪

**鏀瑰姩鍘熷洜**

鐢ㄦ埛纭鍛ㄥ叚鏅氫笂鍙渶瑕佺敓鎴愬懆 PDF 姹囩紪鍊欓€変欢锛屽懆鏃ユ棭鏅ㄥ彧鍙戦€?PDF 姹囩紪锛屼笉搴斿啀鍐欐柊鐨勬瘡鏃ョ簿璇绘枃绔犮€傚悓鏃讹紝鍙戦€佸墠娓呮磥搴﹀畧鍗彧闇€瑕佸湪澶滈噷鍐欏叆鍊欓€変欢鍓嶈繍琛屼竴娆★紝鏃╂櫒鍙戦€佹椂缁х画淇′换澶滈噷淇濆瓨鐨?`quality_gate`銆?

**宸叉敼鏂囦欢**

- `main.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `morning_send` 涓嶅啀閲嶆柊杩愯 `pre_send_cleanliness_guard`锛屽彧璇诲彇澶滈噷鍊欓€変欢涓凡缁忎繚瀛樼殑 `quality_gate`銆?
- 鏂板 `weekly_pdf_candidate` / `weekly_candidate` / `nightly_weekly_pdf` 鍊欓€変欢妯″紡锛氬彧璇诲彇姣忔棩褰掓。鐢熸垚鍛?PDF銆佷繚瀛?`candidate_type=weekly_pdf` 鍊欓€変欢锛屼笉杩涘叆姣忔棩鏂囩珷鎶撳彇銆侀€夋枃鍜岀簿璇诲啓绋挎祦绋嬨€?
- 濡傛灉鍛ㄥ叚澶滈噷浠嶈Е鍙戞櫘閫?`nightly_candidate`锛屼笖 `ENABLE_WEEKLY_PDF=true`銆佸€欓€変欢鏃ユ湡姝ｅソ鏄?`WEEKLY_PDF_WEEKDAY`锛岀▼搴忎細鑷姩杞负鍛?PDF 鍊欓€変欢鐢熸垚锛岄伩鍏嶅懆鏃ュ€欓€変欢璇啓鎴愭瘡鏃ョ簿璇汇€?
- 鍛?PDF 鍊欓€変欢淇濆瓨涓虹浜屽ぉ鍙戦€佹棩鏈燂紱鍛ㄦ棩 `morning_send` 璇诲彇鍚庤蛋宸叉湁 `send_weekly_pdf_candidate`锛屽彧鍙戞眹缂?PDF锛屼笉鍐欏巻鍙叉枃绔犮€佷笉褰掓。姣忔棩绮捐銆?
- 鍛?PDF 鍊欓€変欢閭欢姝ｆ枃鏀逛负鈥滃懆鏃ュ鐩樿鏄庨偖浠垛€濓細鏍囬涓衡€滄湰鍛?PDF 璧勬枡鍖呭凡闄勪笂鈥濓紝姝ｆ枃璇存槑浠婂ぉ涓嶆帹閫佹柊绮捐/閫熻銆佺粰鍑哄涔犻『搴忥紝骞朵繚鐣欏弽棣堥棶棰樺尯锛汸DF 姹囩紪浣滀负闄勪欢鍙戦€併€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 濡傞渶鍦ㄥ懆鏈己鍒剁敓鎴愭櫘閫氭瘡鏃ョ簿璇诲€欓€変欢锛屽彲鍦ㄤ簨浠堕噷鍔?`force_daily=true` 鎴?`skip_weekly_pdf_candidate=true`銆?
2. 鍛?PDF 渚濊禆姣忔棩褰掓。锛涘鏋滃綊妗ｅぉ鏁颁笉瓒筹紝鍊欓€変欢鐢熸垚浼氳褰曠己澶辨棩鏈熷苟鎸夊凡鏈夊懆 PDF 姹囩紪閫昏緫澶勭悊銆?

### 2026-05-22锝滄柊澧炲彂閫佸墠娓呮磥搴﹀畧鍗?

**鏀瑰姩鍘熷洜**

浠婃櫄閭欢涓€滃彲鐢ㄨ〃杈锯€濇ā鍧楀嚭鐜颁簡姝ｆ枃寮€澶存畫鐣欑偣鍙?鍐掑彿鐨勯棶棰橈紝璇存槑鍗曢潬娓叉煋灞傚幓閲嶈繕涓嶅銆備负閬垮厤妯℃澘娈嬬暀銆佹爣绛炬硠婕忋€侀噸澶嶅墠缂€銆佸啋鍙锋畫鐣欏拰鏍囬閲嶅杩涘叆 `latest.json` 鎴栨寮忓彂閫佹鏂囷紝闇€瑕佸湪鍙戦€佸墠澧炲姞涓€灞傜‘瀹氭€х殑娓呮磥搴﹀畧鍗€?

**宸叉敼鏂囦欢**

- `pre_send_cleanliness.py`
- `main.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鏂板 `pre_send_cleanliness_guard(data)`锛屽唴閮ㄦ寜 `check_cleanliness -> auto_fix_cleanliness -> 鍚屾娓叉煋 plain_text/html_body -> recheck_cleanliness -> decide_gate_status` 鎵ц銆?
- 鑷姩淇 `鍙敤琛ㄨ揪锛氬彲鐢ㄨ〃杈撅細`銆乣浣滅瓟涓荤嚎锛氫綔绛斾富绾匡細`銆乣瀹￠鍏抽敭锛氬棰樺叧閿細`銆乣濡傛灉鐐瑰師鏂囷紝閲嶇偣鐪嬶細濡傛灉鐐瑰師鏂囷紝閲嶇偣鐪媊銆佸瓧娈垫鏂囧紑澶村啋鍙?鐐瑰彿娈嬬暀锛屼互鍙婇噸澶嶇殑 `銆愬叕鑰冩櫒璇汇€慲 鏍囬鍓嶇紑銆?
- `featured_article.rewritable_expression` 瀛楁浼氳娓呮垚绾〃杈撅紝涓嶅啀淇濈暀 `鍙敤琛ㄨ揪锛歚 鍓嶇紑锛沗plain_text` 鍜?`html_body` 浼氶殢淇鍚庣殑 brief 鍚屾鏇存柊銆?
- 閲戝彞楂樺害鐩镐技銆?0 绉掕緭鍑哄亸闀裤€佽€冪敓鐗堢瓟妗堟钀藉亸闀垮彧璁板綍涓轰綆椋庨櫓 issue锛屼笉闃绘柇鍙戦€併€?
- 浠婃棩涓€棰橀骞茬己韬唤銆佸満鏅€佺煕鐩俱€佷换鍔¤绱犳椂锛屾竻娲佸害瀹堝崼鍙褰曢珮椋庨櫓 issue锛屼笉纭敼棰樼洰锛屽苟閫氳繃 `module_override=daily_question` 浜ょ粰鍘熸湁 daily_question 閲嶅啓/璐ㄩ噺闂ㄧ澶勭悊銆?
- 娓呮磥搴︾粨鏋滃啓鍏?`quality.final.cleanliness` 鍜?`quality.cleanliness`锛涙湭淇鐨勬槑鏄炬ā鏉挎畫鐣欎細杩涘叆鍘?`quality_gate`銆傝瀹堝崼鍙湪澶滈噷鍊欓€変欢鐢熸垚/璇勪及闃舵杩愯锛屾棭鏅?`morning_send` 缁х画淇′换澶滈噷淇濆瓨鐨?`quality_gate`銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 璇ュ畧鍗彧鍋氳鍒欏瀷娓呮磥鍜岄棬绂侊紝涓嶅紩鍏ユ柊 LLM锛屼篃涓嶆敼鍙橀偖浠剁粨鏋勩€?
2. 鍚庣画濡傛灉鏂板妯″潡鏍囬锛岄渶瑕佸悓姝ュ姞鍏?`pre_send_cleanliness.py` 鐨?`DISPLAY_LABELS`銆?

### 2026-05-22锝滃懆 PDF 鍏ㄩ潰鍒囨崲鎵撳嵃鍙嬪ソ娴呰壊濉厖

**鏀瑰姩鍘熷洜**

鐢ㄦ埛缁х画鍙嶉锛屽懆 PDF 铏界劧宸茬粡鎶婃棩鏍囬鍖烘敼娴咃紝浣嗛椤靛皝闈€侀噾鍙ュ尯缂栧彿鍧椼€佹鏋跺浘姝ラ缂栧彿绛夊厓绱犱粛鏄ぇ闈㈢Н娣辫壊瀹炲績濉厖锛屾墦鍗板悗瀹规槗鍙樻垚鈥滈粦涔庝箮涓€鐗団€濓紝褰卞搷鍙鎬у拰澶嶅嵃浣撻獙銆?

**宸叉敼鏂囦欢**

- `weekly_typst_export.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鍛?PDF 棣栭〉灏侀潰鐢辨繁钃濆ぇ搴曟敼涓烘祬钃濈伆搴曪紝涓绘爣棰樻枃瀛椼€佹暟瀛楃粺璁″崱鐗囨敼涓烘繁鑹叉枃瀛?+ 娴呰壊鍗＄墖锛屾墦鍗版椂涓嶄細鍑虹幇澶ч潰绉繁鑹插簳銆?
- 妗嗘灦鍥惧唴鐨勬楠ょ紪鍙枫€侀噾鍙ュ簱缂栧彿鍧椼€佸叾浠栧皬缂栧彿鏍囩锛岀粺涓€鏀逛负鈥滄祬鑹插簳 + 娣辫壊瀛楋紝甯﹁竟妗嗏€濈殑鎵撳嵃鍙嬪ソ鏍峰紡銆?
- 涓婚鎬昏琛ㄦ牸銆佺簿璇诲師鏂囩储寮曘€佽ˉ鍏呴槄璇诲垪琛ㄧ殑琛ㄥご锛岀敱娣辫壊琛ㄥご鏀逛负娴呰壊琛ㄥご锛屼繚鐣欐繁鑹叉枃瀛楀拰缁撴瀯灞傜骇銆?
- 杩欐浠嶅彧璋冩暣鍛?PDF 妯℃澘閰嶈壊锛屼笉鏀瑰唴瀹规彁鍙栥€佹ā鍧楅『搴忓拰鏂囨鍐呭銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 濡傛灉鍚庣画杩樿缁х画鍘嬫祬棰滆壊锛岄渶瑕佸悓姝ユ娊鏌ュ睆骞曢槄璇绘椂鐨勫姣斿害锛岄伩鍏嶆祬鍒版爣棰樺眰绾т笉澶熸竻銆?
2. 姝ｅ紡涓婄嚎鍓嶅缓璁啀鐢ㄤ竴浠藉畬鏁翠竷澶╂牱鏈鏍哥増寮忥紝纭娴呰壊琛ㄥご鍜岀紪鍙峰潡鍦ㄦ墦鍗版満涓婁粛鏈夎冻澶熻鲸璇嗗害銆?

### 2026-05-22锝滃懆 PDF 鏀逛负妯″潡灏介噺鏁村潡鍒嗛〉銆佹祬鑹叉棩鏍囬涓庨噾鍙ュぇ妗?

**鏀瑰姩鍘熷洜**

鐢ㄦ埛鍙嶉鍛?PDF 瀛樺湪涓変釜闃呰闂锛氫竴鏄枃绔犳鏋跺浘绛夋ā鍧椾細鍦ㄥ垎椤靛琚媶寮€锛涗簩鏄瘡鏃ユ爣棰樺尯娣辫壊搴曟墦鍗颁笉鍙嬪ソ锛涗笁鏄€滃彲鑳岄噾鍙モ€濋€愭潯鍒嗘暎锛岃瑙変笂涓嶅鏁村悎銆?

**宸叉敼鏂囦欢**

- `weekly_typst_export.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- Typst 鍛?PDF 涓殑绮捐鍗°€佹枃绔犳鏋跺浘銆佷粖鏃ュ彲甯﹁蛋绛夎緝灏忔ā鍧楁敼涓哄敖閲忔暣鍧椾繚鐣欙紱濡傛灉褰撳墠椤垫斁涓嶄笅锛屼細浼樺厛鏁翠綋绉诲埌涓嬩竴椤碉紝鍑忓皯妗嗘灦鍥捐法椤点€?
- 姣忔棩鏍囬鍖虹敱娣辫壊鏁村潡搴曟敼涓烘祬钃濈伆搴?+ 娣辫壊鏂囧瓧锛屾洿閫傚悎榛戠櫧鎴栦綆褰╂墦鍗帮紝鍚屾椂淇濈暀灞傛鎰熴€?
- 鈥滃彲鑳岄噾鍙モ€濆尯鍩熸敼涓轰竴涓粺涓€澶ф锛屾鍐呮寜缂栧彿鍒嗘潯灞曠ず锛屼笉鍐嶄互鍒嗘暎灏忓潡鍛堢幇銆?
- 杩欐浠嶅彧璋冩暣鍛?PDF 妯℃澘锛屼笉鏀规瘡鏃ラ偖浠跺唴瀹瑰拰妯″潡鎻愬彇閫昏緫銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 瀵逛簬楂樺害鏄庢樉瓒呰繃涓€椤电殑瓒呴暱妯″潡锛孴ypst 浠嶅彲鑳借杩垎椤碉紱褰撳墠浼樺寲涓昏瑙ｅ喅妗嗘灦鍥俱€佹彁瑕佸崱杩欑被涓皬妯″潡琚媶椤电殑闂銆?
2. 濡傛灉鍚庣画缁х画鍘嬫祬閰嶈壊锛岄渶瑕佸悓鏃跺叧娉ㄥ睆骞曢槄璇诲姣斿害锛岄伩鍏嶆祬鍒板簳鑹插拰姝ｆ枃灞傜骇涓嶆竻銆?

### 2026-05-22锝滃懆 PDF Typst 妯℃澘鏀惧琛岃窛銆佹璺濅笌鍗＄墖鐣欑櫧

**鏀瑰姩鍘熷洜**

鍛?PDF 姹囩紪褰撳墠鐗堟湰鍦ㄨ繛缁ぇ娈垫鏂囥€佸崱鐗囪鏄庡拰妗嗘灦姝ラ鍖哄煙鎺掔増鍋忕揣锛岄槄璇绘椂瀹规槗鏄惧緱鈥滃瘑瀵嗛夯楹烩€濄€傛湰娆″弬鑰冩棫鐗堝懆澶嶇洏 PDF 鐨勭増寮忓瘑搴︼紝鏀惧姝ｆ枃琛岃窛銆佹璺濆拰鍗＄墖鍐呰竟璺濓紝骞跺皢瀛楀彿寰皟鏀惧ぇ锛屼絾閬垮厤鏄庢樉澧為〉銆?

**宸叉敼鏂囦欢**

- `weekly_typst_export.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- Typst 鍛?PDF 姝ｆ枃瀛楀彿浠?`10pt` 寰皟鍒?`10.2pt`銆?
- 鍏ㄥ眬娈佃惤琛岃窛銆佹闂磋窛銆佸垪琛ㄩ棿璺濆悓姝ユ斁瀹斤紝闀挎姝ｆ枃鍜岄鐩瓟妗堝尯鍩熸洿瀹规槗鎵銆?
- 绮捐鍗°€佹枃绔犳鏋跺浘銆佷粖鏃ヤ竴棰樸€佷粖鏃ュ彲甯﹁蛋銆侀噾鍙ュ崱鐗囩瓑妯″潡鐨勫唴杈硅窛鍜屾爣棰樼暀鐧藉悓姝ュ鍔狅紝鏁翠綋瑙嗚鏇存帴杩戞棫鐗堝懆澶嶇洏 PDF 鐨勫懠鍚告劅銆?
- 杩欐鍙皟鐗堝紡瀵嗗害锛屼笉鏀瑰懆 PDF 鐨勫唴瀹圭粨鏋勩€佹ā鍧楅『搴忓拰鎻愬彇閫昏緫銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 鍚庣画濡傛灉缁х画鍔犲ぇ瀛楀彿鎴栫暀鐧斤紝闇€鍚屾椂鍏虫敞鍛?PDF 椤垫暟澧為暱锛岄伩鍏嶅懆鏈檮浠惰繃闀裤€?
2. 涓夊ぉ/鍥涘ぉ棰勮涓庡畬鏁翠竷澶╁懆鎶ョ殑鍒嗛〉鏁堟灉涓嶅悓锛涙寮忎笂绾垮墠浠嶅缓璁敤瀹屾暣涓€鍛ㄦ牱鏈鏍稿垎椤点€?

### 2026-05-22锝滀慨澶嶆ā鍧楁爣棰樺湪姝ｆ枃涓噸澶嶅睍绀?

**鏀瑰姩鍘熷洜**

閮ㄥ垎閭欢瀛楁鏈韩甯︽湁灞曠ず鍓嶇紑锛屼緥濡?`鍙敤琛ㄨ揪锛歚銆乣浣滅瓟涓荤嚎锛歚銆乣濡傛灉鐐瑰師鏂囷紝閲嶇偣鐪嬶細`銆傛覆鏌撳眰鍙堥澶栬緭鍑轰簡涓€娆℃ā鍧楁爣棰橈紝瀵艰嚧鐢ㄦ埛鐪嬪埌鈥滄爣棰?+ 姝ｆ枃閲屽啀閲嶅涓€閬嶅悓鍚嶆爣棰樷€濈殑鍙屾爣棰樺睍绀恒€?

**宸叉敼鏂囦欢**

- `email_renderer.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- HTML 娓叉煋灞備細鍦ㄥ睍绀?`original_reading_focus`銆乣breaking_hint`銆乣rewritable_expression` 鏃讹紝鑷姩鍓ョ涓庢ā鍧楁爣棰樺畬鍏ㄩ噸澶嶇殑寮€澶村墠缂€銆?
- 杩欐鍙鐞嗘樉绀洪噸澶嶏紝涓嶆敼瀛楁鍘熷鍐呭銆佷笉鏀规ā鍧楅『搴忋€佷笉鏀瑰叾瀹冩鏂囨枃妗堛€?
- 濡傛灉姝ｆ枃涓嶆槸浠ヨ繖浜涙ā鍧楁爣棰樺紑澶达紝娓叉煋灞備笉浼氶澶栨敼鍐欏唴瀹广€?

**鍚庣画娉ㄦ剰浜嬮」**

1. 鐢熸垚渚т粛搴斿敖閲忛伩鍏嶅湪杩欎簺瀛楁閲岄噸澶嶅啓灞曠ず鏍囬锛屼絾鍗充娇妯″瀷鍋跺皵甯﹀嚭鍓嶇紑锛屾覆鏌撳眰涔熶細鍏滃簳鍘婚噸銆?
2. 鍚庣画濡傛柊澧炵被浼尖€滄爣棰?+ 姝ｆ枃鈥濇ā鍧楋紝鑻ユ鏂囧瓧娈典篃鍙兘鑷甫鍚屽悕鍓嶇紑锛屽簲鍚屾鎺ュ叆鍚岀被娓叉煋鍘婚噸閫昏緫銆?

### 2026-05-22锝滄棭鏅ㄥ彂閫佹敼涓轰俊浠诲闂村€欓€変欢 quality_gate

**鏀瑰姩鍘熷洜**

澶滈棿鍊欓€変欢宸茬粡瀹屾垚姝ｅ紡璐ㄦ骞跺啓鍏?`quality_gate`锛屼絾鏃╂櫒 `morning_send` 涔嬪墠浠嶄細瀵瑰悓涓€浠藉€欓€変欢鍐嶆鎵ц鍏ㄦ枃璐ㄦ銆傝繖鏍蜂細鍑虹幇鈥滃閲屽€欓€変欢宸叉槸 ok锛屾棭鏅ㄥ嵈鍥犳柊瑙勫垯鎴栭噸妫€缁撴灉琚嫤鎴€濈殑婕傜Щ锛屽鑷存寮忓彂閫佷緷璧栦袱娆′笉鍚屾椂闂寸偣鐨勫唴瀹瑰垽瀹氥€?

**宸叉敼鏂囦欢**

- `main.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鏃╂櫒鍙戦€佽鍙?OSS / 鏈湴淇濆瓨鐨勫€欓€変欢鍚庯紝鐩存帴淇′换鍊欓€変欢鍐呭凡淇濆瓨鐨?`quality_gate`锛屼笉鍐嶅闈炲懆鎶ュ€欓€変欢閲嶈窇鍏ㄦ枃鍐呭璐ㄦ銆?
- 鏃╂櫒鍙戦€佷粛鐒朵繚鐣欏€欓€変欢瀛樺湪鎬с€乣delivery_date` 鍖归厤銆佸凡淇濆瓨 `quality_gate.overall` 鏄惁涓?`ok`銆佹敹浠朵汉涓庡彂閫侀摼璺瓑鍩虹鏍￠獙銆?
- 濡傛灉澶滈棿淇濆瓨涓嬫潵鐨?`quality_gate.overall != ok`锛屾棭鏅ㄤ粛鐒朵細闃绘柇鍙戦€侊紱鍙槸涓嶄細鍐嶅洜涓烘棭鏅ㄩ噸鏂拌窇鍐呭璐ㄦ鑰屾妸澶滈棿宸查€氳繃鐨勫€欓€変欢閲嶆柊鎵撳洖銆?
- 鍛ㄦ姤 PDF 鍊欓€変欢閾捐矾涓嶅彈杩欐鏀瑰姩褰卞搷銆?

**鍚庣画娉ㄦ剰浜嬮」**

1. 鍚庣画濡傛灉鏂板鎴栨敹绱у唴瀹硅川妫€瑙勫垯锛屽闂村€欓€変欢鐢熸垚閾捐矾鎵嶆槸鍞竴鐨勬寮忓唴瀹归棬绂佹潵婧愶紝鏃╂櫒鍙戦€侀摼璺笉鍐嶆壙鎷呪€滈噸鏂板垽鍐呭鏄惁鍚堟牸鈥濈殑鑱岃矗銆?
2. 濡傛灉闇€瑕侀獙璇佹寮忓彂閫佽涓猴紝搴斾紭鍏堢敤鈥滃闂村厛鐢熸垚鍊欓€変欢锛屾棭鏅ㄥ啀璇诲彇鍊欓€変欢鍙戦€佲€濈殑瀹屾暣閾捐矾娴嬭瘯锛岃€屼笉鏄亣璁炬棭鏅ㄥ彂閫佷細鍐嶅仛涓€娆″唴瀹归噸妫€鎴栬嚜鍔ㄤ慨姝ｆ枃妗堛€?

### 2026-05-21锝滅粺涓€浠婃棩涓€棰樹綔绛旀鏋朵笂闄愪负45瀛?

**鏀瑰姩鍘熷洜**

35瀛楄繃绱ф椂瀹规槗璇卞彂鍗婃埅鍙ワ紝45瀛椾綔涓哄畨鍏ㄤ笂闄愶紝浣嗕粛瑕佹眰鐭€佸噯銆佸畬鏁淬€?

**娑夊強鏂囦欢**

- `question_quality.py`
- `content_harness/daily_question_skill.md`
- `content_harness/quality_checks.md`
- `content_harness/daily_question_boundary_rules.md`
- `content_harness/runtime_prompt_rules.md`

**鏈€鏂扮増琛屼负**

- `answer_framework` / `answer_frame` 姣忕偣涓婇檺缁熶竴涓?45 瀛椼€?
- 45瀛椾笉鏄啓婊¤姹傦紱浼樺厛鐭€佸噯銆佸畬鏁达紝涓嶅緱涓轰簡鍘嬬缉鑰屽嚭鐜板崐鎴彞銆?

### 2026-05-21锝滄鏌ヤ粖鏃ヤ竴棰樹唬鐮佸眰杈圭晫鏀瑰姩

**鏀瑰姩鍘熷洜**

Codex 宸插畬鎴愪粖鏃ヤ竴棰樹笁灞傝竟鐣岀浉鍏充唬鐮佷慨鏀癸紝闇€瑕佸皢浠ｇ爜灞傛鏌ョ粨鏋滃悓姝ュ埌鍙樻洿璁板綍锛屾柟渚垮悗缁帴鎵嬫椂鍖哄垎鈥滃凡瀹屾垚鈥濆拰鈥滃緟灏忎慨鈥濈殑鍐呭銆?

**宸叉鏌ユ枃浠?*

- `prompt_templates.py`
- `email_renderer.py`
- `question_quality.py`
- `CHANGELOG_HARNESS.md`

**妫€鏌ョ粨鏋?*

- `prompt_templates.py` 宸插皢 `exam_focus` 鏀逛负鈥滃彧鎷嗛锛屼笉鍐欎綔绛旇矾绾挎垨鍏蜂綋瀵圭瓥鈥濄€?
- `prompt_templates.py` 宸插皢 `breaking_hint` 鏀逛负鈥?鍙ヨ瘽浣滅瓟涓荤嚎鈥濓紝骞惰姹備笉寰楀垪瀹屾暣鍒嗙偣銆佷笉寰楀拰浣滅瓟妗嗘灦閲嶅銆?
- `email_renderer.py` 宸插皢 HTML 灞曠ず鏍囬浠庘€滅牬棰樻彁绀衡€濇敼涓衡€滀綔绛斾富绾库€濓紝搴曞眰瀛楁浠嶈鍙?`breaking_hint` / `breaking_direction` / `review_key`銆?
- `question_quality.py` 宸叉柊澧?`ANSWER_ROUTE_TERMS`锛屽苟鍔犲叆浠ヤ笅杈圭晫璐ㄦ锛?
  - `exam_focus_too_answer_like`
  - `breaking_hint_duplicates_framework`
  - `breaking_hint_too_framework_like`

**鍙戠幇鐨勫緟灏忎慨闂**

- `prompt_templates.py` 涓?`answer_framework` 瀛楁璇存槑鍐欐垚鈥滄瘡鏉′笉瓒呰繃45瀛椻€濓紝褰撳墠瑙勫垯銆丼kill銆佽川妫€宸插湪鍚庣画鍙樻洿涓粺涓€涓?45 瀛楋紝淇濇寔鐢熸垚渚т笌璐ㄦ渚т竴鑷淬€?
- `question_quality.py` 涓己灏戜綔绛斾富绾挎椂鐨勬彁绀鸿浠嶅啓鈥滅己灏戠牬棰樻彁绀衡€濓紝鍚庣画寤鸿鏀规垚鈥滅己灏戜綔绛斾富绾库€濄€傝闂涓嶅奖鍝嶅姛鑳斤紝浣嗕細褰卞搷绠＄悊鍛樻姤鍛婂彛寰勪竴鑷存€с€?

**鏈€鏂扮増琛屼负**

浠ｇ爜灞傚凡缁忓熀鏈畬鎴愨€滃棰樺叧閿?/ 浣滅瓟涓荤嚎 / 浣滅瓟妗嗘灦鈥濊竟鐣屾敼閫狅紱浣嗗湪姝ｅ紡瑙嗕负闂幆鍓嶏紝寤鸿瀹屾垚涓婅堪涓や釜灏忎慨锛屽苟閲嶆柊杩愯锛?

```powershell
python -m py_compile prompt_templates.py question_quality.py email_renderer.py
```

### 2026-05-21锝滄矇娣€浠婃棩涓€棰樹笁灞傝竟鐣屽埌闀挎枃妗?

**鏀瑰姩鍘熷洜**

涓撻」瑙勫垯鏂囦欢宸茬粡寤虹珛锛屼絾闀挎湡缁存姢杩橀渶瑕佸悓姝ヨ繘鍏ユā鍧?Skill 鍜岃川閲忔鏌ユ竻鍗曘€傚惁鍒欏悗缁彧闃呰 `daily_question_skill.md` 鎴?`quality_checks.md` 鏃讹紝浠嶅彲鑳介仐婕忊€滃棰樺叧閿?/ 浣滅瓟涓荤嚎 / 浣滅瓟妗嗘灦鈥濈殑杈圭晫瑕佹眰銆?

**宸叉敼鏂囦欢**

- `content_harness/daily_question_skill.md`
- `content_harness/quality_checks.md`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `daily_question_skill.md` 宸叉妸杈撳嚭閾捐矾鏀逛负鈥滈鐩満鏅?鈫?瀹￠鍏抽敭 鈫?浣滅瓟涓荤嚎 鈫?浣滅瓟妗嗘灦 鈫?鑰冪敓琛ㄨ揪鈥濄€?
- `daily_question_skill.md` 宸叉槑纭?`exam_focus` / `review_key`銆乣breaking_hint`銆乣answer_framework` / `answer_frame` 鐨勫瓧娈靛惈涔夊拰灞曠ず鍏崇郴銆?
- `daily_question_skill.md` 宸叉柊澧炩€滀笁灞傝竟鐣屸€濈珷鑺傘€佸悎鏍?涓嶅悎鏍肩ず渚嬪拰鑷椤广€?
- `quality_checks.md` 宸叉柊澧?`Check 7.7锛氬棰樺叧閿€佷綔绛斾富绾裤€佷綔绛旀鏋舵槸鍚﹁竟鐣屾竻妤歚銆?
- `quality_checks.md` 宸叉妸浠婃棩涓€棰樺畬鏁寸粨鏋勪粠鈥滃棰樺叧閿?+ 浣滅瓟妗嗘灦鈥濆崌绾т负鈥滃棰樺叧閿?+ 浣滅瓟涓荤嚎 + 浣滅瓟妗嗘灦鈥濄€?
- `quality_checks.md` 宸插垪鍑哄缓璁川妫€ code锛歚exam_focus_too_answer_like`銆乣breaking_hint_too_framework_like`銆乣breaking_hint_duplicates_framework`銆?

**鍚庣画寤鸿琛ラ綈**

1. Codex 瀹屾垚 `prompt_templates.py`銆乣email_renderer.py`銆乣question_quality.py` 鍚庯紝鍦ㄦ湰鏂囦欢杩藉姞浠ｇ爜灞傛敼鍔ㄨ褰曘€?
2. 鍚庣画濡傛柊澧炰粖鏃ヤ竴棰樺ソ/鍧忔牱渚嬶紝搴斾紭鍏堣鐩栤€滀笁灞傝竟鐣岄噸澶嶁€濈殑鍥炲綊鏍蜂緥銆?

### 2026-05-21锝滃悓姝?Harness 绱㈠紩涓殑闃呰椤哄簭鍜屼粖鏃ヤ竴棰樿竟鐣岃鍒?

**鏀瑰姩鍘熷洜**

`CHANGELOG_HARNESS.md` 鍜?`daily_question_boundary_rules.md` 宸茬粡寤虹珛锛屼絾 `content_harness/00_index.md` 浠嶆湭鎶婂畠浠撼鍏ユ€昏椤哄簭鍜屼粖鏃ヤ竴棰樺繀璇绘竻鍗曘€傚悗缁?Codex / Cursor 鍙兘鍙寜绱㈠紩璇绘枃浠讹紝浠庤€岄仐婕忔渶鏂拌竟鐣岃鍒欍€?

**宸叉敼鏂囦欢**

- `content_harness/00_index.md`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `content_harness/00_index.md` 鐨勬€昏椤哄簭宸插墠缃?`../CHANGELOG_HARNESS.md` 鍜?`../AGENTS.md`銆?
- 浠婃棩涓€棰樹慨鏀圭被鍨嬬殑蹇呰鏂囦欢宸插姞鍏?`daily_question_boundary_rules.md`銆?
- 浠婃棩涓€棰樸€佽€冪敓琛ㄨ揪璐ㄦ劅銆佽川妫€闂ㄧ绛夌浉鍏充慨鏀圭被鍨嬪潎鎻愮ず鍏堣 `CHANGELOG_HARNESS.md`銆?
- 浠婃棩涓€棰樼珷鑺傛柊澧炵‘璁ょ偣锛氬棰樺叧閿彧鎷嗛锛宍breaking_hint` 搴曞眰瀛楁涓嶆敼浣嗗睍绀鸿涔変负浣滅瓟涓荤嚎锛屼綔绛斾富绾夸笉鍐欐垚绗簩濂楁鏋讹紝浣滅瓟妗嗘灦鎵嶆寮忓垎鐐广€?

**鍚庣画寤鸿琛ラ綈**

1. Codex 瀹屾垚 `prompt_templates.py`銆乣email_renderer.py`銆乣question_quality.py` 鍚庯紝鍦ㄦ湰鏂囦欢杩藉姞浠ｇ爜灞傛敼鍔ㄨ褰曘€?
2. 缁х画鎶婁笁灞傝竟鐣岃鍒欏悓姝ヨ繘 `daily_question_skill.md` 鍜?`quality_checks.md`銆?

### 2026-05-21锝滃己鍒舵帴鎵嬪墠鍏堣鍙樻洿璁板綍

**鏀瑰姩鍘熷洜**

鐢ㄦ埛甯屾湜鍒涘缓涓€涓枃浠讹紝鎶婃瘡娆℃敼鍔ㄣ€佸綋鍓嶆渶鏂扮増琛屼负鍜屽悗缁敞鎰忎簨椤硅褰曚笅鏉ワ紝骞惰姹備互鍚庢瘡娆′慨鏀瑰墠鍏堣杩欎釜鏂囦欢銆?

**宸叉敼鏂囦欢**

- `AGENTS.md`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `AGENTS.md` 宸叉妸 `CHANGELOG_HARNESS.md` 璁句负鎺ユ墜椤圭洰鐨勭涓€闃呰鍏ュ彛銆?
- 鎵€鏈変慨鏀圭被鍨嬬殑蹇呰鏂囦欢涓兘鍔犲叆 `CHANGELOG_HARNESS.md`銆?
- 鍚庣画浠讳綍瑙勫垯銆丳rompt銆佽川妫€銆佹覆鏌撱€佸彂閫侀摼璺€佸綊妗ｉ摼璺垨閮ㄧ讲閰嶇疆鐨勮涓哄彉鍖栵紝閮藉繀椤诲悓姝ヨ拷鍔犲埌 `CHANGELOG_HARNESS.md`銆?

**鍚庣画寤鸿琛ラ綈**

1. 灏?`CHANGELOG_HARNESS.md` 涔熷姞鍏?`content_harness/00_index.md` 鐨勬€昏椤哄簭銆?
2. 鍚庣画姣忔鎻愪氦鍓嶆鏌ユ湰鏂囦欢鏄惁鍚屾鏇存柊銆?

### 2026-05-21锝滄柊澧炰粖鏃ヤ竴棰樹笁灞傝竟鐣屼笓椤硅鍒欐枃浠?

**鏀瑰姩鍘熷洜**

浠呭湪杩愯鏃?Prompt 涓啓瑙勫垯杩樹笉澶燂紝鍚庣画鏀?Prompt銆佽川妫€銆佹覆鏌撴垨鏍蜂緥鏃讹紝闇€瑕佷竴涓洿绋冲畾鐨勪笓椤硅鍒欐枃浠讹紝閬垮厤鈥滃棰樺叧閿?/ 浣滅瓟涓荤嚎 / 浣滅瓟妗嗘灦鈥濊竟鐣屽啀娆℃ā绯娿€?

**宸叉敼鏂囦欢**

- `content_harness/daily_question_boundary_rules.md`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

鏂板涓撻」瑙勫垯鏂囦欢锛屽浐瀹氫互涓嬬害瀹氾細

- `exam_focus` / `review_key` = 瀹￠鍏抽敭锛屽彧鎷嗛锛屼笉灞曞紑瀵圭瓥銆?
- `breaking_hint` = 浣滅瓟涓荤嚎锛屽簳灞傚瓧娈典笉鏀癸紝灞曠ず璇箟鏀逛负鈥滀綔绛斾富绾库€濄€?
- `answer_framework` / `answer_frame` = 浣滅瓟妗嗘灦锛岃礋璐ｆ寮忓垎鐐广€?

**鍚庣画寤鸿琛ラ綈**

1. 灏?`content_harness/daily_question_boundary_rules.md` 鍔犲叆 `AGENTS.md` 鍜?`content_harness/00_index.md` 鐨勫繀璇绘竻鍗曘€?
2. 鍚屾淇敼 `prompt_templates.py`銆乣question_quality.py`銆乣email_renderer.py`銆?

### 2026-05-21锝滄槑纭粖鏃ヤ竴棰樹笁灞傝竟鐣?

**鏀瑰姩鍘熷洜**

鐢ㄦ埛鍙嶉鈥滃棰樺叧閿€濆拰鈥滅牬棰樻彁绀衡€濆惈涔夌浉杩戯紱杩涗竴姝ヨ璁哄悗鍙戠幇锛屽鏋溾€滅牬棰樻彁绀衡€濈瓑浜庣瓟棰樿矾绾匡紝鍙堝彲鑳藉拰鈥滀綔绛旀鏋垛€濋噸澶嶃€傞渶瑕佹妸涓夎€呰竟鐣屽浐鍖栧埌瑙勫垯鍜岃繍琛?Prompt 涓€?

**宸叉敼鏂囦欢**

- `content_harness/runtime_prompt_rules.md`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- `breaking_hint` 搴曞眰瀛楁淇濈暀锛岄伩鍏嶇牬鍧?JSON schema 鍜屾棫浠ｇ爜鍏煎銆?
- 杩愯鏃惰涔夋敼涓衡€滀綔绛斾富绾库€濄€?
- 瀹￠鍏抽敭涓嶅緱鍐欐垚浣滅瓟璺嚎銆?
- 浣滅瓟涓荤嚎涓嶅緱鍐欐垚绗簩濂楃瓟棰樻鏋躲€?
- 浣滅瓟妗嗘灦璐熻矗姝ｅ紡鍒嗙偣锛屽苟涓庤€冪敓鐗堝弬鑰冪瓟妗堝垎宸ャ€?

**鍚庣画寤鸿琛ラ綈**

1. 鍦?`prompt_templates.py` 鐨?`JSON_SCHEMA_HINT` 涓悓姝ヤ慨鏀?`exam_focus`銆乣breaking_hint`銆乣answer_framework` 瀛楁璇存槑銆?
2. 鍦?`question_quality.py` 涓柊澧炰互涓嬭川妫€锛?
   - `exam_focus_too_answer_like`
   - `breaking_hint_duplicates_framework`
   - `breaking_hint_too_framework_like`
3. 鍦?`email_renderer.py` 涓妸灞曠ず鏍囬鈥滅牬棰樻彁绀衡€濇敼涓衡€滀綔绛斾富绾库€濄€?
4. 鍦?`content_harness/daily_question_skill.md` 鍜?`content_harness/quality_checks.md` 涓ˉ鍏呮寮忔枃妗ｈ鏄庛€?

## 鍘嗗彶鏀瑰姩

鏆傛棤鏇存棭浜哄伐鏁寸悊璁板綍銆傚悗缁闇€杩芥函鏇存棭鍙樻洿锛岃鏌ョ湅 Git commit history銆?
### 2026-06-01锝滄斂绛栧潗鏍囦娇鐢ㄥ巻鍙蹭笌 14 澶╁幓閲?
**鏀瑰姩鍘熷洜**

鈥滀粖鏃ユ斂绛栧潗鏍団€濆凡缁忔帴鍏?JSON銆佹覆鏌撳拰璐ㄦ锛岄渶瑕佸啀鍔犱竴灞傗€滀娇鐢ㄥ巻鍙?+ 杩?14 澶╁幓閲嶁€濓紝閬垮厤杩炵画澶氬ぉ閲嶅浣跨敤鍚屼竴鏀跨瓥鍘熸枃銆佸悓涓€鏉°€婃眰鏄€嬭〃杈炬垨鍚屼竴涓撻妗嗘灦銆?
**宸叉敼鏂囦欢**

- `policy_coordinate_usage_history.py`
- `policy_coordinate_matcher.py`
- `main.py`
- `scripts/check_policy_coordinate_usage_history.py`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鏂板 `data/policy_coordinate_usage_history.jsonl` 鐨勭嫭绔?JSONL 鍘嗗彶绠＄悊妯″潡锛岀己鏂囦欢鏃惰嚜鍔ㄤ娇鐢ㄧ┖鍘嗗彶锛屽潖琛屼細璺宠繃骞惰繑鍥?warning锛屼笉浼氫腑鏂富娴佺▼銆?
- `match_policy_coordinate_candidates(...)` 鏂板 `recent_usage` 鍙傛暟锛氳繎 14 澶╁唴閲嶅 `matched_policy_id` / `matched_qiushi_quote_id` 浼氬己闄嶆潈锛屽悓涓€ `matched_framework_id` 杩炵画浣跨敤浼氶檷鏉冿紝鍓嶄袱娆′富棰樼浉鍚屾椂涔熶細閬垮厤绗?3 澶╃户缁敤鍚屼竴涓婚銆?
- 濡傛灉娌℃湁鍏朵粬鍚堥€傛潗鏂欙紝鍏佽浣庝紭鍏堢骇閲嶅锛屼絾浼氬湪 `debug_scores.usage_history.selected_repeat_notes` 鍜岃繍琛屾棩蹇椾腑璇存槑涓轰粈涔堣繕鏄€変簡閲嶅椤广€?
- 鏂板 `build_policy_coordinate_usage_record(...)`锛屽湪鏁村皝閭欢鏈€缁堥€氳繃璐ㄦ鍚庯紝鍗曠嫭鍐欏叆 `policy_coordinate` 浣跨敤鍘嗗彶锛屼笉褰卞搷 `sent_history.json` 鍘熸湁閫昏緫銆?
- `nightly candidate`銆佹墜鍔ㄦ祴璇曞拰琚?quality gate 闃绘柇鐨勮繍琛屼細鏄剧ず skip reason锛屼笉鍐欏叆姝ゆ鍘婚噸鍘嗗彶銆?
- JSONL 鍐欏叆澶辫触鏃跺彧璁版棩蹇?warning锛屼笉浼氫腑鏂敓鎴愩€佸彂閫佹垨鍏朵粬褰掓。閾捐矾銆?
**鍚庣画娉ㄦ剰浜嬮」**

1. 褰撳墠 usage history 鏁呮剰涓嶅拰 `sent_history.json` 鍏变韩瀛樺偍锛屽悗缁闇€ OSS 鍖栵紝搴斿崟鐙璁℃柊鐨勫瓨鍌ㄦā寮忥紝涓嶈鐩存帴鎼敤 `sent_history` 閫昏緫銆?
2. 鐩墠鍘婚噸鍘嗗彶鍙拡瀵归潪 candidate / 闈炴祴璇?/ 闈炴暣浣撻樆鏂繍琛岃繘琛岃褰曪紝濡傛灉鍚庣画甯屾湜璁?preview 涔熷弬涓庡幓閲嶏紝搴斿崟鐙瘎浼版槸鍚﹀奖鍝嶆寮忔櫒鍙戙€?
### 2026-06-02锝滄斂绛栧潗鏍囦富棰樿瘯璺戜笌鎺ュ叆鎶ュ憡
**鏀瑰姩鍘熷洜**

鍦ㄥ墠 7 涓换鍔″畬鎴愬悗锛岄渶瑕佸仛 3 涓富棰樿瘯璺戯紝楠岃瘉 `policy_coordinate` 鍦?daily JSON銆丠TML銆乸lain_text銆佽川妫€鍜岃繎 14 澶╁幓閲嶉摼璺腑鐨勫疄闄呰〃鐜帮紝骞舵矇娣€涓€浠藉彲浜ゆ帴鐨勬帴鍏ユ姤鍛娿€?
**宸叉敼鏂囦欢**

- `main.py`
- `scripts/run_policy_coordinate_trials.py`
- `docs/POLICY_COORDINATE_INTEGRATION_REPORT.md`
- `output/policy_coordinate_trials/*`
- `CHANGELOG_HARNESS.md`

**鏈€鏂扮増琛屼负**

- 鏂板 `scripts/run_policy_coordinate_trials.py`锛屽鐢?`candidates/latest.json` 鐨勫畬鏁?brief 缁撴瀯锛屾瀯閫?3 缁勬ā鎷熶富棰樿緭鍏ュ苟璧扮幇鏈夋斂绛栧尮閰嶃€佹覆鏌撳拰璐ㄦ閾捐矾銆?
- 璇曡窇涓婚瑕嗙洊锛氬熀灞傛不鐞?/ 鏂板氨涓氱兢浣?/ 鍩庡競娌荤悊锛涢珮璐ㄩ噺鍙戝睍 / 鏂拌川鐢熶骇鍔涳紱姘戠敓淇濋殰 / 灏变笟銆?
- 璇曡窇浼氳緭鍑?`daily.json`銆乣email.html`銆乣plain_text.txt`銆乣quality.json`銆乣run.log` 鍒?`output/policy_coordinate_trials/<slug>/`銆?
- 璇曡窇浣跨敤闅旂鐨?`policy_coordinate_usage_history.jsonl`锛岄獙璇?14 澶╁幓閲嶉€昏緫鍙繍琛岋紝鍚屾椂涓嶆薄鏌撴寮忕敓浜у巻鍙层€?
- `main.py` 澧炲姞浜嗗 `exam_transfer` 鐨勪簩娆″厹搴曪細褰撳尮閰嶅埌鐨勬斂绛栬鏂?`exam_usage` 杩囦簬灞曠ず鍖栥€佺己灏戝叿浣撶瓟棰樿搴︽椂锛屼細鍥為€€涓虹▼搴忕敓鎴愮殑缁撴瀯鍖栬€冨満杩佺Щ鍙ャ€?
- 鑷姩鐢熸垚 `docs/POLICY_COORDINATE_INTEGRATION_REPORT.md`锛屾眹鎬绘枃浠舵敼鍔ㄣ€佺煡璇嗗簱璇诲彇銆佸瓧娈点€佹覆鏌撲綅缃€佽川妫€瑙勫垯銆? 涓牱渚嬬粨鏋溿€侀闄╀笌 OSS 鍒囨崲璇存槑銆?
**鍚庣画娉ㄦ剰浜嬮」**

1. 褰撳墠璇曡窇楠岃瘉鐨勬槸鈥滄斂绛栧潗鏍囨帴鍏ラ摼璺€濊€屼笉鏄€滅湡瀹為€夋枃璐ㄩ噺鈥濓紝鍚庣画涓婄嚎鍓嶄粛搴旂粨鍚堢湡瀹炴姄鍙栨枃绔犳娊鏍峰鏍稿嚑杞€?
2. 濡傛灉鍚庣画瀹炵幇鐭ヨ瘑搴?OSS 璇诲彇锛屽缓璁悓姝ユ妸璇曡窇鑴氭湰鏀规垚鍙垏鎹?`local/oss` 涓ょ妯″紡锛岄伩鍏嶆姤鍛婁笌鐢熶骇琛屼负鍒嗗弶銆?
