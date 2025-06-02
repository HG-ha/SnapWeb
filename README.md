# SnapWeb

这是一个基于 FastAPI 和 Playwright 构建的异步网页截图服务。它允许用户通过 API 请求对指定 URL 进行截图，支持全页面截图、视口截图以及特定 HTML 元素的截图。服务还提供了任务管理功能，支持异步提交截图任务并在稍后获取结果。

## 主要功能

*   **多种截图模式**：
    *   **全页面截图**：捕获整个可滚动页面的内容。
    *   **视口截图**：根据用户指定的宽度和高度截取浏览器视口区域。
    *   **元素截图**：根据提供的选择器（CSS、XPath、ID、类名、标签名、属性、文本内容、Canvas、iframe）截取特定 HTML 元素。
*   **设备模拟**：
    *   内置多种设备预设（如 "pc", "phone", "tablet"）。
    *   支持自定义视口宽度、高度和 User-Agent。
*   **异步任务处理**：
    *   通过 `/screenshot/submit` 接口提交截图任务，立即返回任务 ID。
    *   通过 `/task/{task_id}/status` 查询任务状态。
    *   通过 `/task/{task_id}/result` 获取已完成任务的截图结果。
    *   通过  **DELETE** `/task/{task_id}` 手动删除任务。
*   **同步截图**：
    *   通过 `/screenshot/sync` 接口直接获取截图结果，适用于需要即时响应的场景。
*   **资源管理**：
    *   内置任务管理器，控制并发任务数量。
    *   定期清理旧的已完成任务和闲置的浏览器页面资源。
    *   默认禁用浏览器下载行为。
*   **系统监控**：
    *   通过 `/system/stats` 接口获取系统资源使用情况和任务统计。
*   **增强的反爬虫机制**：
    *   通过修改浏览器启动参数和注入JavaScript脚本，努力伪装浏览器指纹，减少被网站识别为自动化工具的风险。
    *   支持用户自定义JavaScript代码注入
*   **Docker 支持**：提供 Dockerfile，方便容器化部署。

## 技术栈

*   Python 3.10+
*   FastAPI: 用于构建 API 服务。
*   Playwright: 用于浏览器自动化和截图。
*   Uvicorn: ASGI 服务器。
*   Pydantic: 用于数据校验和模型定义。
*   Psutil: 用于获取系统资源信息。

## 运行
### 1. Docker 运行
    ```bash
    docker run -p 8000:8000 yiminger/snapweb:latest
    ```

### 2. 源代码运行

**先决条件**:
*   Python 3.10 或更高版本。
*   pip 包管理器。

**步骤**:

1.  **克隆或下载项目代码**
    ```bash
    git clone https://github.com/HG-ha/SnapWeb.git
    ```

3.  **安装 Python 依赖**:
    进入项目根目录，运行：
    ```bash
    pip install -r requirements.txt
    ```

4.  **安装 Playwright 浏览器驱动**:
    ```bash
    playwright install chromium --with-deps
    ```
    `--with-deps` 会尝试安装 Chromium 运行所需的操作系统依赖。如果遇到问题，您可能需要根据 Playwright 的官方文档手动安装这些依赖。

5.  **运行 FastAPI 应用**:
    项目根目录下有一个 `run.py` 文件，它使用 uvicorn 启动应用。
    ```bash
    python run.py
    ```
    或者直接使用 uvicorn (如果 `run.py` 不存在或您想自定义启动参数):
    ```bash
    uvicorn fastapi_webprtsc:app --host 0.0.0.0 --port 8000 --reload
    ```
    服务将在 `http://127.0.0.1:8000` 上可用。API 文档 (Swagger UI) 位于 `http://127.0.0.1:8000/docs`。


## API 端点

### `POST /screenshot/sync`

同步获取截图。请求成功则直接返回图片数据，失败则返回错误信息。

