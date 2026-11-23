# -*- coding: utf-8 -*-
"""BiliInsight 桌面版启动器。

【它是做什么的】
    把"后端服务"和"桌面窗口"装进一个进程里，双击即可使用：

        ┌──────────────────────────────────────────────┐
        │  pywebview 窗口（系统自带 WebView2 内核）      │
        │   └─ 加载 http://127.0.0.1:<port>/           │
        │        ├─ 前端：Django 托管的 Vue 构建产物     │
        │        └─ 接口：同一进程内的 Django 应用        │
        │  waitress（后台线程，WSGI 服务器）             │
        │  SQLite（数据文件，在程序目录 data/ 下）        │
        └──────────────────────────────────────────────┘

【为什么不上 Electron】
    Electron 自带一整套 Chromium，发布包要再加 150MB 左右，
    而我们只需要一个能显示网页的窗口。pywebview 在 Windows 上
    直接复用系统已装的 WebView2（Win10/11 的 Edge 自带），体积小得多。

【为什么先显示启动画面再加载应用】
    首次启动要做三件慢事：
        ① 建表（migrate）
        ② 导入预置数据（40 条视频 + 6720 条弹幕）
        ③ 构建 AI 检索索引
    加起来 5～15 秒。如果等这些做完再开窗口，使用者会以为程序没反应。
    因此先把窗口开出来显示进度，准备就绪后再切换到应用页面。

【启动失败怎么办】
    打包成无控制台程序后，异常没有任何地方显示。
    因此这里把致命错误用 Windows 弹窗提示，并写进 data/logs/desktop.log。
"""

import json
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径准备：让本文件无论被直接运行还是被 PyInstaller 冻结后都能 import 到项目
# ---------------------------------------------------------------------------
if not getattr(sys, "frozen", False):
    # 开发期：把 backend/ 加入 sys.path（本文件就在 backend/ 下）
    _HERE = Path(__file__).resolve().parent
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
else:
    # 打包后：把 exe 所在目录加入 sys.path，便于找到随包附带的数据
    _HERE = Path(sys.executable).resolve().parent
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))

# 必须在 import Django 之前指定配置模块
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.desktop")

# ChromaDB 会悄悄上报 telemetry，桌面版关掉，避免无谓的网络请求
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


