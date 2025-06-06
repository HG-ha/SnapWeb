import asyncio
import sys

# Set event loop policy for Windows at the very top
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import gc
import time
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Page, Error, TimeoutError
import logging
import uuid

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
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-blink-features=AutomationControlled" # Added for anti-detection
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
    
    def _construct_selector(self, eletype: str, elevalue: str, elename: str = "") -> str:
        """
        根据元素类型、名称和值构建选择器
        
        参数:
            eletype: 元素类型 (id, class, name, xpath, css, tag, data, attr, text, canvas, iframe)
            elevalue: 元素值
            elename: 元素名称 (对于data、attr类型使用)
        
        返回:
            构建的选择器字符串
        """
        eletype = eletype.lower().strip()
        
        # 处理空值情况
        if not elevalue:
            logger.warning(f"构建选择器时元素值为空: 类型={eletype}, 名称={elename}")
            return ""
        
        try:
            if eletype == "id":
                return f"#{elevalue}"
            elif eletype == "class":
                return f".{elevalue}"
            elif eletype == "name":
                return f"[name='{elevalue}']"
            elif eletype == "xpath":
                return elevalue  # xpath直接返回值
            elif eletype == "css":
                return elevalue  # css选择器直接返回值
            elif eletype == "tag":
                return elevalue  # 标签名直接返回
            elif eletype == "data":
                attr_name = elename or "data-id"  # 默认为data-id
                return f"[{attr_name}='{elevalue}']"
            elif eletype == "attr":
                if not elename:
                    logger.warning("使用attr类型选择器时未提供属性名")
                    return ""
                return f"[{elename}='{elevalue}']"
            elif eletype == "text":
                # 使用XPath定位包含特定文本的元素
                return f"//*[contains(text(), '{elevalue}')]"
            elif eletype == "canvas":
                # 处理canvas元素
                if elevalue.lower() == "first":
                    return "canvas"  # 页面中第一个canvas
                elif elevalue.isdigit():
                    # 第n个canvas
                    index = int(elevalue) - 1
                    return f"canvas:nth-of-type({index + 1})"
                else:
                    # 按ID或选择器查找
                    if elevalue.startswith("#") or elevalue.startswith("."):
                        return elevalue
                    return f"canvas#{elevalue}"
            elif eletype == "iframe":
                # 处理iframe元素
                if elevalue.lower() == "first":
                    return "iframe"  # 页面中第一个iframe
                elif elevalue.isdigit():
                    # 第n个iframe
                    index = int(elevalue) - 1
                    return f"iframe:nth-of-type({index + 1})"
                else:
                    # 按ID或选择器查找
                    if elevalue.startswith("#") or elevalue.startswith("."):
                        return elevalue
                    return f"iframe#{elevalue}"
            else:
                logger.warning(f"不支持的元素类型: {eletype}")
                return ""
        except Exception as e:
            logger.error(f"构建选择器时发生错误: {e}")
            return ""

            
    async def _create_page(self, device_config=None, custom_js: Optional[str] = None):
        if not self._browser:
            logger.error("浏览器未初始化。请先调用 initialize()。")
            raise RuntimeError("浏览器未初始化")

        context_options = DEFAULT_CONTEXT_OPTIONS.copy()
        if device_config:
            context_options.update({
                "user_agent": device_config.get("user_agent"),
                "viewport": device_config.get("viewport"),
                "device_scale_factor": device_config.get("device_scale_factor"),
                "is_mobile": device_config.get("is_mobile"),
                "has_touch": device_config.get("has_touch"),
            })
        
        # 为每个页面创建独立的浏览器上下文
        browser_context = await self._browser.new_context(**context_options)
        page = await browser_context.new_page()
        page_id = str(uuid.uuid4())
        self._pages[page_id] = {"page": page, "context": browser_context, "created_at": time.time()}

        try:
            # 注入通用的反检测脚本
            await page.add_init_script("""
                // --- WebDriver Flag ---
                try {
                    if (navigator.webdriver || Navigator.prototype.hasOwnProperty('webdriver')) {
                        delete Navigator.prototype.webdriver; // Try to delete it from prototype
                    }
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => false,
                        configurable: true
                    });
                } catch (e) {
                    console.warn('Failed to spoof navigator.webdriver: ' + e.toString());
                }

                // --- Spoof Navigator Properties ---
                try {
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-CN', 'zh', 'en-US', 'en'], // Default Accept-Language is zh-CN,zh;q=0.9,en;q=0.8
                        configurable: true
                    });
                } catch (e) {
                    console.warn('Failed to spoof navigator.languages: ' + e.toString());
                }

                try {
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'Win32', // Common platform, consider making dynamic based on UA
                        configurable: true
                    });
                } catch (e) {
                    console.warn('Failed to spoof navigator.platform: ' + e.toString());
                }

                // --- Plugins and MimeTypes ---
                try {
                    const MOCK_PLUGIN_ARRAY = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', mimeTypes: [] },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', mimeTypes: [] },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', mimeTypes: [] }
                    ];

                    const MOCK_MIME_TYPE_ARRAY = [
                        { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: MOCK_PLUGIN_ARRAY[0] },
                        { type: 'application/pdf', suffixes: 'pdf', description: '', enabledPlugin: MOCK_PLUGIN_ARRAY[1] },
                        { type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable', enabledPlugin: MOCK_PLUGIN_ARRAY[2] },
                        { type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable', enabledPlugin: MOCK_PLUGIN_ARRAY[2] }
                    ];


                    MOCK_PLUGIN_ARRAY[0].mimeTypes.push(MOCK_MIME_TYPE_ARRAY[0]);
                    MOCK_PLUGIN_ARRAY[1].mimeTypes.push(MOCK_MIME_TYPE_ARRAY[1]);
                    MOCK_PLUGIN_ARRAY[2].mimeTypes.push(MOCK_MIME_TYPE_ARRAY[2], MOCK_MIME_TYPE_ARRAY[3]);

                    MOCK_PLUGIN_ARRAY.forEach(p => { Object.freeze(p.mimeTypes); Object.freeze(p); });
                    Object.freeze(MOCK_MIME_TYPE_ARRAY);

                    Object.defineProperty(navigator, 'plugins', { get: () => MOCK_PLUGIN_ARRAY, configurable: true });
                    Object.defineProperty(navigator, 'mimeTypes', { get: () => MOCK_MIME_TYPE_ARRAY, configurable: true });
                } catch (e) {
                    console.warn('Failed to spoof plugins/mimeTypes: ' + e.toString());
                }

                // --- Spoof WebGL ---
                try {
                    const getParameterOld = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {
                        // UNMASKED_VENDOR_WEBGL (0x9245)
                        if (parameter === 37445) return 'Intel Open Source Technology Center';
                        // UNMASKED_RENDERER_WEBGL (0x9246)
                        if (parameter === 37446) return 'Mesa DRI Intel(R) Ivybridge Mobile ';
                        // VENDOR (0x1F00)
                        if (parameter === 7936) return 'Intel Open Source Technology Center';
                        // RENDERER (0x1F01)
                        if (parameter === 7937) return 'Mesa DRI Intel(R) Ivybridge Mobile ';
                        
                        if (getParameterOld.apply) {
                            return getParameterOld.apply(this, arguments);
                        }
                        return null; // Fallback
                    };
                    // Hide the override from toString
                    WebGLRenderingContext.prototype.getParameter.toString = getParameterOld.toString.bind(getParameterOld);
                } catch (e) {
                    console.warn('Failed to spoof WebGL: ' + e.toString());
                }

                // --- Permissions API ---
                try {
                    const originalPermissionsQuery = navigator.permissions.query;
                    navigator.permissions.query = (parameters) => {
                        try {
                            if (parameters.name === 'notifications') {
                                return Promise.resolve({ state: Notification.permission || 'default' });
                            }
                            if (originalPermissionsQuery.call) {
                                return originalPermissionsQuery.call(navigator.permissions, parameters);
                            }
                            return Promise.reject(new Error('Original permissions.query not callable.'));
                        } catch (e) {
                            console.warn('navigator.permissions.query inner failed: ' + e.toString());
                            return Promise.reject(e);
                        }
                    };
                    navigator.permissions.query.toString = originalPermissionsQuery.toString.bind(originalPermissionsQuery);
                } catch (e) {
                    console.warn('Failed to spoof navigator.permissions.query: ' + e.toString());
                }

                // --- Notification Permission ---
                try {
                    if (typeof Notification !== 'undefined' && Notification.permission) {
                        Object.defineProperty(Notification, 'permission', {
                            get: () => 'default', // 'denied' in headless often, 'default' is more neutral
                            configurable: true
                        });
                    }
                } catch (e) {
                    console.warn('Failed to spoof Notification.permission: ' + e.toString());
                }

                // --- Other Navigator Properties ---
                try {
                    if (navigator.deviceMemory === undefined || navigator.deviceMemory === 0) {
                        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8, configurable: true });
                    }
                    if (navigator.hardwareConcurrency === undefined || navigator.hardwareConcurrency === 0) {
                        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4, configurable: true });
                    }
                } catch (e) {
                    console.warn('Failed to spoof deviceMemory/hardwareConcurrency: ' + e.toString());
                }

                // --- User's existing event listeners and overrides (integrated) ---
                window.addEventListener('beforeunload', (event) => {
                    event.preventDefault();
                    event.returnValue = "Navigation blocked";
                });
                document.addEventListener('contextmenu', event => event.preventDefault());
                document.addEventListener('selectstart', event => event.preventDefault());
                window.open = function() { return null; };

            """)

            # 注意：custom_js 现在不在这里执行，而是在页面加载完成后执行
            
            return page_id, page
        except Exception as e:
            logger.error(f"创建页面 {page_id} 时出错: {e}")
            # 如果出错，确保关闭已创建的页面和上下文
            if page_id in self._pages:
                await self._close_page_internal(page_id) # 使用内部关闭方法避免锁问题
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
            
    async def _navigate_to_url(self, page: Page, url: str, wait_until: str = "domcontentloaded", max_retries: int = 3, wait_for_resources: bool = False) -> bool:
        """
        导航到URL，包含重试机制和改进的安全措施
        
        参数:
            page: Playwright页面对象
            url: 要导航到的URL
            wait_until: 导航完成判断标准，可以是 'domcontentloaded', 'load', 'networkidle'
            max_retries: 最大重试次数
            wait_for_resources: 是否等待页面所有资源加载完成
        """
        for attempt in range(max_retries):
            try:                # 设置请求拦截（允许所有常见资源类型）
                await page.route("**/*", lambda route: route.continue_() if route.request.resource_type in ["document", "script", "stylesheet", "image", "font", "xhr", "fetch", "media", "texttrack", "eventsource", "manifest", "other"] else route.abort())
                
                # 导航到页面，根据wait_for_resources参数决定等待策略
                actual_wait_until = "networkidle" if wait_for_resources else wait_until
                response = await page.goto(
                    url, 
                    wait_until=actual_wait_until, 
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
        
    async def prtSc(self, url, device="pc", width="", height="", ua="", full_page: bool = True, wait_time: float = 1.0, wait_for_resources: bool = False, custom_js: Optional[str] = None) -> Dict[str, Any]:
        """
        获取网页截图
        
        参数:
            url: 网页URL
            device: 设备类型 ('pc', 'phone', 'tablet')
            width: 自定义宽度
            height: 自定义高度
            ua: 自定义User-Agent
            full_page: 是否截取完整页面高度
            wait_time: 页面加载后额外等待时间（秒）
            wait_for_resources: 是否等待所有资源（图片、视频等）加载完成
            custom_js: 在页面加载完成后执行的自定义JavaScript代码
        """
        page_id = None
        start_time = time.time()
        try:
            device_config = self._get_device_config(device, width, height)
            if ua:  # 如果提供了ua，则覆盖设备配置中的ua
                device_config["user_agent"] = ua
            
            page_id, page = await self._create_page(device_config=device_config)

            navigate_success = await self._navigate_to_url(page, url, wait_until="load", wait_for_resources=wait_for_resources) # 更改为 "load"
            if not navigate_success:
                raise Exception(f"导航到 {url} 失败")

            # 在页面加载完成后执行自定义JS脚本
            if custom_js:
                try:
                    await page.evaluate(custom_js)
                    logger.info("自定义JS脚本执行成功")
                except Exception as e:
                    logger.warning(f"执行自定义JS脚本时出错: {e}")
            
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            # 截图前执行滚动以确保动态内容加载
            if full_page:
                await self._scroll_page_for_full_screenshot(page)


            screenshot_bytes = await page.screenshot(full_page=full_page, type="png") # Playwright 的 full_page 选项
            
            end_time = time.time()
            logger.info(f"截图成功: {url}, 设备: {device}, 耗时: {end_time - start_time:.2f}s")
            return {"status": "success", "image_bytes": screenshot_bytes, "message": "截图成功"}

        except TimeoutError as e:
            logger.error(f"截图超时: {url}, 错误: {e}")
            return {"status": "error", "message": f"页面加载或截图超时: {e}"}
        except Error as e:  # Playwright特定错误
            logger.error(f"Playwright 截图错误: {url}, 错误: {e}")
            return {"status": "error", "message": f"Playwright操作失败: {e}"}
        except Exception as e:
            logger.error(f"截图失败: {url}, 错误: {e}")
            return {"status": "error", "message": f"截图过程中发生错误: {e}"}
        finally:
            if page_id:
                await self._close_page(page_id)
    
    async def prtScPath(self, url, elename, eletype, elevalue, device="pc", width="", height="", ua="", wait_time: float = 1.0, wait_for_resources: bool = False, custom_js: Optional[str] = None) -> Dict[str, Any]:
        """
        获取页面元素截图
        
        参数:
            url: 网页URL
            elename: 元素名称
            eletype: 元素类型 (包括 id, class, name, xpath, css, tag, data, attr, text, canvas, iframe)
            elevalue: 元素值
            device: 设备类型
            width: 自定义宽度
            height: 自定义高度
            ua: 自定义User-Agent
            wait_time: 页面加载后额外等待时间（秒）
            wait_for_resources: 是否等待所有资源（图片、视频等）加载完成
            custom_js: 在页面加载完成后执行的自定义JavaScript代码
        """
        page_id = None
        start_time = time.time()
        try:
            device_config = self._get_device_config(device, width, height)
            if ua:
                device_config["user_agent"] = ua

            page_id, page = await self._create_page(device_config=device_config)

            navigate_success = await self._navigate_to_url(page, url, wait_until="load", wait_for_resources=wait_for_resources)
            if not navigate_success:
                raise Exception(f"导航到 {url} 失败")


            # 在页面加载完成后执行自定义JS脚本
            if custom_js:
                try:
                    await page.evaluate(custom_js)
                    logger.info("自定义JS脚本执行成功")
                except Exception as e:
                    logger.warning(f"执行自定义JS脚本时出错: {e}")
            
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            element_selector = self._construct_selector(eletype, elevalue, elename)
            if not element_selector:
                return {"status": "error", "message": "无效的元素选择器类型"}

            # 特殊处理 canvas 和 iframe
            if eletype.lower() == "canvas":
                screenshot_bytes = await self._screenshot_canvas(page, element_selector)
            elif eletype.lower() == "iframe":
                screenshot_bytes = await self._screenshot_iframe(page, element_selector)
            else:
                element = await page.query_selector(element_selector)
                if not element:
                    return {"status": "error", "message": f"元素未找到: {element_selector}"}
                await element.scroll_into_view_if_needed() # 确保元素可见
                await asyncio.sleep(0.5) # 等待滚动完成和可能的懒加载
                screenshot_bytes = await element.screenshot(type="png")

            end_time = time.time()
            logger.info(f"元素截图成功: {url}, 元素: {element_selector}, 耗时: {end_time - start_time:.2f}s")
            return {"status": "success", "image_bytes": screenshot_bytes, "message": "元素截图成功"}
        
        except TimeoutError as e:
            logger.error(f"元素截图超时: {url}, 元素: {eletype}={elevalue}, 错误: {e}")
            return {"status": "error", "message": f"页面加载或元素截图超时: {e}"}
        except Error as e:
            logger.error(f"Playwright 元素截图错误: {url}, 元素: {eletype}={elevalue}, 错误: {e}")
            return {"status": "error", "message": f"Playwright操作失败: {e}"}
        except Exception as e:
            logger.error(f"元素截图失败: {url}, 元素: {eletype}={elevalue}, 错误: {e}")
            return {"status": "error", "message": f"元素截图过程中发生错误: {e}"}
        finally:
            if page_id:
                await self._close_page(page_id)
                
    async def autoPrtsc(self, url, device="pc", width="", height="", ua="", element_selector="", custom_js: Optional[str] = None) -> Dict[str, Any]:
        """
        自动截图，如果提供了element_selector则截取元素，否则截取全屏。
        """
        if element_selector:
            # 解析 element_selector, 假设格式为 "type=value" 或 "type=name:value"
            # 为了简单起见，这里我们假设 element_selector 直接是 Playwright 支持的 selector 字符串
            # 或者是一个更复杂的结构，需要解析
            # 此处简化：假设 element_selector 是 "eletype=elevalue" 或 "eletype=elename:elevalue"
            parts = element_selector.split('=', 1)
            eletype = parts[0]
            remaining_value = parts[1] if len(parts) > 1 else ""
            
            elename = ""
            elevalue = remaining_value
            if ':' in remaining_value and eletype.lower() in ['data', 'attr']: # 假设 data 和 attr 类型可能包含 name
                name_parts = remaining_value.split(':', 1)
                elename = name_parts[0]
                elevalue = name_parts[1] if len(name_parts) > 1 else ""

            return await self.prtScPath(url, elename, eletype, elevalue, device, width, height, ua, custom_js=custom_js)
        else:
            return await self.prtSc(url, device, width, height, ua, full_page=True, custom_js=custom_js)
    
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

    async def _screenshot_canvas(self, page: Page, selector: str) -> bytes:
        """
        截取canvas元素的内容
        
        参数:
            page: Playwright页面对象
            selector: 指向canvas元素的选择器
            
        返回:
            canvas元素的截图数据(bytes)或None
        """
        try:
            # 等待并获取canvas元素
            canvas = await page.wait_for_selector(selector, state="visible", timeout=30000)
            
            if not canvas:
                logger.error(f"未找到canvas元素: {selector}")
                return None
                
            # 先确保元素在视口中
            await canvas.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)  # 滚动后短暂等待
            
            # 尝试使用JavaScript获取canvas的内容为base64编码的数据URL
            data_url = await page.evaluate("""(selector) => {
                const canvas = document.querySelector(selector);
                if (!canvas || !(canvas instanceof HTMLCanvasElement)) {
                    return null;
                }
                // 尝试获取canvas内容为PNG格式的dataURL
                try {
                    return canvas.toDataURL('image/png');
                } catch (e) {
                    // 如果canvas是跨域的，toDataURL可能会失败
                    console.error('无法获取canvas内容:', e);
                    return null;
                }
            }""", selector)
            
            if data_url:
                # 从data URL提取base64编码的图像数据
                # 格式为: "data:image/png;base64,..."
                base64_data = data_url.split(',')[1]
                import base64
                image_bytes = base64.b64decode(base64_data)
                return image_bytes
            else:
                # 如果无法通过JavaScript获取，退回到对元素的常规截图
                logger.warning(f"无法通过JavaScript获取canvas内容，使用元素截图代替: {selector}")
                return await canvas.screenshot(type="png")
                
        except Exception as e:
            logger.error(f"截取canvas内容时出错: {str(e)}")
            return None
            
    async def _screenshot_iframe(self, page: Page, selector: str) -> bytes:
        """
        截取iframe元素内的内容
        
        参数:
            page: Playwright页面对象
            selector: 指向iframe元素的选择器
            
        返回:
            iframe内容的截图数据(bytes)或None
        """
        try:
            # 等待iframe元素可见
            iframe_element = await page.wait_for_selector(selector, state="visible", timeout=30000)
            
            if not iframe_element:
                logger.error(f"未找到iframe元素: {selector}")
                return None
                
            # 先确保iframe元素在视口中
            await iframe_element.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)  # 滚动后短暂等待
            
            # 获取iframe的内容框架
            frame = None
            
            # 尝试通过name或id属性定位框架
            frame_props = await page.evaluate("""(selector) => {
                const iframe = document.querySelector(selector);
                if (!iframe) return null;
                return {
                    name: iframe.name || '',
                    id: iframe.id || '',
                    src: iframe.src || ''
                };
            }""", selector)
            
            if frame_props:
                # 尝试通过name定位框架
                if frame_props['name']:
                    try:
                        frame = page.frame(name=frame_props['name'])
                    except:
                        pass
                        
                # 尝试通过URL定位框架
                if not frame and frame_props['src']:
                    try:
                        frames = page.frames
                        for f in frames:
                            if f.url and frame_props['src'] in f.url:
                                frame = f
                                break
                    except:
                        pass
                        
            # 如果上面的方法都失败了，尝试通过选择器直接获取框架
            if not frame:
                try:
                    # 通过选择器获取框架
                    frame = await page.frame_locator(selector).first
                except Exception as e:
                    logger.error(f"通过选择器获取iframe框架失败: {str(e)}")
            
            # 如果成功获取到框架，截取整个框架内容
            if frame:
                # 获取iframe内容区域的尺寸
                size = await iframe_element.bounding_box()
                if size:
                    # 截取整个框架内容
                    return await frame.screenshot(type="png")
            
            # 如果无法获取框架内容，退回到直接截取iframe元素
            logger.warning(f"无法获取iframe内容，使用元素截图代替: {selector}")
            return await iframe_element.screenshot(type="png")
                
        except Exception as e:
            logger.error(f"截取iframe内容时出错: {str(e)}")
            return None
        


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
