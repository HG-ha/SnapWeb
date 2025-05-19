from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional, Dict, Any
import asyncio
import uvicorn
from pydantic import BaseModel, HttpUrl, field_validator  # 更新导入
import io
from webprtsc_playwright_async import AsyncPrtScPlaywright
from task_manager import TaskManager, TaskStatus
import psutil
from contextlib import asynccontextmanager
import sys

# 全局共享的浏览器实例
browser_instance = AsyncPrtScPlaywright()
# 任务管理器
task_manager = TaskManager(max_concurrent_tasks=psutil.cpu_count() or 2)

async def periodic_cleanup():
    """定期清理完成的旧任务"""
    while True:
        await asyncio.sleep(1)
        await task_manager.clean_old_tasks()

class ScreenshotRequest(BaseModel):
    url: HttpUrl
    device: Optional[str] = "pc"
    width: Optional[str] = ""
    height: Optional[str] = ""
    ua: Optional[str] = ""
    # 简化为直接使用元素类型和值
    element_type: Optional[str] = ""  # 例如: id, class, name, xpath, css, tag, data-*, attr, text, canvas, iframe
    element_name: Optional[str] = ""  # 用于data-*属性或其他需要名称的情况 (text/canvas/iframe 类型时忽略)
    element_value: Optional[str] = ""  # 元素的值或要匹配的文本，对于canvas和iframe则是选择器
    full_page: Optional[bool] = False  # 控制是否进行完整页面截图，浏览器方法，非滚动截图
    wait_time: Optional[float] = 1.0   # 页面加载后的等待时间（秒），默认1秒
    timeout: Optional[float] = 120.0    # 整个截图任务的超时时间（秒），默认120秒
    wait_for_resources: Optional[bool] = False  # 是否等待页面所有资源（图片、视频等）加载完成，默认False

    @field_validator('*')
    @classmethod
    def validate_element_selectors(cls, v, field):
        return v

    def get_element_info(self):
        """获取元素选择器信息"""
        if self.element_type and self.element_value:
            # 对于canvas和iframe类型，element_name不是必需的
            if self.element_type in ["canvas", "iframe"]:
                return self.element_type, "", self.element_value
            # 对于text类型，element_name不是必需的
            elif self.element_type == "text":
                return self.element_type, "", self.element_value
            # 对于其他类型，返回完整信息
            return self.element_type, self.element_name, self.element_value
        return None, None, None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    try:
        # 确保在应用启动前正确设置事件循环
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
        await browser_instance.initialize()
        # 启动任务监控
        asyncio.create_task(task_manager.start_monitoring())
        # 启动定期清理任务
        asyncio.create_task(periodic_cleanup())
        # 新增：启动浏览器资源清理任务
        asyncio.create_task(browser_instance.schedule_cleanup())
        
        yield
    except Exception as e:
        print(f"Startup error: {e}")
        raise
    finally:
        # 关闭时清理资源
        await browser_instance.close()
        await task_manager.stop_monitoring()

