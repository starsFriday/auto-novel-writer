根据用户给出的开端，设计一部原创中文长篇小说。

用户开端：
{{opening}}

项目要求：
{{planning}}

规则书：
{{rulebook}}

要求：
- 只输出 JSON。
- 必须原创，不得使用规则书来源小说的角色名、地名、组织名、专有设定或剧情桥段。
- 规划要能支持后续逐章写作，不要只有概念。
- 世界观、人物欲望、冲突阶梯、章节目标必须互相咬合。
- 每章都要有：目标、阻力、信息变化、人物选择、章尾钩子。

输出 JSON 结构：
{
  "title": "原创书名",
  "genre": "类型",
  "logline": "一句话卖点",
  "theme": "主题",
  "reader_promise": ["给读者的爽点/情绪承诺"],
  "worldview": {
    "background": "世界背景",
    "public_rules": ["普通人知道的规则"],
    "hidden_rules": ["后续揭开的隐藏规则"],
    "costs_and_limits": ["力量/资源/身份的代价和限制"],
    "social_order": "社会秩序或利益格局"
  },
  "premise": {
    "inciting_incident": "开端事件",
    "central_question": "贯穿前中期的核心问题",
    "main_goal": "主角阶段目标",
    "stakes": "失败代价"
  },
  "characters": [
    {
      "name": "原创姓名",
      "role": "主角/配角/阻力方",
      "desire": "想要什么",
      "fear": "害怕什么",
      "flaw": "缺陷",
      "secret": "秘密",
      "arc": "成长或变化",
      "voice": "说话方式",
      "relationships": ["与他人的关系张力"]
    }
  ],
  "conflict_design": {
    "external_conflicts": ["外部冲突"],
    "internal_conflicts": ["内心冲突"],
    "relationship_conflicts": ["关系冲突"],
    "stakes_ladder": ["冲突升级阶梯"],
    "secrets_and_reveals": ["秘密和揭示顺序"]
  },
  "outline": {
    "beginning": "开局阶段",
    "middle": "中段阶段",
    "ending": "收束阶段",
    "major_turning_points": ["关键转折"]
  },
  "chapter_plan": [
    {
      "chapter_no": 1,
      "title": "章节名",
      "pov": "视角",
      "goal": "本章目标",
      "conflict": "本章主要冲突",
      "required_scenes": ["必须出现的场景"],
      "turning_point": "本章转折",
      "cliffhanger": "章尾钩子",
      "continuity_notes": ["连续性注意事项"]
    }
  ],
  "foreshadowing": ["伏笔"],
  "continuity_bible": {
    "timeline": ["时间线"],
    "locations": ["地点"],
    "rules": ["不可违反的设定规则"]
  },
  "style_guide": {
    "narration": "叙述风格",
    "dialogue": "对话风格",
    "description_density": "描写密度",
    "avoid": ["风格禁忌"]
  },
  "revision_targets": ["整本书改稿重点"],
  "risk_flags": ["可能写崩的风险"]
}
