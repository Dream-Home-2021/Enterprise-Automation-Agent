# tasks.py
import time
import redis
import json
import uuid
from typing import Dict, Any
from fastapi import FastAPI
from pydantic import BaseModel
from celery import Celery

# 1. 框架层基础设施：配置 Celery (Broker用db1, Backend用db2)
celery_app = Celery(
    "langgraph_hybrid_agent",
    broker="redis://localhost:6380/1",
    backend="redis://localhost:6380/2"
)
celery_app.conf.update(worker_prefetch_multiplier=1, task_acks_late=True)

# 2. 业务层基础设施：配置 Redis db=3 专用于存储控制信号和内部细粒度断点
kv_store = redis.Redis(host="localhost", port=6380, db=3, decode_responses=True)

# 3. 导入 LangGraph 核心组件
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver  # 👈 导入 LangGraph 的官方持久化器

# 定义 LangGraph 的全局状态
class AgentState(dict):
    file_path: str
    analysis_result: str

class UserInterruptException(Exception):
    """专属的用户随时中断异常"""
    pass

# ==================== 🛠️ 深度配合的业务节点 ====================

def data_cleaning_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph 节点 1：负责重度数据清洗（内部包含高耗时大循环）"""
    print("\n▶️ [LangGraph 层] >>> 调度进入: data_cleaning_node")
    
    # 从配置中提取 LangGraph 的会话标识 thread_id
    thread_id = config["configurable"]["thread_id"]
    file_path = state.get("file_path", "unknown_file.csv")
    
    # 📥 【核心配合点 1】：进入节点，先去 Redis 查找属于该 thread_id 的内部细粒度进度
    checkpoint_raw = kv_store.get(f"agent:internal_checkpoint:{thread_id}")
    if checkpoint_raw:
        checkpoint = json.loads(checkpoint_raw)
        start_chunk = checkpoint.get("next_chunk", 0)
        print(f"🔄 [内部续传激活] 🚀 发现内部断点！直接跳过前 {start_chunk} 块，从第 {start_chunk} 块开始增量清洗...")
    else:
        start_chunk = 0
        print("🆕 [全新内部执行] 未发现内部断点，从第 0 块开始完整清洗。")

    try:
        # 模拟内部 5 个数据块的长耗时计算
        for chunk in range(start_chunk, 5):
            # 🛑 【随时刹车点】：每次循环头部检查 Redis 中是否有 stop 信号
            if kv_store.get(f"agent:signal:{thread_id}") == "stop":
                print(f"🛑 [安全刹车成功] 收到取消信号！在处理第 {chunk} 块前优雅停下。")
                
                # 💾 【核心配合点 2】：安全刹车时，把精确的步骤记录到 Redis
                kv_store.set(f"agent:internal_checkpoint:{thread_id}", json.dumps({"next_chunk": chunk}))
                
                # 记录任务对外公开的状态
                kv_store.set(f"agent:status:{thread_id}", json.dumps({"status": "STOPPED", "node": "data_cleaning_node", "next_chunk": chunk}))
                raise UserInterruptException("User clicked stop.")
                
            print(f"  └─ [计算中] 正在清洗大文件 [{file_path}] 的第 {chunk}/5 块数据...")
            time.sleep(2.0) # 模拟重度清洗
            
        # 🏁 5块全部顺利洗完，彻底清除 Redis 里的内部细粒度断点
        kv_store.delete(f"agent:internal_checkpoint:{thread_id}")
        print("✅ [data_cleaning_node] 节点内部全部步骤圆满完成。")
        return {"analysis_result": "Cleaned Data Output"}
        
    except UserInterruptException as e:
        raise e # 向上抛出让 LangGraph 停止
    except Exception as e:
        print(f"节点内部发生未知错误: {e}")
        raise e

def llm_summary_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph 节点 2：负责大模型总结"""
    print("\n▶️ [LangGraph 层] >>> 调度进入: llm_summary_node")
    thread_id = config["configurable"]["thread_id"]
    
    # 模拟大模型调用边界检查
    if kv_store.get(f"agent:signal:{thread_id}") == "stop":
        kv_store.set(f"agent:status:{thread_id}", json.dumps({"status": "STOPPED", "node": "llm_summary_node"}))
        raise UserInterruptException("User clicked stop before LLM.")
        
    print("  └─ [LLM 交互中] 正在调用大模型生成最终分析报告...")
    time.sleep(2.0)
    return {"analysis_result": "Premium Analytics Report v1.0"}


