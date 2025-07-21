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
        self.uvicorn_server = None
        self.server_tasks: Dict[str, asyncio.Task] = {}

    def start_server(self, handler: Callable) -> str:
        # if self.servers[self.uri]:
        #     logger.warning(f"WebSocket服务器已在运行：{self.uri}")
        #     return f"WebSocket服务器已存在：{self.uri}"

        server = WebSocketServer(self, handler)
        self.servers[self.uri] = server
        self.uvicorn_server = uvicorn.Server(uvicorn.Config(
            self.app,
            self.host,
            self.port,
        ))

        self.server_tasks[self.uri] = asyncio.create_task(self.uvicorn_server.serve())

        @self.app.websocket(self.path)
        async def websocket_endpoint(websocket: WebSocket):
            client_id = f"{uuid.uuid4()}"
            await server.handle_client(websocket, client_id)

        logger.info(f"WebSocket服务器已启动：{self.uri}")
        return self.uri

    async def stop_server(self, uri: str, reason: str = "WebSocket服务器已停止"):
        server = self.servers[uri]
        await server.stop_all(reason)
        del self.servers[uri]

        await self.uvicorn_server.shutdown()
        self.server_tasks[uri].cancel()
        del self.server_tasks[uri]
        logger.info(f"WebSocket服务器 {uri} 已停止")
        return True

    async def send_to_client(self, uri: str, client_id: str, message: str):
        """向特定服务器上的特定客户端发送消息"""
        if uri in self.servers:
            await self.servers[uri].send_message(client_id, message)
        else:
            logger.error(f"单播消息失败，未找到用于发送单播消息的服务器：{uri}")

    async def broadcast(self, uri: str, message: str):
        if uri in self.servers:
            await self.servers[uri].broadcast(message)
        else:
            logger.error(f"广播消息失败，未找到用于发送广播消息的服务器：{uri}")

    def get_servers(self) -> list:
        return list(self.servers.keys())
