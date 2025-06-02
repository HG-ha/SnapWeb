# SnapWeb

This is an asynchronous web page screenshot service built with FastAPI and Playwright. It allows users to capture screenshots of specified URLs through API requests, supporting full-page screenshots, viewport screenshots, and screenshots of specific HTML elements. The service also provides task management functionality, supporting asynchronous submission of screenshot tasks and retrieval of results later.

## Main Features

*   **Multiple Screenshot Modes**:
    *   **Full-page Screenshots**: Capture the entire scrollable page content.
    *   **Viewport Screenshots**: Capture the browser viewport area based on user-specified width and height.
    *   **Element Screenshots**: Capture specific HTML elements based on provided selectors (CSS, XPath, ID, class name, tag name, attribute, text content, Canvas, iframe).
*   **Device Emulation**:
    *   Built-in device presets (such as "pc", "phone", "tablet").
    *   Support for custom viewport width, height, and User-Agent.
*   **Asynchronous Task Processing**:
    *   Submit screenshot tasks via the `/screenshot/submit` endpoint, immediately returning a task ID.
    *   Query task status via `/task/{task_id}/status`.
    *   Retrieve screenshot results for completed tasks via `/task/{task_id}/result`.
    *   Manually delete tasks via **DELETE** `/task/{task_id}`.
*   **Synchronous Screenshots**:
    *   Get screenshot results directly via the `/screenshot/sync` endpoint, suitable for scenarios requiring immediate response.
*   **Resource Management**:
    *   Built-in task manager controlling concurrent task numbers.
    *   Regular cleanup of old completed tasks and idle browser page resources.
    *   Browser download behavior disabled by default.
*   **System Monitoring**:
    *   Get system resource usage and task statistics via the `/system/stats` endpoint.
*   **Enhanced Anti-Scraping Mechanisms**:
    *   Disguise browser fingerprints by modifying browser launch parameters and injecting JavaScript scripts, reducing the risk of being identified as an automation tool by websites.
    *   Support for user-defined JavaScript code injection.
*   **Docker Support**: Provides Dockerfile for containerized deployment.

## Technology Stack

*   Python 3.10+
*   FastAPI: For building the API service.
*   Playwright: For browser automation and screenshots.
*   Uvicorn: ASGI server.
*   Pydantic: For data validation and model definition.
*   Psutil: For obtaining system resource information.

## Running
### 1. Running with Docker
    ```bash
    docker run -p 8000:8000 yiminger/snapweb:latest
    ```

### 2. Running from Source Code

**Prerequisites**:
*   Python 3.10 or higher.
*   pip package manager.

**Steps**:

1.  **Clone or download the project code**
    ```bash
    git clone https://github.com/HG-ha/SnapWeb.git
    ```

3.  **Install Python dependencies**:
    Navigate to the project root directory and run:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Playwright browser drivers**:
    ```bash
    playwright install chromium --with-deps
    ```
    The `--with-deps` flag will attempt to install OS dependencies required for Chromium. If issues arise, you may need to manually install these dependencies according to Playwright's official documentation.

5.  **Run the FastAPI application**:
    There is a `run.py` file in the project root directory that starts the application using uvicorn.
    ```bash
    python run.py
    ```
    Or directly use uvicorn (if `run.py` doesn't exist or you want to customize startup parameters):
    ```bash
    uvicorn fastapi_webprtsc:app --host 0.0.0.0 --port 8000 --reload
    ```
    The service will be available at `http://127.0.0.1:8000`. API documentation (Swagger UI) is located at `http://127.0.0.1:8000/docs`.

## cURL Examples

**1. Synchronously get a full-page screenshot of Baidu homepage (PC default)**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'full_page="true"' \
--output baidu_full.png
```

**2. Synchronously get a screenshot with specific viewport size (430x932) simulating phone**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'device="phone"' \
--form 'width="430"' \
--form 'height="932"' \
--form 'full_page="false"' \
--output baidu_viewport_430x932.png
```

**3. Synchronously get a screenshot of a specific element (using CSS selector)**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'element_type="css"' \
--form 'element_value="#su"' \
--output baidu_button.png
```

**4. Synchronously get a screenshot of an element (by text content "百度一下")**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.baidu.com/"' \
--form 'element_type="text"' \
--form 'element_value="百度一下"' \
--output baidu_text_button.png
```

**4.1. Synchronously get a canvas element content**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.example.com/canvas-demo"' \
--form 'element_type="canvas"' \
--form 'element_value="#my-canvas"' \
--output canvas_content.png
```

**4.2. Synchronously get iframe content**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.example.com/iframe-page"' \
--form 'element_type="iframe"' \
--form 'element_value="iframe[src*=\"embedded-content\"]"' \
--output iframe_content.png
```

**5. Submit an asynchronous screenshot task**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/submit' \
--form 'url="https://www.example.com/"' \
--form 'device="phone"' \
--form 'full_page="true"'
```

**5.1 Screenshot task with custom wait time and timeout**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.example.com/"' \
--form 'device="pc"' \
--form 'full_page="true"' \
--form 'wait_time="5.0"' \
--form 'timeout="150.0"' \
--output example_with_longer_wait.png
```

**5.2 Screenshot task with resource waiting (recommended with adequate wait_time and timeout)**
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

**5.3 Using custom_js parameter for automated page interaction and screenshot**
```bash
curl --location 'http://127.0.0.1:8000/screenshot/sync' \
--form 'url="https://www.itdog.cn/http/"' \
--form 'custom_js="document.getElementById(\"host\").value=\"https://www.baidu.com\";check_form(\"fast\");setTimeout(function(){},1e4);"' \
--form 'wait_time="10"' \
--form 'element_type="xpath"' \
--form 'element_value="//*[@id=\"china_map\"]/div[1]/canvas"'
```