**请求体 (JSON)**:
```json
{
  "url": "string (HttpUrl, 必填)",
  "device": "string (可选, 'pc'/'phone'/'tablet', 默认 'pc')",
  "width": "string (可选, 自定义视口宽度, 如 '1920')",
  "height": "string (可选, 自定义视口高度, 如 '1080')",
  "ua": "string (可选, 自定义 User-Agent)",
  "element_type": "string (可选, 元素选择器类型)",
  "element_name": "string (可选, 元素名称, 主要用于 'data-*' 或 'attr' 类型)",
  "element_value": "string (可选, 元素值或文本内容)",
  "full_page": "boolean (可选, 仅当不指定元素时有效, 默认 false)"
}
```

**响应**:
*   成功 (200 OK): `image/png` 类型的图片数据。
*   失败: JSON 对象，包含 `code` 和 `msg`。

### `POST /screenshot/submit`

异步提交截图任务。请求成功则返回任务 ID。

**请求体 (JSON)**: 同 `/screenshot/sync`。

**响应 (JSON)**:
```json
{
  "task_id": "string",
  "status": "submitted",
  "message": "截图任务已提交"
}
```

### `GET /task/{task_id}/status`

查询指定任务 ID 的状态。

**路径参数**:
*   `task_id`: 字符串, 从 `/screenshot/submit` 返回的任务 ID。

**响应 (JSON)**:
```json
{
  "task_id": "string",
  "status": "string ('pending', 'running', 'completed', 'failed', 'not_found')",
  "progress": "integer (0-100, 估算)",
  "message": "string (可选, 额外信息)",
  "error_details": "string (可选, 任务失败时的错误详情)"
}
```

### `GET /task/{task_id}/result`

获取已完成任务的截图结果。

**路径参数**:
*   `task_id`: 字符串。

**响应**:
*   任务完成且成功 (200 OK): `image/png` 类型的图片数据。
*   任务未完成或失败: JSON 对象，包含任务状态或错误信息。

### `DELETE /task/{task_id}`

删除指定 ID 的任务。如果任务当前正在运行，服务会尝试取消该任务。

**路径参数**:
*   `task_id`: 字符串, 要删除的任务 ID。

**响应 (JSON)**:
*   成功删除或已请求取消 (200 OK 或 202 Accepted):
    ```json
    {
      "status": "string ('deleted' 或 'cancelled')",
      "message": "string (操作结果描述)"
    }
    ```
*   任务未找到 (404 Not Found):
    ```json
    {
      "detail": "任务未找到"
    }
    ```

### `GET /system/stats`

获取系统资源使用情况和任务管理器统计。

**响应 (JSON)**:
```json
{
  "system": {
    "cpu_percent": "float",
    "memory_percent": "float"
  },
  "task_manager": {
    "max_concurrent_tasks": "integer",
    "current_running_tasks": "integer",
    "tasks_in_queue": "integer"
  },
  "tasks_overview": {
    "pending_tracked": "integer",
    "running_tracked": "integer",
    "completed_tracked": "integer",
    "failed_tracked": "integer",
    "total_tracked_in_memory": "integer"
  }
}
```

### `GET /`

根路径，返回服务启动信息。

**响应 (JSON)**:
```json
{
  "message": "网页截图API服务已启动"
}
```

## 请求参数详解

*   `url` (HttpUrl, 必填): 需要截图的网页 URL。
*   `device` (string, 可选): 设备类型预设。
    *   `"pc"`: 桌面电脑 (默认)。
    *   `"phone"`: 智能手机。
    *   `"tablet"`: 平板电脑。
    这些预设会设置默认的视口、User-Agent 和 `device_scale_factor`。
