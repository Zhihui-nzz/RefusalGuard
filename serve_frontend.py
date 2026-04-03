"""
RefusalGuard Dashboard 前端静态文件服务器
"""
import http.server
import socketserver
import os
import sys

PORT = 3000
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend_dist")

class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def do_GET(self):
        # 如果请求的文件存在，直接返回
        path = self.translate_path(self.path)
        if os.path.exists(path) and os.path.isfile(path):
            return super().do_GET()
        # 否则返回 index.html（SPA 路由）
        self.path = "/index.html"
        return super().do_GET()

    def log_message(self, format, *args):
        pass  # 静默日志

if __name__ == "__main__":
    if not os.path.exists(FRONTEND_DIR):
        print(f"[错误] 找不到前端目录: {FRONTEND_DIR}")
        sys.exit(1)

    with socketserver.TCPServer(("", PORT), SPAHandler) as httpd:
        print(f"   RefusalGuard Dashboard 已启动")
        print(f"   访问地址: http://localhost:{PORT}")
        print(f"   按 Ctrl+C 停止服务")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务已停止")