# ==================== 📐 构建与编译 LangGraph 状态机 ====================

workflow = StateGraph(AgentState)
workflow.add_node("clean_data", data_cleaning_node)
workflow.add_node("llm_summary", llm_summary_node)

workflow.set_entry_point("clean_data")
workflow.add_edge("clean_data", "llm_summary")
workflow.add_edge("llm_summary", END)

# 💡 【核心关键】：这里配置 LangGraph 自带的 MemorySaver
# 它会自动在内存中帮我们记录当前的节点流转状态（比如任务停在哪个节点）
langgraph_memory = MemorySaver()
app_graph = workflow.compile(checkpointer=langgraph_memory)


# ==================== 📦 Celery 异步任务包装器 ====================

@celery_app.task(bind=True)
def run_langgraph_pipeline_task(self, thread_id: str, file_path: str = None, is_resume: bool = False):
    """Celery 计算节点容器：运行 LangGraph 图实例"""
    print(f"\n🚀 Celery Worker 激活任务! Thread ID (会话ID): {thread_id}")
    kv_store.set(f"agent:status:{thread_id}", json.dumps({"status": "RUNNING"}))
    
    # LangGraph 的关键配置项：thread_id 相同，它就会自动去追溯该会话的节点断点
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        if is_resume:
            print("🔗 [LangGraph 恢复] 框架开始寻找上次死掉的节点...")
            # 恢复时，我们不需要传初始状态数据（传 None），LangGraph 会自动从它的 checkpointer 中还原节点状态！
            app_graph.invoke(None, config=config)
        else:
            print(f"🆕 [LangGraph 启动] 初始化全局状态，文件路径: {file_path}")
            initial_state = {"file_path": file_path, "analysis_result": ""}
            app_graph.invoke(initial_state, config=config)
            
        # 流程全部没有遇到任何异常，顺利跑完
        kv_store.set(f"agent:status:{thread_id}", json.dumps({"status": "SUCCESS"}))
        print(f"🏁 Thread {thread_id} 全图所有节点执行成功！")
        return "Pipeline Success"
        
    except Exception as e:
        # 接住业务抛出的 UserInterruptException，Celery 进程不挂，优雅完结
        print(f"ℹ️ LangGraph 管道被中断退出，退出原因: {e}")
        return "Pipeline Interrupted"


# ==================== 🌐 FastAPI 控制层 Web 接口 ====================

api_server = FastAPI(title="LangGraph 双层恢复测试控制台")

class RunRequest(BaseModel):
    file_path: str

@api_server.post("/agent/start")
def start_agent(req: RunRequest):
    """开启全新任务"""
    thread_id = str(uuid.uuid4()) # 生成唯一的会话ID
    kv_store.delete(f"agent:signal:{thread_id}")
    # 异步推入队列
    run_langgraph_pipeline_task.delay(thread_id, file_path=req.file_path, is_resume=False)
    return {"message": "LangGraph全新任务已在后台启动", "thread_id": thread_id}

@api_server.post("/agent/stop/{thread_id}")
def stop_agent(thread_id: str):
    """随时紧急叫停"""
    kv_store.set(f"agent:signal:{thread_id}", "stop")
    return {"message": "已下发停止信号，LangGraph 将在最近的内部循环或节点边界安全刹车。"}

@api_server.post("/agent/resume/{thread_id}")
def resume_agent(thread_id: str):
    """一键断点续传"""
    kv_store.delete(f"agent:signal:{thread_id}")
    # 告诉 Celery，我们要触发恢复逻辑了
    run_langgraph_pipeline_task.delay(thread_id, is_resume=True)
    return {"message": f"任务 {thread_id} 双层恢复机制已被激活！"}

@api_server.get("/agent/status/{thread_id}")
def get_status(thread_id: str):
    """查询当前状态双向绑定的结果"""
    status = kv_store.get(f"agent:status:{thread_id}")
    internal_checkpoint = kv_store.get(f"agent:internal_checkpoint:{thread_id}")
    
    # 同时看看 LangGraph 框架层的记忆
    graph_state = app_graph.get_state({"configurable": {"thread_id": thread_id}})
    
    return {
        "thread_id": thread_id,
        "kv_store_status": json.loads(status) if status else "UNKNOWN",
        "redis_internal_checkpoint": json.loads(internal_checkpoint) if internal_checkpoint else "NONE (节点内部未积压数据或已洗完)",
        "langgraph_next_node": graph_state.next if graph_state else "UNKNOWN"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api_server, host="127.0.0.1", port=8111)