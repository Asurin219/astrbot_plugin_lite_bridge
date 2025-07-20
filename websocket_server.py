from typing import Callable, Any

from fastapi import WebSocket, WebSocketDisconnect, status

from astrbot.api import logger


class WebSocketServer:
    def __init__(self, manager: Any, handler: Callable):
        self.manager = manager
        self.handler = handler
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"客户端 {client_id} 已连接")

    async def disconnect(self, client_id: str, code: int = status.WS_1000_NORMAL_CLOSURE, reason: str = None):
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            try:
                await websocket.close(code=code, reason=reason)
            except Exception as e:
                logger.error(f"客户端 {client_id} 关闭连接时遇到错误：{e}")
            finally:
                del self.active_connections[client_id]
                logger.info(f"客户端 {client_id} 已正常断开连接，原因：{reason}")

    async def handle_client(self, websocket: WebSocket, client_id: str):
        await self.connect(websocket, client_id)
        try:
            while True:
                try:
                    data = await websocket.receive_text()
                    await self.handler(websocket, client_id, data)
                except WebSocketDisconnect as e:
                    logger.info(f"客户端 {client_id} 断开连接：{e.reason}")
                    await self.disconnect(client_id, e.code, e.reason)
                    break
                except Exception as e:
                    logger.error(f"Error handling message from {client_id}: {e}")
                    await websocket.send_text(f"处理WebSocket消息时遇到错误：{str(e)}")
        finally:
            if client_id in self.active_connections:
                await self.disconnect(client_id, reason="连接中止")

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
