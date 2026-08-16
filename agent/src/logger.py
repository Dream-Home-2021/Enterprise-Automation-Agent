# ============================================================================
# 文件角色：项目日志系统（控制台 + 文件双输出，自动过滤噪音）
# 小白导读：
#   - logging：Python 内置的日志库，用于记录程序运行时的信息、警告、错误
#   - Filter：日志过滤器，决定哪些日志该显示、哪些该隐藏
#   - Handler：日志处理器，决定日志输出到哪里（控制台/文件/网络等）
#   - Formatter：日志格式器，决定日志的显示样式（时间-名称-级别-内容）
#   - MCP：Model Context Protocol，让 AI 模型能调用外部工具的协议
# 协作关系：
#   - 被 src/ 下所有模块调用，统一记录日志
#   - 控制台只显示 INFO 及以上级别，文件记录 DEBUG 及以上（更详细）
# ============================================================================
import logging  # Python 内置日志模块
import sys  # 系统模块，用于获取标准输出（控制台）

class SilenceFilter(logging.Filter):
    """Filter out noisy messages that we don't want to see in the console."""
    def filter(self, record):
        # 小白导读: filter 方法对每条日志返回 True（保留）或 False（丢弃）
        msg = record.getMessage()
        # Blacklist of noisy substrings
        # 小白导读: 黑名单——包含这些关键词的日志会被过滤掉，避免控制台刷屏
        blacklist = [
            "asynchronous generator",
            "cancel scope",
            "different task than it was entered in",
            "Loaded",
            "tools from MCP",
            "Created adapter",
            "Connected to MCP",
            "Connecting to MCP",
            "Discovered",
            "Client does not support MCP Roots",
            "Traceback",
            "GeneratorExit"
        ]
        # 如果消息中包含黑名单任意一项，返回 False（不显示）
        return not any(term in msg for term in blacklist)

# Configure logging
def setup_logger(log_file:str='agent.log'):
    # 小白导读: 初始化日志系统，返回一个配置好的 logger 对象
    # Clear root logger handlers to prevent duplicates from other modules
    # 小白导读: 清除根日志器已有的处理器，避免其他模块重复添加导致日志重复输出
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)  # 根日志器只记录 WARNING 及以上级别

    logger = logging.getLogger("src") # Use a top-level name
    # 小白导读: 创建名为 "src" 的日志器，所有子模块可用 getLogger("src.xxx") 继承配置
    logger.setLevel(logging.DEBUG)  # 该日志器记录 DEBUG 及以上级别（最详细）
    logger.propagate = False # Prevent double logging
    # 小白导读: 禁止日志向父级传播，避免同一条日志被打印两次

    if logger.hasHandlers():
        logger.handlers.clear()  # 清除已有处理器，防止重复

    # Formatter
    # 小白导读: 定义日志输出格式：时间 - 日志器名 - 级别 - 消息内容
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # File handler (Keep everything for debugging)
    # 小白导读: 文件处理器——把日志写入文件，用于事后排查问题
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)  # 文件记录最详细的 DEBUG 级别
    file_handler.setFormatter(formatter)

    # Console handler (Filtered progress)
    # 小白导读: 控制台处理器——把日志打印到屏幕，方便实时观察
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # 控制台只显示 INFO 及以上（减少噪音）
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SilenceFilter())  # 小白导读: 给控制台加上过滤器，屏蔽黑名单里的噪音日志

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Force global suppression again to be sure
    # 小白导读: 强制把第三方库的日志级别设为 CRITICAL，彻底屏蔽它们的输出
    for name in ["asyncio", "anyio", "httpx", "httpcore", "langchain", "langgraph"]:
        logging.getLogger(name).setLevel(logging.CRITICAL)

    return logger
