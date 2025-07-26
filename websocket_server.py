from typing import Callable, Any

from fastapi import WebSocket, WebSocketDisconnect, status

from astrbot.api import logger
from . import websocket_manager


class WebSocketServer:
    def __init__(self, manager: websocket_manager, handler: Callable):
        self.manager = manager
        self.handler = handler
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"客户端 {client_id} 已连接")

    async def disconnect(self, client_id: str, reason: str = None):
        if client_id in self.active_connections:
            logger.info(f"客户端 {client_id} 断开了连接：{reason}")
            del self.active_connections[client_id]

    async def handle_client(self, websocket: WebSocket, client_id: str):
        await self.connect(websocket, client_id)
        try:
            while True:
                try:
                    data = await websocket.receive_text()
                    await self.handler(websocket, client_id, data)
                except WebSocketDisconnect as e:
                    await self.disconnect(client_id, reason=e.reason)
                    break
                except Exception as e:
                    logger.error(f"处理客户端 {client_id} 的消息时遇到错误：{e}")
                    await websocket.send_text(f"处理WebSocket消息时遇到错误：{str(e)}")
        finally:
            if client_id in self.active_connections:
                await self.disconnect(client_id, reason="Finally")

    async def send_message(self, client_id: str, message: str):
        """向特定客户端发送消息"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(message)
                logger.debug(f"发送消息到客户端：{client_id}（消息内容：{message}）")
            except Exception as e:
                logger.error(f"发送消息到客户端 {client_id} 失败：{e}")
        else:
            logger.warning(f"未找到发送消息的目标客户端：{client_id}")

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"广播消息时遇到错误：{e}")

    async def stop_all(self, reason: str = "WebSocket服务器已关闭"):
        for client_id in list(self.active_connections.keys()):
            await self.disconnect(client_id, reason=reason)
