from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At, Plain
import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path

@register("welcome_group", "User", "QQ群新人入群自动欢迎插件", "1.0.5", "https://github.com/mjy1113451/welcome_group")
class WelcomePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        try:
            from astrbot.api.star import StarTools
            self.data_dir = StarTools.get_data_dir() / "welcome_group"
        except ImportError:
            self.data_dir = Path(os.getcwd()) / "data" / "welcome_group"

        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.data_dir / "config.json"
        self.config = self.load_config()

    def _get_default_config(self):
        return {
            "default_message": "欢迎 {at} 加入本群！当前时间：{time}",
            "default_leave_message": "{user_id} 离开了本群。",
            "default_kick_message": "{user_id} 被移出了本群。",
            "global_enabled": False,
            "global_welcome_message": "欢迎 {at} 加入本群！当前时间：{time}",
            "global_leave_message": "{user_id} 离开了本群。",
            "global_kick_message": "{user_id} 被移出了本群。",
            "groups": {},
            "llm_enabled": False,
            "llm_provider_id": ""
        }

    def load_config(self):
        default_config = self._get_default_config()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # 兼容旧版配置文件：补充缺失的默认字段
                for key, value in default_config.items():
                    if key not in saved:
                        saved[key] = value
                return saved
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                return default_config
        return default_config

    def save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    # ==================== LLM 消息生成 ====================

    async def _generate_message_with_llm(self, event: AstrMessageEvent, prompt: str) -> str | None:
        """使用 LLM 生成消息文案"""
        try:
            provider_id = self.config.get("llm_provider_id", "")
            if not provider_id:
                # 尝试获取当前聊天的 provider
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)

            if not provider_id:
                logger.warning("WelcomePlugin: 未配置 LLM provider")
                return None

            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt="你是一个QQ群管理助手，请根据用户的要求生成合适的群消息文案。回复要简洁、自然、友好。只返回文案内容，不要添加任何其他解释。"
            )

            if llm_resp and llm_resp.completion_text:
                return llm_resp.completion_text.strip()
            return None
        except Exception as e:
            logger.error(f"WelcomePlugin: LLM 生成失败: {e}")
            return None

    async def _get_message_template(self, event: AstrMessageEvent, message_type: str, fallback: str) -> str:
        """获取消息模板，优先使用 LLM 生成（如果启用）"""
        if self.config.get("llm_enabled", False):
            prompts = {
                "welcome": "请为QQ群生成一条简短的入群欢迎消息，要求友好、热情。只返回消息内容。",
                "leave": "请为QQ群生成一条简短的退群通知消息，要求礼貌、温和。只返回消息内容。",
                "kick": "请为QQ群生成一条简短的被踢通知消息，要求正式、简洁。只返回消息内容。"
            }
            prompt = prompts.get(message_type, "")
            if prompt:
                generated = await self._generate_message_with_llm(event, prompt)
                if generated:
                    return generated
        return fallback

    # ==================== 入群欢迎 ====================

    def _resolve_welcome(self, group_id: str) -> tuple:
        """解析欢迎语模板和是否启用。
        返回 (template, enabled, source) 三元组：
        - source 为 "group" / "global" / "disabled"
        """
        group_config = self.config["groups"].get(group_id)
        # 1. 群级配置优先
        if group_config:
            if group_config.get("enabled", False):
                template = group_config.get("message") or self.config.get(
                    "global_welcome_message", self.config["default_message"]
                )
                return template, True, "group"
        # 2. 全局配置
        if self.config.get("global_enabled", False):
            template = self.config.get(
                "global_welcome_message", self.config["default_message"]
            )
            return template, True, "global"
        return "", False, "disabled"

    def _resolve_leave(self, group_id: str) -> tuple:
        """解析退群模板。返回 (template, enabled, source)"""
        group_config = self.config["groups"].get(group_id)
        if group_config:
            if group_config.get("leave_enabled", False):
                template = group_config.get("leave_message") or self.config.get(
                    "global_leave_message", self.config["default_leave_message"]
                )
                return template, True, "group"
        if self.config.get("global_enabled", False):
            template = self.config.get(
                "global_leave_message", self.config["default_leave_message"]
            )
            return template, True, "global"
        return "", False, "disabled"

    def _resolve_kick(self, group_id: str) -> tuple:
        """解析被踢模板。返回 (template, enabled, source)"""
        group_config = self.config["groups"].get(group_id)
        if group_config:
            if group_config.get("kick_enabled", False):
                template = group_config.get("kick_message") or self.config.get(
                    "global_kick_message", self.config["default_kick_message"]
                )
                return template, True, "group"
        if self.config.get("global_enabled", False):
            template = self.config.get(
                "global_kick_message", self.config["default_kick_message"]
            )
            return template, True, "global"
        return "", False, "disabled"

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_increase(self, event: AstrMessageEvent):
        """处理新人入群事件"""
        try:
            raw = self._get_raw_message(event)
            if raw is None:
                return

            # 获取 post_type，兼容 dict 和 Event 对象
            post_type = self._get_dict_value(raw, "post_type")
            notice_type = self._get_dict_value(raw, "notice_type")

            if post_type != "notice" or notice_type != "group_increase":
                return

            group_id = str(self._get_dict_value(raw, "group_id", ""))
            user_id = self._get_dict_value(raw, "user_id")
            self_id = self._get_dict_value(raw, "self_id")

            if str(user_id) == str(self_id):
                return

            welcome_template, enabled, source = self._resolve_welcome(group_id)
            if not enabled:
                return

            time_str = self._parse_time(raw)

            # 尝试使用 LLM 生成消息
            llm_message = None
            if self.config.get("llm_enabled", False):
                llm_message = await self._generate_message_with_llm(
                    event,
                    f"请为新成员 {user_id} 生成一条简短的入群欢迎消息，要求友好、热情。只返回消息内容。"
                )

            # 使用 LLM 生成的消息或模板
            if llm_message:
                processed = llm_message
            else:
                processed = welcome_template.replace("{time}", time_str).replace("{user_id}", str(user_id))

            message_list = self._build_onebot_message(processed, int(user_id))

            logger.info(f"WelcomePlugin: 准备发送入群欢迎 -> 群 {group_id} 用户 {user_id} (来源: {source})")

            await self._send_group_msg(event, group_id, message_list)

        except Exception as e:
            logger.error(f"WelcomePlugin: 处理入群事件失败: {e}")

    # ==================== 退群 / 被踢 ====================

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_decrease(self, event: AstrMessageEvent):
        """处理退群 / 被踢出群事件"""
        try:
            raw = self._get_raw_message(event)
            if raw is None:
                return

            # 获取 post_type，兼容 dict 和 Event 对象
            post_type = self._get_dict_value(raw, "post_type")
            notice_type = self._get_dict_value(raw, "notice_type")

            if post_type != "notice" or notice_type != "group_decrease":
                return

            sub_type = self._get_dict_value(raw, "sub_type", "")

            # 机器人自己被踢，无法发消息，仅记录日志
            if sub_type == "kick_me":
                logger.info(f"WelcomePlugin: 机器人被踢出群 {self._get_dict_value(raw, 'group_id')}，操作者: {self._get_dict_value(raw, 'operator_id')}")
                return

            group_id = str(self._get_dict_value(raw, "group_id", ""))
            user_id = self._get_dict_value(raw, "user_id")

            if sub_type == "leave":
                template, enabled, source = self._resolve_leave(group_id)
                if not enabled:
                    return
                log_label = "退群"
            elif sub_type == "kick":
                template, enabled, source = self._resolve_kick(group_id)
                if not enabled:
                    return
                log_label = "被踢"
            else:
                return

            time_str = self._parse_time(raw)

            # 尝试使用 LLM 生成消息
            llm_message = None
            if self.config.get("llm_enabled", False):
                llm_message = await self._generate_message_with_llm(
                    event,
                    f"请为用户 {user_id} 生成一条简短的{log_label}通知消息，要求礼貌。只返回消息内容。"
                )

            # 使用 LLM 生成的消息或模板
            if llm_message:
                processed = llm_message
            else:
                processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))

            message_list = self._build_onebot_message(processed, int(user_id))

            logger.info(f"WelcomePlugin: 准备发送{log_label}通知 -> 群 {group_id} 用户 {user_id} (来源: {source})")

            await self._send_group_msg(event, group_id, message_list)

        except Exception as e:
            logger.error(f"WelcomePlugin: 处理退群/被踢事件失败: {e}")

    # ==================== 指令入口 ====================

    @filter.command_group("welcome")
    def welcome_group_cmd(self):
        """群欢迎/退群/踢人通知插件管理"""
        pass

    # ---- 入群欢迎指令 ----

    @welcome_group_cmd.command("set", "设置当前群欢迎语")
    async def set_welcome(self, event: AstrMessageEvent, message: str = ""):
        """设置入群欢迎语。例如: /welcome set 欢迎 {at} 加入本群！"""
        if not event.message_obj.group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)

        if message.strip():
            group_config["enabled"] = True
            group_config["message"] = message.strip()
            self.save_config()
            yield event.plain_result(f"已设置本群入群欢迎语为：\n{message}")
        else:
            group_config["enabled"] = False
            group_config["message"] = ""
            self.save_config()
            yield event.plain_result("已重置为全局默认欢迎语")

    @welcome_group_cmd.command("on")
    async def enable_welcome(self, event: AstrMessageEvent):
        """开启当前群的入群欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        self._ensure_group(group_id)
        self.config["groups"][group_id]["enabled"] = True
        self.save_config()
        yield event.plain_result("本群入群欢迎功能已开启。")

    @welcome_group_cmd.command("off")
    async def disable_welcome(self, event: AstrMessageEvent):
        """关闭当前群的入群欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["enabled"] = False
            self.save_config()
        yield event.plain_result("本群入群欢迎功能已关闭。")

    @welcome_group_cmd.command("test", "测试入群欢迎提示")
    async def test_welcome(self, event: AstrMessageEvent):
        """测试发送当前群的入群欢迎语"""
        async for result in self._run_test(
            event,
            template_field="message",
            default_key="default_message",
            log_label="欢迎",
            llm_prompt="入群欢迎",
            llm_tone="友好、热情",
            resolver=self._resolve_welcome,
        ):
            yield result

    # ---- 退群通知指令 ----

    @welcome_group_cmd.command("leave", "设置退群提示")
    async def set_leave(self, event: AstrMessageEvent, message: str = ""):
        """设置退群提示语。例如: /welcome leave {user_id} 离开了本群"""
        if not event.message_obj.group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)

        if message.strip():
            group_config["leave_enabled"] = True
            group_config["leave_message"] = message.strip()
            self.save_config()
            yield event.plain_result(f"已设置本群退群通知语为：\n{message}")
        else:
            group_config["leave_enabled"] = False
            group_config["leave_message"] = ""
            self.save_config()
            yield event.plain_result("已禁用退群提示")

    @welcome_group_cmd.command("kick", "设置被踢提示")
    async def set_kick(self, event: AstrMessageEvent, message: str = ""):
        """设置被踢提示语。例如: /welcome kick {user_id} 被移出了本群"""
        if not event.message_obj.group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)

        if message.strip():
            group_config["kick_enabled"] = True
            group_config["kick_message"] = message.strip()
            self.save_config()
            yield event.plain_result(f"已设置本群被踢通知语为：\n{message}")
        else:
            group_config["kick_enabled"] = False
            group_config["kick_message"] = ""
            self.save_config()
            yield event.plain_result("已禁用被踢提示")

    @welcome_group_cmd.command("test_leave", "测试退群通知")
    async def test_leave(self, event: AstrMessageEvent):
        """测试发送当前群的退群通知"""
        async for result in self._run_test(
            event,
            template_field="leave_message",
            default_key="default_leave_message",
            log_label="退群",
            llm_prompt="退群通知",
            llm_tone="礼貌",
            resolver=self._resolve_leave,
        ):
            yield result

    @welcome_group_cmd.command("test_kick", "测试被踢通知")
    async def test_kick(self, event: AstrMessageEvent):
        """测试发送当前群的被踢通知"""
        async for result in self._run_test(
            event,
            template_field="kick_message",
            default_key="default_kick_message",
            log_label="被踢",
            llm_prompt="被踢通知",
            llm_tone="正式、简洁",
            resolver=self._resolve_kick,
        ):
            yield result

    # ---- LLM 配置指令 ----

    @welcome_group_cmd.command("llm")
    async def toggle_llm(self, event: AstrMessageEvent):
        """开启/关闭 LLM 自动生成消息功能"""
        current = self.config.get("llm_enabled", False)
        self.config["llm_enabled"] = not current
        self.save_config()
        status = "开启" if not current else "关闭"
        yield event.plain_result(f"LLM 自动生成消息功能已{status}。")

    @welcome_group_cmd.command("llm_provider", "设置 LLM 模型供应商 ID")
    async def set_llm_provider(self, event: AstrMessageEvent, provider_id: str = ""):
        """设置 LLM 模型供应商 ID。例如: /welcome llm_provider openai_gpt4"""
        if not provider_id.strip():
            yield event.plain_result("请提供 provider ID。\n使用 /welcome llm_list 查看可用的 provider。")
            return
        self.config["llm_provider_id"] = provider_id.strip()
        self.save_config()
        yield event.plain_result(f"已设置 LLM provider 为: {provider_id.strip()}")

    @welcome_group_cmd.command("llm_list")
    async def list_llm_providers(self, event: AstrMessageEvent):
        """列出所有可用的 LLM provider"""
        try:
            providers = self.context.get_all_providers()
            if not providers:
                yield event.plain_result("没有可用的 LLM provider。请先在 AstrBot 中配置。")
                return

            lines = ["可用的 LLM provider："]
            for p in providers:
                lines.append(f"- {p.id}")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"获取 provider 列表失败: {e}")

    # ---- 全局配置指令 ----
    # issue #48: 维护者拍板改为独立顶层命令，降低 /welcome global_xxx 的记忆负担。
    # 原 /welcome global / global_set / global_leave / global_kick 分别对应
    # /global_switch /global_welcome /global_leave /global_kick。

    @filter.command("global_switch", "开启/关闭全局欢迎/通知模式")
    async def toggle_global(self, event: AstrMessageEvent):
        """开启/关闭全局模式。
        全局模式开启后，未单独配置过的群将使用全局模板发送欢迎/退群/被踢通知。
        """
        current = self.config.get("global_enabled", False)
        self.config["global_enabled"] = not current
        self.save_config()
        status = "开启" if not current else "关闭"
        yield event.plain_result(f"全局模式已{status}。")

    @filter.command("global_welcome", "设置全局入群欢迎语")
    async def set_global_welcome(self, event: AstrMessageEvent, message: str = ""):
        """设置全局入群欢迎语。例如: /global_welcome 欢迎 {at} 加入！"""
        if not message.strip():
            yield event.plain_result("请提供欢迎语内容。")
            return
        self.config["global_welcome_message"] = message.strip()
        self.save_config()
        yield event.plain_result(f"已设置全局入群欢迎语为：\n{message}")

    @filter.command("global_leave", "设置全局退群提示")
    async def set_global_leave(self, event: AstrMessageEvent, message: str = ""):
        """设置全局退群提示。例如: /global_leave {user_id} 离开了本群"""
        if not message.strip():
            yield event.plain_result("请提供提示内容。")
            return
        self.config["global_leave_message"] = message.strip()
        self.save_config()
        yield event.plain_result(f"已设置全局退群提示为：\n{message}")

    @filter.command("global_kick", "设置全局被踢提示")
    async def set_global_kick(self, event: AstrMessageEvent, message: str = ""):
        """设置全局被踢提示。例如: /global_kick {user_id} 被移出了本群"""
        if not message.strip():
            yield event.plain_result("请提供提示内容。")
            return
        self.config["global_kick_message"] = message.strip()
        self.save_config()
        yield event.plain_result(f"已设置全局被踢提示为：\n{message}")

    @welcome_group_cmd.command("status", "查看当前群配置状态")
    async def show_status(self, event: AstrMessageEvent):
        """查看全局模式、当前群配置和当前生效的模板来源"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用。")
            return

        group_id = str(event.message_obj.group_id)
        global_on = self.config.get("global_enabled", False)

        welcome_t, welcome_enabled, welcome_src = self._resolve_welcome(group_id)
        leave_t, leave_enabled, leave_src = self._resolve_leave(group_id)
        kick_t, kick_enabled, kick_src = self._resolve_kick(group_id)

        def _trunc(t: str) -> str:
            return f"{t[:50]}{'...' if len(t) > 50 else ''}"

        lines = [
            f"全局模式: {'开启' if global_on else '关闭'}",
            f"全局欢迎语: {_trunc(self.config.get('global_welcome_message', ''))}",
            f"全局退群语: {_trunc(self.config.get('global_leave_message', ''))}",
            f"全局被踢语: {_trunc(self.config.get('global_kick_message', ''))}",
            "",
            f"本群 (群 {group_id}) 当前生效配置:",
            f"- 欢迎: {'开启' if welcome_enabled else '关闭'} (来源: {welcome_src})",
            f"  模板: {_trunc(welcome_t)}",
            f"- 退群: {'开启' if leave_enabled else '关闭'} (来源: {leave_src})",
            f"  模板: {_trunc(leave_t)}",
            f"- 被踢: {'开启' if kick_enabled else '关闭'} (来源: {kick_src})",
            f"  模板: {_trunc(kick_t)}",
        ]
        yield event.plain_result("\n".join(lines))

    # ==================== 工具方法 ====================

    @staticmethod
    def _get_raw_message(event: AstrMessageEvent):
        """兼容不同 event 类型获取 raw_message"""
        if hasattr(event, 'raw_message') and event.raw_message:
            return event.raw_message
        elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'raw_message'):
            return event.message_obj.raw_message
        return None

    @staticmethod
    def _get_dict_value(data, key, default=None):
        """从 dict 或类 dict 对象中获取值"""
        if isinstance(data, dict):
            return data.get(key, default)
        elif hasattr(data, 'get'):
            return data.get(key, default)
        elif hasattr(data, key):
            return getattr(data, key)
        return default

    @staticmethod
    def _parse_time(raw: dict) -> str:
        """将 OneBot 事件中的 time 字段转为格式化字符串"""
        event_time = WelcomePlugin._get_dict_value(raw, "time", time.time())
        try:
            return datetime.fromtimestamp(event_time).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_group(self, group_id: str):
        """确保群配置条目存在"""
        if group_id not in self.config["groups"]:
            self.config["groups"][group_id] = {
                "enabled": False,
                "message": "",
                "leave_enabled": False,
                "leave_message": "",
                "kick_enabled": False,
                "kick_message": ""
            }
        return self.config["groups"][group_id]

    @staticmethod
    def _build_onebot_message(template: str, user_id) -> list:
        """构建 AstrBot 消息组件列表"""
        if "{at}" in template:
            parts = template.split("{at}")
            message_list = []
            for i, part in enumerate(parts):
                if part:
                    message_list.append(Plain(part))
                if i < len(parts) - 1:
                    message_list.append(At(qq=user_id))
            return message_list
        else:
            return [Plain(template)]

    @classmethod
    async def _send_group_msg(cls, event: AstrMessageEvent, group_id: str, message_list: list):
        """发送群消息 - 直接使用 bot API，绕过框架的 Reply 组件注入"""
        try:
            bot = getattr(event, 'bot', None)
            if bot and hasattr(bot, 'send_group_msg'):
                # 将消息组件转为 OneBot JSON 格式
                raw_messages = []
                for comp in message_list:
                    if hasattr(comp, 'toDict'):
                        raw_messages.append(comp.toDict())
                    elif isinstance(comp, dict):
                        # 校验 dict 段必须包含 type 和 data 字段，否则跳过并记录告警
                        if 'type' in comp and 'data' in comp:
                            raw_messages.append(comp)
                        else:
                            logger.warning(
                                f"WelcomePlugin: 跳过非法消息段 dict={comp!r}，缺少 type 或 data"
                            )
                    else:
                        # 未知类型退化为纯文本（best-effort，不抛错以保证消息至少能发送）
                        raw_messages.append({"type": "text", "data": {"text": str(comp)}})
                if not raw_messages:
                    logger.error(f"WelcomePlugin: 消息段全部非法，跳过发送 -> 群 {group_id}")
                    return
                await bot.send_group_msg(group_id=int(group_id), message=raw_messages)
                logger.info(f"WelcomePlugin: 发送消息成功 -> 群 {group_id}")
            elif hasattr(event, 'send'):
                await event.send(MessageChain(message_list))
                logger.info(f"WelcomePlugin: 发送消息成功(event.send) -> 群 {group_id}")
            else:
                logger.warning("WelcomePlugin: 无法获取 bot 对象或 send 方法")
        except Exception as e:
            logger.error(f"WelcomePlugin: 发送消息失败: {e}")
            logger.error(traceback.format_exc())

    async def _run_test(self, event: AstrMessageEvent, template_field: str, default_key: str, log_label: str, llm_prompt: str, llm_tone: str, resolver=None):
        """测试命令的公共实现：读取模板 -> LLM 生成（可选）-> 构建消息 -> 发送

        resolver: 可选的 (group_id) -> (template, enabled, source) 解析器，
                  传入时使用与真实事件相同的优先级（群配置 > 全局 > 跳过）
        """
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if resolver:
            template, enabled, source = resolver(str(group_id))
            if not enabled:
                yield event.plain_result(f"该群未开启{log_label}功能（来源: {source}）。")
                return
        else:
            template = self.config["groups"].get(str(group_id), {}).get(
                template_field, self.config.get(default_key, "")
            )
            if not template:
                yield event.plain_result("未找到模板，请先通过 /welcome set 等命令配置。")
                return

        user_id = event.get_sender_id()
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        llm_message = None
        if self.config.get("llm_enabled", False):
            llm_message = await self._generate_message_with_llm(
                event,
                f"请为用户 {user_id} 生成一条简短的{llm_prompt}消息，要求{llm_tone}。只返回消息内容。",
            )

        if llm_message:
            processed = llm_message
        else:
            processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))

        message_list = self._build_onebot_message(processed, int(user_id))
        try:
            await self._send_group_msg(event, str(group_id), message_list)
        except Exception as e:
            logger.error(f"WelcomePlugin: 测试{log_label}消息发送失败: {e}")
            yield event.plain_result("测试失败: " + str(e))
