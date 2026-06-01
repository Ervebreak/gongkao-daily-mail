from __future__ import annotations

import copy
import json
import shutil
import sys
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import requests as _requests  # type: ignore
except Exception:
    requests_stub = types.ModuleType("requests")
    requests_stub.packages = types.SimpleNamespace(
        urllib3=types.SimpleNamespace(disable_warnings=lambda *args, **kwargs: None)
    )
    requests_stub.get = lambda *args, **kwargs: None
    requests_stub.post = lambda *args, **kwargs: None
    requests_stub.put = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

from brief_schema import ensure_brief_schema
from email_renderer import render_email_html, render_plain_text
from knowledge_base_loader import (
    load_policy_all,
    load_policy_core,
    load_qiushi_quotes_candidates,
    load_qiushi_quotes_core,
)
from logger import RunLogger
from main import (
    build_policy_coordinate_usage_record,
    ensure_policy_coordinate_for_render,
    enforce_policy_coordinate_quality,
)
from policy_coordinate_matcher import match_policy_coordinate_candidates
from policy_coordinate_quality import evaluate_policy_coordinate_quality
import policy_coordinate_usage_history as usage_history_module
from policy_coordinate_usage_history import (
    append_policy_coordinate_usage,
    load_policy_coordinate_usage_history,
    recent_policy_coordinate_usage,
)


TRIAL_OUTPUT_DIR = ROOT / "output" / "policy_coordinate_trials"
TRIAL_HISTORY_PATH = TRIAL_OUTPUT_DIR / "policy_coordinate_usage_history.jsonl"
REPORT_PATH = ROOT / "docs" / "POLICY_COORDINATE_INTEGRATION_REPORT.md"
BASE_CANDIDATE_PATH = ROOT / "candidates" / "latest.json"


