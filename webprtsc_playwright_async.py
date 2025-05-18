import asyncio
import gc
import time
from typing import Dict, Any
from playwright.async_api import async_playwright, Page, Error, TimeoutError
import logging
import sys

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("webprtsc")

DEFAULT_CONTEXT_OPTIONS = {
    "accept_downloads": False,
    "java_script_enabled": True,
    "bypass_csp": True,  # 绕过内容安全策略以确保截图功能正常
    "permissions": [],  # 清空所有权限
    "proxy": None,  # 禁用代理
    "extra_http_headers": { # 默认的额外HTTP头
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8", # 修改为中文优先
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Dest": "document"
    }
    # user_agent, viewport, device_scale_factor, is_mobile, has_touch 将从设备配置中获取或覆盖
}

class AsyncPrtScPlaywright:
    def __init__(self):
        self._playwright = None
        self._browser = None
        # self._browser_context = None # 不再需要全局浏览器上下文
        self._pages = {}  # 存储创建的页面
        self._last_cleanup = time.time()
        self._initialized = False
        
        self.device_presets = {
            "pc": {
                "width": 1920,
                "height": 1080,
                "device_scale_factor": 1,
                "is_mobile": False,
                "has_touch": False,
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
            },
            "phone": {
                "width": 390,
                "height": 844, # iPhone 12/13 Pro viewport
                "device_scale_factor": 3, # iPhone 12/13 Pro dsf
                "is_mobile": True,
                "has_touch": True,
                "viewport": {"width": 390, "height": 844},
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
            },
            "tablet": {
                "width": 1024,
                "height": 1366, # iPad Pro 12.9" portrait
                "device_scale_factor": 2,
                "is_mobile": True, # Playwright considers tablets mobile for emulation purposes
                "has_touch": True,
                "viewport": {"width": 1024, "height": 1366},
                "user_agent": "Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
            }
        }
        
    async def initialize(self):
        """初始化Playwright和浏览器"""
        if self._initialized:
            return
            
        try:
            self._playwright = await async_playwright().start()
            # 增加更多安全相关的浏览器参数
            browser_args = [
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--no-sandbox",
                "--no-zygote",
                "--disable-notifications",
                "--disable-popup-blocking",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--disable-translate",
                "--hide-scrollbars",
                "--metrics-recording-only",
                "--mute-audio",
                "--no-first-run",
                "--disable-features=IsolateOrigins,site-per-process"
            ]
            
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=browser_args
            )
            # 全局的 _browser_context 不再创建或配置于此
            self._initialized = True
            logger.info("Playwright 和浏览器已初始化")
        except Exception as e:
            logger.error(f"初始化浏览器时出错: {e}")
            raise
    
    async def close(self):
        """关闭浏览器和Playwright"""
        try:
            if self._browser:
                # 首先关闭所有页面
                for page_id in list(self._pages.keys()):
                    await self._close_page(page_id)
                    
                # 然后关闭浏览器和上下文
                if self._browser_context:
                    await self._browser_context.close()
                await self._browser.close()
                self._browser = None
                self._browser_context = None
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                
            self._initialized = False
            logger.info("浏览器和Playwright已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器时出错: {e}")
            
    async def schedule_cleanup(self):
        """定期清理资源"""
        while True:
            await asyncio.sleep(300)  # 5分钟检查一次
            try:
                await self._cleanup_resources()
            except Exception as e:
                logger.error(f"资源清理时出错: {e}")
    
    async def _cleanup_resources(self):
        """清理未使用的资源"""
        current_time = time.time()
        if current_time - self._last_cleanup < 300:  # 至少间隔5分钟
            return
            
        logger.info("开始清理浏览器资源...")
        
        # 关闭闲置的页面
        for page_id in list(self._pages.keys()):
            page_info = self._pages[page_id]
            if current_time - page_info["last_used"] > 300:  # 5分钟未使用
                await self._close_page(page_id)
        
        # 手动触发垃圾回收
        gc.collect()
        
        self._last_cleanup = current_time
        logger.info(f"资源清理完成，当前页面数量: {len(self._pages)}")
            
    async def _create_page(self, device_config=None):
        """创建新的页面对象"""
        try:
            if not self._initialized:
                await self.initialize()
            
            if not self._browser:
                raise Exception("浏览器未初始化")

            # 确保有默认配置（如果未提供）
            effective_device_config = device_config or self.device_presets["pc"]

            # 准备上下文选项
            context_options = DEFAULT_CONTEXT_OPTIONS.copy() # 从全局默认开始
            context_options["extra_http_headers"] = (DEFAULT_CONTEXT_OPTIONS.get("extra_http_headers") or {}).copy() # 深拷贝

            # 应用设备特定配置
            context_options.update({
                "viewport": effective_device_config["viewport"],
                "device_scale_factor": effective_device_config["device_scale_factor"],
                "is_mobile": effective_device_config["is_mobile"],
                "has_touch": effective_device_config["has_touch"],
            })
            
            # 如果设备配置提供了User-Agent，则使用它，否则使用默认UA（如果DEFAULT_CONTEXT_OPTIONS中定义了）
            # 或者Playwright的默认UA（如果两者都未定义）
            if effective_device_config.get("user_agent"):
                context_options["user_agent"] = effective_device_config["user_agent"]
            elif not context_options.get("user_agent"): # 如果默认选项里也没有UA
                 # 使用Playwright的默认UA，或者根据is_mobile选择一个通用UA
                if effective_device_config["is_mobile"]:
                    # 可以设置一个通用的移动UA作为后备
                    context_options["user_agent"] = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.0.0 Mobile Safari/537.36"
                else:
                    context_options["user_agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"


            # 如果设备配置有额外的HTTP头，合并它们
            if "extra_http_headers" in effective_device_config:
                context_options["extra_http_headers"].update(effective_device_config["extra_http_headers"])

            context = await self._browser.new_context(**context_options)
            page = await context.new_page()
            
            page.set_default_timeout(90000)
            page.set_default_navigation_timeout(90000)
            
            # 路由拦截和初始化脚本保持不变
            await page.route("**/*", lambda route: route.continue_() if route.request.resource_type in ["document", "script", "stylesheet", "image", "font"] else route.abort())

            await page.add_init_script("""
                window.addEventListener('beforeunload', (event) => {
                    event.preventDefault();
                    return event.returnValue = "Navigation blocked";
                });
                document.addEventListener('contextmenu', event => event.preventDefault());
                document.addEventListener('selectstart', event => event.preventDefault());
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); // 尝试隐藏webdriver标志
                window.open = function() { return null; };
            """)
            
            page_id = f"page_{id(page)}"
            self._pages[page_id] = {
                "page": page,
                "context": context, # 保存上下文，以便关闭
                "created_at": time.time(),
                "last_used": time.time()
            }
            
            return page_id
            
        except Exception as e:
            logger.error(f"创建页面时出错: {e}")
            raise
    
    async def _get_page(self, page_id):
        """获取现有页面"""
        page_info = self._pages.get(page_id)
        if page_info:
            # 更新最后使用时间
            page_info["last_used"] = time.time()
            return page_info["page"]
        return None
    
    async def _close_page(self, page_id):
        """关闭页面及其上下文"""
        page_info = self._pages.pop(page_id, None) # 使用pop确保移除
        if page_info:
            try:
                await page_info["page"].close()
                if page_info.get("context"): # 关闭与页面关联的上下文
                    await page_info["context"].close()
                logger.info(f"页面 {page_id} 及其上下文已关闭")
            except Exception as e:
                logger.error(f"关闭页面 {page_id} 或其上下文时出错: {e}")
            # finally: # pop已经移除了元素
            #     pass 
    
    async def _navigate_to_url(self, page: Page, url: str, wait_until: str = "domcontentloaded", max_retries: int = 3) -> bool:
        """导航到URL，包含重试机制和改进的安全措施"""
        for attempt in range(max_retries):
            try:
                # 设置请求拦截
                await page.route("**/*", lambda route: route.continue_() if route.request.resource_type in ["document", "script", "stylesheet", "image"] else route.abort())
                
                # 导航到页面
                response = await page.goto(
                    url, 
                    wait_until=wait_until, 
                    timeout=90000
                )
                
                if not response:
                    logger.warning(f"导航到 {url} 没有响应对象 (尝试 {attempt+1}/{max_retries})")
                    if attempt == max_retries - 1:
                        return False
                    continue
                
                # 检查响应状态
                if response.ok:
                    # 等待页面稳定
                    await asyncio.sleep(1)
                    
                    # 注入额外的安全措施
                    await page.evaluate("""
                        // 禁用alert等对话框
                        window.alert = window.confirm = window.prompt = function() {};
                        
                        // 禁用一些可能导致问题的API
                        window.print = function() {};
                        window.find = function() {};
                        window.requestFileSystem = function() {};
                    """)
                    
                    return True
                else:
                    logger.warning(f"导航到 {url} 响应状态: {response.status} (尝试 {attempt+1}/{max_retries})")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"导航到 {url} 时出错: {e}")
                if attempt == max_retries - 1:
                    return False
                
        return False
        
    async def prtSc(self, url, device="pc", width="", height="", ua="", full_page: bool = True) -> Dict[str, Any]:
        """获取网页截图"""
        page_id = None
        try:
            device_config = self._get_device_config(device, width, height)
            logger.info(f"使用设备配置: {device_config}")
            
            page_id = await self._create_page(device_config)
            page = await self._get_page(page_id)
            
            if ua:
                await page.set_extra_http_headers({"User-Agent": ua})
            
            navigation_success = await self._navigate_to_url(page, url)
            if not navigation_success:
                return {"code": 404, "msg": "导航到页面失败"}
            
            await asyncio.sleep(1)
            
            # 根据 full_page 参数决定截图方式
            screenshot_bytes = await page.screenshot(
                full_page=full_page, # 使用传入的 full_page 参数
                type="png",
                scale="css"
            )
            
            return {"code": 200, "msg": "成功", "data": screenshot_bytes}
            
        except Exception as e:
            logger.error(f"截图错误: {str(e)}")
            return {"code": 500, "msg": f"截图失败: {str(e)}"}
        finally:
            if page_id:
                await self._close_page(page_id)
    
    async def prtScPath(self, url, elename, eletype, elevalue, device="pc", width="", height="", ua="") -> Dict[str, Any]:
        """获取页面元素截图"""
        page_id = None
        try:
            # 配置设备参数
            device_config = self._get_device_config(device, width, height)
            logger.info(f"使用元素截图的设备配置: {device_config}") # 修改了日志信息，移除了 print
            # 创建新页面
            page_id = await self._create_page(device_config)
            page = await self._get_page(page_id)
            
            # 设置自定义UA（如果提供）
            if ua:
                await page.set_extra_http_headers({"User-Agent": ua})
            
            # 导航到URL，优先使用domcontentloaded
            navigation_success = await self._navigate_to_url(page, url)
            
            if not navigation_success:
                return {"code": 404, "msg": "导航到页面失败"}
            
            await asyncio.sleep(0.5) # 导航后短暂等待，确保页面初步渲染

            try:
                screenshot_bytes = None
                if eletype == "text":
                    try:
                        # 使用 get_by_text 定位元素，默认精确匹配
                        locator = page.get_by_text(elevalue, exact=True)
                        
                        # 等待第一个匹配的元素可见
                        await locator.first.wait_for(state="visible", timeout=30000)
                        await locator.first.scroll_into_view_if_needed() # 确保元素在视口内
                        await asyncio.sleep(0.5) # 滚动后短暂等待
                        
                        # 对第一个匹配的元素截图
                        screenshot_bytes = await locator.first.screenshot(type="png")
                    except TimeoutError:
                        return {"code": 404, "msg": f"等待文本元素 '{elevalue}' 超时或不可见"}
                    except Error as e: # Playwright特定错误
                        logger.error(f"文本元素 '{elevalue}' 定位或截图错误: {str(e)}")
                        if "strict mode violation" in str(e).lower() or "matches multiple elements" in str(e).lower():
                             return {"code": 400, "msg": f"找到多个匹配文本 '{elevalue}' 的元素。请使用更精确的文本或不同的选择策略。"}
                        return {"code": 500, "msg": f"文本元素截图时发生Playwright错误: {str(e)}"}
                else:
                    # 根据元素类型构建选择器
                    selector = None
                    if eletype == "xpath":
                        selector = f"xpath={elevalue}"
                    elif eletype == "data": # data-* 属性
                        selector = f"[data-{elename}='{elevalue}']"
                    elif eletype == "attr": # 其他属性
                        selector = f"[{elename}='{elevalue}']"
                    elif eletype in ["id", "class", "name"]: # id, class, name 作为属性选择器
                        selector = f"[{eletype}='{elevalue}']"
                    elif eletype == "tag": # HTML 标签名
                        selector = elevalue
                    elif eletype == "css": # 用户提供的完整CSS选择器
                        selector = elevalue
                    else:
                        # 未知类型，默认作为属性处理，并记录警告
                        logger.warning(f"未知的 eletype '{eletype}'，尝试作为属性选择器 [{eletype}='{elevalue}'] 处理。")
                        selector = f"[{eletype}='{elevalue}']"

                    try:
                        # 等待并获取元素
                        element = await page.wait_for_selector(selector, state="visible", timeout=30000)
                        # wait_for_selector 成功则 element 不会是 None
                        # if not element: 
                        #     return {"code": 404, "msg": f"未找到元素: {selector}"}

                        # 截图前确保元素可见
                        await element.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5) # 滚动后短暂等待
                        
                        # 截图
                        screenshot_bytes = await element.screenshot(type="png")
                        
                    except TimeoutError:
                        return {"code": 404, "msg": f"等待元素 '{selector}' 超时或不可见"}
                
                if screenshot_bytes:
                    return {"code": 200, "msg": "成功", "data": screenshot_bytes}
                else:
                    # 此处理论上不应到达，因为前面分支要么成功截图，要么返回错误
                    return {"code": 500, "msg": "未能获取元素截图，原因未知。"}
                    
            except Error as e: # Playwright 的其他 Error
                logger.error(f"元素截图时发生Playwright错误 (eletype: {eletype}, elevalue: '{elevalue}'): {str(e)}")
                return {"code": 500, "msg": f"元素截图错误: {str(e)}"}
                
        except Exception as e:
            logger.error(f"元素截图流程中发生一般错误: {str(e)}")
            return {"code": 500, "msg": f"元素截图失败: {str(e)}"}
        finally:
            # 关闭页面释放资源
            if page_id:
                await self._close_page(page_id)
                
    async def autoPrtsc(self, url, device="pc", width="", height="", ua="", element_selector="") -> Dict[str, Any]:
        """
        自动选择整页面或元素进行截图
        """
        if element_selector:
            # 如果提供了选择器，进行元素截图
            return await self.prtScPath(
                url=url,
                elename="auto",
                eletype="css",
                elevalue=element_selector,
                device=device,
                width=width,
                height=height,
                ua=ua
            )
        else:
            # 否则进行整页面截图
            return await self.prtSc(
                url=url,
                device=device,
                width=width,
                height=height,
                ua=ua
                # 注意：如果 autoPrtsc 也需要控制 full_page，这里也需要传递
                # full_page=full_page # 假设 autoPrtsc 也获得了一个 full_page 参数
            )
    
    def _get_device_config(self, device, width="", height=""):
        """获取设备配置"""
        # 首先获取基础配置
        if device in self.device_presets:
            config = self.device_presets[device].copy()
        else:
            # 如果设备类型不存在，使用PC配置作为基础
            config = self.device_presets["pc"].copy()
        
        # 应用自定义宽高（如果提供）
        try:
            if width and height:
                width_int = int(width)
                height_int = int(height)
                if width_int > 0 and height_int > 0:
                    config.update({
                        "width": width_int,
                        "height": height_int,
                        "viewport": {
                            "width": width_int,
                            "height": height_int
                        },
                        "device_scale_factor": 1  # 自定义尺寸时使用1:1的缩放比
                    })
        except (ValueError, TypeError):
            pass
            
        return config


# 如果直接运行此文件，执行测试
if __name__ == "__main__":
    async def test():
        prtsc = AsyncPrtScPlaywright()
        try:
            await prtsc.initialize()
            result = await prtsc.prtSc("https://www.baidu.com")
            print(f"截图结果: {result['code']} - {result['msg']}")
            if result["code"] == 200:
                with open("test.png", "wb") as f:
                    f.write(result["data"])
                print("截图已保存为 test.png")
        finally:
            await prtsc.close()
    
    # 运行测试
    asyncio.run(test())
