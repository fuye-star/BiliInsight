# -*- coding: utf-8 -*-
"""
授予 bili 用户创建测试数据库的权限。

【为什么需要】
Django 的测试运行器会创建一个独立的测试库（test_biliinsight），
运行结束后再删除它。而 bili 用户原先只有 biliinsight 库的权限，
因此 `manage.py test` 会报：
    (1044, "Access denied for user 'bili'@'%' to database 'test_biliinsight'")

本脚本用 root 账号连接，补上测试库权限。

【安全性说明】
仅授予 test_biliinsight 这一个库的权限，不是全局权限。
若将来修改了数据库名，测试库名也会随之变化，需重新执行本脚本。

运行：
    python scripts/grant_test_db.py
"""

import sys

import pymysql

# 连接参数：默认连 Docker 容器里的 MySQL（宿主机端口 3307）
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3307
ROOT_USER = "root"
ROOT_PASSWORD = "root_pass_2026"

# 需要授权的测试库名（Django 默认在库名前加 test_）
TEST_DB = "test_biliinsight"


def main():
    print(f"正在以 root 连接 {MYSQL_HOST}:{MYSQL_PORT} ...")
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=ROOT_USER,
            password=ROOT_PASSWORD,
            connect_timeout=10,
        )
    except Exception as exc:
        print(f"[X] 连接失败: {exc}")
        print("    请确认 Docker 容器正在运行：docker compose ps")
        return 1

    try:
        with conn.cursor() as cur:
            # -----------------------------------------------------------------
            # 第一步：查出 bili 用户实际存在哪些 host 记录
            # -----------------------------------------------------------------
            # 【为什么必须先查】
            # MySQL 8.0 的 GRANT 不再隐式创建用户。若对不存在的
            # 'bili'@'localhost' 执行 GRANT，会直接报：
            #     (1410, 'You are not allowed to create a user with GRANT')
            # 而使用 Docker 部署时通常只创建了 'bili'@'%'，
            # 因此这里动态探测，只给已存在的账号授权。
            cur.execute(
                "SELECT host FROM mysql.user WHERE user = 'bili'"
            )
            hosts = [row[0] for row in cur.fetchall()]

            if not hosts:
                print("[X] 未找到 bili 用户，请先执行 README B-1 的建号语句")
                return 1

            print(f"  检测到 bili 用户的 host 记录: {hosts}")

            # -----------------------------------------------------------------
            # 第二步：逐个 host 授予测试库权限
            # -----------------------------------------------------------------
            # 注意：库名中的下划线需要转义，否则 _ 会被当作单字符通配符，
            # 导致权限范围被意外放大。
            escaped = TEST_DB.replace("_", r"\_")

            granted = 0
            for host in hosts:
                # 用参数化无法拼 GRANT 里的标识符，这里 host 来自数据库自身、
                # 且需用单引号包裹，故用格式化字符串（值受控，无注入风险）
                sql = f"GRANT ALL PRIVILEGES ON `{escaped}`.* TO 'bili'@'{host}'"
                try:
                    cur.execute(sql)
                    print(f"  [OK] 已授权 bili@{host} -> {TEST_DB}")
                    granted += 1
                except Exception as exc:
                    print(f"  [!] bili@{host} 授权失败: {exc}")

            cur.execute("FLUSH PRIVILEGES")
            print("  [OK] 权限表已刷新")

            # -----------------------------------------------------------------
            # 第三步：回读校验
            # -----------------------------------------------------------------
            print("\nbili 用户当前权限：")
            for host in hosts:
                cur.execute(f"SHOW GRANTS FOR 'bili'@'{host}'")
                for row in cur.fetchall():
                    print(f"  {row[0]}")

        conn.commit()
    finally:
        conn.close()

    if granted:
        print(f"\n完成（{granted} 条授权）。现在可以运行：python manage.py test")
        return 0

    print("\n[X] 未能完成任何授权")
    return 1


if __name__ == "__main__":
    sys.exit(main())