TRIAL_CASES: list[dict[str, Any]] = [
    {
        "slug": "grassroots_governance",
        "date": "2026-06-01",
        "email_subject": "把新就业群体变成基层治理合伙人",
        "today_theme": "基层治理 / 新就业群体 / 城市治理",
        "today_focus": "抓住平台搭建、诉求收集、协同处置和力量转化四个环节，把骑手等新就业群体从服务对象变成治理参与者。",
        "must_remember_sentence": "基层治理不是政府单向管理，而是把群众和新就业群体真正组织起来、吸纳进来、作用发挥出来。",
        "daily_question_short": "如果你是街道办工作人员，如何把外卖骑手、快递员等新就业群体更好吸纳进社区治理？",
        "featured": {
            "title": "“小哥议事厅”让骑手成为社区治理新力量",
            "source": "人民日报",
            "published_at": "2026-06-01",
            "url": "https://example.com/trials/grassroots-governance",
            "theme": "基层治理",
            "one_sentence": "一些城市通过议事厅、骑手驿站、随手拍上报等机制，把新就业群体纳入城市治理链条，让他们既能被服务，也能反哺治理。",
            "three_useful_points": [
                "过去对骑手更多停留在管理和服务层面，现在开始把他们吸纳进社区协商、风险预警和文明劝导环节。",
                "基层最缺的不是事项，而是对流动群体需求和问题的及时感知，骑手最熟悉街面情况，能补上治理触角。",
                "治理平台不是多开会，而是要让诉求收集、部门响应、结果反馈形成闭环，真正把参与意愿转化为治理效能。",
            ],
            "exam_use": [
                "申论对策可从建平台、畅诉求、强协同、促闭环四步展开，体现多元共治和基层精细化治理。",
                "面试综合分析可强调把新就业群体从被管理对象转化为治理共同体成员，增强城市治理的感知力和响应力。",
            ],
            "rewritable_expression": "抓基层治理，既要把服务做到位，也要把群众组织起来，让流动中的治理资源沉下来、用起来。",
            "original_reading_focus": "重点看议事厅如何设置参与入口，街道、社区和平台企业怎样共建共治，以及骑手意见如何进入办理闭环。",
            "framework_style": "吸纳主体进入平台 → 畅通诉求收集 → 强化协同办理 → 形成治理闭环",
            "framework_steps": [
                ("把群体吸纳进来", "依托骑手驿站、议事厅和网格联络员，为外卖骑手、快递员设置固定参与入口。"),
                ("把问题收集上来", "通过随手拍、微建议、线上工单等方式，让骑手把路面隐患、秩序问题和群众急难及时反馈。"),
                ("把部门协同起来", "街道统筹社区、城管、物业和平台企业联动办理，避免意见收了没人管、问题转了没人接。"),
                ("把结果闭环落下去", "及时反馈处置结果并吸纳优秀骑手担任流动网格员，让参与有回应、有激励、有持续性。"),
            ],
            "exam_tags": ["基层治理", "新就业群体", "城市精细化治理"],
        },
        "question": {
            "question_type": "申论对策题",
            "question": "如果你是街道办工作人员，如何把外卖骑手、快递员等新就业群体更好吸纳进社区治理？",
            "exam_focus": "核心是把新就业群体纳入治理体系，既解决服务覆盖问题，也解决参与机制和协同闭环问题。",
            "breaking_hint": "作答不能只谈关爱服务，要把平台建设、诉求表达、部门协同和激励反馈一起写出来。",
            "answer_framework": [
                "建平台入口：依托驿站和议事厅设置稳定参与渠道。",
                "畅诉求收集：用线上工单和随手拍汇聚一线问题。",
                "强协同办理：街道统筹社区、物业和平台企业联动处置。",
                "促激励闭环：及时反馈结果并让优秀骑手常态化参与治理。",
            ],
            "candidate_answer": "要把新就业群体吸纳进社区治理，关键是把他们从“被服务者”转化为“参与者”。第一，搭建稳定参与平台，依托骑手驿站、社区议事厅和网格联络点，设置固定议事和反馈入口。第二，畅通问题收集渠道，推广随手拍、微建议、线上工单，让骑手把路面设施损坏、停车秩序混乱、楼道安全隐患等问题及时上传。第三，强化协同办理机制，由街道统筹社区、城管、物业和平台企业联动响应，做到有人接单、限时办理、结果反馈。第四，完善激励和保障，对积极参与治理的骑手在评优激励、驿站服务、企业评价等方面予以体现，让治理参与形成常态、形成闭环。",
            "thirty_second_answer": "我会从搭平台、收问题、强协同、促反馈四个环节入手，把骑手纳入社区治理闭环，让他们既能被服务，也能参与治理。",
            "output_prompt": "请用一句话概括把新就业群体吸纳进基层治理的核心思路。",
            "output_sentence_template": "把新就业群体吸纳进基层治理，关键不是简单增加服务，而是为他们搭平台、给渠道、建闭环，让流动治理资源真正发挥作用。",
            "topic_category": "基层治理 / 新就业群体",
        },
        "takeaway": {
            "keywords": ["基层治理", "新就业群体", "共建共治共享", "城市治理"],
            "common_knowledge_points": ["基层治理要从单向管理转向多元协同，把治理对象转化为治理力量。"],
            "golden_sentences": [
                "治理越精细，越要把一线群众和流动群体组织起来、吸纳进来。",
                "平台不是摆设，平台要能收诉求、转任务、看反馈、促闭环。",
            ],
            "framework": "建平台、畅诉求、聚力量、促闭环",
        },
        "quick_reads": [
            {
                "title": "社区驿站延伸服务链条，增强新就业群体归属感",
                "source": "人民网评",
                "published_at": "2026-06-01",
                "url": "https://example.com/trials/grassroots-governance-quick-1",
                "exam_value": "可补充说明基层治理既要吸纳参与，也要做好服务保障，增强群体认同。",
                "one_sentence": "服务做实，参与才有持续性。",
            },
            {
                "title": "城市治理要善于从流动场景中发现治理线索",
                "source": "浙江宣传",
                "published_at": "2026-06-01",
                "url": "https://example.com/trials/grassroots-governance-quick-2",
                "exam_value": "可补充城市精细化治理中如何提升问题发现能力和快速响应能力。",
                "one_sentence": "治理触角要延伸到街面最活跃的流动群体。",
            },
        ],
    },
    {
        "slug": "new_quality_productivity",
        "date": "2026-06-02",
        "email_subject": "以科技创新牵引新质生产力加快形成",
        "today_theme": "高质量发展 / 新质生产力",
        "today_focus": "围绕创新链、产业链、资金链和人才链协同发力，把科技成果转化、产业升级和未来产业培育放到同一条主线上。",
        "must_remember_sentence": "发展新质生产力，不是另起炉灶，而是让科技创新真正穿透产业、带动升级、塑造新优势。",
        "daily_question_short": "如果你是市发改委工作人员，如何推动科技创新更快转化为新质生产力？",
        "featured": {
            "title": "让科技成果加速转化为看得见的新质生产力",
            "source": "新华社",
            "published_at": "2026-06-02",
            "url": "https://example.com/trials/new-quality-productivity",
            "theme": "新质生产力",
            "one_sentence": "一些地方围绕成果转化、中试验证、金融支持和人才集聚联动发力，让创新成果更快进入产业化场景，推动传统产业升级和未来产业培育同步突破。",
            "three_useful_points": [
                "科技成果转化慢，往往不是技术本身不行，而是中试验证、应用场景和金融配套跟不上。",
                "发展新质生产力不能只盯未来产业，也要推动传统产业高端化、智能化、绿色化升级。",
                "高质量发展要把创新链、产业链、资金链、人才链贯通起来，形成从研发到应用的完整闭环。",
            ],
            "exam_use": [
                "申论可从强创新平台、补转化环节、育应用场景、优要素配置四个角度展开。",
                "面试可强调发展新质生产力既要向前布局未来产业，也要向内改造传统产业，形成新旧动能接续转换。",
            ],
            "rewritable_expression": "新质生产力不是停留在实验室里的新概念，而是要通过成果转化、场景牵引和要素协同，变成能支撑高质量发展的现实增量。",
            "original_reading_focus": "重点看地方怎样打通中试验证、场景开放、科技金融和人才保障，让创新成果真正跨过“最后一公里”。",
            "framework_style": "做强创新平台 → 打通转化堵点 → 培育应用场景 → 优化要素配置",
            "framework_steps": [
                ("做强创新平台", "统筹实验室、产业研究院和技术转移中心建设，增强关键核心技术研发和成果承接能力。"),
                ("打通转化堵点", "围绕中试验证、知识产权运用和标准衔接补齐短板，让技术从样品走向产品。"),
                ("培育应用场景", "通过政府采购、重点工程和揭榜挂帅机制开放场景，让新技术先试先用、边用边优。"),
                ("优化要素配置", "强化科技金融、产业基金和人才政策协同，把资金、人才和项目配置到最需要的环节。"),
            ],
            "exam_tags": ["高质量发展", "新质生产力", "科技创新"],
        },
        "question": {
            "question_type": "申论对策题",
            "question": "如果你是市发改委工作人员，如何推动科技创新更快转化为新质生产力？",
            "exam_focus": "关键是打通成果转化链条，让科技创新真正进入产业、形成增量，并带动传统产业升级。",
            "breaking_hint": "不能只写“加大研发投入”，要把平台建设、中试验证、应用场景和要素保障写实写细。",
            "answer_framework": [
                "强平台支撑：提升实验室和转移中心承接能力。",
                "补转化环节：围绕中试验证和知识产权运用疏堵点。",
                "育应用场景：让新技术在工程和市场中先试先用。",
                "优要素供给：协同金融、基金和人才政策精准滴灌。",
            ],
            "candidate_answer": "推动科技创新更快转化为新质生产力，关键在于打通从研发到产业化的全链条。第一，做强平台支撑，统筹实验室、产业研究院、技术转移中心等载体，提升关键技术研发和成果承接能力。第二，补齐转化环节短板，围绕中试验证、知识产权运用、标准制定等关键节点建立服务体系，让科技成果顺利跨越样品到产品、产品到产业的门槛。第三，培育应用场景，通过政府采购、重点工程、揭榜挂帅等方式开放更多试验场和首用场，让新技术在真实需求中迭代成熟。第四，优化要素供给，推动科技金融、产业基金、人才政策协同发力，把资金、人才和项目精准配置到最关键的环节，形成创新链和产业链深度耦合的转化闭环。",
            "thirty_second_answer": "我会围绕平台支撑、转化服务、场景开放和要素协同四个方面发力，让科技成果更快转化为新质生产力。",
            "output_prompt": "请用一句话概括发展新质生产力的抓手。",
            "output_sentence_template": "发展新质生产力，关键是把科技创新这个“源头活水”通过转化、场景和要素协同，变成支撑高质量发展的现实生产力。",
            "topic_category": "新质生产力 / 高质量发展",
        },
        "takeaway": {
            "keywords": ["高质量发展", "新质生产力", "科技创新", "现代化产业体系"],
            "common_knowledge_points": ["新质生产力强调以科技创新为核心驱动，兼顾传统产业升级和未来产业培育。"],
            "golden_sentences": [
                "创新成果只有进入产业、形成增量，才能真正转化为新质生产力。",
                "抓新质生产力，要把创新链、产业链、资金链、人才链拧成一股绳。",
            ],
            "framework": "强创新、补转化、育场景、优要素",
        },
        "quick_reads": [
            {
                "title": "传统产业升级是发展新质生产力的重要落点",
                "source": "人民网评",
                "published_at": "2026-06-02",
                "url": "https://example.com/trials/new-quality-productivity-quick-1",
                "exam_value": "可补充说明新质生产力并非只面向未来产业，也面向传统产业改造提升。",
                "one_sentence": "新与旧不是割裂关系，而是升级与培育并进。",
            },
            {
                "title": "开放应用场景是科技成果转化的重要一环",
                "source": "浙江宣传",
                "published_at": "2026-06-02",
                "url": "https://example.com/trials/new-quality-productivity-quick-2",
                "exam_value": "可补充政府如何通过场景开放牵引技术落地和企业成长。",
                "one_sentence": "场景是检验技术、催熟产业的重要土壤。",
            },
        ],
    },
    {
        "slug": "employment_security",
        "date": "2026-06-03",
        "email_subject": "把公共就业服务送到群众家门口",
        "today_theme": "民生保障 / 就业",
        "today_focus": "围绕高校毕业生、就业困难群体和灵活就业人员，把岗位供给、技能培训、服务下沉和兜底帮扶贯通起来。",
        "must_remember_sentence": "就业工作不是简单发岗位，而是把岗位、培训、服务和兜底一体推进，真正提高就业匹配度和稳定性。",
        "daily_question_short": "如果你是人社局工作人员，如何提升公共就业服务的可及性和有效性？",
        "featured": {
            "title": "公共就业服务要从“有人管”走向“更好用”",
            "source": "人民网评",
            "published_at": "2026-06-03",
            "url": "https://example.com/trials/employment-security",
            "theme": "民生保障",
            "one_sentence": "一些地方把就业服务站建到园区、社区和商圈，结合岗位归集、技能培训、重点群体帮扶和数字匹配，让求职服务更下沉、更精准、更有温度。",
            "three_useful_points": [
                "就业服务存在“看得见但够不着”的问题，群众最需要的是离得近、找得到、能解决实际问题的服务触点。",
                "岗位供需错位往往不是岗位总量不够，而是信息不对称、技能不匹配和重点群体服务不到位。",
                "稳就业要把岗位归集、技能培训、分类帮扶和兜底保障联动起来，形成公共服务闭环。",
            ],
            "exam_use": [
                "申论对策可从服务下沉、精准匹配、培训赋能、兜底帮扶四个角度展开。",
                "面试可强调就业优先要落到服务可及性和政策精准度上，让群众在家门口找到机会、获得帮助。",
            ],
            "rewritable_expression": "公共就业服务不是“坐等来办”，而是要主动下沉、精准匹配、分类帮扶，把政策温度真正传导到群众身边。",
            "original_reading_focus": "重点看服务站点如何布设，岗位与培训怎样联动，重点群体如何分类施策，数字平台怎样提升匹配效率。",
            "framework_style": "服务下沉到身边 → 岗位培训相衔接 → 分类帮扶更精准 → 兜底保障不断线",
            "framework_steps": [
                ("服务站点下沉", "把就业服务站布局到社区、园区、商圈和零工市场，让群众在家门口就能咨询、登记和求职。"),
                ("岗位培训衔接", "同步归集岗位信息和培训资源，围绕企业缺工方向开展订单式、项目制培训。"),
                ("重点群体分类帮扶", "针对高校毕业生、就业困难人员和灵活就业者建立分层分类服务台账，提供有针对性的岗位推荐和政策辅导。"),
                ("兜底保障不断线", "对长期失业和困难家庭成员强化公益岗位、帮扶补贴和就业援助，守住基本民生底线。"),
            ],
            "exam_tags": ["民生保障", "高质量充分就业", "公共服务均等化"],
        },
        "question": {
            "question_type": "申论对策题",
            "question": "如果你是人社局工作人员，如何提升公共就业服务的可及性和有效性？",
            "exam_focus": "重点不只是“提供岗位”，而是把岗位、培训、帮扶和兜底服务做成闭环，提高服务命中率和就业稳定性。",
            "breaking_hint": "作答要体现服务下沉、岗位培训衔接、重点群体分类帮扶和兜底保障，避免只停留在宣传政策层面。",
            "answer_framework": [
                "下沉服务站点：把服务触角延伸到社区园区商圈。",
                "做实岗位培训：推动岗位归集与技能培训联动。",
                "强化分类帮扶：对重点群体建立分层服务台账。",
                "兜牢民生底线：用援助岗位和补贴政策托底。",
            ],
            "candidate_answer": "提升公共就业服务的可及性和有效性，要把“群众找服务”转变为“服务找群众”。第一，下沉服务站点，把公共就业服务延伸到社区、园区、商圈和零工市场，让群众在家门口就能咨询、登记和求职。第二，做实岗位培训衔接，同步归集岗位需求和培训资源，围绕企业急需紧缺岗位开展订单式、项目制培训，提升供需匹配度。第三，强化重点群体分类帮扶，针对高校毕业生、就业困难人员、灵活就业者建立分层服务台账，提供岗位推荐、政策辅导、职业指导等精准服务。第四，兜牢民生底线，对长期失业和困难家庭成员强化公益岗位、帮扶补贴和就业援助，确保基本生活和就业机会不断线。",
            "thirty_second_answer": "我会从服务下沉、岗位培训联动、重点群体分类帮扶和兜底保障四个方面提升公共就业服务质效。",
            "output_prompt": "请用一句话概括如何把就业服务送到群众家门口。",
            "output_sentence_template": "做好就业服务，关键是把服务站点沉下去、把岗位培训接起来、把重点群体扶上来、把兜底保障托起来。",
            "topic_category": "民生保障 / 就业",
        },
        "takeaway": {
            "keywords": ["民生保障", "高质量充分就业", "公共服务均等化", "就业优先"],
            "common_knowledge_points": ["就业优先既要扩岗位，也要优服务、强培训、托底线。"],
            "golden_sentences": [
                "就业工作越到基层，越要把服务做到家门口、做到心坎上。",
                "岗位供给、技能培训和重点帮扶要同向发力，才能提高就业稳定性。",
            ],
            "framework": "沉服务、强匹配、分类扶、稳兜底",
        },
        "quick_reads": [
            {
                "title": "技能培训要更贴近企业需求和岗位变化",
                "source": "新华社",
                "published_at": "2026-06-03",
                "url": "https://example.com/trials/employment-security-quick-1",
                "exam_value": "可补充就业服务不能只推岗位，还要提高劳动者技能匹配度。",
                "one_sentence": "培训要围着岗位转，围着就业转。",
            },
            {
                "title": "零工市场规范化建设提升灵活就业服务温度",
                "source": "浙江宣传",
                "published_at": "2026-06-03",
                "url": "https://example.com/trials/employment-security-quick-2",
                "exam_value": "可补充灵活就业群体服务保障和公共服务均等化表达。",
                "one_sentence": "灵活就业群体也需要稳定、可及、可信的公共服务支撑。",
            },
        ],
    },
]


