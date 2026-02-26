from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At, Plain
import json
import os
import time
from datetime import datetime
from pathlib import Path

@register("welcome_group", "User", "QQ群新人入群自动欢迎插件", "1.0.4", "https://github.com/User/astrbot_plugin_Welcome-group")
class WelcomePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 尝试获取数据目录，如果失败则回退到当前目录
        try:
            from astrbot.api.star import StarTools
            self.data_dir = StarTools.get_data_dir() / "welcome_group"
        except ImportError:
            self.data_dir = Path(os.getcwd()) / "data" / "welcome_group"
        
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
        self.config_path = self.data_dir / "config.json"
        self.config = self.load_config()

    def load_config(self):
        default_config = {
            "default_message": "欢迎 {at} 加入本群！当前时间：{time}",
            "groups": {}
        }
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
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

    # 监听事件
    # 尝试使用 platform_adapter_type 来监听特定平台的所有事件，这通常比 event_message_type 更宽泛
    # 如果 PlatformAdapterType 不可用，回退到 event_message_type
    try:
        from astrbot.api.event.filter import PlatformAdapterType, EventMessageType
        
        # 优先尝试监听 AIOCQHTTP (OneBot) 平台的所有事件
        # 注意：这里我们同时使用了两个装饰器，或者根据环境选择一个
        # 为了保险起见，我们定义一个统一的 handler，并尝试用多种方式注册
        
        # 策略：如果能导入 PlatformAdapterType，就用它。这通常能捕获所有来自该 Adapter 的事件。
try:
@filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
        async def on_group_increase(self, event: AstrMessageEvent):
            result = await self._handle_group_increase(event)
            if result:
                yield result
            
    except ImportError:
        # 回退方案
        try:
            from astrbot.api.event import EventMessageType
@filter.event_message_type(EventMessageType.ALL)
            async def on_group_increase(self, event: AstrMessageEvent):
                result = await self._handle_group_increase(event)
                if result:
                    yield result
        except ImportError:
            logger.error("WelcomePlugin: 无法导入必要的 Filter 类型，监听可能失败。")

    async def _handle_group_increase(self, event: AstrMessageEvent):
        """统一处理逻辑"""
        try:
            # 兼容不同类型的 event 对象获取 raw_message
            raw = None
            if hasattr(event, 'raw_message'):
                raw = event.raw_message
            elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'raw_message'):
                raw = event.message_obj.raw_message
            
            # 调试日志：打印事件类型，帮助用户排查
            if raw and isinstance(raw, dict):
                post_type = raw.get("post_type")
                notice_type = raw.get("notice_type")
                # 仅在是 notice 事件时打印日志，避免刷屏
                if post_type == "notice":
                    logger.debug(f"WelcomePlugin received notice: {notice_type}")
            
            # 检查是否为 notice 事件且为 group_increase
            if not isinstance(raw, dict):
                return None
            
            if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_increase":
                return None

            group_id = str(raw.get("group_id"))
            user_id = raw.get("user_id")
            
            # 忽略机器人自己入群（可选）
            if str(user_id) == str(raw.get("self_id")):
                return None

            # 检查该群是否配置了欢迎语
            group_config = self.config["groups"].get(group_id)
            if not group_config or not group_config.get("enabled", False):
                return None

            welcome_template = group_config.get("message", self.config["default_message"])
            
            # 解析时间
            # OneBot 事件通常包含 time 字段 (Unix 时间戳)
            event_time = raw.get("time", time.time())
            try:
                time_str = datetime.fromtimestamp(event_time).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            message_chain = []
            
            # 替换变量
            # 先处理不需要拆分的变量
            # {time}, {user_id}, {nickname} (如果能获取到)
            
            # 注意：{nickname} 通常无法直接从 notice 获取，除非调用 API。这里暂不支持或仅支持 {user_id}
            # 如果用户写了 {nickname}，暂时替换为 user_id，或者不做处理
            processed_template = welcome_template.replace("{time}", time_str).replace("{user_id}", str(user_id))
            
            # 构建 OneBot v11 消息段 (字典格式)，用于 bot.send_group_msg
            message_list = []
            if "{at}" in processed_template:
                parts = processed_template.split("{at}")
                for i, part in enumerate(parts):
                    if part:
                        message_list.append({"type": "text", "data": {"text": part}})
                    if i < len(parts) - 1:
                        message_list.append({"type": "at", "data": {"qq": str(user_id)}})
            else:
                message_list.append({"type": "text", "data": {"text": processed_template}})

            logger.info(f"WelcomePlugin: 准备发送欢迎消息给群 {group_id} 用户 {user_id}: {message_list}")
            
            # 尝试发送消息
            # 优先使用 event.bot.send_group_msg (参照 qqadmin 插件的 JoinHandle)
            # AiocqhttpMessageEvent (event) 通常有 bot 属性 (CQHttp 客户端)
            bot = getattr(event, "bot", None)
            if bot and hasattr(bot, "send_group_msg"):
                try:
                    await bot.send_group_msg(group_id=int(group_id), message=message_list)
                    logger.info("WelcomePlugin: 通过 bot.send_group_msg 发送成功")
                    return None # 已发送，无需返回 chain_result
                except Exception as e:
                    logger.error(f"WelcomePlugin: bot.send_group_msg 发送失败: {e}")

            # 如果上述发送失败，不再尝试其他不可靠的方法，直接返回 None
            return None

        except Exception as e:
            logger.error(f"WelcomePlugin: 处理事件失败: {e}")
        return None

