你要把一批小说规则卡融合成“原创中文长篇小说写作规则书”。

模式：{{mode}}

输入规则：
{{cards}}

要求：
- 只输出 JSON。
- 只保留抽象方法，不保留任何原书角色、专有名词、原文句子或可识别桥段。
- 规则要可执行，不要空泛，例如不要只写“节奏要好”，要写“每章至少有一个目标推进、一个阻力升级、一个信息变化”。
- 规则书必须覆盖：世界观、大纲、人物设定、章节设计、冲突设计、改稿、逻辑检查、风格评估，以及长篇小说必要部分。

输出 JSON 结构：
{
  "rules": {
    "core_principles": ["总原则"],
    "reader_promise": ["读者承诺"],
    "worldview": {
      "design_steps": ["世界观设计步骤"],
      "rules_and_costs": ["力量/职业/社会规则必须有边界和代价"],
      "reveal_methods": ["通过场景展示世界观的方法"]
    },
    "premise_and_opening": ["开端规则"],
    "outline": {
      "macro_structure": ["全书结构"],
      "arc_design": ["阶段性剧情弧"],
      "turning_points": ["关键转折安排"]
    },
    "characters": {
      "protagonist": ["主角设计"],
      "supporting_cast": ["配角设计"],
      "antagonists": ["反派/阻力设计"],
      "relationships": ["人物关系张力"]
    },
    "chapter_design": ["单章设计清单"],
    "conflict_design": ["冲突升级规则"],
    "dialogue": ["对话规则"],
    "pacing": ["节奏规则"],
    "prose_style": ["语言风格规则"],
    "revision_checklist": ["改稿清单"],
    "logic_checklist": ["逻辑检查清单"],
    "style_evaluation_rubric": ["风格评估标准"],
    "anti_copy_rules": ["原创和避抄规则"]
  }
}