*   `width` (string, 可选): 自定义视口宽度（CSS 像素）。如果提供，将覆盖设备预设的宽度，并将 `device_scale_factor` 设为 1。
*   `height` (string, 可选): 自定义视口高度（CSS 像素）。如果提供，将覆盖设备预设的高度。
*   `ua` (string, 可选): 自定义 User-Agent 字符串。如果提供，将覆盖设备预设或默认的 User-Agent。
*   `element_type` (string, 可选): 用于元素截图的选择器类型。如果此参数和 `element_value` 都提供，则进行元素截图。
    *   `\"id\"`: 通过元素 ID 定位 (如 `element_value=\"main-content\"`)。
    *   `\"class\"`: 通过类名定位 (如 `element_value=\"button-primary\"`)。
    *   `\"name\"`: 通过 `name` 属性定位 (如 `element_value=\"username\"`)。
    *   `\"tag\"`: 通过 HTML 标签名定位 (如 `element_value=\"h1\"`)。
    *   `\"css\"`: 使用完整的 CSS 选择器 (如 `element_value=\"#nav > li:first-child .link\"`)。
    *   `\"xpath\"`: 使用 XPath 表达式 (如 `element_value=\"//button[@id=\'submit\']\"`)。
    *   `\"attr\"`: 通过通用属性定位。此时 `element_name` 为属性名，`element_value` 为属性值 (如 `element_type=\"attr\"`, `element_name=\"role\"`, `element_value=\"button\"`)。
    *   `\"data\"`: 通过 `data-*` 属性定位。此时 `element_name` 为 `data-` 后面的部分，`element_value` 为属性值 (如 `element_type=\"data\"`, `element_name=\"testid\"`, `element_value=\"login-button\"`)。
    *   `\"text\"`: 通过元素包含的文本内容定位（精确匹配）。`element_value` 为要匹配的文本。`element_name` 在此类型下被忽略。
    *   `\"canvas\"`: 通过 CSS 选择器定位 `canvas` 元素。`element_value` 为 `canvas` 元素的 CSS 选择器 (如 `element_value=\"#my-canvas\"`)。`element_name` 在此类型下被忽略。
    *   `\"iframe\"`: 通过 CSS 选择器定位 `iframe` 元素。`element_value` 为 `iframe` 元素的 CSS 选择器 (如 `element_value=\"iframe[name='my-frame']\"`)。`element_name` 在此类型下被忽略。
*   `element_name` (string, 可选): 当 `element_type` 为 `\"attr\"` 或 `\"data\"` 时使用，指定属性的名称。
*   `element_value` (string, 可选): 选择器的值，或当 `element_type` 为 `"text"` 时要匹配的文本。
*   `full_page` (boolean, 可选): 仅当不进行元素截图时有效。
    *   `true`: 截取整个可滚动页面的高度。
    *   `false`: (默认值) 截图高度将严格等于请求中 `height` 参数指定的视口高度。如果未提供 `height`，则使用设备预设的视口高度。
*   `wait_time` (float, 可选): 页面加载完成后的等待时间（秒），给页面留出足够的时间进行渲染、执行JavaScript或完成其他动态内容加载。默认值为1.0秒。
*   `timeout` (float, 可选): 整个截图任务的超时时间（秒），如果超过这个时间仍未完成截图，任务将被取消并返回超时错误。默认值为120.0秒。
*   `wait_for_resources` (boolean, 可选): 是否等待页面所有资源（图片、视频等）加载完成。
    *   `true`: Playwright 将尝试等待网络活动静默（`networkidle`状态）后才认为页面加载完成。这有助于确保大部分资源（如图片、部分视频流的初始缓冲）加载完毕。但请注意，对于持续加载或延迟加载的内容，此选项可能无法完美覆盖所有情况。建议配合 `wait_time` 使用，以获得更稳定的结果。
    *   `false`: (默认值) 主要等待DOM内容加载完成 (`domcontentloaded`)，不强制等待所有网络资源，适合快速截图或对资源完整性要求不高的场景。
*   `custom_js` (string, 可选): 页面加载后、截图前注入并执行的自定义JavaScript代码。可用于自动填写表单、触发页面交互等。代码将在截图前在页面上下文中执行，适合需要动态操作页面的场景。

## cURL 示例

**1. 同步获取百度首页的完整页面截图 (PC 默认)**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'full_page="true"' \
--output baidu_full.png
```

**2. 同步获取特定视口大小 (430x932) 的截图 (模拟手机)**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'device="phone"' \
--form 'width="430"' \
--form 'height="932"' \
--form 'full_page="false"' \
--output baidu_viewport_430x932.png
```

