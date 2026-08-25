import logging
import sys

class SilenceFilter(logging.Filter):
    """Filter out noisy messages that we don't want to see in the console."""
    def filter(self, record):

        msg = record.getMessage()

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

    # Clear root logger handlers to prevent duplicates from other modules

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)

    logger = logging.getLogger("src")

    logger.setLevel(logging.DEBUG)
    logger.propagate = False


    if logger.hasHandlers():
        logger.handlers.clear()


    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler (Filtered progress)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SilenceFilter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


    for name in ["asyncio", "anyio", "httpx", "httpcore", "langchain", "langgraph"]:
        logging.getLogger(name).setLevel(logging.CRITICAL)

    return logger
