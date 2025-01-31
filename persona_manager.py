import json
import os
from collections import Counter
from typing import Dict, List, Set
import jieba
import jieba.analyse

class PersonaManager:
    def __init__(self, config: dict, base_dir: str):
        self.config = config
        self.user_personas_dir = os.path.join(base_dir, config['user_persona_path'])
        self.ensure_directory()
        self.priority_traits = config['persona_settings']['priority_traits']
        self.ignored_keywords = set(config['persona_settings']['ignored_keywords'])
        self.template_categories = ['professions', 'personalities', 'speaking_styles', 'relationships']
        self.templates = self.load_all_templates()
        self.default_template = "intellectual_maid"
        self.user_profiles = {}
        self.init_custom_dict()
        self.init_quick_responses()
        
    def ensure_directory(self):
        os.makedirs(self.user_personas_dir, exist_ok=True)

    def get_user_persona_path(self, user_id: str) -> str:
        return os.path.join(self.user_personas_dir, f"{user_id}.json")

    def init_custom_dict(self):
        """初始化自定义词典"""
        custom_words = [
            ("猫猫", 10), ("喵喵", 10), ("小猫", 8),
            ("你好啊", 5), ("早安", 5), ("晚安", 5),
            ("主人", 10), ("笨蛋", 5), ("前辈", 8)
        ]
        for word, weight in custom_words:
            jieba.suggest_freq(word, True)
            jieba.add_word(word, weight)

    def init_quick_responses(self):
        """初始化快速响应模板"""
        self.quick_patterns = {
            "问候": {
                "patterns": ["你好", "猫猫", "喵喵", "在吗", "在不在"],
                "responses": {
                    "first_time": "喵~初次见面，我是你的AI助手，请多指教~",
                    "normal": "喵喵~我在呢，有什么需要帮忙的吗？",
                    "familiar": "主人好啊，一直都在等你呢~"
                }
            },
            "再见": {
                "patterns": ["再见", "拜拜", "晚安", "下次见"],
                "responses": {
                    "normal": "好的喵~下次见~",
                    "familiar": "主人再见，要想我哦~"
                }
            }
        }

    def analyze_conversation(self, messages: List[str]) -> Dict[str, int]:
        """改进的对话分析逻辑"""
        if not messages:
            return {}
            
        # 合并短消息
        if len(messages) > 1:
            combined_text = " ".join(messages[-3:])  # 只分析最近3条消息
        else:
            combined_text = messages[0]
            
        # 使用自定义词典分析
        words = jieba.cut(combined_text)
        word_counter = Counter(words)
        
        # 匹配特征词
        trait_counter = Counter()
        for word, count in word_counter.items():
            for category, traits in self.priority_traits.items():
                if word in traits:
                    trait_counter[f"{category}:{word}"] = count
                    
        return dict(trait_counter)

    def check_quick_response(self, message: str) -> Optional[str]:
        """检查是否需要快速响应"""
        message = message.lower()
        
        # 检查各个模式
        for pattern_type, pattern_data in self.quick_patterns.items():
            if any(p in message for p in pattern_data["patterns"]):
                responses = pattern_data["responses"]
                # TODO: 根据用户熟悉度选择合适的回复
                return responses.get("normal", responses["normal"])
                
        return None

    def get_greeting_response(self, user_id: str, message: str) -> Optional[str]:
        """获取问候回复"""
        familiarity = self.get_user_familiarity(user_id)
        if "早" in message:
            return self.generate_morning_greeting(familiarity)
        elif "晚" in message:
            return self.generate_night_greeting(familiarity)
        return self.generate_normal_greeting(familiarity)

    def update_user_persona(self, user_id: str, new_traits: Dict[str, int]):
        persona_path = self.get_user_persona_path(user_id)
        current_persona = self.load_user_persona(user_id)
        
        # 更新权重
        for trait, count in new_traits.items():
            if trait in current_persona['traits']:
                current_persona['traits'][trait] = max(
                    current_persona['traits'][trait],
                    count
                )
            else:
                current_persona['traits'][trait] = count
        
        # 清理低频特征
        current_persona['traits'] = {
            k: v for k, v in current_persona['traits'].items()
            if v >= self.config['persona_settings']['min_keyword_frequency']
        }
        
        with open(persona_path, 'w', encoding='utf-8') as f:
            json.dump(current_persona, f, ensure_ascii=False, indent=2)

    def load_user_persona(self, user_id: str) -> dict:
        persona_path = self.get_user_persona_path(user_id)
        if os.path.exists(persona_path):
            with open(persona_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"traits": {}, "last_updated": None}

    def generate_prompt_modifier(self, user_id: str) -> str:
        persona = self.load_user_persona(user_id)
        if not persona['traits']:
            return ""
            
        modifiers = []
        # 按类别组织特征
        traits_by_category = {}
        
        for trait, weight in sorted(
            persona['traits'].items(), 
            key=lambda x: x[1], 
            reverse=True
        ):
            category, value = trait.split(':')
            if category not in traits_by_category:
                traits_by_category[category] = []
            traits_by_category[category].append(value)
        
        # 生成每个类别的组合描述
        for category, values in traits_by_category.items():
            if category == "身份关系":
                modifiers.append(f"你是我的{values[0]}")
            elif category == "称谓方式":
                modifiers.append(f"你应该称呼我为{values[0]}")
            elif category == "说话特征":
                modifiers.append(f"说话时要经常使用 {', '.join(values)}")
            else:
                modifiers.append(f"请保持{', '.join(values)}的{category}")
            
        return "\n".join(modifiers)
    
    def clean_user_data(self, max_age_days: int = 30):
        """清理超过指定天数的用户数据"""
        current_time = datetime.now()
        for user_id in self.get_all_users():
            persona = self.load_user_persona(user_id)
            if self.is_expired(persona, current_time, max_age_days):
                self.reset_user_persona(user_id)
                
    def merge_traits(self, base_traits: dict, user_traits: dict) -> dict:
        """智能合并基础特征和用户特征"""
        merged = base_traits.copy()
        for category, traits in user_traits.items():
            if category in merged:
                merged[category].extend(traits)
            else:
                merged[category] = traits
        return merged

    def load_category_templates(self, category: str) -> Dict[str, dict]:
        category_path = os.path.join(self.templates_dir, category)
        templates = {}
        if os.path.exists(category_path):
            for file in os.listdir(category_path):
                if file.endswith('.json'):
                    with open(os.path.join(category_path, file), 'r', encoding='utf-8') as f:
                        template = json.load(f)
                        templates[template['role']] = template['persona']
        return templates
    
    def load_all_templates(self) -> Dict[str, Dict[str, dict]]:
        templates = {}
        for category in self.template_categories:
            templates[category] = self.load_category_templates(category)
        return templates

    def combine_templates(self, user_id: str) -> dict:
        user_persona = self.load_user_persona(user_id)
        if not user_persona or 'base_templates' not in user_persona:
            user_persona = self.get_default_persona()
        
        combined = {
            "traits": {},
            "principles": [],
            "speaking_patterns": [],
            "relationship_settings": {}
        }

        for category, template_name in user_persona['base_templates'].items():
            if template_name and category in self.templates:
                category_data = self.templates[category].get(template_name, {})
                # 合并各个模板的特征
                self.merge_template_data(combined, category_data)
                
        return combined

    def merge_template_data(self, combined: dict, template_data: dict):
        """合并模板数据到最终配置中"""
        if 'traits' in template_data:
            combined['traits'].update(template_data['traits'])
        if 'principles' in template_data:
            combined['principles'].extend(template_data['principles'])
        if 'speaking_patterns' in template_data:
            combined['speaking_patterns'].extend(template_data['speaking_patterns'])

    def get_default_persona(self) -> dict:
        default_path = os.path.join(self.user_personas_dir, 'default.json')
        if os.path.exists(default_path):
            with open(default_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def create_user_persona(self, user_id: str) -> None:
        default_persona = self.get_default_persona()
        user_path = self.get_user_persona_path(user_id)
        if not os.path.exists(user_path):
            with open(user_path, 'w', encoding='utf-8') as f:
                json.dump(default_persona, f, ensure_ascii=False, indent=2)

    def combine_persona_templates(self, profession: str = None, personality: str = None) -> dict:
        """组合职业和性格模板"""
        combined = {
            "核心特征": [],
            "表达方式": [],
            "情感倾向": [],
            "语言示例": [],
            "禁止特征": []
        }
        
        # 加载职业模板
        if profession and profession in self.templates['professions']:
            prof_template = self.templates['professions'][profession]
            for key in combined:
                if key in prof_template:
                    combined[key].extend(prof_template[key])
                    
        # 加载性格模板
        if personality and personality in self.templates['personalities']:
            pers_template = self.templates['personalities'][personality]
            for key in combined:
                if key in pers_template:
                    combined[key].extend(pers_template[key])
        
        return combined

    def create_character_card(self, template_names: dict) -> dict:
        """根据模板名称创建完整人物卡"""
        profession = template_names.get('profession')
        personality = template_names.get('personality')
        
        # 组合基础模板
        base_persona = self.combine_persona_templates(profession, personality)
        
        return {
            "base_templates": template_names,
            "combined_persona": base_persona,
            "last_updated": datetime.now().isoformat()
        }

    def get_or_create_persona(self, user_id: str, template_names: dict = None) -> dict:
        """获取或创建用户人物卡"""
        user_path = self.get_user_persona_path(user_id)
        
        if os.path.exists(user_path):
            with open(user_path, 'r', encoding='utf-8') as f:
                persona = json.load(f)
                if not template_names:  # 如果没有指定新模板，返回现有的
                    return persona
        
        # 创建新的人物卡
        if template_names:
            persona = self.create_character_card(template_names)
            with open(user_path, 'w', encoding='utf-8') as f:
                json.dump(persona, f, ensure_ascii=False, indent=2)
        
        return persona

    def get_final_prompt(self, user_id: str) -> str:
        """生成最终的提示词，包含模板和用户画像"""
        base_prompt = self.get_persona_prompt(user_id)
        user_profile = self.user_profiles.get(user_id)
        if user_profile:
            profile_prompt = user_profile.get_profile_prompt()
            if profile_prompt:
                base_prompt = f"{base_prompt}\n\n用户信息:\n{profile_prompt}"
        return base_prompt

    def update_user_profile(self, user_id: str, messages: List[str]):
        """更新用户画像"""
        keywords = self.extract_keywords(messages)
        if not keywords:
            return
            
        user_profile = self.load_user_profile(user_id)
        
        # 更新关键词频率
        keyword_counter = user_profile.get("keyword_frequency", {})
        for keyword in keywords:
            keyword_counter[keyword] = keyword_counter.get(keyword, 0) + 1
            
        # 保留出现频率最高的20个关键词
        top_keywords = sorted(
            keyword_counter.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]
        
        user_profile["keyword_frequency"] = dict(top_keywords)
        self.save_user_profile(user_id, user_profile)

    def extract_keywords(self, messages: List[str]) -> List[str]:
        """从对话中提取关键词"""
        combined_text = " ".join(messages)
        
        # 分词权重设置
        keywords_weight = {
            # 情感词权重
            "喜欢": 2.0, "讨厌": 2.0, "开心": 1.8, "生气": 1.8, 
            # 兴趣词权重
            "游戏": 1.5, "音乐": 1.5, "动漫": 1.5, "运动": 1.5,
            # 称谓词权重
            "老师": 2.0, "同学": 1.8, "朋友": 1.8, "前辈": 2.0
        }

        # 添加自定义词典
        for word in self.priority_traits.values():
            jieba.suggest_freq(word, True)

        # 使用 TF-IDF 提取关键词
        keywords_tfidf = jieba.analyse.extract_tags(
            combined_text,
            topK=20,  # 最多保留20个关键词
            withWeight=True,
            allowPOS=('n', 'v', 'a', 'i')  # 允许名词、动词、形容词、成语
        )

        # 使用 TextRank 提取关键词
        keywords_textrank = jieba.analyse.textrank(
            combined_text,
            topK=20,
            withWeight=True,
            allowPOS=('n', 'v', 'a', 'i')
        )

        # 合并两种算法的结果
        keywords = {}
        for word, weight in keywords_tfidf:
            keywords[word] = weight
        for word, weight in keywords_textrank:
            if word in keywords:
                keywords[word] = (keywords[word] + weight) / 2
            else:
                keywords[word] = weight

        # 应用自定义权重
        for word in keywords:
            if word in keywords_weight:
                keywords[word] *= keywords_weight[word]

        # 过滤忽略的关键词
        filtered_keywords = {
            k: v for k, v in keywords.items() 
            if k not in self.ignored_keywords
        }

        # 按权重排序并返回前20个关键词
        sorted_keywords = sorted(
            filtered_keywords.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:20]

        return [word for word, _ in sorted_keywords]