@filter.command_group("welcome")
    def welcome_group_cmd(self):
        """群欢迎插件管理"""
        pass

@welcome_group_cmd.command("set")
    async def set_welcome(self, event: AstrMessageEvent, message: str):
        """设置欢迎语。支持变量: {at}, {user_id}, {time}。例如: /welcome set 欢迎 {at} 于 {time} 加入！"""
        # AstrBot 默认只会解析第一个参数到 message
        # 如果消息包含空格，后面的内容会被忽略，所以需要手动获取完整内容
        # 假设指令是 /welcome set xxx yyy zzz
        # message 可能只是 xxx
        
        # 获取除去指令部分后的原始内容
        full_text = event.message_str
        # 简单的切分逻辑：找到 "set" 之后的内容
        # 注意：这依赖于指令的具体形式，如果用户用了别名可能会有问题
        # 更稳妥的方式是：
        parts = full_text.split()
        if len(parts) >= 3: # /welcome set content...
             # 重新拼接第三个参数及之后的所有内容
             message = " ".join(parts[2:])
        
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if group_id not in self.config["groups"]:
            self.config["groups"][group_id] = {}
            
        self.config["groups"][group_id]["enabled"] = True
        self.config["groups"][group_id]["message"] = message
        self.save_config()
        
        yield event.plain_result(f"已设置本群欢迎语为：\n{message}")

@welcome_group_cmd.command("on")
    async def enable_welcome(self, event: AstrMessageEvent):
        """开启当前群的欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if group_id not in self.config["groups"]:
            self.config["groups"][group_id] = {"message": self.config["default_message"]}
        
        self.config["groups"][group_id]["enabled"] = True
        self.save_config()
        yield event.plain_result("本群欢迎功能已开启。")

@welcome_group_cmd.command("off")
    async def disable_welcome(self, event: AstrMessageEvent):
        """关闭当前群的欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["enabled"] = False
            self.save_config()
            
        yield event.plain_result("本群欢迎功能已关闭。")

@welcome_group_cmd.command("test")
    async def test_welcome(self, event: AstrMessageEvent):
        """测试发送当前群的欢迎语"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        # 模拟一个 welcome 消息
        group_config = self.config["groups"].get(group_id, {})
        welcome_template = group_config.get("message", self.config["default_message"])
        
        message_chain = []
        user_id = event.get_sender_id()
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        processed_template = welcome_template.replace("{time}", time_str).replace("{user_id}", str(user_id))
        
        if "{at}" in processed_template:
            parts = processed_template.split("{at}")
            for i, part in enumerate(parts):
                if part:
                    message_chain.append(Plain(part))
                if i < len(parts) - 1:
                    message_chain.append(At(qq=user_id))
        else:
            message_chain.append(Plain(processed_template))
            
        yield event.chain_result(message_chain)
