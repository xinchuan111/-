from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        logger.error("🔥 MyPlugin LOADED (helloworld) 🔥")

    async def initialize(self):
        pass

    # ✅ 群聊消息监听：放在类里
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        logger.error("🟣 GROUP MESSAGE HANDLER TRIGGERED 🟣")
        msg = event.message_obj
        logger.info("====== DEBUG: raw message chain ======")
        logger.info(repr(msg.message))   # 最关键：看 Face/Image 段字段
        logger.info(str(msg.message))    # 可选：更好读
        logger.info("====== DEBUG END ======")

        # 不要 yield，避免每条群消息都自动回复（这里只做打印）
        return

    # 指令：/helloworld
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        user_name = event.get_sender_name()
        message_str = event.message_str
        message_chain = event.get_messages()
        logger.info(f"command message_chain => {repr(message_chain)}")

        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!")

    async def terminate(self):
        pass