app = FastAPI(
    title="网页截图API",
    description="基于Playwright的异步网页截图服务",
    version="0.0.2",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {"message": "网页截图API服务已启动"}

@app.post("/screenshot/submit", response_model=Dict[str, Any])
async def submit_screenshot(request: ScreenshotRequest):
    """
    提交截图任务（支持全页面或元素截图）
    
    - **url**: 必填，网页URL
    - **device**: 可选，设备类型 (pc/phone/tablet)，默认pc
    - **width**: 可选，自定义宽度
    - **height**: 可选，自定义高度
    - **ua**: 可选，自定义User-Agent
    - **element_type**: 可选，元素选择器类型(id/class/name/xpath/css/tag/data/attr/text等)
    - **element_name**: 可选，元素名称(用于data-*或attr属性，text类型时忽略)
    - **element_value**: 可选，元素值或要匹配的文本
    - **full_page**: 可选 (仅当不指定元素时)，是否截取完整页面高度，默认False (截取视口高度)
    - **wait_time**: 可选，页面加载后的等待时间（秒），默认1秒
    - **timeout**: 可选，整个截图任务的超时时间（秒），默认90秒
    """
    element_type, element_name, element_value = request.get_element_info()

    if element_type and element_value:        # 元素截图 (full_page 不适用于元素截图)
        task_id = await task_manager.create_task(
            browser_instance.prtScPath,
            url=str(request.url),
            elename=element_name,
            eletype=element_type,
            elevalue=element_value,
            device=request.device,
            width=request.width,
            height=request.height,
            ua=request.ua,
            wait_time=request.wait_time,
            timeout=request.timeout  # 添加 timeout 参数
        )
    else:        # 全页面截图
        task_id = await task_manager.create_task(
            browser_instance.prtSc,
            url=str(request.url),
            device=request.device,
            width=request.width,
            height=request.height,
            ua=request.ua,
            full_page=request.full_page, # 传递 full_page 参数
            wait_time=request.wait_time,
            timeout=request.timeout  # 添加 timeout 参数
        )
    
    return {
        "task_id": task_id,
        "status": "submitted",
        "message": "截图任务已提交"
    }

@app.post("/screenshot/sync")
async def sync_screenshot(request: ScreenshotRequest):
    """
    同步获取截图（支持全页面或元素截图）
    
    - **url**: 必填，网页URL
    - **device**: 可选，设备类型 (pc/phone/tablet)，默认pc
    - **width**: 可选，自定义宽度
    - **height**: 可选，自定义高度
    - **ua**: 可选，自定义User-Agent
    - **element_type**: 可选，元素选择器类型(id/class/name/xpath/css/tag/data/attr/text等)
    - **element_name**: 可选，元素名称(用于data-*或attr属性，text类型时忽略)
    - **element_value**: 可选，元素值或要匹配的文本
    - **full_page**: 可选 (仅当不指定元素时)，是否截取完整页面高度，默认False (截取视口高度)
    - **wait_time**: 可选，页面加载后的等待时间（秒），默认1秒
    - **timeout**: 可选，整个截图任务的超时时间（秒），默认90秒
    
    返回：直接返回图片数据或错误信息
    """
    try:
        element_type, element_name, element_value = request.get_element_info()  # 修复：正确解构三个返回值

        if element_type and element_value:
            # 元素截图
            result = await asyncio.wait_for(
                browser_instance.prtScPath(
                    url=str(request.url),
                    elename=element_name,
                    eletype=element_type,
                    elevalue=element_value,
                    device=request.device,
                    width=request.width,
                    height=request.height,
                    ua=request.ua,
                    wait_time=request.wait_time
                ),
                timeout=request.timeout
            )
        else:
            # 全页面截图
            result = await asyncio.wait_for(
                browser_instance.prtSc(
                    url=str(request.url),
                    device=request.device,
                    width=request.width,
                    height=request.height,
                    ua=request.ua,
                    full_page=request.full_page, # 传递 full_page 参数
                    wait_time=request.wait_time
                ),
                timeout=request.timeout
            )

        # 增加超时处理
        if not result or result.get("code") != 200:
            return JSONResponse(
                status_code=500,
                content={"code": result.get("code", 500), "msg": result.get("msg", "截图失败")}
            )
        
        # 确保有数据返回
        if not result.get("data"):
            return JSONResponse(
                status_code=500,
                content={"code": 500, "msg": "截图成功但没有数据返回"}
            )
            
        return StreamingResponse(
            io.BytesIO(result["data"]),
            media_type="image/png",
            headers={"Content-Disposition": "attachment; filename=screenshot.png"}
        )
        
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"code": 504, "msg": f"截图超时，超过{request.timeout}秒"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "msg": f"截图过程出错: {str(e)}"}
        )

@app.get("/task/{task_id}/status")
async def get_task_status(task_id: str):
    """
    获取任务当前状态
    
    - **task_id**: 任务ID
    
    返回任务状态信息
    """
    status = await task_manager.get_task_status(task_id)
    
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="任务未找到")
    
    return status

