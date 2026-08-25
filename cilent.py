# client.py
import requests
import time
from pynput import keyboard

# 配置你的 FastAPI 地址
BASE_URL = "http://127.0.0.1:8111"
CURRENT_THREAD_ID = None
IS_RUNNING = False

def on_press(key):
    global CURRENT_THREAD_ID, IS_RUNNING
    try:
        # 🎯 【核心拦截点】：当检测到按下了键盘的 ESC 键
        if key == keyboard.Key.esc and IS_RUNNING and CURRENT_THREAD_ID:
            print(f"\n⌨️  [检测到按下 ESC] 正在向后台紧急下发中断信号... Thread ID: {CURRENT_THREAD_ID}")
            
            # 向 FastAPI 发送 stop 请求
            response = requests.post(f"{BASE_URL}/agent/stop/{CURRENT_THREAD_ID}")
            if response.status_code == 200:
                print("🛑 停止信号下发成功！Agent 将在最近的内部循环边界安全刹车。")
                IS_RUNNING = False
                return False # 停止键盘监听器
            else:
                print(f"❌ 下发失败: {response.text}")
    except Exception as e:
        print(f"监听出错: {e}")

def start_remote_agent():
    global CURRENT_THREAD_ID, IS_RUNNING
    print("🚀 正在通过客户端向后台请求启动全新数据分析任务...")
    
    # 1. 触发 FastAPI 的 start 接口
    payload = {"file_path": "heavy_keyboard_demo_2026.csv"}
    try:
        response = requests.post(f"{BASE_URL}/agent/start", json=payload)
        if response.status_code == 200:
            CURRENT_THREAD_ID = response.json().get("thread_id")
            IS_RUNNING = True
            print(f"✅ 任务启动成功！当前会话 Thread ID: {CURRENT_THREAD_ID}")
            print("💡 【提示】现在你可以随时按下 [ESC] 键来紧急叫停该任务...\n")
            
            # 2. 启动异步键盘监听器
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
        else:
            print(f"启动失败: {response.text}")
    except Exception as e:
        print(f"无法连接到 FastAPI 服务器: {e}")

if __name__ == "__main__":
    start_remote_agent()