def load_base_brief() -> dict[str, Any]:
    payload = json.loads(BASE_CANDIDATE_PATH.read_text(encoding="utf-8-sig"))
    brief = payload.get("brief") if isinstance(payload.get("brief"), dict) else {}
    if not brief:
        raise RuntimeError(f"brief not found in {BASE_CANDIDATE_PATH}")
    return brief


def build_featured_article(case: dict[str, Any]) -> dict[str, Any]:
    featured = case["featured"]
    steps = [
        {"label": label, "content": content}
        for label, content in featured["framework_steps"]
    ]
    framework_map = {
        "type": case["today_theme"],
        "article_type": case["today_theme"],
        "main_thread": featured["one_sentence"],
        "framework_style": featured["framework_style"],
        "steps": steps,
        "exam_tags": featured["exam_tags"],
        "overall_exam_value": " / ".join(featured["exam_tags"]),
        "self_check": "已补齐文章框架、考试价值和结构闭环字段。",
    }
    article_framework = [f"{item['label']}：{item['content']}" for item in steps]
    return {
        "title": featured["title"],
        "source": featured["source"],
        "published_at": featured["published_at"],
        "url": featured["url"],
        "theme": featured["theme"],
        "one_sentence": featured["one_sentence"],
        "three_useful_points": featured["three_useful_points"],
        "exam_use": featured["exam_use"],
        "rewritable_expression": featured["rewritable_expression"],
        "original_reading_focus": featured["original_reading_focus"],
        "article_framework_map": framework_map,
        "original_overview": [featured["one_sentence"]],
        "core_viewpoint": featured["one_sentence"],
        "main_thread": featured["one_sentence"],
        "article_type": case["today_theme"],
        "article_framework": article_framework,
        "structure_breakdown": article_framework,
        "usable_for_exam": featured["exam_use"],
        "exam_conversion": featured["exam_use"],
        "golden_sentences": [],
        "url_status": "valid",
        "url_status_reason": "trial fixture",
    }