# ===========================================================================
# 启动画面
# ===========================================================================
SPLASH_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>BiliInsight</title>
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background: linear-gradient(135deg, #1e2a44 0%, #2b3a5c 100%);
    color: #e8eefc;
    font-family: "Microsoft YaHei", system-ui, sans-serif;
    user-select: none;
  }
  .logo {
    font-size: 30px; font-weight: 700; letter-spacing: 2px;
    background: linear-gradient(90deg, #7fb3ff, #b18cff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 10px;
  }
  .sub { font-size: 13px; color: #9db0d4; margin-bottom: 34px; }
  .spinner {
    width: 34px; height: 34px; margin-bottom: 18px;
    border: 3px solid rgba(255,255,255,.15);
    border-top-color: #7fb3ff; border-radius: 50%;
    animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  #status { font-size: 13px; color: #c3d2ee; min-height: 20px; }
  .tip { margin-top: 28px; font-size: 11px; color: #6d7f9e; }
</style>
</head>
<body>
  <div class="logo">BiliInsight</div>
  <div class="sub">B站热门视频数据分析与智能推荐系统</div>
  <div class="spinner"></div>
  <div id="status">正在启动…</div>
  <div class="tip">首次启动需要准备数据，请稍候</div>
  <script>
    // 供 Python 侧调用以更新进度文本
    window.setStatus = function (text) {
      document.getElementById('status').textContent = text;
    };
  </script>
</body>
</html>
"""


# ===========================================================================
# 崩溃现场保存
# ===========================================================================
def _crash_log_path() -> Path:
    """崩溃日志的落脚点。

    【为什么不用 data/logs】
        data 目录是由 Django 配置创建的。如果崩溃发生在
        「Django 还没初始化成功」的阶段，那个目录根本不存在 ——
        恰恰是最需要日志的时候写不进去。

        因此这里只依赖 sys.executable，落在 exe 同级，
        任何阶段都可用。
    """
    try:
        base = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent
        )
    except Exception:  # noqa: BLE001
        base = Path(".")
    return base / "startup-error.log"


def _emergency_log(text: str) -> None:
    """把崩溃信息写进文件（尽力而为，绝不抛异常）。"""
    try:
        with open(_crash_log_path(), "a", encoding="utf-8") as handle:
            handle.write(f"\n{'=' * 68}\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n{text}\n")
    except Exception:  # noqa: BLE001
        pass


def _show_error(message: str) -> None:
    """在没有控制台的情况下把错误显示给人看。

    先用 Windows 原生弹窗（最可靠，不依赖任何 GUI 库），
    失败则退回控制台输出。
    """
    _emergency_log(message)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "BiliInsight 启动失败", 0x10)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        print(message, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def _port_in_use(port: int) -> bool:
    """端口是否已经有服务在监听（能连上就说明被占）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _can_bind(port: int) -> bool:
    """能否在本机回环地址上绑定该端口。

    【为什么不用 SO_REUSEADDR —— 这是个 Windows 专属的坑】
        Windows 上 SO_REUSEADDR 的语义与 Unix 不同：
        它允许两个 socket 绑定同一个端口（相当于 Linux 的 SO_REUSEPORT）。
        用它做"端口是否空闲"的探测，会把**已经被别的程序监听**的端口
        误判为空闲，然后真正起服务时两个进程争抢同一个端口，
        表现为"时好时坏"的诡异故障 —— 很难查。

        这里改用 SO_EXCLUSIVEADDRUSE（Windows 专有），
        它明确禁止共享端口，绑定成功才代表真的可用。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _find_free_port(preferred: int = 8000) -> int:
    """找一个真正可用的端口。

    优先用 8000（便于使用者自己在浏览器打开），
    被占用则依次往后试 8010-8099，最后交给系统分配。
    """
    candidates = [preferred] + list(range(8010, 8100))
    for port in candidates:
        if _port_in_use(port):
            continue
        if _can_bind(port):
            return port

    # 全被占用：让系统随便给一个
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _make_status_pusher(window):
    """构造一个把进度文本推到启动画面的函数。"""

    def push(message: str) -> None:
        try:
            window.evaluate_js(f"window.setStatus({json.dumps(message)});")
        except Exception:  # noqa: BLE001
            # 窗口还没准备好或已关闭，忽略即可
            pass

    return push


# ===========================================================================
# 主流程
# ===========================================================================
class DesktopApp:
    """把 Django + waitress + 窗口组装起来的容器。"""

    def __init__(self):
        self.port = _find_free_port()
        self.url = f"http://127.0.0.1:{self.port}/"
        self._server = None
        self._django_ready = False

    # -- 步骤 1：Django 环境 -------------------------------------------
    def setup_django(self) -> None:
        """初始化 Django（导入设置、注册应用）。"""
        import django

        django.setup()
        self._django_ready = True

    # -- 步骤 2：启动 WSGI 服务 ----------------------------------------
    def start_server(self) -> None:
        """在后台线程里启动 waitress。

        【为什么用 waitress 而不是 runserver】
            runserver 是开发服务器，单线程且明确不适合交付使用；
            它也更容易在请求稍慢时卡住。waitress 是纯 Python 的
            生产级 WSGI 服务器，Windows 上无需额外依赖。
        """
        from django.core.wsgi import get_wsgi_application
        from waitress.server import create_server

        application = get_wsgi_application()
        self._server = create_server(
            application,
            host="127.0.0.1",
            port=self.port,
            threads=8,
            # 抓取接口可能一次跑几秒，超时给宽一点
            channel_timeout=180,
            # 关掉 waitress 启动横幅（无控制台时写不进任何地方）
            clear_untrusted_proxy_headers=True,
        )
        thread = threading.Thread(
            target=self._server.run, name="waitress", daemon=True
        )
        thread.start()

    def stop_server(self) -> None:
        """关闭 WSGI 服务。"""
        if self._server is not None:
            try:
                self._server.close()
            except Exception:  # noqa: BLE001
                pass
            self._server = None

    # -- 步骤 3：等待端口可连接 ----------------------------------------
    def wait_until_ready(self, timeout: float = 20.0) -> bool:
        """轮询直到 HTTP 端口能建立连接。"""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                if sock.connect_ex(("127.0.0.1", self.port)) == 0:
                    return True
            time.sleep(0.15)
        return False

    # -- 步骤 4：首次启动准备 ------------------------------------------
    def bootstrap(self, push) -> None:
        """建表 / 导入预置数据 / 构建索引。"""
        from apps.common.bootstrap import ensure_ready

        result = ensure_ready(progress=push)
        if not result["ok"]:
            raise RuntimeError(result.get("error") or "初始化失败")

    # -- 步骤 5：串起来 -------------------------------------------------
    def boot_in_background(self, window) -> None:
        """后台线程：初始化 -> 起服务 -> 切换到应用页面。"""

        push = _make_status_pusher(window)
        try:
            push("正在检查数据库结构…")
            self.bootstrap(push)

            push("正在启动服务…")
            self.start_server()
            if not self.wait_until_ready():
                raise RuntimeError(f"服务未能在预期时间内启动（端口 {self.port}）")

            push("正在加载界面…")
            window.load_url(self.url)
        except Exception as exc:  # noqa: BLE001
            detail = traceback.format_exc()
            try:
                with open(
                    Path(os.environ.get("BILIINSIGHT_LOG_FALLBACK", ".")) / "startup-error.log",
                    "w",
                    encoding="utf-8",
                ) as handle:
                    handle.write(detail)
            except Exception:  # noqa: BLE001
                pass
            push(f"启动失败：{exc}")
            _show_error(f"{exc}\n\n详细信息已记录到 data/logs/desktop.log")


def _run_with_pywebview(app: DesktopApp) -> int:
    """用 pywebview 打开窗口；失败则退回系统浏览器。"""
    import webview

    window = webview.create_window(
        "BiliInsight · B站热门视频数据分析",
        html=SPLASH_HTML,
        width=1440,
        height=900,
        min_size=(1024, 680),
        text_select=True,
    )

    threading.Thread(
        target=app.boot_in_background,
        args=(window,),
        name="bootstrap",
        daemon=True,
    ).start()

    webview.start()
    return 0


def _run_with_browser(app: DesktopApp) -> int:
    """没有 WebView2 时的兜底：用系统浏览器打开。"""
    print("未检测到可用的 WebView2 运行时，改用系统浏览器打开…")
    app.bootstrap(progress=lambda msg: print(f"  {msg}"))
    app.start_server()
    if not app.wait_until_ready():
        _show_error("服务启动失败，请查看 data/logs/desktop.log")
        return 1

    webbrowser.open(app.url)
    print(f"\nBiliInsight 已在本机运行：{app.url}")
    print("关闭本窗口即可退出程序。\n")
    try:
        # 保持主线程存活，直到用户按 Ctrl+C
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_server()
    return 0


def main() -> int:
    """程序入口。"""
    try:
        app = DesktopApp()
    except Exception as exc:  # noqa: BLE001
        _show_error(f"初始化失败：{exc}\n\n{traceback.format_exc()}")
        return 1

    try:
        app.setup_django()
    except Exception as exc:  # noqa: BLE001
        detail = traceback.format_exc()
        _show_error(
            f"Django 初始化失败：{exc}\n\n"
            f"完整信息已写入 startup-error.log（在程序同一目录下）。"
        )
        _emergency_log(detail)
        return 1

    try:
        return _run_with_pywebview(app)
    except Exception as exc:  # noqa: BLE001
        # WebView2 缺失 / 窗口创建失败等：退回系统浏览器
        _emergency_log(f"pywebview 启动失败：{exc}\n\n{traceback.format_exc()}")
        try:
            return _run_with_browser(app)
        except Exception as inner:  # noqa: BLE001
            _show_error(
                f"启动失败：{exc}\n兜底方案也失败：{inner}\n\n"
                f"完整信息已写入 startup-error.log。"
            )
            _emergency_log(traceback.format_exc())
            return 1
    finally:
        app.stop_server()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        # 最外层兜底：任何未捕获异常都要留下痕迹，否则无控制台时完全无从排查
        _emergency_log(f"未捕获异常：\n{traceback.format_exc()}")
        raise
