import os
import json
import logging
from typing import List, Optional
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *
from .persona_manager import PersonaManager

@register(name="ChronoPersona", description="Persona management system", version="0.1", author="YourName")
class ChronoPersonaPlugin(BasePlugin):
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.config = self.load_config()
        self.templates_dir = os.path.join(os.path.dirname(__file__), self.config['template_path'])
        self.user_prefs_dir = os.path.join(os.path.dirname(__file__), "user_preferences")
        self.ensure_directories()
        self.base_templates = {}
        self.user_preferences = {}
        self.persona_manager = PersonaManager(self.config, os.path.dirname(__file__))
        self.conversation_history: Dict[str, List[str]] = {}
        self.logger = logging.getLogger(__name__)
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            filename='chronopersona.log',
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def load_config(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def ensure_directories(self):
        os.makedirs(self.templates_dir, exist_ok=True)
        os.makedirs(self.user_prefs_dir, exist_ok=True)
        # 创建模板子目录
        for category in ['professions', 'personalities', 'speaking_styles', 'relationships']:
            os.makedirs(os.path.join(self.templates_dir, category), exist_ok=True)
        # 创建用户数据目录
        os.makedirs(os.path.join(os.path.dirname(__file__), 'user_personas'), exist_ok=True)

    async def initialize(self):
        self.load_base_templates()
        self.load_user_preferences()

    def load_base_templates(self):
        self.base_templates = {}
        for template_file in os.listdir(self.templates_dir):
            if template_file.endswith('.json'):
                template_path = os.path.join(self.templates_dir, template_file)
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                    self.base_templates[template_data['role']] = template_data['persona']

    def load_user_preferences(self):
        for filename in os.listdir(self.user_prefs_dir):
            if filename.endswith('.json'):
                user_id = filename[:-5]
                with open(os.path.join(self.user_prefs_dir, filename), 'r', encoding='utf-8') as f:
                    self.user_preferences[user_id] = json.load(f)

    def get_persona_prompt(self, user_id: str) -> str:
        try:
            template_name = self.config['default_template']
            if user_id in self.user_preferences:
                template_name = self.user_preferences[user_id].get('template', template_name)
            
            template = self.base_templates.get(template_name, self.base_templates[self.config['default_template']])
            prompt = self.format_template(template)
            persona_modifier = self.persona_manager.generate_prompt_modifier(user_id)
            
            # 如果是猫娘模板,确保修饰词不会覆盖猫娘特征
            if template_name == 'catgirl':
                prompt = f"{prompt}\n{persona_modifier}\n记住要保持猫娘的语气喵~"
            else:
                prompt = f"{prompt}\n{persona_modifier}"
                
            return prompt.strip()
        except Exception as e:
            self.logger.error(f"Error generating prompt for user {user_id}: {e}")
            return self.get_fallback_prompt()
    
    def get_fallback_prompt(self) -> str:
        return "你是一个友好的AI助手，请用平和的语气交谈。"

    def format_template(self, template):
        # 检查是否是猫娘模板
        is_catgirl = template.get('identity', '').find('猫娘') != -1
        
        formatted = (f"{template['identity']}\n\n"
                    f"行为准则:\n" + 
                    "\n".join(f"- {p}" for p in template['principles']) +
                    f"\n\n说话方式: {template.get('speaking_style', '')}\n"
                    f"语言风格: {template['language_style']}")
        
        if is_catgirl:
            formatted += "\n\n特别注意: 每次回答都必须以'喵~'开头或结尾"
            
        return formatted

    @handler(PersonNormalMessageReceived)
    async def handle_person_message(self, ctx: EventContext):
        user_id = str(ctx.event.sender_id)
        message = ctx.event.text_message
        
        # 检查快速响应
        quick_response = self.persona_manager.check_quick_response(message)
        if quick_response:
            ctx.add_return("reply", [quick_response])
            ctx.prevent_default()
            return
            
        # 更新对话历史
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
            
        self.conversation_history[user_id].append(message)
        
        # 限制历史记录长度
        max_history = self.config['persona_settings']['max_history_analysis']
        self.conversation_history[user_id] = self.conversation_history[user_id][-max_history:]
        
        # 只有非快速响应的消息才进行特征分析
        if len(message) > 5:  # 忽略过短的消息
            new_traits = self.persona_manager.analyze_conversation([message])
            if new_traits:
                self.persona_manager.update_user_persona(user_id, new_traits)

    def __del__(self):
        # 清理工作
        pass
