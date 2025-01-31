from typing import List

class PersonaCommands:
    def __init__(self, plugin):
        self.plugin = plugin

    async def handle_command(self, command: str, args: List[str], user_id: str) -> str:
        commands = {
            "!persona": self.change_persona,
            "!list": self.list_personas,
            "!reset": self.reset_persona,
            "!save": self.save_current,
            "!traits": self.show_traits
        }
        
        cmd = commands.get(command.lower())
        if cmd:
            return await cmd(args, user_id)
        return "未知命令。可用命令: !persona, !list, !reset, !save, !traits"

    async def change_persona(self, args: List[str], user_id: str) -> str:
        if not args:
            return "请指定人格模板名称"
        template_name = args[0]
        if template_name in self.plugin.base_templates:
            self.plugin.update_user_template(user_id, template_name)
            return f"已切换到{template_name}模板"
        return "未找到指定模板"
