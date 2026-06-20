"""
应用入口：组装 Agent + 启动 Gradio UI
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.web_ui import create_ui, theme, custom_css
from agent.service import make_generate_response
from utils.log import get_logger

logger = get_logger("main")


def main():
    logger.info("Starting agent UI...")
    generate_response = make_generate_response()

    app = create_ui(
        llm_func=generate_response,
        tab_name="My Agent - LangGraph MVP",
        main_title="🤖 My Agent",
    )

    logger.info("Launching Gradio on http://localhost:7860")
    app.launch(
        server_name="localhost",
        server_port=7860,
        share=False,
        theme=theme,
        css=custom_css,
    )


if __name__ == "__main__":
    main()