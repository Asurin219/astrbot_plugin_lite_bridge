import asyncio
import uuid
from typing import Callable, Dict

import uvicorn
from fastapi import FastAPI, WebSocket

from astrbot.api import logger
from .websocket_server import WebSocketServer


class WebSocketManager:
    def __init__(self, config):
        self.app = FastAPI()
        self.config = config
        self.host = config["listening_address"]
        self.port = config["listening_port"]
        self.path = config["endpoint"]
        self.uri = f"ws://{self.host}:{self.port}{self.path}"
        self.servers: Dict[str, WebSocketServer] = {}
        self.server_tasks: Dict[str, asyncio.Task] = {}

    def start_server(self, handler: Callable) -> str:
        if self.path in self.servers:
            logger.warning(f"WebSocket服务器已在运行：{self.uri}")
            return f"WebSocket服务器已存在：{self.uri}"

        server = uvicorn.Server(uvicorn.Config(
            self.app,
            self.host,
            self.port,
        ))

        asyncio.create_task(server.serve())
        server_id = str(uuid.uuid4())
        server = WebSocketServer(self, handler)
        self.servers[server_id] = server

        @self.app.websocket(self.path)
        async def websocket_endpoint(websocket: WebSocket):
            client_id = f"{uuid.uuid4()}"
            await server.handle_client(websocket, client_id)

        logger.info(f"WebSocket服务器已启动：{self.uri}")
        return server_id

    async def stop_server(self, server_id: str, reason: str = "WebSocket服务器已停止"):
        if server_id not in self.servers:
            logger.error(f"WebSocket服务器 {server_id} 未找到")
            return False

        server = self.servers[server_id]
        await server.stop_all(reason)
        del self.servers[server_id]
        logger.info(f"WebSocket服务器 {server_id} 已停止")
        return True

    async def send_to_client(self, server_id: str, client_id: str, message: str):
        """向特定服务器上的特定客户端发送消息"""
        if server_id in self.servers:
            await self.servers[server_id].send_message(client_id, message)
        else:
            logger.error(f"单播消息失败，未找到用于发送单播消息的服务器：{server_id}")

    async def broadcast(self, server_id: str, message: str):
        if server_id in self.servers:
            await self.servers[server_id].broadcast(message)
        else:
            logger.error(f"广播消息失败，未找到用于发送广播消息的服务器：{server_id}")

    def get_server_ids(self) -> list:
        return list(self.servers.keys())