**3. 同步获取页面上某个元素 (通过 CSS 选择器) 的截图**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'element_type="css"' \
--form 'element_value="#su"' \
--output baidu_button.png
```

**4. 同步获取页面上某个元素 (通过文本内容 "百度一下") 的截图**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'element_type="text"' \
--form 'element_value="百度一下"' \
--output baidu_text_button.png
```

**4.1. 同步获取页面上的canvas元素内容**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.example.com/canvas-demo"' \
--form 'element_type="canvas"' \
--form 'element_value="#my-canvas"' \
--output canvas_content.png
```

**4.2. 同步获取iframe内的内容**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.example.com/iframe-page"' \
--form 'element_type="iframe"' \
--form 'element_value="iframe[src*=\\"embedded-content\\"]"' \
--output iframe_content.png
```

**5. 异步提交截图任务**
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/screenshot/submit' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "url": "https://www.example.com/",
  "device": "phone",
  "full_page": true
}'
```
假设返回: `{"task_id":"some_unique_task_id", "status":"submitted", "message":"截图任务已提交"}`

**5.1 使用自定义等待时间和超时时间的截图任务**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.example.com/"' \
--form 'device="pc"' \
--form 'full_page="true"' \
--form 'wait_time="5.0"' \
--form 'timeout="150.0"' \
--output example_with_longer_wait.png
```

**5.2 使用资源等待功能的截图任务 (建议配合足够的 wait_time 和 timeout)**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.example.com/complex-page-with-many-resources"' \
--form 'device="pc"' \
--form 'full_page="true"' \
--form 'wait_for_resources="true"' \
--form 'wait_time="3.0"' \
--form 'timeout="180.0"' \
--output example_with_resources_loaded.png
```

**5.3 使用 custom_js 参数自动操作页面并截图**
```bash
# 使用itdog对baidu进行测速并获得结果

curl --location --request POST 'http://127.0.0.1:8000/screenshot/sync' \
--header 'User-Agent: Apifox/1.0.0 (https://apifox.com)' \
--form 'url="https://www.itdog.cn/http/"' \
--form 'custom_js="document.getElementById(\"host\").value=\"https://www.baidu.com\";check_form(\"fast\");setTimeout(function(){},1e4);"' \
--form 'wait_time="10"' \
--form 'element_type="xpath"' \
--form 'element_value="//*[@id=\"china_map\"]/div[1]/canvas"'
```

**6. 查询任务状态**
```bash
curl -X 'GET' \
  'http://127.0.0.1:8000/task/some_unique_task_id/status' \
  -H 'accept: application/json'
```

**7. 获取任务结果 (任务完成后)**
```bash
curl -X 'GET' \
  'http://127.0.0.1:8000/task/some_unique_task_id/result' \
  -H 'accept: application/json' \
  --output example_async.png
```

**8. 删除任务**
```bash
curl -X 'DELETE' \
  'http://127.0.0.1:8000/task/some_unique_task_id' \
  -H 'accept: application/json'
```

## 项目文件结构 (关键文件)

```
.
├── Dockerfile                # Docker 镜像构建文件
├── fastapi_webprtsc.py       # FastAPI 应用、API 端点定义
├── requirements.txt          # Python 依赖列表
├── run.py                    # Uvicorn 启动脚本
├── task_manager.py           # 异步任务管理器实现
└── webprtsc_playwright_async.py # Playwright 截图核心逻辑
```

## 注意事项

*   确保运行环境（本地或 Docker）具有访问目标 URL 的网络权限。
*   对于需要登录或复杂交互才能到达的页面，当前版本的 API 可能无法直接截图。
*   长时间运行的服务建议部署在具有足够 CPU 和内存资源的服务器上。
*   `playwright install --with-deps` 在某些 Linux 发行版上可能无法完全自动安装所有依赖，请参考 Playwright 官方文档解决依赖问题。
*   **反爬虫说明**：尽管已采取多种措施增强反爬虫能力，但反爬虫技术和策略是不断演进的。本服务不能保证100%绕过所有网站的检测。对于防护严密的网站，仍有被识别的风险。建议合理使用，并遵守目标网站的爬虫协议（如 `robots.txt`）。