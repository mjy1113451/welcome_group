from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain
import json
import os
from datetime import datetime
from pathlib import Path

@register(
    "welcome_group",
    "YourName",
    "QQ群新人入群自动欢迎插件",
    "2.4.0",
    "https://github.com/mjy1113451/welcome_group"
)

class WelcomePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 初始化数据目录路径
        try:
            from astrbot.api.star import StarTools
            self.data_dir = StarTools.get_data_dir() / "welcome_group"
        except ImportError:
            self.data_dir = Path(os.getcwd()) / "data" / "welcome_group"
        
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_path = self.data_dir / "config.json"
        # 初始化配置文件
        self.config = self.load_config()

    def _get_default_config(self) -> dict:
        """获取默认配置结构"""
        return {
            "groups": {},
            # 直接使用字典存储全局配置
            "global_enabled": False,
            "global_increase_message": "欢迎 {at} 加入本群！当前时间：{time}",
            "global_leave_message": "{user_id} 离开了本群。",
            "global_kick_message": "{user_id} 被移出了本群。"
        }

    def load_config(self) -> dict:
        """加载配置文件"""
        default_config = self._get_default_config()
        
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    # 合并配置，确保所有必需的键都存在
                    for key, value in default_config.items():
                        if key not in saved:
                            saved[key] = value
                    
                    # 确保groups键存在
                    if "groups" not in saved:
                        saved["groups"] = {}
                    
                    return saved
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                return default_config
        return default_config

    def save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    def _ensure_group(self, group_id: str) -> dict:
        """确保群组配置存在，如果不存在则创建默认配置"""
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

    def _get_raw_message(self, event: AstrMessageEvent):
        """获取原始消息对象"""
        try:
            return event.message_obj.raw_message
        except AttributeError:
            return None

    def _parse_time(self, raw: dict) -> str:
        """解析时间"""
        try:
            timestamp = raw.get("time")
            if timestamp:
                return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _build_onebot_message(self, processed: str, user_id):
        """构建 OneBot 消息"""
        # 将 {at} 替换为 At 组件
        if "{at}" in processed:
            from astrbot.api.message_components import At
            parts = processed.split("{at}")
            message_list = []
            for i, part in enumerate(parts):
                if part:
                    message_list.append(Plain(part))
                if i < len(parts) - 1:
                    message_list.append(At(qq=user_id))
            return message_list
        else:
            return [Plain(processed)]

    def _build_fallback_chain(self, processed: str, user_id):
        """构建回退消息链"""
        # 简单的文本替换
        fallback = processed.replace("{at}", f"@{user_id}")
        return [Plain(fallback)]

    async def _send_group_msg(self, event: AstrMessageEvent, group_id: str, message_list):
        """发送群消息"""
        try:
            if hasattr(event, 'send'):
                await event.send(message_list)
                return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
        return False

    # ==================== 事件监听 ====================
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_increase(self, event: AstrMessageEvent):
        """处理新人入群事件"""
        try:
            raw = self._get_raw_message(event)
            if not raw or not isinstance(raw, dict):
                return
            
            if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_increase":
                return
            
            group_id = str(raw.get("group_id"))
            user_id = raw.get("user_id")
            self_id = raw.get("self_id")

            # 忽略机器人自己进群
            if str(user_id) == str(self_id):
                return
            
            group_config = self.config["groups"].get(group_id)
            welcome_template = ""
            
            if not group_config:
                # 如果群未配置，检查全局开关
                if self.config.get("global_enabled", False):
                    logger.info(f"群 {group_id} 未配置，使用全局入群欢迎语")
                    welcome_template = self.config.get("global_increase_message", "欢迎 {at} 加入本群！当前时间：{time}")
                else:
                    # 如果全局没开，则不做任何事
                    logger.info(f"群 {group_id} 未配置且全局模式未开启，跳过欢迎")
                    return
            else:
                # 群已配置，检查群开关
                if not group_config.get("enabled", False):
                    return
                # 使用群独立配置，如果没填则回退到全局配置
                welcome_template = group_config.get("message", self.config.get("global_increase_message", "欢迎 {at} 加入本群！当前时间：{time}"))

            # 发送消息
            time_str = self._parse_time(raw)
            processed = welcome_template.replace("{time}", time_str).replace("{user_id}", str(user_id))
            message_list = self._build_onebot_message(processed, user_id)
            success = await self._send_group_msg(event, group_id, message_list)
            
            if not success:
                try:
                    chain = self._build_fallback_chain(processed, user_id)
                    if hasattr(event, 'send'):
                        await event.send(chain)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"处理入群事件时出错: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_decrease(self, event: AstrMessageEvent):
        """处理退群 / 被踢出群事件"""
        try:
            raw = self._get_raw_message(event)
            if not raw or not isinstance(raw, dict):
                return
            
            if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_decrease":
                return
            
            sub_type = raw.get("sub_type", "")
            group_id = str(raw.get("group_id"))
            user_id = raw.get("user_id")
            self_id = raw.get("self_id")
            
            if sub_type == "kick_me" or str(user_id) == str(self_id):
                return
            
            group_config = self.config["groups"].get(group_id, {})
            template = ""

            # 直接从config字典获取全局配置
            default_leave = self.config.get("global_leave_message", "{user_id} 离开了本群。")
            default_kick = self.config.get("global_kick_message", "{user_id} 被移出了本群。")

            if sub_type == "leave":
                # 退群逻辑
                if not group_config.get("leave_enabled", False):
                    # 如果群没有开启退群通知，则不发送
                    if not group_config: # 群完全没配置的情况
                        if self.config.get("global_enabled", False):
                            template = default_leave
                        else:
                            return
                    else:
                        # 群有配置，但开关关了
                        return
                # 如果走到了这里，说明要发送。取群配置或回退全局
                template = group_config.get("leave_message", default_leave)
            
            elif sub_type == "kick":
                # 被踢逻辑
                if not group_config.get("kick_enabled", False):
                    if not group_config:
                        if self.config.get("global_enabled", False):
                            template = default_kick
                        else:
                            return
                    else:
                        return
                template = group_config.get("kick_message", default_kick)
            
            else:
                return

            time_str = self._parse_time(raw)
            processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
            message_list = self._build_onebot_message(processed, user_id)
            await self._send_group_msg(event, group_id, message_list)
        
        except Exception as e:
            logger.error(f"处理退群事件时出错: {e}")

    # ==================== 指令处理 ====================
    @filter.command_group("welcome", "欢迎功能管理")
    def welcome(self):
        pass

    @welcome.command("set", description="设置当前群欢迎语", alias={'设置欢迎'})
    async def set_welcome(self, event: AstrMessageEvent, message: str = ""):
        """
        设置当前群的入群欢迎语
        不填内容则重置为全局欢迎语
        """
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)

        if not message.strip():
            # 重置为全局配置
            group_config["message"] = ""
            self.save_config()
            yield event.plain_result("已重置本群欢迎语为全局默认配置")
            return

        group_config["message"] = message
        group_config["enabled"] = True
        self.save_config()
        yield event.plain_result(f"已设置本群欢迎语为：\n{message}")

    @welcome.command("on", description="开启当前群欢迎功能", alias={'开启欢迎'})
    async def enable_welcome(self, event: AstrMessageEvent):
        """开启当前群的自动欢迎功能"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)
        group_config["enabled"] = True
        self.save_config()
        yield event.plain_result("已开启本群自动欢迎功能")

    @welcome.command("off", description="关闭当前群欢迎功能", alias={'关闭欢迎'})
    async def disable_welcome(self, event: AstrMessageEvent):
        """关闭当前群的自动欢迎功能"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["enabled"] = False
            self.save_config()
            yield event.plain_result("已关闭本群自动欢迎功能")
        else:
            yield event.plain_result("本群尚未配置欢迎功能")

    @welcome.command("test", description="测试当前群欢迎语", alias={'测试欢迎'})
    async def test_welcome(self, event: AstrMessageEvent):
        """测试当前群的欢迎语效果"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self.config["groups"].get(group_id)
        
        if not group_config or not group_config.get("enabled", False):
            yield event.plain_result("本群未开启欢迎功能")
            return

        # 直接从config字典获取全局配置
        template = group_config.get("message", self.config.get("global_increase_message", "欢迎 {at} 加入本群！当前时间：{time}"))
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = event.sender.user_id
        
        processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
        message_list = self._build_onebot_message(processed, user_id)
        
        if hasattr(event, 'send'):
            await event.send(message_list)
            yield event.plain_result("已发送测试欢迎语")
        else:
            yield event.plain_result("无法发送测试消息")

    # ==================== 退群和被踢指令 ====================
    
    @filter.command_group("leave", "退群通知管理")
    def leave(self):
        pass

    @leave.command("set", description="设置退群消息", alias={'设置退群'})
    async def set_leave(self, event: AstrMessageEvent, message: str = ""):
        """
        设置当前群的退群消息
        不填内容则重置为全局退群消息
        """
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)

        if not message.strip():
            # 重置为全局配置
            group_config["leave_message"] = ""
            self.save_config()
            yield event.plain_result("已重置本群退群消息为全局默认配置")
            return

        group_config["leave_message"] = message
        group_config["leave_enabled"] = True
        self.save_config()
        yield event.plain_result(f"已设置本群退群消息为：\n{message}")

    @leave.command("on", description="开启退群通知", alias={'开启退群'})
    async def enable_leave(self, event: AstrMessageEvent):
        """开启当前群的退群通知功能"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)
        group_config["leave_enabled"] = True
        self.save_config()
        yield event.plain_result("已开启本群退群通知功能")

    @leave.command("off", description="关闭退群通知", alias={'关闭退群'})
    async def disable_leave(self, event: AstrMessageEvent):
        """关闭当前群的退群通知功能"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["leave_enabled"] = False
            self.save_config()
            yield event.plain_result("已关闭本群退群通知功能")
        else:
            yield event.plain_result("本群尚未配置退群通知功能")

    @filter.command_group("kick", "被踢通知管理")
    def kick(self):
        pass

    @kick.command("set", description="设置被踢消息", alias={'设置被踢'})
    async def set_kick(self, event: AstrMessageEvent, message: str = ""):
        """
        设置当前群的被踢消息
        不填内容则重置为全局被踢消息
        """
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)

        if not message.strip():
            # 重置为全局配置
            group_config["kick_message"] = ""
            self.save_config()
            yield event.plain_result("已重置本群被踢消息为全局默认配置")
            return

        group_config["kick_message"] = message
        group_config["kick_enabled"] = True
        self.save_config()
        yield event.plain_result(f"已设置本群被踢消息为：\n{message}")

    @kick.command("on", description="开启被踢通知", alias={'开启被踢'})
    async def enable_kick(self, event: AstrMessageEvent):
        """开启当前群的被踢通知功能"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        group_config = self._ensure_group(group_id)
        group_config["kick_enabled"] = True
        self.save_config()
        yield event.plain_result("已开启本群被踢通知功能")

    @kick.command("off", description="关闭被踢通知", alias={'关闭被踢'})
    async def disable_kick(self, event: AstrMessageEvent):
        """关闭当前群的被踢通知功能"""
        if not event.message_obj.group_id:
            yield event.plain_result("此指令只能在群聊中使用")
            return

        group_id = str(event.message_obj.group_id)
        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["kick_enabled"] = False
            self.save_config()
            yield event.plain_result("已关闭本群被踢通知功能")
        else:
            yield event.plain_result("本群尚未配置被踢通知功能")
