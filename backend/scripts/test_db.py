# ============================================================
# BiliInsight 数据库连通性测试
# 用法：
#   cd backend
#   .\.venv\Scripts\Activate.ps1
#   pip install pymysql redis python-dotenv
#   python scripts\test_db.py
#
# 作用：验证 MySQL 与 Redis(Memurai) 是否可连，并自动建库
# 依赖：纯 PyMySQL / redis，不需 Django（便于早期排查）
# ============================================================

import os
import sys

try:
    import pymysql
except ImportError:
    print("[X] 缺少 pymysql，请执行:  pip install pymysql")
    sys.exit(1)

try:
    import redis
except ImportError:
    print("[X] 缺少 redis，请执行:  pip install redis")
    sys.exit(1)

# ---------- 从 .env 读取（没有则用默认值）----------
def load_env(path=".env"):
    cfg = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

env = load_env()

MYSQL = {
    "host":     env.get("MYSQL_HOST", "127.0.0.1"),
    "port":     int(env.get("MYSQL_PORT", 3306)),
    "user":     env.get("MYSQL_USER", "bili"),
    "password": env.get("MYSQL_PASSWORD", "bili_pass_2026"),
    "database": env.get("MYSQL_DATABASE", "biliinsight"),
}

REDIS_URL = env.get("REDIS_URL", "redis://127.0.0.1:6379/0")

OK, FAIL = "[OK]", "[X]"


def test_mysql():
    print("\n" + "=" * 58)
    print("  MySQL 连通性测试")
    print("=" * 58)
    print(f"  目标: {MYSQL['user']}@{MYSQL['host']}:{MYSQL['port']}/{MYSQL['database']}")

    try:
        conn = pymysql.connect(
            host=MYSQL["host"], port=MYSQL["port"],
            user=MYSQL["user"], password=MYSQL["password"],
            database=MYSQL["database"], charset="utf8mb4",
            connect_timeout=8,
        )
    except pymysql.err.OperationalError as e:
        code = e.args[0] if e.args else "?"
        print(f"  {FAIL} 连接失败 (错误码 {code})")
        if code == 1045:
            print("      -> 账号或密码错误。请核对 .env 里的 MYSQL_USER / MYSQL_PASSWORD，")
            print("         或重新执行建号语句（见 README B-1）。")
        elif code == 2003:
            print("      -> 无法连接到服务。请确认 MySQL 服务已启动：")
            print("         Get-Service MySQL*   （应为 Running）")
        elif code == 1049:
            print("      -> 数据库不存在。请先执行建库语句（见 README B-1）。")
        return False
    except Exception as e:
        print(f"  {FAIL} 连接异常: {e}")
        return False

    with conn.cursor() as cur:
        cur.execute("SELECT VERSION()")
        ver = cur.fetchone()[0]
        print(f"  {OK} 已连接，MySQL 版本: {ver}")

        cur.execute("SELECT DATABASE()")
        print(f"  {OK} 当前数据库: {cur.fetchone()[0]}")

        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        if tables:
            print(f"  {OK} 已有 {len(tables)} 张表: {', '.join(tables[:8])}"
                  + (" ..." if len(tables) > 8 else ""))
        else:
            print("  [i] 当前无表（正常，Django migrate 后会创建）")

        # 验证写入权限（迁移需要建表权限）
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS _conn_test (id INT PRIMARY KEY)")
            cur.execute("DROP TABLE _conn_test")
            conn.commit()
            print(f"  {OK} 具备建表权限（Django migrate 可正常执行）")
        except Exception as e:
            print(f"  {FAIL} 缺少建表权限: {e}")
            conn.close()
            return False

    conn.close()
    return True


def test_redis():
    print("\n" + "=" * 58)
    print("  Redis / Memurai 连通性测试")
    print("=" * 58)
    print(f"  目标: {REDIS_URL}")

    try:
        r = redis.from_url(REDIS_URL, socket_connect_timeout=8)
        r.ping()
    except redis.exceptions.ConnectionError as e:
        print(f"  {FAIL} 连接失败: {e}")
        print("      -> 请确认 Memurai 服务已启动：")
        print("         Get-Service Memurai")
        print("         & \"C:\\Program Files\\Memurai\\memurai-cli.exe\" ping   (应返回 PONG)")
        return False
    except Exception as e:
        print(f"  {FAIL} 连接异常: {e}")
        return False

    info = r.info()
    print(f"  {OK} 已连接，PING 成功")
    print(f"  {OK} 服务版本: {info.get('redis_version', '未知')}")
    print(f"  {OK} 运行模式: {info.get('redis_mode', '未知')}")

    try:
        r.set("biliinsight:test", "ok", ex=10)
        val = r.get("biliinsight:test")
        r.delete("biliinsight:test")
        if val == b"ok":
            print(f"  {OK} 读写测试通过")
        else:
            print(f"  {FAIL} 读写异常，读回: {val!r}")
            return False
    except Exception as e:
        print(f"  {FAIL} 读写失败: {e}")
        return False

    # Celery 用不同 DB，顺手验证
    for db in (1, 2):
        try:
            r2 = redis.from_url(REDIS_URL.rsplit("/", 1)[0] + f"/{db}",
                                socket_connect_timeout=5)
            r2.ping()
            print(f"  {OK} 数据库 db{db} 可用（Celery Broker/Backend）")
        except Exception as e:
            print(f"  {FAIL} db{db} 不可用: {e}")
            return False

    return True


def main():
    print("\n  BiliInsight 数据库连通性测试")
    print("  " + "-" * 54)

    if not os.path.exists(".env"):
        print("\n  [i] 未找到 .env，使用默认值。建议先执行：")
        print("      Copy-Item .env.example .env")

    m = test_mysql()
    r = test_redis()

    print("\n" + "=" * 58)
    print("  结论")
    print("=" * 58)
    print(f"  MySQL  : {OK + ' 通过' if m else FAIL + ' 失败'}")
    print(f"  Redis  : {OK + ' 通过' if r else FAIL + ' 失败'}")
    print()
    if m and r:
        print("  两个数据库均已就绪，可以开始 Django 开发！")
    else:
        print("  请先解决上面标 [X] 的问题，详见 README 第四、五章。")
    print()
    return 0 if (m and r) else 1


if __name__ == "__main__":
    sys.exit(main())
