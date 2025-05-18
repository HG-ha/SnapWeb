import uuid
import asyncio
import time
from typing import Dict, Any, Optional, Callable

class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled" # 新增状态
    NOT_FOUND = "not_found"

class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 2):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: Dict[str, Dict[str, Any]] = {}  # 存储所有任务信息
        self.task_queue = asyncio.Queue()  # 任务队列
        self.running_tasks = set()  # 正在运行的任务ID集合
        self.lock = asyncio.Lock()  # 用于同步访问共享资源
        self.is_running = False  # 监控器运行状态
        self.workers = []  # 存储工作者协程

    async def create_task(self, func: Callable, **kwargs) -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        async with self.lock:
            self.tasks[task_id] = {
                "id": task_id,
                "func": func,
                "kwargs": kwargs,
                "status": TaskStatus.PENDING,
                "result": None,
                "error_details": None,
                "created_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "progress": 0,
                "task_obj": None # 用于存储 asyncio.Task 对象
            }
            # 将任务放入队列
            await self.task_queue.put(task_id)
        return task_id

    async def start_monitoring(self):
        """启动任务监控"""
        self.is_running = True
        # 创建工作者
        self.workers = [
            asyncio.create_task(self._worker(f"worker-{i}")) 
            for i in range(self.max_concurrent_tasks)
        ]

    async def stop_monitoring(self):
        """停止任务监控"""
        self.is_running = False
        # 等待所有工作者完成
        for worker in self.workers:
            try:
                worker.cancel()
                await worker
            except asyncio.CancelledError:
                pass
        self.workers.clear()

    async def _worker(self, worker_id: str):
        """工作者协程"""
        while self.is_running:
            try:
                # 从队列获取任务
                task_id = await self.task_queue.get()
                if task_id is None:
                    continue

                async with self.lock:
                    if task_id not in self.tasks:
                        self.task_queue.task_done()
                        continue
                    
                    task_info = self.tasks[task_id]
                    if task_info["status"] != TaskStatus.PENDING:
                        self.task_queue.task_done()
                        continue
                        
                    # 更新任务状态为运行中
                    self.tasks[task_id]["status"] = TaskStatus.RUNNING
                    self.tasks[task_id]["started_at"] = time.time()
                    self.running_tasks.add(task_id)

                try:
                    # 执行任务
                    func = task_info["func"]
                    kwargs = task_info["kwargs"]
                    result = await func(**kwargs)

                    async with self.lock:
                        self.tasks[task_id].update({
                            "status": TaskStatus.COMPLETED,
                            "result": result,
                            "completed_at": time.time(),
                            "progress": 100
                        })

                except Exception as e:
                    async with self.lock:
                        self.tasks[task_id].update({
                            "status": TaskStatus.FAILED,
                            "error_details": str(e),
                            "completed_at": time.time()
                        })

                finally:
                    async with self.lock:
                        if task_id in self.running_tasks:
                            self.running_tasks.remove(task_id)
                    self.task_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return {"status": TaskStatus.NOT_FOUND}
            
            return {
                "status": task["status"],
                "progress": task["progress"],
                "created_at": task["created_at"],
                "started_at": task["started_at"],
                "completed_at": task["completed_at"],
                "error_details": task["error_details"]
            }

    async def get_task_result(self, task_id: str) -> Optional[Any]:
        """获取任务结果"""
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            return task.get("result")

    async def clean_old_tasks(self, max_age: float = 600):
        """清理旧任务"""
        current_time = time.time()
        async with self.lock:
            task_ids = list(self.tasks.keys())
            for task_id in task_ids:
                task = self.tasks[task_id]
                if task["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    if current_time - task["created_at"] > max_age:
                        print(f"Clear the cache task: {task_id}")
                        del self.tasks[task_id]

    async def delete_task(self, task_id: str) -> Dict[str, Any]:
        """删除一个任务。如果任务正在运行，则尝试取消它。"""
        async with self.lock:
            task_data = self.tasks.get(task_id)

            if not task_data:
                return {"status": TaskStatus.NOT_FOUND, "message": "任务未找到"}

            current_status = task_data["status"]
            task_obj_to_cancel = task_data.get("task_obj")

            if task_obj_to_cancel and not task_obj_to_cancel.done():
                try:
                    task_obj_to_cancel.cancel()
                    await asyncio.wait_for(task_obj_to_cancel, timeout=1.0) 
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    pass
                
                task_data["status"] = TaskStatus.CANCELLED
                task_data["error_details"] = "任务被用户删除并尝试取消"
                task_data["completed_at"] = time.time()
                task_data["progress"] = 0
                return {"status": TaskStatus.CANCELLED, "message": "任务已被请求删除并尝试取消"}
            else:
                del self.tasks[task_id]
                return {"status": "deleted", "message": f"任务 (状态: {current_status}) 已删除"}

    def get_current_stats(self) -> Dict[str, int]:
        """获取当前任务统计信息"""
        return {
            "pending_in_queue": self.task_queue.qsize(),
            "running_tasks": len(self.running_tasks)
        }