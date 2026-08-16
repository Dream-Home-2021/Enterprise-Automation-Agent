# main.py
from fastapi import FastAPI
import uuid
import redis
import json
from tasks import run_openclaw_agent_pipeline

app = FastAPI(title="OpenClaw 风格 Agent 控制台")
kv_store = redis.Redis(host="localhost", port=6380, db=2, decode_responses=True)

@app.post("/agent/run")
def start_or_resume_agent(task_id: str = None):
    """启动或断点恢复一个 Agent 任务"""
    if task_id:
        # 恢复现有任务：清除之前的停止信号
        kv_store.delete(f"agent:signal:{task_id}")
        run_openclaw_agent_pipeline.delay(task_id, resume=True)
        message = f"任务 {task_id} 已从检查点触发断点续传！"
    else:
        # 开启全新任务
        task_id = str(uuid.uuid4())
        run_openclaw_agent_pipeline.delay(task_id, resume=False)
        message = "全新 Agent 数据分析任务已启动。"
        
    return {"message": message, "task_id": task_id}

@app.post("/agent/stop/{task_id}")
def stop_agent(task_id: str):
    """【发送中断指令】向 Steering Queue 写入 stop 信号"""
    if not kv_store.get(f"agent:status:{task_id}"):
        return {"error": "未找到对应的 Agent 任务"}
        
    # 模拟 OpenClaw 的 Steering 机制：不直接杀进程，而是下发 stop 信号
    kv_store.set(f"agent:signal:{task_id}", "stop")
    return {"message": "停止指令已下发，Agent 将在下一个安全边界自动刹车。"}

@app.get("/agent/status/{task_id}")
def get_agent_status(task_id: str):
    """查询任务当前的状态和检查点"""
    status = kv_store.get(f"agent:status:{task_id}")
    checkpoint = kv_store.get(f"agent:checkpoint:{task_id}")
    return {
        "task_id": task_id,
        "live_status": json.loads(status) if status else "UNKNOWN",
        "last_checkpoint": json.loads(checkpoint) if checkpoint else "NONE"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8111)