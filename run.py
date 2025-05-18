import asyncio
import sys
import uvicorn
import psutil
import gc
import os

def setup_environment():
    """设置运行环境变量和参数"""
    
    # 禁用无头浏览器时的沙箱
    os.environ["PLAYWRIGHT_CHROMIUM_NO_SANDBOX"] = "1"
    
    # 强制使用默认字体
    os.environ["PLAYWRIGHT_FORCE_SYSTEM_FONTS"] = "1"
    
    # 调整Python GC策略
    gc.set_threshold(700, 10, 5)  # 更积极的GC策略

if __name__ == "__main__":
    # 设置环境
    setup_environment()
    
    # 确保设置了正确的事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        # 预创建一个事件循环确保类型正确
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    # 获取CPU数量，用于设置工作进程数
    cpu_count = psutil.cpu_count(logical=False) or 1
    workers = max(1, cpu_count)
    
    print(f"系统检测到 {cpu_count} 个物理CPU核心，设置 {workers} 个工作进程")
    print("开始启动网页截图服务...")
    
    uvicorn.run(
        "fastapi_webprtsc:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 关闭 reload 避免事件循环相关问题
        workers=1,     # 单进程模式，因为我们使用异步任务
        log_level="info"
    )
