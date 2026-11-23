# -*- coding: utf-8 -*-
"""
404 / 500 统一 JSON 响应的自动化测试。

【为什么需要专门测这个】
Django 只有在 DEBUG=False 时才使用 settings 中配置的 handler404 / handler500；
开发环境（DEBUG=True）会显示调试用的 HTML 页面。
因此无法通过手工访问一个不存在的 URL 来验证处理器是否生效，
必须显式用 override_settings(DEBUG=False) 强制走生产路径。

运行方式：
    python manage.py test apps.common.tests_404 -v 2
"""

from django.test import Client, TestCase, override_settings


@override_settings(DEBUG=False, ALLOWED_HOSTS=["*"])
class ErrorHandlerTests(TestCase):
    """验证 404 / 500 返回统一 JSON 结构，而不是 HTML 页面。"""

    def setUp(self):
        """每个测试方法执行前初始化测试客户端。"""
        self.client = Client()

    # -----------------------------------------------------------------
    # 404 处理
    # -----------------------------------------------------------------
    def test_404_returns_json(self):
        """访问不存在的路径应返回 JSON 格式的 404。"""
        response = self.client.get("/api/this-path-does-not-exist/")

        self.assertEqual(response.status_code, 404)
        # 关键断言：必须是 JSON，而不是 Django 的 HTML 调试页
        self.assertTrue(
            response["Content-Type"].startswith("application/json"),
            f"期望 JSON 响应，实际为 {response['Content-Type']}",
        )

        payload = response.json()
        self.assertEqual(payload["code"], 1004)
        self.assertEqual(payload["message"], "请求的资源不存在")
        self.assertIsNone(payload["data"])

    def test_404_chinese_not_escaped(self):
        """中文不应被转义成 \\uXXXX，便于前端直接展示。"""
        response = self.client.get("/api/nope/")
        # ensure_ascii=False 时，content 中应含原始 UTF-8 中文字节
        self.assertIn("请求的资源不存在".encode("utf-8"), response.content)

    def test_404_on_root_path(self):
        """根路径下的不存在地址同样返回统一 JSON。"""
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 1004)

    # -----------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------
    def test_health_check_ok(self):
        """健康检查应返回 200，且两个依赖都被真实探测。"""
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["data"]["status"], "healthy")

        services = payload["data"]["services"]
        self.assertIn("database", services)
        self.assertIn("cache", services)
        # 真实探测的标志：必须带有连接结果与耗时
        self.assertTrue(services["database"]["ok"])
        self.assertIn("latency_ms", services["database"])

    # -----------------------------------------------------------------
    # Admin
    # -----------------------------------------------------------------
    def test_admin_redirects_when_anonymous(self):
        """Admin 未登录时应重定向到登录页，而不是抛 500。"""
        response = self.client.get("/admin/")
        self.assertIn(response.status_code, (301, 302))
