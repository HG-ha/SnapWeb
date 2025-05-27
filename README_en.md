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
    