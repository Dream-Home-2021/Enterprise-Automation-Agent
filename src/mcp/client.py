"""
MCP 沙箱客户端 — Docker 容器隔离执行

职责：
  - 为每个 Session 调度独立的 Docker 容器实例
  - 资源硬限制：CPU ≤ 0.5 核, Memory ≤ 512MB
  - 代码执行超时：≤ 10s，超时自动 kill
  - 文件读写隔离在容器工作目录内
"""

import os
import asyncio
from typing import Optional

import docker
from docker.errors import DockerException, ContainerError, NotFound
from dotenv import load_dotenv

load_dotenv()

# 配置
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "emotional-agent-sandbox:latest")
CPU_LIMIT = float(os.getenv("SANDBOX_CPU_LIMIT", "0.5"))
MEM_LIMIT = os.getenv("SANDBOX_MEM_LIMIT", "512m")
EXEC_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "10"))

# Docker 客户端单例
_docker_client: Optional[docker.DockerClient] = None


def _get_client() -> docker.DockerClient:
    """获取 Docker 客户端"""
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


# ---------------------------------------------------------------------------
# 容器生命周期管理
# ---------------------------------------------------------------------------

async def create_sandbox_container(session_id: str, file_path: str = "") -> str:
    """
    为指定 Session 创建隔离沙箱容器

    Args:
        session_id: 会话标识（用于容器命名隔离）
        file_path: 需要挂载的数据文件路径

    Returns:
        容器 ID
    """
    client = _get_client()
    container_name = f"sandbox-{session_id.replace('/', '-')}"

    # 清理可能存在的同名旧容器
    try:
        old = client.containers.get(container_name)
        old.remove(force=True)
        print(f"[sandbox] Removed stale container: {container_name}")
    except NotFound:
        pass

    # 构建挂载卷
    volumes = {}
    if file_path and os.path.exists(file_path):
        abs_path = os.path.abspath(file_path)
        volumes[abs_path] = {"bind": f"/workspace/{os.path.basename(abs_path)}", "mode": "rw"}

    def _create():
        return client.containers.create(
            image=SANDBOX_IMAGE,
            name=container_name,
            detach=True,
            network_mode="none",          # 网络隔离
            cpu_quota=int(CPU_LIMIT * 100000),  # CPU 限制
            mem_limit=MEM_LIMIT,          # 内存限制
            memswap_limit=MEM_LIMIT,      # 禁止 swap
            working_dir="/workspace",
            volumes=volumes,
            command="sleep infinity",     # 保持容器运行
        )

    container = await asyncio.to_thread(_create)
    await asyncio.to_thread(container.start)

    print(f"[sandbox] Container '{container_name}' started (CPU≤{CPU_LIMIT}, MEM≤{MEM_LIMIT})")
    return container.id


async def destroy_sandbox_container(session_id: str):
    """销毁沙箱容器"""
    client = _get_client()
    container_name = f"sandbox-{session_id.replace('/', '-')}"

    try:
        def _remove():
            container = client.containers.get(container_name)
            container.remove(force=True)

        await asyncio.to_thread(_remove)
        print(f"[sandbox] Container '{container_name}' destroyed.")

    except NotFound:
        pass


# ---------------------------------------------------------------------------
# 代码执行
# ---------------------------------------------------------------------------

async def execute_in_sandbox(code: str, file_path: str = "", session_id: str = "default") -> dict:
    """
    在隔离沙箱中执行 Python 代码

    Args:
        code: Python 代码
        file_path: 数据文件路径
        session_id: 会话 ID

    Returns:
        {"stdout": str, "stderr": str, "exit_code": int}
    """
    client = _get_client()
    container_name = f"sandbox-{session_id.replace('/', '-')}"

    try:
        def _exec():
            try:
                container = client.containers.get(container_name)
            except NotFound:
                return {"error": f"Sandbox container '{container_name}' not found."}

            try:
                exit_code, output = container.exec_run(
                    cmd=["python", "-c", code],
                    demux=True,
                    workdir="/workspace",
                )
                stdout, stderr = output
                return {
                    "stdout": (stdout or b"").decode("utf-8", errors="replace"),
                    "stderr": (stderr or b"").decode("utf-8", errors="replace"),
                    "exit_code": exit_code,
                }
            except Exception as e:
                return {"error": str(e)}

        # 带超时执行
        result = await asyncio.wait_for(
            asyncio.to_thread(_exec),
            timeout=EXEC_TIMEOUT,
        )
        return result

    except asyncio.TimeoutError:
        # 超时强杀
        try:
            def _kill():
                container = client.containers.get(container_name)
                container.kill()
            await asyncio.to_thread(_kill)
        except Exception:
            pass

        return {
            "error": f"Execution timeout ({EXEC_TIMEOUT}s). Process killed.",
            "exit_code": -1,
        }


async def read_file_from_sandbox(file_path: str, session_id: str = "default") -> dict:
    """从沙箱中读取文件"""
    client = _get_client()
    container_name = f"sandbox-{session_id.replace('/', '-')}"

    def _read():
        try:
            container = client.containers.get(container_name)
            exit_code, output = container.exec_run(
                cmd=["cat", f"/workspace/{os.path.basename(file_path)}"],
                demux=True,
            )
            stdout, _ = output
            return {"content": (stdout or b"").decode("utf-8", errors="replace")}
        except Exception as e:
            return {"error": str(e)}

    return await asyncio.to_thread(_read)


async def list_sandbox_files(directory: str = "/workspace", session_id: str = "default") -> dict:
    """列出沙箱目录文件"""
    client = _get_client()
    container_name = f"sandbox-{session_id.replace('/', '-')}"

    def _list():
        try:
            container = client.containers.get(container_name)
            exit_code, output = container.exec_run(
                cmd=["ls", "-la", directory],
                demux=True,
            )
            stdout, _ = output
            return {"files": (stdout or b"").decode("utf-8", errors="replace")}
        except Exception as e:
            return {"error": str(e)}

    return await asyncio.to_thread(_list)
