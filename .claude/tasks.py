# tasks.py
import time
import redis
import json
from celery import Celery

# 1. 初始化 Celery (使用本地 Redis)
app = Celery(
    "openclaw_style_agent",
    broker="redis://localhost:6380/1",
    backend="redis://localhost:6380/2"
)
app.conf.update(worker_prefetch_multiplier=1, task_acks_late=True)

# 2. 初始化用于控制信号的 Redis 连接
kv_store = redis.Redis(host="localhost", port=6380, db=2, decode_responses=True)

class OpenClawInterruptException(Exception):
    """仿 OpenClaw 风格的边界退出异常"""
    pass

def check_steering_queue_for_cancel(task_id: str, boundary_name: str) -> bool:
    """
    【OpenClaw 精神核心】：转向队列/信号检查点。
    高频调用，检查用户是否发送了 stop 指令。
    """
    signal = kv_store.get(f"agent:signal:{task_id}")
    if signal == "stop":
        print(f"🛑 [OpenClaw 拦截成功] 在边界 【{boundary_name}】 捕获到用户停止指令！")
        # 记录中断时的上下文和断点
        kv_store.set(f"agent:status:{task_id}", json.dumps({"status": "STOPPED", "stopped_at": boundary_name}))
        return True
    return False


# ==================== 模拟长耗时的数据分析工具 ====================

def heavy_clean_tool(task_id: str, start_chunk: int = 0) -> int:
    """工具 1：模拟大型数据清洗（包含内部多步分块循环）"""
    node_name = "Data_Cleaning_Tool"
    
    # 模拟数据连接句柄
    db_cursor = "Fake_ClickHouse_Cursor"
    
    try:
        # 模拟 4 个数据分块处理，每个分块需要较长时间
        for chunk in range(start_chunk, 4):
            # 🎯 【OpenClaw 内部循环检查点】：不在执行计算的中途强杀，而是在每个 Chunk 块处理的头部检查
            if check_steering_queue_for_cancel(task_id, f"{node_name}_chunk_{chunk}"):
                raise OpenClawInterruptException()
                
            print(f"  [工具计算中] -> {node_name} 正在清洗第 {chunk}/4 块数据...")
            time.sleep(4.5) # 模拟重度数据清洗计算
            
            # 记录子图检查点进度，以便后续断点续传
            kv_store.set(f"agent:checkpoint:{task_id}", json.dumps({"node": node_name, "next_chunk": chunk + 1}))
            
        return 0 # 正常执行完毕返回 0
    except OpenClawInterruptException:
        print(f"  🧹 [{node_name}] 收到退出信号，开始释放当前块的未提交内存...")
        raise OpenClawInterruptException() # 继续向上抛出
        
def heavy_feature_tool(task_id: str) -> int:
    """工具 2：模拟特征工程（单次耗时约 2 秒）"""
    node_name = "Feature_Engineering_Tool"
    
    # 🎯 【OpenClaw 工具执行前检查点】
    if check_steering_queue_for_cancel(task_id, f"Before_{node_name}"):
        raise OpenClawInterruptException()
        
    print(f"  [工具计算中] -> {node_name} 开始提取特征向量...")
    time.sleep(7.0) # 模拟耗时操作
    
    kv_store.set(f"agent:checkpoint:{task_id}", json.dumps({"node": "COMPLETED", "next_chunk": 0}))
    return 0


# ==================== Agent 编排管道容器 ====================

@app.task(bind=True)
def run_openclaw_agent_pipeline(self, task_id: str, resume: bool = False):
    """Celery 异步 Worker：调度各个分析节点与大模型"""
    print(f"🚀 OpenClaw-Style Agent Pipeline 启动. Task ID: {task_id}")
    kv_store.set(f"agent:status:{task_id}", json.dumps({"status": "RUNNING"}))
    
    # 读取检查点状态（用于断点恢复）
    checkpoint_raw = kv_store.get(f"agent:checkpoint:{task_id}")
    checkpoint = json.loads(checkpoint_raw) if checkpoint_raw else {"node": "START", "next_chunk": 0}
    
    try:
        # ----------------------------------------------------
        # 1. 调度节点：数据清洗
        # ----------------------------------------------------
        if checkpoint["node"] in ["START", "Data_Cleaning_Tool"]:
            heavy_clean_tool(task_id, start_chunk=checkpoint["next_chunk"])
            
        # ----------------------------------------------------
        # 🎯 黄金边界点 1：【工具与工具的交接处】
        # ----------------------------------------------------
        if check_steering_queue_for_cancel(task_id, "Boundary_Between_Tools"):
            raise OpenClawInterruptException()
            
        # ----------------------------------------------------
        # 2. 调度节点：特征工程
        # ----------------------------------------------------
        if checkpoint["node"] in ["START", "Data_Cleaning_Tool", "Feature_Engineering_Tool"]:
            heavy_feature_tool(task_id)
            
        # ----------------------------------------------------
        # 🎯 黄金边界点 2：【投喂给大模型做最终总结之前】
        # ----------------------------------------------------
        if check_steering_queue_for_cancel(task_id, "Boundary_Before_LLM_Summary"):
            raise OpenClawInterruptException()
            
        print("  [LLM交互中] -> 正在调用大模型生成数据分析报告...")
        time.sleep(5.5) # 模拟大模型生成
        
        # 流程全部正常结束
        kv_store.set(f"agent:status:{task_id}", json.dumps({"status": "SUCCESS"}))
        print(f"🏁 Task {task_id} 全部节点执行成功！")
        return "Success"
        
    except OpenClawInterruptException:
        # 整个 Celery 进程没有死，安全接住了异常，能够继续高效率处理下一个用户的 Agent 任务
        print(f"ℹ️ Pipeline 捕捉到边界退出信号，Task {task_id} 优雅刹车成功。")
        return "Interrupted"



# 阶段一：用户点击“开始分析”
        # 前端下发任务。Celery 启动执行 LangGraph 的 app_graph.invoke(..., config={"configurable": {"thread_id": "user_abc"}})。

        # LangGraph 激活图，状态归档：当前激活节点 = clean_data。

        # 进入节点内部，开始跑循环。洗完第 0 块，洗完第 1 块。


# 阶段二：洗到第 2 块时，用户突然点击“中断”
        # API 接收到请求，往 Redis 里塞入 agent:signal:user_abc = "stop"。

        # 节点内部循环头部检测到 stop，数据踩刹车。

        # 退出前，代码向 Redis 记了一笔：agent:internal_checkpoint:user_abc = {"next_chunk": 2}。

        # 随后抛出异常，整个 Celery 任务退出。

        # 此时的状态：

        # LangGraph 的存储里记得：user_abc 上次死在 clean_data 节点。

        # 你的 Redis 里记得：user_abc 内部洗到了 第 2 块。
        

# 阶段三：用户点击“断点续传（继续）”
        # 前端重新下发带有相同 thread_id="user_abc" 的请求。

        # 第一层恢复（LangGraph）：LangGraph 根据它的记忆，直接把图复活在 clean_data 节点。

        # 第二层恢复（你的业务逻辑）：clean_data 节点内部跑第一行代码时，去 Redis 查到了 next_chunk: 2。

        # 完美合流：代码直接执行 for chunk in range(2, 5)。