@app.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    """
    获取任务结果（如果已完成）
    
    - **task_id**: 任务ID
    
    如果任务完成，返回截图结果
    """
    status_info = await task_manager.get_task_status(task_id) # 获取完整状态信息
    
    if status_info.get("status") == TaskStatus.NOT_FOUND:
        raise HTTPException(status_code=404, detail="任务未找到")
    
    if status_info["status"] == TaskStatus.FAILED:
        return JSONResponse(
            status_code=500, # 或者根据错误类型调整
            content={
                "task_id": task_id,
                "status": TaskStatus.FAILED,
                "message": "任务执行失败",
                "error_details": status_info.get("error_details", "未知错误")
            }
        )

    if status_info["status"] != TaskStatus.COMPLETED:
        return {
            "task_id": task_id,
            "status": status_info["status"],
            "progress": status_info["progress"],
            "message": "任务尚未完成"
        }
    
    result = await task_manager.get_task_result(task_id)
    
    if not result or result.get("code") != 200:
        return JSONResponse(content={
            "code": result.get("code", 500),
            "msg": result.get("msg", "任务执行失败")
        })
    
    # 返回图片文件
    return StreamingResponse(
        io.BytesIO(result["data"]), 
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=screenshot_{task_id}.png"}
    )

@app.delete("/task/{task_id}", response_model=Dict[str, Any])
async def delete_task_endpoint(task_id: str):
    """
    删除指定ID的任务。
    如果任务正在运行，会尝试取消它。
    """
    result = await task_manager.delete_task(task_id)
    
    if result["status"] == TaskStatus.NOT_FOUND:
        raise HTTPException(status_code=404, detail=result["message"])
    
    status_code = 200
    if result["status"] == TaskStatus.CANCELLED:
        # 任务被请求取消，可能仍在进行中，但最终会被标记为CANCELLED
        status_code = 202 # Accepted: 请求已被接受处理，但处理尚未完成
        
    return JSONResponse(status_code=status_code, content=result)

@app.get("/system/stats")
async def get_system_stats():
    """获取系统资源使用情况和任务统计"""
    pending_count = 0
    running_count = 0
    completed_count = 0
    failed_count = 0
    
    # 统计任务状态
    # 使用锁来安全地迭代 tasks 字典
    async with task_manager.lock:
        for task_id, task_data in task_manager.tasks.items():
            status = task_data["status"]
            if status == TaskStatus.PENDING:
                # PENDING 状态的任务可能在队列中，也可能还未被工作者拾取
                # task_manager.get_current_stats()["pending_in_queue"] 更准确反映队列中的
                pass # PENDING 状态由队列大小反映更佳
            elif status == TaskStatus.RUNNING:
                running_count += 1
            elif status == TaskStatus.COMPLETED:
                completed_count += 1
            elif status == TaskStatus.FAILED:
                failed_count += 1
    
    # 从 task_manager 获取更准确的队列和运行中任务计数
    current_tm_stats = task_manager.get_current_stats()
    pending_in_queue = current_tm_stats["pending_in_queue"]
    # running_count 应该与 current_tm_stats["running_tasks"] 一致
    # total_tasks_in_memory = len(task_manager.tasks) # 内存中所有任务（包括已完成等待清理的）

    return {
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
        },
        "task_manager": {
            "max_concurrent_tasks": task_manager.max_concurrent_tasks,
            "current_running_tasks": current_tm_stats["running_tasks"],
            "tasks_in_queue": pending_in_queue,
        },
        "tasks_overview": { # 内存中任务状态快照
            "pending_tracked": sum(1 for t in task_manager.tasks.values() if t['status'] == TaskStatus.PENDING), # 刚提交，可能还未入队或已被取出
            "running_tracked": running_count,
            "completed_tracked": completed_count,
            "failed_tracked": failed_count,
            "total_tracked_in_memory": len(task_manager.tasks)
        }
    }

if __name__ == "__main__":
    # 在主程序的最开始就设置正确的事件循环策略
    if sys.platform == 'win32':
        # Windows 平台使用 ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    uvicorn.run(
        "fastapi_webprtsc:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