def build_trial_brief(base_brief: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    brief = copy.deepcopy(base_brief)
    brief["email_subject"] = case["email_subject"]
    brief["date"] = case["date"]
    brief["today_theme"] = case["today_theme"]
    brief["today_focus"] = case["today_focus"]
    brief["today_three_things"] = {
        "theme": case["today_theme"],
        "must_remember_sentence": case["must_remember_sentence"],
        "daily_question": case["daily_question_short"],
    }
    brief["featured_article"] = build_featured_article(case)
    question = case["question"]
    brief["daily_question"] = {
        "question_type": question["question_type"],
        "question": question["question"],
        "exam_focus": question["exam_focus"],
        "breaking_hint": question["breaking_hint"],
        "answer_framework": question["answer_framework"],
        "answer_frame": question["answer_framework"],
        "candidate_answer": question["candidate_answer"],
        "thirty_second_answer": question["thirty_second_answer"],
        "output_prompt": question["output_prompt"],
        "output_sentence_template": question["output_sentence_template"],
        "question_source": "featured",
        "question_source_title": case["featured"]["title"],
        "breaking_direction": question["breaking_hint"],
        "topic_category": question["topic_category"],
        "review_key": question["exam_focus"],
        "conflicts": [
            "政策目标和基层落地之间存在堵点。",
            "资源配置和群众需求之间存在错位。",
            "短期见效和长效治理之间需要衔接。",
        ],
    }
    takeaway = case["takeaway"]
    brief["today_takeaway"] = {
        "keywords": takeaway["keywords"],
        "common_knowledge_points": takeaway["common_knowledge_points"],
        "golden_sentences": takeaway["golden_sentences"],
        "framework": takeaway["framework"],
    }
    brief["quick_reads"] = copy.deepcopy(case["quick_reads"])
    brief["policy_coordinate"] = {}
    brief.pop("_policy_coordinate_disabled_reason", None)
    return brief


def verify_trial(case: dict[str, Any], brief: dict[str, Any], plain_text: str, html_body: str, quality: dict[str, Any]) -> dict[str, Any]:
    coordinate = brief.get("policy_coordinate") if isinstance(brief.get("policy_coordinate"), dict) else {}
    policy_lookup = {item.get("policy_id"): item for item in load_policy_core() + load_policy_all()}
    quote_lookup = {item.get("quote_id"): item for item in load_qiushi_quotes_core() + load_qiushi_quotes_candidates()}
    matched_policy = policy_lookup.get(coordinate.get("matched_policy_id"))
    matched_quote = quote_lookup.get(coordinate.get("matched_qiushi_quote_id")) if coordinate.get("matched_qiushi_quote_id") else None
    repeated_line = html_body.count("今日政策坐标")
    checks = {
        "daily_json_has_policy_coordinate": bool(coordinate),
        "html_has_policy_coordinate": "今日政策坐标" in html_body,
        "plain_text_has_policy_coordinate": "今日政策坐标" in plain_text,
        "policy_quote_from_policy_corpus": bool(matched_policy),
        "authoritative_quote_from_topic_knowledge": (not coordinate.get("authoritative_quote")) or bool(matched_quote),
        "qiushi_not_rendered_as_policy_quote": (
            not coordinate.get("authoritative_quote")
            or coordinate.get("policy_quote") != coordinate.get("authoritative_quote")
        ) and ("求是" not in str(coordinate.get("policy_source") or "")),
        "article_connection_specific": len(str(coordinate.get("article_connection") or "")) >= 20,
        "exam_transfer_specific": len(str(coordinate.get("exam_transfer") or "")) >= 20 and len(coordinate.get("answer_angles") or []) >= 3,
        "no_truncated_sentence": not any(issue.get("code") == "incomplete_sentence" for issue in quality.get("issues") or []),
        "no_obvious_duplication": not any(issue.get("code") == "duplicate_content" for issue in quality.get("issues") or []),
        "quality_check_passed": bool(quality.get("ok")),
        "render_title_not_duplicated": repeated_line == 1,
    }
    checks["all_passed"] = all(checks.values())
    return {
        "case_slug": case["slug"],
        "checks": checks,
        "matched_policy_source_title": matched_policy.get("source_title") if matched_policy else "",
        "matched_qiushi_source_title": matched_quote.get("source_title") if matched_quote else "",
    }


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def build_report_markdown(
    trial_results: list[dict[str, Any]],
    dedupe_probe: dict[str, Any],
) -> str:
    sample_blocks: list[str] = []
    for item in trial_results:
        coordinate = item["brief"]["policy_coordinate"]
        sample_blocks.append(
            "\n".join(
                [
                    f"### {item['label']}",
                    f"- 主题：`{coordinate.get('theme')}`",
                    f"- 政策原文：{coordinate.get('policy_source')}提出，“{coordinate.get('policy_quote')}”。",
                    (
                        f"- 权威论述：{coordinate.get('authoritative_source')}强调，“{coordinate.get('authoritative_quote')}”。"
                        if coordinate.get("authoritative_quote") and coordinate.get("authoritative_source")
                        else "- 权威论述：本样例未展示《求是》权威论述。"
                    ),
                    f"- 文章落点：{coordinate.get('article_connection')}",
                    f"- 考场迁移：{coordinate.get('exam_transfer')}",
                    f"- 答题角度：{'；'.join(coordinate.get('answer_angles') or [])}",
                ]
            )
        )

    files_list = [
        "config.py",
        "knowledge_base_loader.py",
        "policy_coordinate_matcher.py",
        "policy_coordinate_usage_history.py",
        "policy_coordinate_quality.py",
        "email_renderer.py",
        "main.py",
        "scripts/check_knowledge_base_loader.py",
        "scripts/check_policy_coordinate_matcher.py",
        "scripts/check_policy_coordinate_usage_history.py",
        "scripts/run_policy_coordinate_trials.py",
        "docs/POLICY_COORDINATE_INTEGRATION_REPORT.md",
        "knowledge_base/policy_corpus/policy_statements_core.jsonl",
        "knowledge_base/policy_corpus/policy_statements.jsonl",
        "knowledge_base/topic_knowledge/article_index.jsonl",
        "knowledge_base/topic_knowledge/article_chunks.jsonl",
        "knowledge_base/topic_knowledge/authoritative_quotes_core.jsonl",
        "knowledge_base/topic_knowledge/authoritative_quotes_candidates.jsonl",
        "knowledge_base/topic_knowledge/topic_frameworks.jsonl",
    ]
    kb_files = [
        "knowledge_base/policy_corpus/policy_statements_core.jsonl",
        "knowledge_base/policy_corpus/policy_statements.jsonl",
        "knowledge_base/topic_knowledge/article_index.jsonl",
        "knowledge_base/topic_knowledge/article_chunks.jsonl",
        "knowledge_base/topic_knowledge/authoritative_quotes_core.jsonl",
        "knowledge_base/topic_knowledge/authoritative_quotes_candidates.jsonl",
        "knowledge_base/topic_knowledge/topic_frameworks.jsonl",
        "data/policy_coordinate_usage_history.jsonl",
    ]
    fields = [
        "`policy_coordinate.theme`",
        "`policy_coordinate.policy_quote` / `policy_source` / `policy_source_type` / `policy_translation`",
        "`policy_coordinate.authoritative_quote` / `authoritative_source`",
        "`policy_coordinate.article_connection` / `exam_transfer` / `answer_angles`",
        "`policy_coordinate.matched_policy_id` / `matched_qiushi_quote_id` / `matched_qiushi_article_id` / `matched_framework_id` / `matched_chunk_ids`",
        "`policy_coordinate.source_type`",
        "`quote_status` / `display_priority` / `theme_confidence` / `display_ready` / `usage_tier` / `freshness`（语料清洗字段）",
        "`data/policy_coordinate_usage_history.jsonl` 的 `date` / `theme` / `matched_*` / `policy_quote` / `authoritative_quote`",
    ]
    quality_rules = [
        "有 `policy_coordinate` 时，`policy_quote`、`policy_source`、`policy_translation`、`article_connection`、`exam_transfer` 不得为空。",
        "`policy_quote` 不超过 90 字；`authoritative_quote` 如存在不超过 120 字。",
        "`authoritative_quote` 如存在，必须同时存在 `authoritative_source`。",
        "不得把《求是》论述写成政策原文，也不得出现“某领导人指出”但没有具体来源。",
        "`matched_policy_id` 必须能在政策库中找到；`matched_qiushi_quote_id` 如存在必须能在《求是》表达库中找到。",
        "不得出现半截句、空泛转译、与今日精读/今日可带走/今日一题大段重复。",
        "《求是》权威论述不合格时自动删除；政策原文不合格时尝试重匹配，仍失败则隐藏整个模块。",
    ]
    risks = [
        "当前知识库加载器仍是本地文件读取，`KNOWLEDGE_BASE_MODE=oss` 只完成了配置预留，尚未实现 OSS 拉取逻辑。",
        "近 14 天去重目前依赖运行时历史文件；正式去重效果取决于生产环境是否持续保留 `data/policy_coordinate_usage_history.jsonl`。",
        "不同主题下《求是》权威论述的可召回性不完全均衡，部分样例可能只展示政策原文而不展示《求是》论述。",
        "试跑使用的是模拟文章输入，能验证链路和质量门槛，但不等同于真实抓取文章的最终选题表现。",
    ]

    checks_lines: list[str] = []
    for item in trial_results:
        checks_lines.append(f"### {item['label']}")
        for key, value in item["verification"]["checks"].items():
            checks_lines.append(f"- `{key}`: {'pass' if value else 'fail'}")

    return "\n".join(
        [
            "# Policy Coordinate Integration Report",
            "",
            "## 1. 新增或修改了哪些文件",
            *[f"- `{item}`" for item in files_list],
            "",
            "## 2. 读取了哪些知识库文件",
            *[f"- `{item}`" for item in kb_files],
            "",
            "## 3. 新增了哪些字段",
            *[f"- {item}" for item in fields],
            "",
            "## 4. 渲染位置在哪里",
            "- `email_renderer.py` 将“今日政策坐标”放在“今日精读”之后、“今日一题”之前。",
            "- HTML 和 plain_text 同步渲染；`brief` 本体不写栏目标题，只写结构化 `policy_coordinate` 数据。",
            "",
            "## 5. 质检规则有哪些",
            *[f"- {item}" for item in quality_rules],
            "",
            "## 6. 三个试跑样例的 policy_coordinate 内容",
            *sample_blocks,
            "",
            "## 7. 试跑检查结果",
            *checks_lines,
            "",
            "## 8. 近 14 天去重逻辑验证",
            f"- 试跑使用隔离历史文件：`{TRIAL_HISTORY_PATH.relative_to(ROOT)}`。",
            f"- 正式三次试跑依次写入临时 usage history，后续样例匹配时 `recent_count` 分别提升为：{' / '.join(str(item['recent_usage_count']) for item in trial_results)}。",
            f"- 额外重复探测主题：`{dedupe_probe.get('theme')}`。",
            f"- 首次命中政策 ID：`{dedupe_probe.get('first_policy_id')}`；重复探测命中政策 ID：`{dedupe_probe.get('probe_policy_id')}`。",
            f"- 去重调试信息：`selected_repeat_notes={json.dumps(dedupe_probe.get('selected_repeat_notes') or {}, ensure_ascii=False)}`。",
            "",
            "## 9. 目前还有哪些风险",
            *[f"- {item}" for item in risks],
            "",
            "## 10. 后续如果切换 OSS，需要怎么配置",
            "- 环境变量层面：设置 `KNOWLEDGE_BASE_MODE=oss`、`KNOWLEDGE_OSS_PREFIX=<你的 OSS 目录前缀>`，并继续保留 `OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`。",
            "- 代码层面：当前 `knowledge_base_loader.py` 仍只读取本地 `KNOWLEDGE_BASE_DIR`，切换 OSS 前需要在加载器里补齐 OSS 下载/缓存逻辑，再让各个 `load_*()` 走统一读取入口。",
            "- 生产部署层面：如果还希望去重历史也跨实例持久化，建议将 `data/policy_coordinate_usage_history.jsonl` 也一并迁移到 OSS 或其他持久化存储。",
            "",
            "## 11. 本地试跑产物位置",
            f"- `output/policy_coordinate_trials/` 下保存了 3 组 `daily.json`、`email.html`、`plain_text.txt`、`quality.json` 和 `run.log`。",
        ]
    ) + "\n"


def main() -> int:
    if TRIAL_OUTPUT_DIR.exists():
        shutil.rmtree(TRIAL_OUTPUT_DIR)
    TRIAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    original_history_path = usage_history_module.DEFAULT_USAGE_HISTORY_PATH
    usage_history_module.DEFAULT_USAGE_HISTORY_PATH = TRIAL_HISTORY_PATH
    trial_results: list[dict[str, Any]] = []
    dedupe_probe: dict[str, Any] = {}

    try:
        base_brief = load_base_brief()
        first_case_inputs: dict[str, Any] | None = None
        for case in TRIAL_CASES:
            label = case["today_theme"]
            trial_dir = TRIAL_OUTPUT_DIR / case["slug"]
            logger = RunLogger(trial_dir)
            brief = build_trial_brief(base_brief, case)
            brief, schema_warnings = ensure_brief_schema(brief, case["date"])
            if schema_warnings:
                logger.info("trial schema warnings", warnings=schema_warnings)

            brief = ensure_policy_coordinate_for_render(brief, logger=logger)
            plain_text = render_plain_text(brief)
            html_body = render_email_html(brief)
            quality_result = enforce_policy_coordinate_quality(brief, plain_text, html_body, logger=logger)
            brief = quality_result["brief"]
            plain_text = quality_result["plain_text"]
            html_body = quality_result["html_body"]
            policy_quality = evaluate_policy_coordinate_quality(brief, plain_text, html_body)
            verification = verify_trial(case, brief, plain_text, html_body, policy_quality)

            coordinate = brief.get("policy_coordinate") if isinstance(brief.get("policy_coordinate"), dict) else {}
            if not verification["checks"]["all_passed"]:
                raise RuntimeError(f"trial failed checks for {case['slug']}: {verification['checks']}")

            wrapper = {
                "delivery_date": case["date"],
                "subject": brief.get("email_subject"),
                "brief": brief,
                "plain_text": plain_text,
                "html_body": html_body,
                "policy_coordinate_quality": policy_quality,
                "verification": verification,
            }
            write_json(trial_dir / "daily.json", wrapper)
            save_text(trial_dir / "email.html", html_body)
            save_text(trial_dir / "plain_text.txt", plain_text)
            write_json(trial_dir / "quality.json", policy_quality)
            logger.save("run.log")

            usage_record = build_policy_coordinate_usage_record(brief, case["date"])
            if usage_record:
                append_meta = append_policy_coordinate_usage(usage_record)
                logger.info("trial usage history append", **append_meta)
            history_rows, _ = load_policy_coordinate_usage_history()
            recent_rows = recent_policy_coordinate_usage(history_rows, days=14)

            trial_results.append(
                {
                    "slug": case["slug"],
                    "label": label,
                    "brief": brief,
                    "plain_text": plain_text,
                    "html_body": html_body,
                    "policy_quality": policy_quality,
                    "verification": verification,
                    "recent_usage_count": len(recent_rows),
                }
            )

            if first_case_inputs is None:
                first_case_inputs = {
                    "article_title": brief["featured_article"]["title"],
                    "article_summary": brief["featured_article"]["one_sentence"],
                    "main_theme": brief["featured_article"]["theme"],
                    "sub_themes": brief["today_takeaway"]["keywords"],
                    "keywords": brief["today_takeaway"]["keywords"] + [brief["today_theme"]],
                    "exam_scenarios": [
                        brief["daily_question"]["question_type"],
                        brief["daily_question"]["topic_category"],
                        brief["daily_question"]["exam_focus"],
                    ],
                    "first_policy_id": coordinate.get("matched_policy_id"),
                    "theme": label,
                }

        if first_case_inputs:
            history_rows, _ = load_policy_coordinate_usage_history()
            recent_rows = recent_policy_coordinate_usage(history_rows, days=14)
            probe = match_policy_coordinate_candidates(
                article_title=first_case_inputs["article_title"],
                article_summary=first_case_inputs["article_summary"],
                main_theme=first_case_inputs["main_theme"],
                sub_themes=first_case_inputs["sub_themes"],
                keywords=first_case_inputs["keywords"],
                exam_scenarios=first_case_inputs["exam_scenarios"],
                recent_usage=recent_rows,
            )["matched_policy_coordinate_candidates"]
            debug_usage = probe.get("debug_scores", {}).get("usage_history", {})
            dedupe_probe = {
                "theme": first_case_inputs["theme"],
                "first_policy_id": first_case_inputs["first_policy_id"],
                "probe_policy_id": (probe.get("best_policy") or {}).get("policy_id"),
                "selected_repeat_notes": debug_usage.get("selected_repeat_notes"),
                "recent_count": debug_usage.get("recent_count"),
            }

        report_markdown = build_report_markdown(trial_results, dedupe_probe)
        save_text(REPORT_PATH, report_markdown)
        write_json(TRIAL_OUTPUT_DIR / "summary.json", {"trials": trial_results, "dedupe_probe": dedupe_probe})
    finally:
        usage_history_module.DEFAULT_USAGE_HISTORY_PATH = original_history_path

    print(json.dumps(
        {
            "trial_count": len(trial_results),
            "report_path": str(REPORT_PATH),
            "output_dir": str(TRIAL_OUTPUT_DIR),
            "dedupe_probe": dedupe_probe,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
