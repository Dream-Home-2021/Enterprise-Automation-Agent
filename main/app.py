# -*- coding: utf-8 -*-

"""
应用入口：组装 Agent + 启动 Gradio UI
"""

import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.web_ui import create_ui, theme, custom_css
from agent.service import make_generate_response


def main():
    # 创建流式响应生成器
    generate_response = make_generate_response()

    # 创建 Gradio UI
    app = create_ui(
        llm_func=generate_response,
        tab_name="My Agent - LangGraph MVP",
        main_title="🤖 My Agent",
    )

    # 启动服务
    app.launch(
        server_name="localhost",
        server_port=7860,
        share=False,
        theme=theme,
        css=custom_css,
    )


if __name__ == "__main__":
    main()