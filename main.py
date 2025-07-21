import json

from fastapi import WebSocket

import astrbot.core.message.components as Comp
from astrbot.api import AstrBotConfig
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain
from .websocket_manager import WebSocketManager


@register("LiteBridge", "Asurin219", "基于WebSocket的Minecraft群服互通插件", "1.0.0")
class LiteBridge(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config["websocket_server_config"]
        self.manager = None

    async def initialize(self):
        """初始化插件"""
        self.manager = WebSocketManager(self.config)

        self.manager.start_server(self.websocket_message_handler)

        logger.info("LiteBridge插件已初始化")

    async def websocket_message_handler(self, websocket: WebSocket, client_id: str, message_str):

        try:
            message = json.loads(message_str)
            message_flag = message.get("message_flag")
            params = message.get("params", {})

            logger.debug(f'收到Minecraft游戏消息: {message}')

            # 只转发特定事件到QQ
            if message_flag not in [1001, 1002, 1003, 1004, 1011, 1012, 1013, 1014, 1015]: return

            server_name = params.get("server_name")
            content = None

            # 构造QQ消息内容
            if message_flag == 1001:
                content = f'[{server_name}] 服务器正在启动'
            elif message_flag == 1002:
                content = f'[{server_name}] 服务器启动完成'
            elif message_flag == 1003:
                content = f'[{server_name}] 服务器正在关闭'
            elif message_flag == 1004:
                content = f'[{server_name}] 服务器已经关闭'
            elif message_flag == 1011:
                content = f'[{server_name}] {params.get("player_name")} 加入了服务器'
            elif message_flag == 1012:
                content = f'[{server_name}] {params.get("player_name")} 离开了服务器'
            elif message_flag == 1013:
                content = f'[{server_name}]\n{params.get("player_name")}：{params.get("chat_message", "")}'
            elif message_flag == 1014:
                content = f'[{server_name}]\n{params.get("player_name")}似了~（原因：{params.get("dead_reason", "")}）'
            elif message_flag == 1015:
                content = f'[{server_name}]\n{params.get("player_name")}获得成就: {params.get("advancement", "")}'

            for group_id in self.config.get("group_ids"):
                if group_id is None: return
                umo = f"aiocqhttp:GroupMessage:{group_id}"

                chain = MessageChain(chain=[Comp.Plain(content)])
                await self.context.send_message(umo, chain)

        except Exception as e:
            logger.error(f'处理Minecraft消息遇到错误: {e}')

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """处理QQ群消息"""
        message_obj = event.message_obj
        group_info = await self.get_group_info(event)
        group_name = group_info["group_name"]
        group_id = str(message_obj.group_id)

        user_name = message_obj.sender.nickname
        user_id = message_obj.sender.user_id
        message_str = message_obj.message_str

        logger.info(f'[{group_name}]<{user_name}> {message_str}')

        # 构建QQ消息格式
        message = {
            "message_flag": 2003,
            "params": {
                "group_id": group_id,
                "group_name": group_name,
                "member_id": user_id,
                "member_name": user_name,
                "chat_message": message_str,
                "raw_message": f'§b[QQ群聊]§e ({group_name}) §a<{user_name}> §r{message_str}'
            }
        }

        if group_id not in self.config.get("group_ids"): return

        for server in self.manager.get_servers():
            await self.manager.broadcast(server, json.dumps(message))

    async def get_group_info(self, event: AstrMessageEvent):
        """获取QQ群信息"""
        if event.get_platform_name() != "aiocqhttp":
            return {"group_name": "未知群组"}

        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
        assert isinstance(event, AiocqhttpMessageEvent)

        client = event.bot
        payloads = {"group_id": event.message_obj.group_id}

        try:
            return await client.api.call_action('get_group_info', **payloads)
        except Exception:
            return {"group_name": "未知群组"}

    async def terminate(self):
        for server in self.manager.get_servers():
            await self.manager.stop_server(server, "Server shutdown")
            logger.info("WebSocket服务已停止")
