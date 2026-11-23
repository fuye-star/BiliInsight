# BiliInsight · B站热门视频数据分析与智能推荐系统

> **BiliInsight** = Bilibili + Insight
> 一个覆盖「互联网数据采集 → 清洗挖掘 → 数据库存储 → Web可视化 → 情感分析 → AI智能推荐」全链路的
> 前后端分离数据平台，对应 PPT「项目 7 - 自拟题目」方向。

<p align="left">
  <img alt="python" src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white">
  <img alt="django" src="https://img.shields.io/badge/Django-5.2%20LTS-092E20?logo=django&logoColor=white">
  <img alt="vue" src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white">
  <img alt="vite" src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white">
  <img alt="mysql" src="https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white">
  <img alt="redis" src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white">
  <img alt="license" src="https://img.shields.io/badge/License-MIT--Educational-green">
</p>

---

## 目录

- [零、当前进度](#零当前进度) ← **开发状态看这里**
- [一、项目概述](#一项目概述)
- [二、系统架构](#二系统架构)
- [三、技术栈清单](#三技术栈清单)
- [四、环境要求与本机实测结果](#四环境要求与本机实测结果) ← **含缺失工具与下载路径**
- [五、速通部署（推荐路径）](#五速通部署推荐路径)
- [六、完整部署步骤](#六完整部署步骤)
- [七、AI 模块配置（RAG + 情感分析）](#七ai-模块配置rag--情感分析)
- [八、接口文档](#八接口文档)
- [九、目录结构](#九目录结构)
- [十、测试与性能优化](#十测试与性能优化)
- [十一、常见问题排查](#十一常见问题排查)
- [十二、数据合规声明](#十二数据合规声明)
- [十三、团队分工](#十三团队分工)
- [十四、答辩自查清单](#十四答辩自查清单)

---

## 零、当前进度

| 阶段 | 内容 | 状态 | 完成时间 |
| --- | --- | --- | --- |
| **环境搭建** | Python / Node / WSL2 / Docker / MySQL / Redis / PyCharm | ✅ **已完成** | 2026-09-16 |
| **阶段一：框架搭建** | Django 项目骨架 + 6 个 app + 数据模型 + 健康检查 | ✅ **已完成** | **2026-09-18** |
| **阶段二：数据采集** | BaseSpider 基类 + B站爬虫 + 解析器 + Celery 任务 + 演示数据 | ✅ **已完成** | **2026-09-18** |
| **阶段三：分析接口** | analytics 聚合统计 + 视频/弹幕/UP主接口 + 情感分析接口 | ✅ **已完成** | **2026-09-18** |
| **阶段四：前端看板** | Vue 3 + Element Plus + ECharts 五大页面 | ✅ **已完成** | **2026-09-18** |
| **阶段五：AI 模块** | RAG 检索 + 向量库 + 双 Provider LLM + 对话助手 | ✅ **已完成** | **2026-09-18** |
| **阶段六：体验修复** | 数据来源标注 + 跳转链接优化 + 详情页弹回 Bug 修复 | ✅ **已完成** | **2026-09-27** |
| **阶段六补：真实数据入库** | 抓取 **97 条真实视频**（科技分区）+ 索引重建 + 全链路复验 | ✅ **已完成** | **2026-09-27** |
| **阶段六补 2：同步缺陷修复** | 分析缓存未清 + UP主排行硬编码 + 数据来源估算错误 | ✅ **已完成** | **2026-09-27** |
| **阶段六补 3：真实弹幕入库** | 补抓 5 个真实视频的 **1216 条弹幕** + 情感标注，情感分析接入真实数据 | ✅ **已完成** | **2026-09-27** |
| **阶段六补 4：抓取能力增强** | 封面防盗链修复 + UP主 粉丝数抓取 + 弹幕整合 + `reset_data`/`patient_crawl` 新命令 | ✅ **已完成** | **2026-09-27** |
| **阶段六补 5：全量重抓** | 清空全部旧数据，按新要求重抓 **40 条全真实数据**（封面 + 粉丝数 + 6720 条弹幕） | ✅ **已完成** | **2026-09-27** |
| **阶段六补 6：AI 检索修复** | 向量化器与索引维度不匹配导致检索全空（静默失败）+ 自动校验自愈 | ✅ **已完成** | **2026-09-27** |
| **阶段七：桌面版打包** | SQLite 单机版 + pywebview 窗口 + 界面内「更新数据」+ 免安装 zip（200.7 MB） | ✅ **已完成** | **2026-11-23** |
| **阶段八：自定义模型 Provider** | 界面管理大模型 API（4 类服务商 + Key 加密存储 + 测试连接 + 热切换） | ✅ **已完成** | **2026-11-23** |
| 阶段九（可选） | AI 助手图片理解 / 多模态输入 | ⬜ 未开始 | — |

> 📅 **开发日志**
> - **2026-09-16**：环境搭建完成（Docker + MySQL 8.0.46 + Redis 7.4.11 全部跑通）
> - **2026-11-23**：**大模型提供商改为界面可配置（用户自带 API Key）**
>   - 支持 4 类：DeepSeek / 通义千问 / 本地 Ollama / **OpenAI 兼容（自定义）**
>   - API Key 用 SECRET_KEY 派生的 Fernet 密钥**加密存储**，接口只返回打码值
>   - 「测试连接」发真实小请求，能发现"模型名填错 / 余额不足"这类 ping 查不出的问题
>   - 配置优先级：界面配置 > 显式指定 > 环境变量 > 检索式兜底
>   - 迁移：启动时把已有 `.env` / `config.json` 里的 Key 一次性导入成配置，幂等
>   - **修掉一处真实泄密风险**：OpenAI 兼容 Provider 在 Key 为空时会回落到
>     `settings.DEEPSEEK_API_KEY`，把 DeepSeek 密钥发给用户填的任意第三方地址
>   - 新增 28 个测试，套件 **232/232 通过**
> - **2026-11-23**：**打包成桌面应用（发给老师/同学）**
>   - 形态：SQLite + LocMemCache + 同步抓取 + pywebview 窗口，
>     从"4 进程 + 2 中间件"变成**单进程双击即用**
>   - 界面新增「数据更新」卡片：联网点一下即可抓取最新排行榜（1 次请求，约 1-3 秒）
>   - 自带预置数据集，**没网也能看到完整图表**
>   - 产物：`BiliInsight-Desktop-win64.zip` **200.7 MB**（解压 416.4 MB）
>   - 验收：zip 全新解压 → 12.6 秒首启 → 首页 200 / 40 视频 / AI 索引就绪
>   - 修掉 6 个坑，其中 2 个只在打包期暴露（模板里的 TS 注解、缺 `@types/node`）、
>     1 个导致 exe 静默退出（`celery.fixups` 动态导入）
>   - 测试套件 **204/204 通过**（新增 12 个桌面交付测试）
> - **2026-09-27**：修复 AI 助手"检索不到内容"（静默失败）
>   - 现象：状态面板显示"索引就绪 40 条"，但提问永远回答"没有相关视频"
>   - 根因：本地向量化器维度随语料规模变化（297 条→256 维，40 条→39 维），
>     重建索引后 Web 进程内存里仍是旧的 256 维实例；
>     `search()` 只在"完全未训练"时才加载磁盘状态，**跳过了刷新**
>   - 异常被 `except: return []` 吞掉，界面完全看不出原因
>   - 修复：集合元数据记录 `embedding_dim` + 语料指纹，检索前校验并自动重载
>   - 新增 3 个回归测试，测试套件 **192/192 通过**
> - **2026-09-27**：**抓取能力增强 + 全量重抓**
>   - 清空 297 条旧数据（模拟 + 早期真实），**数据库现在 100% 是真实数据**
>   - 新增 UP主 粉丝数抓取（`x/relation/stat`，按 mid 去重）：**40/40 成功**
>   - 修复封面防盗链：带本地 Referer 返回 403，实测 **403 → 200**
>   - 新增 `Video.cid` 字段，让抓弹幕省掉逐个详情请求（**1 次换 39 次**）
>   - 新增 `reset_data`（安全清库）与 `patient_crawl.py`（风控下长期磨数据）
>   - 抓弹幕时挖出 **4 个隐蔽 Bug**，其中"风控 JSON 被当成弹幕数据"
>     曾导致 19 个视频被静默误判
>   - 最终：40 视频 / 40 UP主 / 6720 条弹幕，测试 **185/185 通过**
> - **2026-09-27**：补抓真实弹幕，情感分析接入真实数据
>   - 5 个视频全部一次成功、零风控，共 **11 次 HTTP 请求**，入库 **1216 条真实弹幕**
>   - 选片策略：挑**短视频**而非弹幕多的视频（分包数由时长决定，与弹幕量无关）
>   - 真实弹幕出现 `relic`、`刀剑神域` 等社区梗，是最直观的真实性证据
>   - `analyze_sentiment` 标注 1216 条（1.1 秒），`analytics/sentiment/` 立即可见
> - **2026-09-27**：修复"分析类页面没同步"的三个 Bug
>   - 根因：抓完数据**没清分析缓存**，而 `clear_analytics_cache` 的注释
>     谎称"Celery 任务结束时已触发"，实际从未被调用
>   - 修复：`_finish_task` 统一兜底 + 三个管理命令各自补上；修正失实注释
>   - 另修：`UpUserView` 硬编码 `follower_count`（真实 UP主 该字段为 0）
>   - 另修：数据来源提示条按"榜单前 10 条"估算比例 → 改用全库准确计数
>   - 新增 **9 个回归测试**，测试套件 **170/170 通过**
> - **2026-09-27**：**真实数据抓取成功** —— 切换手机热点绕过 IP 风控，1 次请求入库 **97 条真实视频**
>   - 数据库：`200 模拟 + 97 真实 = 297 条`；UP主 137 位，分区 10 个
>   - 真实数据 TOP1：`BV1kCoxYZEAc`「小学生拿到新电脑VS大学生拿到新电脑」播放 801 万
>   - RAG 索引重建为 **297 条**（2.03 秒，256 维）
>   - 验证 `data_source=real` / `source_url` 在列表页与分析接口均正确透出
> - **2026-09-18**：**五个阶段全部完成**
>   - 阶段一：26 张表创建成功，健康检查接口返回真实依赖版本
>   - 阶段二：真实抓取 dry-run 验证通过（97 条视频 + 302 条弹幕解析成功率 100%）
>   - 阶段三：**16 个接口**全部实测通过
>   - 阶段四：**28 个前端文件**、5 个页面，浏览器实测全部正常渲染
>   - 阶段五：**向量索引 200 条**（2.04 秒建成）、RAG 对话与 SSE 流式实测通过
>   - 累计 **144 个单元测试**全部通过





### 阶段一交付物（已实测通过）

**已验证的功能**：

| 验证项 | 命令 / 地址 | 结果 |
| --- | --- | --- |
| 配置检查 | `python manage.py check` | ✅ 0 issues |
| 数据库迁移 | `python manage.py migrate` | ✅ 26 张表创建成功 |
| 健康检查 | <http://127.0.0.1:8000/api/health/> | ✅ `MySQL 8.0.46` + `Redis 7.4.11` |
| 接口文档 | <http://127.0.0.1:8000/api/docs/> | ✅ Swagger UI 正常 |
| 管理后台 | <http://127.0.0.1:8000/admin/> | ✅ 账号 `admin` |
| 单元测试 | `python manage.py test apps.common.tests_404` | ✅ 5 个测试全通过 |

**已创建的数据表**（4 张业务表 + 3 张辅助表）：

```
videos_partition    分区（科技/数码/游戏...）        ← 4 个索引
videos_upuser       UP主                            ← 1 个索引
videos_video        视频主表（含 7 个互动指标）       ← 4 个索引
videos_danmaku      弹幕（含情感分析字段）            ← 3 个索引 + 1 唯一约束
spider_crawltask    爬取任务记录                     ← 1 个索引
ai_chatsession      AI 对话会话
ai_chatmessage      AI 对话消息（含 RAG 溯源字段）
```

**代码规模**：约 1500 行 Python（含约 20% 中文注释与文档字符串）

### 快速验证阶段一成果

```powershell
# 1) 启动中间件（若未启动）
cd "E:\deepseek harness\Biliinsight"
docker compose up -d

# 2) 启动后端
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver 8000

# 3) 浏览器访问
#    http://127.0.0.1:8000/api/health/   -> 健康检查 JSON
#    http://127.0.0.1:8000/api/docs/     -> 接口文档
#    http://127.0.0.1:8000/admin/        -> 后台（admin / admin123456）
```

> ⚠️ **测试库权限**：运行 `manage.py test` 前需先执行一次
> `python scripts\grant_test_db.py`（Django 测试会创建 `test_biliinsight` 库，
> `bili` 用户默认无此权限）。

### 阶段二交付物（2026-09-18 完成，已实测通过）

**新增文件**：

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `apps/spider/base.py` | ~320 | **BaseSpider 抽象基类**：限速、重试、UA、日志、统计 |
| `apps/spider/constants.py` | ~200 | 接口地址、15 个分区 tid 表、数据实体、时间工具 |
| `apps/spider/parsers.py` | ~420 | **纯解析函数**（视频 JSON + 弹幕 protobuf），零网络零数据库 |
| `apps/spider/bilibili.py` | ~330 | `BiliBiliSpider`：请求 + 编排 + 幂等入库 |
| `apps/spider/persistence.py` | ~180 | 入库层：`upsert_video` / `upsert_danmaku` / `upsert_upuser` |
| `apps/spider/tasks.py` | ~250 | 5 个 Celery 任务（分区/热门/弹幕/批量） |
| `apps/spider/management/commands/crawl.py` | ~290 | `manage.py crawl` 命令行抓取 |
| `apps/spider/management/commands/seed_demo.py` | ~420 | `manage.py seed_demo` 离线演示数据 |
| `apps/spider/tests.py` | ~330 | **25 个单元测试**（全部离线） |

**已验证**：

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 配置检查 | `python manage.py check` | ✅ 0 issues |
| 解析器测试 | `python manage.py test apps.spider` | ✅ **25/25 通过** |
| 命令行帮助 | `python manage.py crawl --help` | ✅ 参数正常 |
| 演示数据 | `python manage.py seed_demo` | 见下方命令 |

**两种取数方式**：

```powershell
# 方式一：真实抓取（需联网，遵守合规限速）
python manage.py crawl --dry-run --partition 科技     # 先试运行验证接口
python manage.py crawl --partition 科技,数码 --limit 50
python manage.py crawl --hot --limit 50
python manage.py crawl --danmaku BV1xx411c7mD --limit 2000
python manage.py crawl --batch-danmaku 10             # 批量抓弹幕

# 方式二：离线演示数据（无需联网，固定随机种子可复现）
python manage.py seed_demo                            # 200 视频 + 3000 弹幕
python manage.py seed_demo --videos 500 --danmaku 8000
python manage.py seed_demo --clear                    # 先清空再生成
```

**设计要点**：

| 决策 | 理由 |
| --- | --- |
| **解析与抓取分离** | 解析函数零依赖，可用 fixture 离线测试（本阶段 25 个测试全部不联网） |
| **手写 protobuf 解析** | 弹幕接口返回 protobuf；手写 wire-format 解析器免去 protoc 编译与 `.proto` 维护，答辩现场零风险。只涉及 varint 与 length-delimited 两种类型 |
| **限速下限硬编码 1.0 秒** | 即使误配置也无法把间隔调到 1 秒以下，从代码层面保证合规 |
| **限速用"补差"而非固定 sleep** | 固定 `sleep(2)` 会让请求耗时白白浪费；按"距上次请求不足间隔才补足"实现，既合规又不降效率，并加 ±20% 抖动避免机器特征 |
| **`CrawlStats` 与模型字段一一对应** | 统计对象可直接 `as_dict()` 写入 `CrawlTask`，无需转换代码 |
| **弹幕用 `bulk_create(ignore_conflicts=True)`** | 逐条 `update_or_create` 是 2 次查询；万条弹幕下批量插入快一个数量级，配合唯一约束实现幂等 |
| **`seed_demo` 用幂律分布造数** | 播放量/粉丝数按帕累托分布生成，使互动率落在合理区间（2%-15%），榜单排序才有意义；固定种子保证可复现 |

**验证命令**：

```powershell
# 生成数据后校验质量（互动率是否合理、外键是否完整、分布是否有区分度）
python scripts\verify_demo_data.py
```

**实测输出**（2026-09-18）：

```
分区: 6    UP主: 40    视频: 200    弹幕: 3000

播放量  最小 5,001      最大 257,085
        平均 12,963     总计 2,592,625
互动率  最小 0.0402     最大 0.1352     平均 0.0859
[OK] 平均互动率在合理区间（1%-20%）
[OK] 播放量呈长尾分布（最大值 > 平均值×10）
[OK] 外键关联完整（孤儿记录 0 条）

弹幕情感分布：正向 58.8% / 中性 30.3% / 负向 10.9%
```

**踩坑记录**：本阶段实现过程中处理了两个易错点（已在代码中规避并加测试覆盖）
- **protobuf 的 `dmid` 是 int64**：真实弹幕 ID 已超过 21 亿（int32 上限），
  手写解析器必须使用 Python 原生大整数。已加测试用例 `test_large_dmid_beyond_int32` 覆盖。
- **`progress` 字段单位是毫秒**：接口返回毫秒，而模型 `video_time` 存秒，
  转换遗漏会导致情绪波动图的横轴放大 1000 倍。已在 `_parse_danmaku_elem` 中统一 `/1000`，
  并由 `test_parse_single_danmaku` 断言（47880ms → 47.88s）。

### 阶段三交付物（2026-09-18 完成，16 个接口全部实测通过）

**新增文件**：

| 文件 | 作用 |
| --- | --- |
| `apps/analytics/services.py` | **统计服务层**：8 组聚合查询 + Redis 缓存 |
| `apps/analytics/views.py` | 8 个分析接口（含参数校验与文档注解） |
| `apps/videos/serializers.py` | 列表/详情/弹幕三套序列化器 |
| `apps/videos/views.py` | 5 个视频类接口（分页/筛选/搜索/排序） |
| `apps/ai/sentiment.py` | **可插拔情感分析**：SnowNLP/PaddleNLP + 关键词修正 |
| `apps/ai/views.py` | 情感分析接口（单条 + 批量） |
| `apps/ai/management/commands/analyze_sentiment.py` | 批量打标命令 |
| `apps/common/cache_utils.py` | 基于 SCAN 的按键模式缓存清理 |
| `apps/analytics/tests.py` | 32 个服务层测试（构造已知答案的小数据集） |
| `apps/videos/tests.py` | 31 个接口契约测试 |

**16 个接口清单**：

| 接口 | 说明 |
| --- | --- |
| `GET /api/analytics/overview/` | 总览指标 |
| `GET /api/analytics/trend/` | 播放量趋势（按天聚合） |
| `GET /api/analytics/partition-ratio/` | 分区占比（数量占比 + 播放占比双维度） |
| `GET /api/analytics/top-upusers/` | UP主排行（5 种排序维度） |
| `GET /api/analytics/top-videos/` | 视频排行（6 种排序维度） |
| `GET /api/analytics/wordcloud/` | 词云（jieba 分词 + 停用词过滤） |
| `GET /api/analytics/sentiment/` | 情感分布 + 情绪波动曲线 + 分值直方图 |
| `GET /api/analytics/interaction/` | 互动质量分析（创作者选题的核心数据） |
| `GET /api/videos/` | 视频列表（分页/筛选/搜索/排序） |
| `GET /api/videos/{bvid}/` | 视频详情 |
| `GET /api/videos/{bvid}/danmaku/` | 视频弹幕（可按情感筛选） |
| `GET /api/upusers/` | UP主列表 |
| `GET /api/partitions/` | 分区列表 |
| `POST /api/ai/analyze-sentiment/` | 文本情感分析（单条/批量） |
| `GET /api/ai/sentiment-health/` | 情感分析后端自检 |
| `GET /api/health/` | 健康检查 |

**实测结果（真实数据 200 视频 / 3000 弹幕）**：

```
总览          video_count=200  total_view=2,592,625  avg_interaction_rate=0.0859
分区占比      知识区 21% 的视频占 29.66% 播放量  ← 可看出内容效率差异
UP主排行      每日测评的猫  view_sum=309,478  avg_view=51,579.7
词云          收藏/学习/受益匪浅 等实义词进入榜单（停用词已过滤）
情感分布      正向 58.8% / 中性 25.4% / 负向 15.8%（3000 条真实分析结果）
情感性能      3000 条 / 1.7 秒 = 1780 条/秒（bulk_update 批量优化）
```

**情感分析准确率（人工标注 18 条弹幕对比）**：

```
太强了！        → 正向 (0.650)    「高燃」
有点失望        → 负向 (0.100)    「失望」
泪目了          → 正向 (0.900)    「泪目」
没看懂，求讲解   → 负向 (0.350)    ← 修正前被误判为正向 0.795
准确率 14/18 = 78%
```

> ⚠️ **准确率的局限说明**：剩下 4 例误判源于 SnowNLP 的语料偏差
> （用电商评论训练，对"画面有点糊"这类表达给出 0.773 的高分）。
> 这是模型固有问题，已通过关键词层缓解。需要更高精度时切换到
> PaddleNLP 后端（`SENTIMENT_BACKEND=paddlenlp`，需 Python 3.11/3.12）。
> **在报告中如实说明这一局限，比宣称"准确率很高"更可信。**

**本阶段发现的 3 个隐性 Bug（都值得记录）**：

| # | 问题 | 为什么危险 | 修复 |
| --- | --- | --- | --- |
| 1 | **`EXCEPTION_HANDLER` 从未注册** | 阶段一写好了自定义异常处理器，但漏配 settings，导致它**一次都没被调用**。所有错误仍以 DRF 默认的 `{"detail": ...}` 返回 | 补配 `REST_FRAMEWORK["EXCEPTION_HANDLER"]` |
| 2 | **`clear_analytics_cache()` 静默失效** | 用了 `hasattr(cache, "delete_pattern")` 判断，但 Django 内置 RedisCache **没有**这个方法 → 永远删 0 个键且不报错，爬虫跑完缓存永不刷新 | 改用基于 SCAN 的 `cache_utils.delete_pattern()` |
| 3 | **缓存键双前缀** | `cache.make_key("analytics:x")` 实际是 `biliinsight:1:analytics:x`，我手工又加了 `biliinsight:` → 键名变成 `biliinsight:1:biliinsight:analytics:x` | 去掉手工前缀，让 Django 自动处理 |

> 这 3 个 bug 有共同特征：**不报错，但功能静默失效**。
> 第 2 个是靠"清理后缓存依然命中"的测试发现的，
> 第 1 个是靠对比接口返回格式发现的。这说明
> **"接口返回 200"不等于"功能正确"**——必须写断言具体行为的测试。

### 阶段四交付物（2026-09-18 完成）

**⚠️ 首次运行前必须安装前端依赖**（我无法代跑，原因见下方说明）：

```powershell
cd "E:\deepseek harness\Biliinsight\frontend"
npm install
```

> **为什么需要你手动执行**：`npm install` 需要创建子进程与写入
> `node_modules`，而我的执行环境禁止这两类操作（`spawn EPERM`）。
> 这与之前 `pip install` 的情况相同。依赖清单已写好在 `package.json` 里，
> 你执行 `npm install` 即可。

**启动前端**：

```powershell
# 终端 1：后端（若未启动）
cd "E:\deepseek harness\Biliinsight\backend"
.\.venv\Scripts\Activate.ps1
python manage.py runserver 8000

# 终端 2：前端
cd "E:\deepseek harness\Biliinsight\frontend"
npm run dev
# 打开 http://localhost:8080
```

**28 个前端文件**：

| 目录 | 文件 | 作用 |
| --- | --- | --- |
| 根 | `package.json` | 依赖清单（Vue 3.5 / Vite 6 / Element Plus 2.9 / ECharts 5.5） |
| | `vite.config.ts` | 端口 8080 + `/api` 代理到 8000 + 手动分包 |
| | `tsconfig.json` / `index.html` | TS 配置 + 首屏加载占位 |
| `src/api/` | `request.ts` | Axios 封装：统一拆信封 + 错误分类 + 业务异常 |
| | `index.ts` | 15 个接口的集中定义（含类型） |
| `src/types/` | `index.ts` | 与后端序列化器一一对应的 TS 类型 |
| `src/utils/` | `echarts.ts` | **ECharts 按需注册**（减小体积） |
| | `chartOptions.ts` | **8 个图表配置生成器**（纯函数，可复用） |
| | `format.ts` | 数字/日期/情感配色格式化 |
| `src/components/` | `EChart.vue` | **ECharts 封装**：实例生命周期 + ResizeObserver 自适应 |
| | `StatCard.vue` | 指标卡片 |
| `src/layouts/` | `MainLayout.vue` | 侧边栏 + 顶栏（含后端健康状态指示） |
| `src/router/` | `index.ts` | 路由（**全部懒加载**） |
| `src/stores/` | `app.ts` | Pinia：健康状态 + 分区列表缓存 |
| `src/views/` | `DashboardView.vue` | **数据总览**：6 指标卡 + 趋势 + 分区占比 + UP主排行 + 热榜 |
| | `VideoListView.vue` | 视频列表：分页 + 分区筛选 + **防抖搜索** + 10 种排序 |
| | `VideoDetailView.vue` | 视频详情：基本信息 + 互动指标 + 情感分析 + 弹幕列表 |
| | `UpUserView.vue` | UP主排行：粉丝数对比图 + 排行榜表格 |
| | `SentimentView.vue` | **情感分析**：分布 + 情绪波动 + 直方图 + 词云 + **实时分析工具** |
| | `AiChatView.vue` | AI 助手：批量情感分析（阶段五接入对话式 RAG） |

**技术要点**：

| 要点 | 说明 |
| --- | --- |
| **Vite 代理解决跨域** | 前端只请求同源 `/api`，由 Vite 转发到 8000，浏览器不触发 CORS 预检 |
| **ECharts 按需注册** | 只引入折线/柱状/饼/散点 + 必要组件，而非完整包（体积从 ~1MB 降到约 1/3） |
| **路由懒加载** | 每个页面独立 chunk，首屏只下载布局 + 当前页 |
| **手动分包** | ECharts / Element Plus / 框架层拆成独立 chunk，改业务代码不会让第三方库缓存失效 |
| **ResizeObserver 自适应** | 侧边栏折叠、窗口缩放都能正确重绘（`window.resize` 捕捉不到容器变化） |
| **`shallowRef` 存图表实例** | ECharts 实例含大量循环引用，用 `ref` 深度响应式化会严重卡顿 |
| **搜索防抖 400ms** | "数据分析"四个字否则会触发 4 次请求 |
| **`Promise.all` 并行请求** | 总览页 6 个接口并行，总耗时取决于最慢而非累加 |
| **词云零依赖实现** | 用散点图 + 标签模拟词云（黄金角螺旋布局，可复现），避免引入 `echarts-wordcloud` |
| **双 Y 轴趋势图** | 播放量（百万级）与视频数（个位）量级差距大，共轴会让后者贴底不可见 |
| **情感曲线固定 Y 轴 0-1** | 若自动缩放，平稳曲线会被放大成剧烈波动，造成误读 |

**已验证**：

| 验证项 | 结果 |
| --- | --- |
| 前端将调用的 15 个接口 | ✅ 全部 HTTP 200 且有数据 |
| `package.json` / `tsconfig.json` 语法 | ✅ 通过 |
| 10 个 `.vue` 文件标签配对 | ✅ 通过 |
| 10 个 `.vue` 的 `<script setup>` TS 语法 | ✅ 通过（Node 24 原生检查） |
| 8 个独立 `.ts` 文件语法 | ✅ 通过 |
| `npm install` + `npm run dev` | ✅ **用户实测通过**（105 个包，Vite 1.07s 启动） |
| 5 个页面浏览器实测 | ✅ **全部正常渲染**，图表与接口数据一致 |

**浏览器实测核对（2026-09-18）**：

| 页面 | 核对结果 |
| --- | --- |
| 数据总览 | 6 指标卡数值与接口一致；趋势图 14 个柱高与接口 `video_count` 逐项吻合（3,6,8,6,4,2,8,7,3,11,5,11,7,3）；分区环形图、UP主横向柱状图正常 |
| 视频数据 | 200 条分页正确；封面、时长格式化（30:14 / 01:34）、互动率标签、分区标签均正常 |
| UP主排行 | 40 位；粉丝数降序正确；状态标签（作品较多/少量收录）正常 |
| 情感分析 | 3000 条分布（正向 58.8% / 中性 25.4% / 负向 15.8%）+ 情绪标签 + 波动曲线（含 0.5 中性参考线）正常 |
| AI 助手 | 批量分析输入区与后端状态标签（snownlp）正常 |

**实测中发现并修复的 1 个逻辑缺陷**：

| 问题 | 为什么危险 | 修复 |
| --- | --- | --- |
| UP主页「粉丝数对比」图表取**当前页**数据 | 翻到第 2 页时图表显示的是第 21-30 名的粉丝数（第 1 名仅 13,720），**但标题仍写"粉丝数对比"，用户会误以为是全局排行** | 改为固定调用 `analytics/top-upusers/?order_by=follower_count` 取**全库 Top 10**，与表格分页彻底解耦 |

> 这个问题说明：**"图表能画出来"不等于"图表表达正确"**。
> 数据本身没算错，但取数范围与图表标题的语义不匹配，
> 属于典型的"静默误导"。核对方式是：翻到第 2 页看图表是否变化——
> 全局排行不该随分页变化。

### 阶段五交付物（2026-09-18 完成，RAG 全链路实测通过）

**新增文件**：

| 文件 | 作用 |
| --- | --- |
| `apps/ai/embedding.py` | **可插拔向量化**：Ollama / DashScope / 本地 TF-IDF+SVD |
| `apps/ai/vector_store.py` | ChromaDB 封装：建索引、语义检索、元数据过滤 |
| `apps/ai/llm.py` | **LLM 工厂**：Ollama / 通义千问 / 检索式兜底 |
| `apps/ai/rag.py` | **RAG 编排**：意图识别 → 检索 → Prompt → 生成 → 溯源 |
| `apps/ai/views.py` | 对话/状态/索引/历史接口（含 **SSE 流式**） |
| `apps/ai/management/commands/build_index.py` | 索引构建命令（含检索自检） |
| `apps/ai/tests.py` | **40 个测试**（向量化、意图、Prompt、检索、降级、接口） |
| `frontend/src/views/AiChatView.vue` | 重写为**流式对话界面**（含引用溯源） |
| `frontend/src/api/request.ts` | 新增 `postStream()`：fetch + ReadableStream 解析 SSE |

**新增 6 个接口**：

| 接口 | 说明 |
| --- | --- |
| `POST /api/ai/chat/` | RAG 对话（SSE 流式 / 普通 JSON 双模式） |
| `GET /api/ai/status/` | RAG 链路状态（索引 + 大模型） |
| `POST /api/ai/build-index/` | 重建向量索引 |
| `GET /api/ai/history/` | 历史会话列表 |
| `GET /api/ai/history/{id}/` | 会话消息记录 |
| （阶段三已有 2 个情感分析接口） | |

**实测结果**：

```
索引构建    200 条视频 / 2.04 秒 / 199 维向量

检索自检：
  「科技区的芯片评测」→【国产芯片】深度评测｜第10期    相似度 0.709
  「美食做饭教程」    →【火锅】做法详解｜第24期        相似度 0.499
  「游戏攻略」        →【像素游戏】全成就攻略｜第57期  相似度 0.815

对话（非流式）：检索 3 条科技区视频，带 bvid / 相似度 / 播放量 完整溯源
对话（SSE）：21 帧，meta → 逐段 chunk → done，意图识别为 recommend
历史记录：会话与消息正确落库，404 返回统一格式
测试套件：144/144 通过
```

**四种向量化后端对比（可插拔设计的价值）**：

| 后端 | 语义能力 | 依赖 | 适用场景 |
| --- | --- | --- | --- |
| `ollama` | ⭐⭐⭐ 真语义 | 需 Ollama 服务 + 嵌入模型 | 效果最好且可离线 |
| `dashscope` | ⭐⭐⭐ 真语义 | 需 API Key + 外网 | 云端最佳效果 |
| **`local`（默认）** | ⭐ 词法匹配 | **零依赖** | 开箱即用、确定性、答辩保底 |
| `fallback`（LLM） | — | 零依赖 | 无大模型时用真实数据组织回答 |

**关键设计决策**：

| 决策 | 理由 |
| --- | --- |
| **默认用本地 TF-IDF+SVD 而非外部模型** | 本项目已两次踩"依赖不可用"的坑（paddlenlp 装不上、Ollama 未启动）。AI 是核心加分项，**绝不能因为外部服务没起来就整体失效**。本地后端向量只需构建一次并持久化，之后检索零外部依赖 |
| **LLM 三级降级**：ollama → dashscope → fallback | 调用方永远拿得到可用实例，不用写一堆 `if`。`fallback` 用检索到的**真实数据**组织回答，并明确标注"未接入大模型"——不欺骗用户，也不让功能空白 |
| **不用 LangChain 的 LLM 封装** | `langchain-community` 已官方标记 sunset（导入即打弃用警告）。我们只需"发请求 + 收流"两件事，直接调 REST 更短、更透明、少一层失效环节 |
| **SSE 用 fetch 而非 EventSource** | 浏览器原生 `EventSource` 只支持 GET 且不能带请求头，无法发送 JSON 体。必须用 `fetch` + `ReadableStream` 手动解析 SSE 协议 |
| **Prompt 明确约束"仅依据参考资料"** | 这是抑制幻觉的关键。同时要求标注 `[1] [2]` 引用编号，使回答可溯源 |
| **要求"不要输出思考过程"** | 本机装的 `deepseek-r1:8b` 是推理模型，会把思维链一起吐出来，对终端用户是噪声 |
| **检索结果先于正文推送（meta 帧）** | 前端可在正文出现前就渲染"参考来源"区域，避免先看文字再看来源的割裂感 |
| **切换向量后端后强制 rebuild** | TF-IDF 的 IDF 依赖全量语料，且不同后端维度可能不同。增量追加会让新旧向量处于不同语义空间，检索结果混乱。命令中已做检测并拒绝不一致的增量构建 |

**诚实的局限说明**：

> 默认的 `local` 后端是**词法匹配，不是语义理解**：
> 「芯片」能匹配「芯片」，但匹配不到「半导体」。
> 它适合演示与开发；要真正的语义检索，请切换 `EMBEDDING_BACKEND=ollama`
> 并 `ollama pull bge-m3`，然后 `python manage.py build_index --rebuild`。
>
> 本项目已实测：切换后需重建索引，否则检索结果会因语义空间不一致而混乱
> （命令中已内置检测与提示）。

**本阶段发现的 1 个会导致功能完全不可用的 Bug**：

| 问题 | 现象 | 修复 |
| --- | --- | --- |
| 给 SSE 响应设置了 `Connection: keep-alive` | 该头是 **HTTP 逐跳头（hop-by-hop）**，WSGI 规范禁止应用设置，`wsgiref` 直接抛 `AssertionError`，**流式接口整体 500** | 移除该头。`Cache-Control` 与 `X-Accel-Buffering` 可以保留（后者用于告诉 Nginx 不要缓冲） |

> 这个 bug 的特点：**只在触发流式请求时才暴露**，
> 普通的 JSON 接口完全正常。是靠实际发一个 `stream=true` 请求才发现的——
> 又一次印证"接口能返回 200"不等于"功能可用"。
>
> 另外测试中发现 ChromaDB **无法在系统临时目录**打开数据库
> （`error code: 14 unable to open database file`），
> 必须放在项目目录内。测试里已改用 `backend/data/_test_chroma_*` 并在 tearDown 清理。

### 阶段六：体验修复（2026-09-27 完成）

上线试用后收集到 4 个痛点，本轮修复前 3 个（第 4 个待排期）。

**痛点 1：数据可信性 —— 根因是当前全是模拟数据**

排查发现数据库里 **200 条视频全部是 `seed_demo` 生成的模拟数据**，
其 bvid 是随机串（如 `BV5j14cx2nqu`），**在B站根本不存在**，
所以搜索不到。这解释了"爬取的数据可信性丢失"的困惑。

修复（方案 A + B）：

| 方案 | 实现 |
| --- | --- |
| **A. 明确标注** | 新增 `Video.is_demo` 字段（迁移 `0002`）+ 索引；序列化器暴露 `is_demo` / `data_source` / `source_url`；前端在列表、详情、看板三处显示「模拟数据」标签 |
| **B. 抓真实数据** | 提供 `crawl` 命令；`is_demo=False` 的数据标题可点击跳B站核对。原本的风控冷却后即可抓取 |
| **辅助** | 新增 `mark_data_source` 命令修正历史数据（旧数据默认被当成真实数据），并可按分区查看真实/模拟比例 |

**关键设计：模拟数据不显示跳转入口**

给用户一个点不通的按钮**比不给更糟**——会让人以为系统坏了。
因此 `is_demo=True` 时：
- 标题不渲染成链接
- 「原站」按钮禁用并给出 tooltip 说明原因
- 详情页顶部显示醒目告警，附上抓取真实数据的命令

**痛点 2：跳转B站链接**

| 位置 | 改进 |
| --- | --- |
| 列表页标题 | 真实数据**点标题直接跳B站**（外链样式：默认正文色，悬浮变蓝加下划线，避免整表被蓝色淹没） |
| 列表页操作列 | 「原站」+ 新增「复制」按钮；模拟数据的「原站」禁用并提示 |
| 详情页 | BV 号可点击复制；「观看原视频」+「复制链接」；模拟数据额外显示告警 |
| 看板热榜 | 标题同样支持外链 |
| AI 助手引用来源 | 已支持点击跳转（沿用） |

**痛点 3：点详情后 2 秒弹回列表（真 bug）**

```diff
- // 视频不存在时给出明确提示并返回列表
- if (!v) {
-   setTimeout(() => router.replace({ name: 'videos' }), 1500)
-   return
- }
+ // 视频不存在时停留展示错误页，不自动跳转
+ if (!v) {
+   notFound.value = true
+   loadError.value = `数据库中找不到视频 ${bvid.value}`
+   return
+ }
```

**为什么自动跳转是错误设计**：
1. 用户正在读错误提示，页面突然跳走，体验很差
2. 无法判断是"数据没了"还是"点击出错"，也来不及复制错误信息排查

改为停留展示：`el-result` 错误页 + **可能原因列表**（含"演示数据重建后 bvid 会变化"这条）+ 「返回列表 / 重试」按钮。

**顺带修掉一个隐藏隐患：bvid 不确定**

排查痛点 3 时发现：`seed_demo` 的 bvid 用 `random` 生成，
**每次重建都会变**，导致前端缓存的旧链接全部失效——
这正是"弹回列表"的深层原因之一。

```python
# 改为基于索引的确定性哈希
digest = hashlib.md5(f"biliinsight-demo-{index}-{salt}".encode()).hexdigest()
```

⚠️ **不能用内置 `hash()`**：它对字符串加随机盐（`PYTHONHASHSEED`），
每次进程启动结果都不同，无法用于确定性生成。已加测试固化这一约定。

**本轮验证**：

```
数据重建 2 次，前 3 个 bvid 完全一致  ✅ 确定性验证通过
is_demo 标记         200/200 全部正确
接口字段             is_demo / data_source / source_url 均返回
RAG 状态             LLM=deepseek  索引=200  ready=True
测试套件             161/161 通过（本轮新增 10 个）
```

---

#### 阶段六补：真实数据抓取成功（2026-09-27）

痛点 1 的**方案 B 已落地**——数据库里现在有真实可核对的B站数据。

**怎么解决风控的：换网络环境**

前面实测确认风控按 **IP 维度**统计，而且当时那台机器的出口 IP
已经因为反复尝试进入长冷却。**改用手机热点后，新 IP 没有风控记录，
第一次请求直接成功。**

**关键认知：成本按「请求次数」计，不按「视频条数」计**

这是本轮最有价值的发现。翻代码确认 `run_partition()` 只调用一次
`fetch_ranking()`，排行榜接口**一次返回 97 条**，`--limit` 只是入库上限：

```python
# apps/spider/bilibili.py
def run_partition(self, partition_name, limit=50):
    payload = self.fetch_ranking(tid)      # ← 整个方法只有这 1 次 HTTP 请求
    items = parsers.parse_video_list(payload)   # 97 条
    return self._save_videos(items, limit=limit)  # 纯本地入库，不再发请求
```

所以：

| 命令 | HTTP 请求 | 拿到数据 |
| --- | --- | --- |
| `--limit 30` | **1 次** | 30 条 |
| `--limit 100` | **1 次** | **97 条** |

**同样的风控代价，后者数据量是前者的 3 倍。** 在风控敏感的场景下，
应该一次把 `--limit` 开到接口能返回的上限，而不是保守地取小值。

**执行的命令与结果**：

```bash
python manage.py crawl --partition 科技 --limit 100 --interval 5
```

```
分区 科技：解析 97 条，新增 97 条，更新 0 条
HTTP请求 : 1 次
```

入库结果：

| 分区 | 条数 |
| --- | --- |
| 数码 | 64 |
| 计算机技术 | 11 |
| 科工机械 | 11 |
| 软件应用 | 7 |
| 极客DIY | 4 |

真实数据 TOP 3（**BV 号可在B站直接搜索核对**）：

| bvid | 标题 | 播放 | UP主 |
| --- | --- | --- | --- |
| `BV1kCoxYZEAc` | 小学生拿到新电脑VS大学生拿到新电脑 | 8,014,165 | 黑客老K |
| `BV15FZGYyEdc` | 好文采！这篇作文听着听着眼前就全是风景😭 | 7,334,669 | 共青团中央 |
| `BV1bMo4YrEBC` | 平板/旋转/履带/滚筒，哪种扫地机拖布能真正拖干净！？ | 4,289,387 | 哏工侃智能 |

**收尾动作**：

```bash
python manage.py build_index --rebuild   # 索引 200 -> 297 条，2.03 秒
```

**全链路复验**（直接请求后端 API，模拟前端调用）：

```
/api/videos/?ordering=-view_count
  BV1kCoxYZEAc | data_source=real | is_demo=False
  link -> https://www.bilibili.com/video/BV1kCoxYZEAc        ✅

/api/analytics/top-videos/?limit=3&order_by=view_count
  is_demo=false  data_source=real  source_url 均已透出        ✅

/api/analytics/overview/
  video_count=297  upuser_count=137  partition_count=10
  total_view=98,667,090  avg_interaction_rate=0.0758          ✅
```

**遗留说明**：本地 TF-IDF 向量化是**词法匹配**，检索自检时
「科技区的芯片评测」仍会命中模板化的模拟数据标题（相似度 0.636）——
模拟数据的标题由模板批量生成，关键词密度天然更高。
启用语义后端（`ollama` / `dashscope`）可缓解，已在第七章说明。

---

#### 阶段六补 2：分析类页面"没同步"的三个真实 Bug（2026-09-27）

抓完真实数据后，用户反馈：

> 视频数据是同步了，但 UP主排行、情感分析、数据总览好像并没有同步

排查后发现**不是数据没同步，而是三个独立缺陷**。
其中一个是很隐蔽的缓存 Bug，值得完整记录。

##### Bug 1：写完数据不清分析缓存（影响最大）

**现象**：视频列表立刻变新，分析类页面却保持旧值。

**根因**：`clear_analytics_cache()` 的文档字符串写着
> 用途：爬虫跑完后调用……在 Celery 任务成功结束时触发（见 `apps/spider/tasks.py`）

但 `apps/spider/tasks.py` 里**从来没有调用过它**。
`grep` 全仓库只有 4 处调用，全在测试和 `ai/views.py` 里。
**注释描述的是意图，不是事实** —— 这个缺口因此长期没有被发现。

于是两条写入路径全部漏清缓存：

| 路径 | 是否清缓存 |
| --- | --- |
| `/api/videos/` 列表、详情 | 无缓存，所以立刻生效 ✅ |
| `/api/analytics/overview/` | 缓存 300s，未清 ❌ |
| `/api/analytics/top-upusers/` | 缓存 600s，未清 ❌ |
| `/api/analytics/sentiment/` | 缓存 600s，未清 ❌ |

**修复**（一处覆盖全部任务，避免以后再漏）：

```python
# apps/spider/tasks.py -> _finish_task()
# 放在公共收尾里，5 个 Celery 任务自动全部获得该行为
if task.status == "success" and (task.total_created or task.total_updated):
    try:
        from apps.analytics.services import clear_analytics_cache
        clear_analytics_cache()
    except Exception as exc:
        # 清缓存失败绝不能影响"抓取成功"这个事实
        logger.warning("清理分析缓存失败（不影响抓取结果）：%s", exc)
```

同步路径各自补上（`crawl` / `seed_demo` / `mark_data_source`），
并修正了 `clear_analytics_cache` 那句失实的文档字符串。

**这个 Bug 有多隐蔽**：修复过程中实测到一条过期缓存
**跨过了后端进程重启**依然存活（Redis 里的 TTL 没到期），
所以"重启一下试试"这种常规排查手段对它无效。

##### Bug 2：UP主排行硬编码了拿不到的字段

`UpUserView.vue` 第 101 行把排序**硬编码**为粉丝数：

```ts
// 修复前
() => analyticsApi.topUpusers({ limit: 10, order_by: 'follower_count' }),
```

而 **B站排行榜接口不返回 UP主 粉丝数**，
所以真实抓取入库的 97 位 UP主，`follower_count` 全部是 `0` ——
按粉丝数排序时永远排不上榜，图表里一个真实 UP主 都没有。

而作品总播放量（`view_sum`）是由 `videos` 表实时聚合的，
真实数据一入库就有值。验证：把排序换成 `view_sum` 后，
**Top 10 立刻全部变成刚抓的真实 UP主**（黑客老K、共青团中央、影视飓风……）。

```diff
- const globalTop = ... order_by: 'follower_count'
+ const chartMetric = ref<'view_sum' | 'follower_count'>('view_sum')
+ watch(chartMetric, loadGlobalTop)
```

修复为**可切换指标**，默认「作品总播放量」，
并在选到粉丝数时给出如实提示（有多少位 UP主 缺该字段、为什么缺）。

##### Bug 3：数据来源提示条按"榜单前 10 条"估算比例

`DashboardView.vue` 原本这样判断数据来源：

```ts
const items = topVideos.value?.items ?? []      // 只有 10 条
const demoCount = items.filter((v) => v.is_demo).length
if (demoCount === 0) return null               // 不显示任何提示
```

抓回真实数据后，播放量最高的前 10 条恰好全是真实数据，
于是 `demoCount === 0` → **提示条整个消失** ——
而库里其实还有 **200 条模拟数据**。
用户会因此以为数据已全部同步成真实的。

修复：`/api/analytics/overview/` 补上全库准确计数，
前端改用真实计数而非 10 条样本。

```python
# apps/analytics/services.py -> get_overview()
"real_videos": real_videos,      # 97
"demo_videos": demo_videos,      # 200
"real_ratio": round(real_videos / video_count, 4),   # 0.3266
```

修改后提示条如实显示：

> 混合数据：97 条真实抓取 + 200 条模拟数据（共 297 条）

##### 本轮验证

```
新增回归测试                    8 + 1 = 9 个
完整测试套件                    170/170 通过
manage.py check                 no issues
Vite 编译（三个改动文件）         全部通过
/api/analytics/overview/        real_videos=97 demo_videos=200 real_ratio=0.3266
```

##### 遗留：一个"数据源能力边界"（不是 Bug）

| 页面 | 现状 | 原因 |
| --- | --- | --- |
| UP主 粉丝数 | 真实 UP主 全为 `0` | B站排行榜接口不返回粉丝数，需逐位补抓（`x/relation/stat`，97 次请求），**已决定暂不补** |

已按如实标注处理（界面提示缺字段原因 + 默认改用「作品总播放量」排名），
属于数据源客观限制下的取舍，而非缺陷。

---

#### 阶段六补 3：补抓真实弹幕，情感分析接入真实数据（2026-09-27）

修复 Bug 1 之后，情感分析的数字**依然没变** —— 因为它不是缓存问题：
**3000 条弹幕全部来自模拟视频**，真实视频只有 `danmaku_count` 计数，
没有任何弹幕内容。要让它有真实数据，只能逐视频补抓。

##### 选片策略：优先"时长短 × 弹幕密集"

弹幕接口按 **6 分钟一包** 返回，因此请求次数由**视频时长**决定，与弹幕总量无关：

| 视频 | 时长 | 弹幕量 | 分包数 | 实际请求 |
| --- | --- | --- | --- | --- |
| `BV11PZsY8EtB` 脑机接口 | 165s | 39,319 | 1 | **2** |
| `BV13bZpYvEDr` 81192 | 49s | 4,089 | 1 | **3** |
| `BV15tZPYWEUh` OPPO开箱 | 434s | 3,703 | 1 | **2** |
| `BV1tnZqYTEx6` 手机续航横评 | 1190s | 9,090 | 2+ | **2** |
| `BV11eZ8YLEZ6` 再见Switch | 1082s | 4,495 | 2+ | **2** |

**结论：挑"短视频"比挑"弹幕多的视频"更省请求。**
39,319 条弹幕的视频只要 2 次请求（因为它只有 165 秒，一包到底）。

##### 一个容易误解的参数

`--limit` **不是严格的条数上限**，它只在**包与包之间**做判断：

```python
for segment in range(1, max_segments + 1):
    if collected >= limit:      # 只在换包时检查
        break
    items = parse(raw)          # 整包全部入库
    upsert_danmaku(video, items)   # 不受 limit 约束
    collected += len(items)
```

所以 `--limit 50` 的实际语义是「**只抓一包就停**」——
一包里的几万条弹幕会全部入库。
用它把请求数压到最低（每视频 2 次：1 次取 cid + 1 次取弹幕包）。

##### 执行结果

```
5 个视频全部一次成功，零风控
共入库真实弹幕 1216 条（真实 1216 / 模拟 3000，总 4216 条）
HTTP 请求合计 11 次
```

**真实弹幕一眼可辨**（对比模拟数据的模板文本）：

| 来源 | 样例 |
| --- | --- |
| **真实** | 「愿人类荣光永存」「小时候看这集给relic看故障了」「加入光荣的进化吧！」「刀剑神域沉浸式体验我来了」「博士，简直是个天才」 |
| 模拟 | 「已三连」「看哭了哈哈」「好久不见」「更新了」 |

真实弹幕里出现 `relic`（赛博朋克 2077）、`刀剑神域`、`哈夫克` 等**社区梗**，
这是模板生成的数据不可能有的——最直观的真实性证据。

##### 情感标注与效果

```bash
python manage.py analyze_sentiment        # 1216 条，耗时 1.1 秒，1110 条/秒
```

| 指标 | 数值 |
| --- | --- |
| 总标注弹幕 | 4,216 条 |
| 正向 / 中性 / 负向 | 55.38% / 29.70% / 14.92% |
| 真实视频 `BV11PZsY8EtB` | 182 条，正向 60.99% / 中性 24.18% / 负向 14.84% |

真实视频现在有了**完整的情感曲线**（按播放进度分段）与情绪标签
（疑问 33 / 高燃 7 / 打卡 5 / 惊叹 4 / 搞笑 1）。

**如实说明一个准确率问题**：snownlp 对**网络口语与反讽**判断不佳，例如

```
「这不是水管，这是大动脉啊」      -> 判为 negative（实为夸赞）
「和OPPO官号的爆料一起发啊」      -> 判为 negative（实为普通陈述）
```

真实弹幕比模板文本更口语化，因此**准确率会比模拟数据上略低**。
这是所选情感模型的固有局限（`SENTIMENT_BACKEND` 可切换到
`paddlenlp` 的 SKEP 模型改善，但需 Python 3.12 环境，见 7.5 节）。

##### 顺带印证了 Bug 1 的修复

抓第一条弹幕时命令输出：

```
弹幕 BV11PZsY8EtB：解析 182 条，新增 182 条，更新 0 条
HTTP请求 : 2 次
已清分析缓存 : 3 个键        ← 修复自动生效
```

`analytics:*` 与 `sentiment:*` 被自动清掉，
**不再需要手动清缓存**，情感分析页面立刻显示新数据。

##### 本轮验证

```
完整测试套件        170/170 通过
弹幕归属            真实 1216 / 模拟 3000
/api/analytics/sentiment/           total=4216  analyzed=4216
/api/analytics/sentiment/?bvid=…    单视频曲线与标签均正常
/api/analytics/wordcloud/           6423 词 / 1787 独立词，含真实弹幕词
```

---

#### 阶段六补 4：抓取能力增强 —— 封面 / 粉丝数 / 弹幕（2026-09-27）

需求：**以后抓取要同时拿到视频封面、UP主 粉丝数、弹幕。**

先说结论：**封面本来就在抓，但界面上显示不出来**（防盗链），
粉丝数是**真的缺**，弹幕已有能力但需要整合进主流程。

##### ① 视频封面：抓到了，但被图床防盗链挡住

排查发现封面其实早就解析并入库了
（`parsers.py` 里 `pic -> cover_url`，前端列表页与详情页也都在渲染），
数据库里 97 条真实数据的 `cover_url` 全部非空。

但用浏览器打开就是裂图。实测 B站图床的 Referer 规则：

| 请求头 | 结果 |
| --- | --- |
| 无 Referer | ✅ HTTP 200 |
| `Referer: http://localhost:8080/` | ❌ **HTTP 403** |
| `Referer: https://www.bilibili.com/` | ✅ HTTP 200 |

浏览器从本项目加载图片时会自动带上 `Referer: http://localhost:8080/`，
于是**所有封面与 UP主 头像都被 403 拦掉**。

> ⚠️ 这个 Bug 在数据库层面完全看不出来 ——
> 字段有值、URL 格式正确、长度正常。
> **只有真的用浏览器打开才会暴露。**

修复（双保险）：

```html
<!-- frontend/index.html：一行解决所有图片（封面 + 头像） -->
<meta name="referrer" content="no-referrer" />
```

```vue
<!-- 图片标签上再加一次，防止将来有人删掉 meta -->
<el-image :src="row.cover_url" referrerpolicy="no-referrer" />
```

##### ② UP主 粉丝数：新增独立抓取能力

**为什么必须单独请求**：B站排行榜接口的 `owner` 字段只有
`mid / name / face`，**不返回粉丝数**。
所以要让「UP主排行」按粉丝数排得动，只能逐个 UP主 调
`/x/relation/stat?vmid={mid}` —— **1 位 UP主 = 1 次请求**。

这是本项目最"贵"的一项抓取，因此做了三重节省：

| 节省手段 | 说明 |
| --- | --- |
| **按 mid 去重** | 同一 UP主 只请求一次（一个 UP主 可能有多条视频） |
| **跳过已有值** | `follower_count > 0` 的直接跳过 |
| **可限额** | `--followers-limit N` 控制本次最多补几位 |

实测结果（40 位 UP主，全部一次成功）：

| UP主 | 粉丝数 |
| --- | --- |
| 影视飓风 | 18,424,395 |
| 共青团中央 | 12,168,644 |
| -欣小萌- | 5,991,621 |
| 极客湾Geekerwan | 5,567,503 |
| 小白测评 | 4,722,057 |

##### ③ 弹幕：整合进主流程 + 用 cid 省掉一半请求

弹幕抓取本来就有（`--danmaku BV...`），这次做的是**整合与优化**。

**关键优化：把 cid 存进数据库**

翻代码时发现一件可惜的事：
`parsers.py` 第 111 行**已经解析了**排行榜响应里的 `cid`：

```python
cid=safe_int(raw.get("cid")) or None,   # 排行榜本来就返回 cid
```

但 `Video` 模型**没有 cid 字段**，于是这个值被直接丢掉了。
而抓弹幕必须用 cid，早期实现只能为每个视频**再请求一次详情接口**。

新增 `Video.cid` 字段（迁移 `0003`）之后：

| 方案 | 抓 40 个视频的弹幕所需请求 |
| --- | --- |
| 旧：逐视频取详情 | 40（取 cid）+ 40（取弹幕）= **80 次** |
| 新：复用已存 cid | 1（排行榜回填全部 cid）+ 40（取弹幕）= **41 次** |

**一次请求换掉 39 次请求。** 在风控严格的环境下这是很可观的节省。

```python
# apps/spider/bilibili.py -> run_danmaku()
# 优先用库里已存的 cid，只有缺失时才回落到详情接口
cid = video.cid if (video is not None and video.cid) else None
if cid is None:
    cid = self._fetch_cid(bvid)
```

##### ④ 新增两个命令

**`reset_data` —— 安全地推倒重来**

```bash
python manage.py reset_data           # 只预览，不删（安全）
python manage.py reset_data --yes     # 确认清空
```

删除顺序很关键，因为外键是级联的：

```
UpUser --CASCADE--> Video --CASCADE--> Danmaku
```

**先删 UP主 会把视频和弹幕一起带走**；只删 Video 又会留下
"没有任何视频的孤儿 UP主"，干扰 UP主排行。
所以命令显式按 `Danmaku -> Video -> UpUser` 删除，
并顺手清掉两处派生数据：**分析缓存**（否则看板显示已删数据的统计值）
与 **向量索引**（否则 AI 会引用已不存在的视频）。

**`scripts/patient_crawl.py` —— 在风控下长期磨数据**

进度直接存在数据库里（待补粉丝数 = `follower_count == 0`；
待抓弹幕 = 没有关联 Danmaku），所以**随时可以 Ctrl+C 或被杀掉，
下次运行自动从断点继续**，不需要额外的进度文件。

自适应退避：命中风控 -> 冷却拉长（×1.5，有上限）；
连续成功 10 次 -> 冷却缓慢回落。

##### ⑤ 修正之前对风控节奏的判断

阶段六补 2 里我根据一次现象推断"每 30 分钟只能发 12 次请求"。
本轮拿到更完整的数据后，这个结论**下得太早了**：

| 时间 | 请求 | 结果 |
| --- | --- | --- |
| 15:53:20 | 粉丝数第 1 次 | ❌ -352 |
| 15:54:52 | 同一请求重试（**仅隔 1.5 分钟**） | ✅ 成功 |
| 15:54:52→15:56:49 | **连续 40 次**（间隔 3 秒） | ✅ **全部成功** |
| 15:56:51 | 排行榜请求 | ❌ -352 |

**修正后的结论**：

1. 风控是**短时突发限制**，命中后**等 1-2 分钟通常就能恢复**，
   不是 30 分钟级的长冷却；
2. 只要**间隔 ≥ 3 秒、顺序发送**，连续 40 次请求可以稳定通过；
3. **不同接口的额度可能不同** —— 40 次 `/x/relation/stat` 通过后，
   紧接着的 `/web-interface/ranking/v2` 被拦，说明排行榜接口更敏感
   （或者总请求数在跨接口累计）。

因此 `patient_crawl.py` 的初始冷却定为 **2 分钟**（而非 30 分钟），
命中后按 ×1.5 升级，上限 30 分钟 —— 恢复快，又不会硬撞。

##### ⑥ 途中挖出的三个隐蔽 Bug

这一段的排查过程比预想的曲折，三个 Bug 都很值得记录。

**Bug A：弹幕接口的风控响应被当成了"这个视频没有弹幕"**

抓 40 个视频的弹幕时，前 21 个正常，**后 19 个全部返回 0 条**，
日志里只有一句莫名其妙的：

```
弹幕 protobuf 解析中断：不支持的 wire_type=3（已解析 0 条）
```

`wire_type=3` 是 protobuf 早已废弃的"分组"类型，正常的弹幕数据不可能出现。
但把**同样的 cid** 稍后手动请求一次，就正常解析出 112 条。

于是直接把响应的原始字节打出来看：

```
响应字节数 : 39
前 16 字节 : 7b22636f6465223a2d3335322c226d65
```

`0x7B` 是 `{` —— 这段"数据"解开就是：

```json
{"code":-352,"message":"请求过于频繁，请稍后再试"}
```

**根因**：弹幕接口是**二进制协议**，调用时传了 `expect_json=False`，
于是这段 JSON 错误体**绕过了 `BaseSpider` 里所有的业务码检查**
（包括限流识别），被原样交给 protobuf 解析器。

**后果比看起来严重**：

| 影响 | 说明 |
| --- | --- |
| 静默误判 | 19 个视频被判成"没有弹幕"，日志里看不出真实原因 |
| 白耗额度 | 每个视频都实打实花了 1 次请求额度 |
| **重跑也无法自愈** | 因为根因不是数据，重跑依然失败，很容易被误认为"这些视频就是没弹幕" |

**修复**：在拿到原始字节后加一道特征检查 ——
正常弹幕数据是二进制，而 **JSON 错误体一定以 `{` 开头**：

```python
# apps/spider/bilibili.py -> _guard_danmaku_payload()
if raw[:1] == b"{":
    code = json.loads(...).get("code")
    if code in self.RATE_LIMIT_CODES:
        raise RateLimitedError(f"接口返回 {code}（弹幕分段），触发目标站点风控")
    raise SpiderError(f"弹幕接口返回了非预期内容（不是 protobuf）：...")
```

修好后，19 个视频全部抓到弹幕，且限流能被节奏控制器正确退避。

**Bug B：CDN 偶发漏发 Content-Encoding，压缩字节被当 protobuf 解析**

排查 Bug A 的过程中还发现另一种失败形态。
按 gzip / zlib 魔数识别并自行解压即可兜住，避免白花额度：

```python
# apps/spider/parsers.py -> _maybe_decompress()
if data[:2] == b"\x1f\x8b":      # gzip 魔数
    return gzip.decompress(data)
if data[0] == 0x78 and data[1] in (0x01, 0x5E, 0x9C, 0xDA):   # zlib 头
    return zlib.decompress(data)
```

**Bug C：`distinct()` 被 `Meta.ordering` 悄悄破坏**

回填 cid 时按分区去重，本该得到 5 行，实际返回了 **40 行**（一视频一行），
白白多发 35 次请求。这是 Django 的已知陷阱：

> `order_by()` 里用到的字段会被**加进 SQL 的 SELECT 列**，
> 与 `distinct()` 一起使用时会导致去重失效。

```python
# 修复：先 .order_by() 清空排序，再 distinct
Video.objects.filter(...).order_by().values_list(...).distinct()
```

**Bug D：子分区名不在常量表里**

入库时存的是 B站返回的**细分**分区名（`数码` / `极客DIY` / `科工机械`…），
这些名字不在 `constants.PARTITIONS` 对照表里，
用名字去查排行榜会直接报"无法识别的分区名"。
改为直接使用库里存的数字 `bili_tid`。

##### ⑦ 修正对风控的判断：不同接口的配额不一样

阶段六补 2 里我根据单次现象推断"每 30 分钟只能发 12 次请求"，
本轮拿到更完整的数据后，这个结论**下得太早了**：

| 时间 | 接口 | 请求量 | 结果 |
| --- | --- | --- | --- |
| 15:54:52→15:56:49 | `/x/relation/stat` | **连续 40 次** | ✅ 全部成功 |
| 16:00 / 16:02 / 16:04 | `/ranking/v2` | 各 1 次 | ❌ 全部 -352 |
| 15:53:20 | `/x/relation/stat` | 1 次 | ❌ -352（**1.5 分钟后再试就通了**） |
| 16:04→16:06 | `/dm/web/seg.so` | **21 次** | ✅ 成功 |
| 16:06 之后 | `/dm/web/seg.so` | 连续多次 | ❌ -352 |

**修正后的结论**：

1. 风控是**短时突发限制**，命中后等 1-5 分钟通常即可恢复，
   不是 30 分钟级的长冷却；
2. 只要**间隔 ≥ 3 秒、顺序发送**，连续几十次请求可以稳定通过；
3. **各接口配额差异很大**：`relation/stat` 宽松（40 次无阻），
   而 `ranking/v2` 在同一时段持续被拦、
   `dm/web/seg.so` 大约 21 次后开始限流。
4. 因此"被风控了"要区分是**哪个接口**被风控，
   换接口往往还能继续抓。

`patient_crawl.py` 的初始冷却因此定为 **2 分钟**（弹幕场景用 5 分钟），
命中后按 ×1.5 升级，上限 30 分钟。

##### 本轮验证

```
完整测试套件            185/185 通过（本轮新增 15 个）
manage.py check         no issues
```

**达标验证（用户提出的三项）**

| 要求 | 结果 |
| --- | --- |
| ① 视频封面 | `cover_url` 非空 **40/40**；UP主 头像非空 **40/40**；防盗链修复后实测 **403 → 200**（277KB 正常图片） |
| ② UP主 粉丝数 | 粉丝数 > 0 的 UP主 **40/40** |
| ③ 弹幕抓取 | 弹幕 **6720 条**，覆盖 **40/40** 个视频，全部完成情感标注 |

**数据纯度**

```
模拟数据残留     0 条        （原 200 条演示数据已全部清除）
旧真实数据       0 条        （原 97 条一并清除后重新抓取）
视频             40 条  全部真实，data_source=real，real_ratio=1.0
UP主             40 位  全部有真实粉丝数
弹幕             6720 条 全部来自真实视频
cid 覆盖率       40/40
```

**抓取请求账（共约 100 次请求）**

| 阶段 | 请求数 | 说明 |
| --- | --- | --- |
| 视频列表（含封面） | 1 | 1 次排行榜请求拿到 40 条视频 |
| UP主 粉丝数 | 40 | 1 位 1 次，无法批量 |
| cid 回填 | 5 | 排行榜接口被拦，改由详情接口逐个取（含在下一项） |
| 弹幕（40 个视频） | 40+ | 每视频 1 次详情（取 cid）+ 1 次弹幕包 |
| **合计** | **约 100 次** | 全程 `--interval 3~4`，命中风控 1 次，冷却 5 分钟后恢复 |

**情感分析结果（6720 条真实弹幕）**

| 倾向 | 占比 |
| --- | --- |
| 正向 | 41.29% |
| 中性 | 29.82% |
| 负向 | 28.88% |

> ⚠️ **负向占比偏高（28.9%）需要如实说明**：
> 真实弹幕里最高频的"情绪标签"是**疑问（704 条）**，
> 而 snownlp 对网络口语、反问、玩梗的判断能力有限，
> 大量中性甚至夸赞的句子被归到负向。
> 换 `paddlenlp` 的 SKEP 模型可以改善（需 Python 3.12，见 7.5 节）。
> **这是所选情感模型的固有局限，不是数据问题。**

---

#### 阶段六补 6：AI 助手检索失效 —— 一个"静默失败"的典型（2026-09-27）

用户反馈：**AI 助手回答"现有数据无法回答这个问题"**，
但右侧状态面板明明写着「索引就绪 40 条向量」「可用性：可以回答」。

这种"功能看着正常、就是永远没结果"的问题最难查，记录完整过程。

##### 现象与第一层线索

面板上有两处数字对不上：

| 位置 | 显示 |
| --- | --- |
| 状态面板 | 向量化后端 `local (**256 维**)` |
| 我重建索引时的输出 | `✅ 索引构建完成：40 条，维度 **39**` |

**同一个系统里，向量维度出现了两个值。**

##### 第二层：直接量出真实维度

```python
Chroma 里向量的维度 = 39
全新进程加载的向量化器维度 = 256
```

**查询向量 256 维，向量库 39 维 —— 根本没法比对，自然什么都检索不到。**

##### 第三层：服务器日志给出了铁证

```
[15:48:40] INFO  已加载本地向量化器：256 维，语料 297 条
[16:20:14] ERROR 向量检索失败：Collection expecting embedding with
                 dimension of 39, got 256
[16:20:45] ERROR 向量检索失败：Collection expecting embedding with
                 dimension of 39, got 256
```

##### 根因

本地向量化器是**用全量语料训练**出来的：TF-IDF 的词表与 IDF、
SVD 的投影矩阵都依赖当时那批文档，**连输出维度都会随语料规模变化**
（297 条 → 256 维，40 条 → 39 维）。

而它在 Web 进程里是**缓存**的。重建索引若发生在 CLI 或另一个进程，
Web 进程内存里仍是旧的那一份。问题出在 `search()` 的判断条件：

```python
# 修复前
if embedder.vectorizer is None:      # 只在"完全没训练过"时才加载
    embedder.load(...)
```

内存里那份**是训练过的旧版本**，`vectorizer` 不为 None，
于是这个条件为假 → **跳过了加载** → 拿着 256 维的过期投影去查 39 维的新库。

更糟的是异常被吞掉了：

```python
except Exception as exc:
    logger.error("向量检索失败：%s", exc)
    return []                       # 静默降级成"没检索到"
```

于是界面只说"没有找到相关视频"，
**连一句"索引与向量化器不匹配"的提示都没有** —— 排查时完全无从下手。

##### 修复：给索引发一张"身份证"，检索前先核对

**① 建索引时记录"我是谁建的"**

```python
# apps/ai/vector_store.py -> build_index()
collection.modify(metadata={
    "embedding_dim": embedder.dim,
    "corpus_size": embedder.corpus_size,
    "corpus_fingerprint": embedder.corpus_fingerprint,   # 语料 md5 前 16 位
})
```

**② 检索前校验，不匹配就自动重新加载**

```python
# apps/ai/vector_store.py -> search()
embedder = _ensure_embedder_matches(collection, embedder)
if embedder is None:
    return []      # 已在内部打了明确的 ERROR 日志，提示重建索引
```

`_ensure_embedder_matches()` 的逻辑：

```
维度 / 指纹都匹配        -> 直接用（不重建，避免每次检索都重训）
不匹配                   -> 清缓存 -> 取新实例 -> 从磁盘加载最新训练结果
重新加载后仍不匹配        -> 打 ERROR 日志并返回 None（明确告知要重建索引）
旧索引没有元数据          -> 放行，保持向后兼容
```

**③ 语料指纹而非只看维度**

只看维度会漏掉一种情况：语料换了、维度恰好相同，
此时向量化器不配套但能跑通，**返回的是错误的相似度**（比报错更危险）。
因此加了语料 md5 指纹：

```python
def _fingerprint_texts(texts):
    digest = hashlib.md5()
    for text in texts:
        digest.update(str(text).encode("utf-8"))
        digest.update(b"\x00")     # 分隔符，避免 ["ab","c"] 与 ["a","bc"] 撞车
    return digest.hexdigest()[:16]
```

##### 验证：人为复现故障再确认自愈

```python
# 用另一批语料训练一个"过期向量化器"塞进缓存（完全复现线上场景）
stale = LocalEmbedder(); stale.fit([...300 条无关语料...])
embedding._EMBEDDER_CACHE["local"] = stale
```

```
人造的过期向量化器：dim = 155（真实索引是 39 维）
   [未校验] 查询失败 -> Collection expecting embedding with dimension of 39, got 155
走修复后的 search()：
   检索到 5 条 ✅
   向量化器已刷新并与索引匹配：dim=39 指纹=97953c868bf15721
```

**端到端复验**（真实提问）：

```
提问：最近哪些视频播放量最高
intent=ranking  provider=deepseek  retrieved=5  latency=2304ms  fallback=False

1.《首次揭秘，影视飓风百人团建幕后！》— 播放量 277.5万，UP主影视飓风，
  数码分区，互动率 5.55% [1]
2.《蒙德：高清重置》— 播放量 248.4万，UP主ferrari044，
  计算机技术分区，互动率 13.91% [2]
...
```

##### 经验总结

| 教训 | 说明 |
| --- | --- |
| **静默降级比报错更危险** | `except: return []` 把"维度不匹配"伪装成"没有相关数据"，用户和开发者都看不出问题 |
| **缓存 + 派生状态必须校验** | 向量化器是缓存，索引是另一份派生状态，两者必须能互相确认是否配套 |
| **维度会变的嵌入不适合长期缓存** | 本地 TF-IDF+SVD 的输出维度随语料规模变化，这是设计上的脆弱点 |
| **状态面板要显示"真实来源"** | 面板显示 256 而索引是 39，正是这个矛盾第一时间提示了方向 |

##### 本轮验证

```
新增回归测试            3 个（过期向量化器自愈、元数据写入、配套时不重建）
完整测试套件            192/192 通过
AI 助手                 intent/retrieved/latency 均正常，引用来源准确
```

---


---

## 一、项目概述

### 1.1 解决的问题

| 角色 | 痛点 | BiliInsight 的解法 |
| --- | --- | --- |
| 内容创作者 | 选题靠感觉，不知道哪个分区/话题正在起量 | 分区热度趋势 + 关键词挖掘 + AI 选题建议 |
| 普通观众 | 优质视频发现效率低，推荐流同质化 | 基于播放/点赞/投币比的多维榜单 + 语义检索 |
| 数据分析者 | 缺少结构化的 B 站公开数据 | 定时爬虫 + 清洗后的规范化数据仓库 |

### 1.2 功能模块

| # | 模块 | 说明 | 评分点 |
| --- | --- | --- | --- |
| M1 | **数据采集** | B 站热门视频、分区排行、弹幕、评论爬虫；`BaseSpider` 抽象基类可扩展 | ✅ 互联网爬取数据 |
| M2 | **清洗与挖掘** | Pandas 去重/缺失值/异常值处理；Jieba 分词；K-Means 用户聚类；协同过滤推荐 | ✅ 数据处理、清洗、挖掘 |
| M3 | **数据存储** | MySQL 8.0 存主数据；Redis 缓存热榜与 Celery 消息队列；ChromaDB 存视频语义向量 | ✅ 数据库存储 |
| M4 | **Web 可视化** | Vue 3 + ECharts：播放量趋势、分区占比饼图、UP主排行、弹幕词云、情绪波动图 | ✅ Web 端数据可视化 |
| M5 | **弹幕情感分析** | PaddleNLP 情感倾向 + 关键词情绪分类（高燃/泪目/搞笑/吐槽） | 🔥 加分：AI 功能 + 国产框架 |
| M6 | **AI 推荐助手** | LangChain + RAG：检索向量库 + 弹幕情感 → 大模型生成个性化推荐与选题分析 | 🔥 加分：AI 功能模块 |
| M7 | **Celery 异步** | 爬虫任务、AI 推理、向量化全部异步化，不阻塞主线程 | 🔥 加分：代码优化 |

### 1.3 加分项映射

| 评分参考加分项 | 本项目落点 | 证明材料 |
| --- | --- | --- |
| 使用市场主流技术 | Vue3 + TS + Vite / Django 5 + DRF / MySQL / Redis / Celery / Docker | 第三章技术栈表 |
| 使用国产框架 | Element Plus、PaddleNLP（飞桨）、通义千问（DashScope） | M5、M6 运行截图 |
| 使用 AI 协助开发 | 通义灵码 / GitHub Copilot 生成爬虫解析、DRF 序列化器、Vue 组件 | 报告"AI 协作"章节 + 对话截图 |
| 有 AI 功能模块 | AI 推荐助手（RAG）+ 弹幕情感分析 | 演示视频重点片段 |
| 做过代码优化 | 索引 + Redis 缓存 + Celery + `select_related` + 前端懒加载 | 第二十三章优化前后 QPS 对比 |
| Git 协作 | 分支管理 + PR/MR 流程 | Gitee/GitHub 提交记录 |

---

## 二、系统架构

### 2.1 总体架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                        浏览器 (Vue 3 SPA)                             │
│   Element Plus UI  ·  ECharts 5  ·  Pinia  ·  Axios  ·  AI 悬浮助手    │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ HTTP / JSON (JWT Bearer)
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Nginx / Vite Dev Proxy (:8080)                     │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ /api/*  →  :8000
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Django 5 + DRF (WSGI/Gunicorn)                     │
│  ┌────────────┬─────────────┬──────────────┬──────────────────────┐  │
│  │  accounts  │   videos    │   analytics  │        ai            │  │
│  │  JWT 认证   │  视频/UP主   │  聚合统计     │  RAG / 情感分析       │  │
│  └────────────┴─────────────┴──────────────┴──────────────────────┘  │
└───────┬──────────────────┬─────────────────────┬─────────────────────┘
        │                  │                     │
        ▼                  ▼                     ▼
┌───────────────┐  ┌───────────────┐   ┌──────────────────────────────┐
│  MySQL 8.0    │  │   Redis 7     │   │  ChromaDB (向量库)            │
│  主数据存储     │  │ 缓存 + Broker │   │  视频语义向量 / 检索           │
└───────────────┘  └───────┬───────┘   └──────────────────────────────┘
                           │
                           ▼
                 ┌───────────────────────┐
                 │   Celery Worker       │
                 │  · 定时爬虫 (Beat)     │
                 │  · 清洗挖掘任务         │
                 │  · AI 推理 / 向量化     │
                 └───────────┬───────────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │  Bilibili 公开 Web API │
                 │  (限速 + UA + 重试)     │
                 └───────────────────────┘
```

### 2.2 数据流

```
B站 API ──► Spider ──► Raw JSON ──► Pandas 清洗 ──► MySQL
                                          │
                                          ├──► Jieba 分词 ──► 词频 ──► 词云
                                          ├──► PaddleNLP ──► 情感标签 ──► 情绪波动图
                                          └──► Embedding ──► ChromaDB
                                                                  │
用户提问 ──► 向量检索 Top-K ──► Prompt 组装 ──► 大模型 ──► AI 推荐回答
```

---

## 三、技术栈清单

### 3.1 前端

| 技术 | 版本 | 用途 |
| --- | --- | --- |
| Vue | 3.5.x | 前端框架（Composition API + `<script setup>`） |
| TypeScript | 5.x | 类型安全 |
| Vite | 7.x | 构建工具与开发服务器 |
| Element Plus | 2.x | UI 组件库（国产） |
| ECharts | 5.6.x | 数据可视化 |
| Axios | 1.x | HTTP 请求 |
| Pinia | 3.x | 状态管理 |
| Vue Router | 4.x | 路由 + 懒加载 |

### 3.2 后端

| 技术 | 版本 | 用途 |
| --- | --- | --- |
| Django | 5.2 LTS | Web 框架 |
| djangorestframework | 3.16.x | RESTful API |
| djangorestframework-simplejwt | 5.x | JWT 认证 |
| Celery | 5.6.x | 异步任务 |
| django-celery-beat | 2.x | 定时任务调度 |
| Gunicorn / Waitress | - | 生产 WSGI（Windows 用 Waitress） |

### 3.3 数据库与中间件

| 技术 | 版本 | 用途 |
| --- | --- | --- |
| MySQL | 8.0+ | 主数据库 |
| Redis | 7.x | 缓存 + Celery Broker |
| ChromaDB | 1.5.x | 向量数据库（视频语义检索） |

### 3.4 算法与 AI

| 技术 | 版本 | 用途 |
| --- | --- | --- |
| Pandas | 2.x | 数据清洗与挖掘 |
| NumPy | 2.x | 数值计算 |
| Scikit-learn | 1.7.x | K-Means 聚类、协同过滤 |
| Jieba | 0.42.1 | 中文分词 |
| PaddlePaddle | 3.3.x | 深度学习框架（国产） |
| PaddleNLP | 2.8.x | 情感分析、实体抽取 |
| LangChain | 1.x | AI 助手编排 |
| langchain-community | - | `ChatTongyi` 等模型接入 |
| dashscope | 1.27.x | 通义千问官方 SDK |

---

## 四、环境要求与本机实测结果

> **实测时间**：2026-09-14 · **机器**：Windows 11 (10.0.26100)

### 4.1 ✅ 已就绪（无需安装）

| 工具 | 本机版本 | 路径 | 项目中的用途 |
| --- | --- | --- | --- |
| Python | **3.13.13** | `D:\develop\python\python.exe` | 后端运行环境（已确认 PaddlePaddle 有 cp313 wheel） |
| pip | 26.0.1 | 同上 | 依赖安装 |
| Node.js | **v24.16.0** | `D:\develop\nodeJS\node.exe` | 前端运行环境（要求 18+，✔ 满足） |
| npm | 11.13.0 | 同上 | 前端依赖管理 |
| Git | 2.47.1 | - | 版本控制 |
| **PyCharm Professional** | **2026.1.5** (`productCode=PY`) | `D:\develop\pycharm\PyCharm 2026.1.1\bin\pycharm64.exe` | 主 IDE ✔ **专业版**，支持 Django 项目创建/调试 |
| **Apifox** | 2.8.32 | `D:\develop\apifox\Apifox.exe` | API 接口测试 ✔ 已安装 |
| **Ollama** | 0.7.0（含 `deepseek-r1:8b`） | `D:\develop\ollama\` | **可选的免费本地大模型**，无需 API Key |
| IntelliJ IDEA | 2025.2.4 | `D:\develop\IntelliJ IDEA 2025.2.4` | 备用 IDE |
| JDK / javac | 21.0.8 LTS | - | PyCharm 运行时 |
| .NET SDK | 9.0.100 | - | 与项目无关，仅记录 |

> 💡 **PyCharm 已确认是专业版**，`rdme.txt` 中「必须使用专业版」的要求已满足，无需额外安装。
>
> 💡 **Ollama + deepseek-r1:8b 是惊喜项**：可让 AI 助手在**无 API Key、无外网**的情况下跑通演示，答辩现场零风险。详见 [7.3](#73-方案b本地-ollama零密钥可离线)。

### 4.2 ⚠️ 缺失，需要安装

按**优先级**排序。P0 = 不装则后端跑不起来；P1 = 影响功能完整性；P2 = 锦上添花。

| 优先级 | 工具 | 用途 | 官方下载路径 | winget 一键安装 |
| --- | --- | --- | --- | --- |
| **P0** | **MySQL 8.0** | 主数据库 | <https://dev.mysql.com/downloads/installer/> | `winget install Oracle.MySQL` |
| **P0** | **Memurai**（替代 Redis） | 缓存 + Celery Broker | <https://www.memurai.com/get-memurai> | `winget install Memurai.MemuraiDeveloper` |
| **P1** | **MySQL Workbench** | MySQL 可视化管理（随 Installer 一起装） | 见 MySQL Installer | - |
| **P1** | **DBeaver Community** | 通用数据库管理（可选替代 Workbench） | <https://dbeaver.io/download/> | `winget install dbeaver.dbeaver` |
| **P1** | **Docker Desktop** | 一键起 MySQL + Redis（⚠️ **需先启用 WSL2**，见路径 C） | <https://www.docker.com/products/docker-desktop/> | `winget install Docker.DockerDesktop` |
| **P2** | **Apache JMeter** | 接口压测（报告"性能优化"章节需要） | <https://jmeter.apache.org/download_jmeter.cgi> | `winget install Apache.JMeter` |
| **P2** | **Python 3.11** | `rdme.txt` 要求的虚拟环境版本；**可选**，见下方说明 | <https://www.python.org/downloads/release/python-3119/> | `winget install Python.Python.3.11` |
| **P2** | **WSL2** | 仅路径 C 需要 | `wsl --install`（管理员 PowerShell） | - |

#### 关于 Redis on Windows 的重要提示

Redis 官方**不提供 Windows 原生版本**。三种可行方案：

1. **Memurai（本机推荐）**——Windows 原生 Redis 兼容服务，[Redis 官方合作伙伴](https://redis.io/partners/memurai/)，免费 Developer 版够用，**无需虚拟化、无需重启**；
2. **Docker Desktop**——`docker compose up -d` 一条命令起两个服务，但**本机需先启用 WSL2 并重启**（见路径 C）；
3. **WSL2**——`wsl --install` 后在 Ubuntu 里 `apt install redis-server`。

> ⚠️ **本机实测：WSL 与虚拟机平台均未启用**，因此 Docker 路径当前不可用，
> 请优先采用 Memurai。详细对比见 [路径 B](#路径-b完全不用-dockermysql--memurai--本机推荐)。

#### 关于 Python 3.11 vs 3.13

`rdme.txt` 写的是 Python 3.11，但本机只有 **3.13.13**。已实测确认：

- ✅ `paddlepaddle-3.3.1-cp313-cp313-win_amd64.whl` **存在**，PaddlePaddle 官方已支持 cp313；
- ✅ `Django 5.2 LTS` 支持 Python 3.10–3.13。

**结论：直接用本机 Python 3.13 即可跑通全链路，不必安装 3.11。** 若答辩现场遇到冷门轮子编译失败，再装 3.11 兜底。

#### winget 不可用时的兜底

本机 `winget` 位于 `C:\Users\11140\AppData\Local\Microsoft\WindowsApps\winget.exe`，但在受限 shell 中调用可能失败。**如果 winget 报错，请直接使用上表的「官方下载路径」手动安装。**

### 4.3 一键环境自检（推荐先跑这个）

项目内置了自检脚本，会自动检测上表所有技术栈并打印缺失项与下载路径：

```powershell
# 在项目根目录执行
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-env.ps1
```

输出示例（本机实测结果）：

```
P0 - 必需（缺失则项目无法运行）
  [OK]      Python     Python 3.13.13
  [OK]      Node.js    v24.16.0
  [OK]      npm        11.13.0
  [OK]      git        git version 2.47.1.windows.1
  [MISSING] MySQL      主数据库（或改用 Docker）
            下载: https://dev.mysql.com/downloads/installer/
  [MISSING] Redis      缓存/Broker（或 Docker/Memurai）
            下载: https://github.com/redis-windows/redis-windows/releases

P1 - 强烈建议
  [MISSING] Docker     一键起 MySQL+Redis（最省事的方案）
  [OK]      PyCharm    261.27258.51.0-PY

P2 - 可选
  [部分]    Ollama     已安装但不在 PATH，需手动启动服务
  [OK]      Apifox     2.8.32

自检结论
  共 3 项缺失，请按上面的下载路径安装：
    - MySQL              https://dev.mysql.com/downloads/installer/
    - Redis              https://github.com/redis-windows/redis-windows/releases
    - Docker Desktop     https://www.docker.com/products/docker-desktop/
```

> **注意**：本项目脚本用 **Windows PowerShell 5.1** 运行即可（本机未安装 PowerShell 7，
> 故不要用 `pwsh`，请用 `powershell`）。脚本文件必须以 **UTF-8 BOM** 保存，否则中文会乱码。

### 4.4 安装包安全验证

大体积安装包（MySQL 300 MB、Docker 600 MB）下载时，浏览器常弹出
**「Microsoft Defender SmartScreen 无法扫描此文件」**。

> ✅ **这是正常现象，不是报错，也不代表文件有问题。**
> SmartScreen 的云查杀对超大文件有大小上限，超出后它无法扫描，
> 于是保守地提示"除非确定其安全性，否则不保留它"。
>
> **放行方法**：点下载项右侧的 `···` → **「保留」**；
> 或点提示条 **「更多信息」→「仍然保留」**。

**放行后务必核对数字签名**，确认文件确实来自官方厂商：

```powershell
# MySQL 安装包：签名者应为 Oracle Corporation
Get-AuthenticodeSignature "E:\Downloads\mysql-installer-community-8.0.x.msi" |
  Format-List Status, SignerCertificate

# Docker 安装包：签名者应为 Docker Inc.
Get-AuthenticodeSignature "E:\Downloads\Docker Desktop Installer.exe" |
  Format-List Status, SignerCertificate

# Memurai 安装包：签名者应为 Janea Systems, Inc.
Get-AuthenticodeSignature "E:\Downloads\Memurai.msi" |
  Format-List Status, SignerCertificate
```

**判断标准**：

| 字段 | 期望值 | 说明 |
| --- | --- | --- |
| `Status` | `Valid` | 签名有效 |
| `SignerCertificate.Subject` | 含官方厂商名 | 见上方各自期望值 |

若 `Status` 为 `NotSigned` 或签名者与官方不符，**说明文件被篡改或来源非官方，请勿安装**，改从本文档给出的官方链接重新下载。

> 💡 **本机下载目录是 `E:\Downloads`**（不是默认的 `C:\Users\11140\Downloads`），
> 上面的命令路径请按实际情况调整。

### 4.5 网络与端口规划

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| Vue Dev Server | **8080** | 前端访问入口 → <http://localhost:8080> |
| Django | **8000** | 后端 API → <http://localhost:8000/api/> |
| MySQL | 3306 | 数据库 |
| Redis / Memurai | 6379 | 缓存/Broker |
| ChromaDB | 8001 | 向量库 HTTP 服务（本地模式可不开） |

> 本机实测 3306 / 6379 / 8000 / 8080 / 5173 **当前均未被占用**，可直接使用。

### 4.6 硬件建议

| 项 | 最低 | 推荐 | 说明 |
| --- | --- | --- | --- |
| 内存 | 8 GB | **16 GB** | MySQL + Redis + Django + Vite + Chroma + 本地大模型 |
| 磁盘 | 10 GB | 30 GB | 依赖 + 向量库 + 模型文件（deepseek-r1:8b 已占 4.87 GB） |
| 网络 | 可访问 PyPI / npm / B站 | 同左 | 首次装依赖需外网 |

---

## 五、速通部署（推荐路径）

### 路径 A：Docker 起中间件 + 本地跑应用

> ⚠️ **本机不推荐此路径**：经实测本机 **WSL 与虚拟机平台均未启用**，
> Docker Desktop 会卡在 "Starting the Docker Engine..."。
> 请优先使用 **路径 B**，或先按 **路径 C** 启用 WSL2（需改 BIOS + 重启）。

```powershell
# 0) 进入项目根目录
cd "E:\deepseek harness\Biliinsight"

# 1) 一键启动 MySQL + Redis（需先安装并启动 Docker Desktop）
docker compose up -d
docker compose ps                    # 确认两个服务都是 healthy

# 2) 后端
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env          # 然后按需修改 .env
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo           # 生成演示数据（无需真实爬虫即可看效果）
python manage.py runserver 8000

# 3) 另开一个终端 → Celery Worker（Windows 必须用 solo 池）
cd "E:\deepseek harness\Biliinsight\backend"
.\.venv\Scripts\Activate.ps1
celery -A config worker -l info -P solo

# 4) 再开一个终端 → 前端
cd "E:\deepseek harness\Biliinsight\frontend"
npm install
npm run dev
```

打开 <http://localhost:8080> 即可看到数据看板。

### 路径 B：完全不用 Docker（MySQL + Memurai）—— ⭐ 本机推荐

> **为什么本机推荐这条路径？**
> 本机 **WSL / VirtualMachinePlatform 均处于 Disabled 状态**，而 Docker Desktop 强依赖
> WSL2 或 Hyper-V。启用 WSL2 需改 BIOS 并重启，对只需一个 MySQL + 一个 Redis 的
> 课程项目性价比很低。**方案 B 与方案 A 在项目功能上完全等价**，且无需重启。

#### B-1 安装 MySQL 8.0

**下载**：<https://dev.mysql.com/downloads/installer/>
选 **`mysql-installer-community-8.0.x.msi`**（约 300 MB）。建议用这个离线版，
不要用 `web-community` 在线安装版（它装到一半还要联网下载，更容易失败）。

> ⚠️ **若浏览器弹出「Microsoft Defender SmartScreen 无法扫描此文件」**：
> **这是正常现象，不是报错。** 大体积安装包超出 SmartScreen 云查杀的大小上限，
> 它无法扫描所以保守提示。这不是"文件有问题"的信号。
>
> **放行方法**：点下载项右侧的 `···` → **「保留」**；
> 或点提示条的 **「更多信息」→「仍然保留」**。
>
> 放行后请务必按 [4.4 安装包安全验证](#44-安装包安全验证) 核对数字签名。

**安装向导要点**：

| 步骤 | 选择 |
| --- | --- |
| Choosing a Setup Type | **Custom**（自定义，避免装一堆用不上的东西） |
| Select Products | 只添加 **MySQL Server 8.0.x** + **MySQL Workbench** |
| Authentication Method | **Use Strong Password Encryption** |
| Accounts and Roles | 设置 **root 密码**（务必记住） |
| Windows Service | ✅ Configure as a Windows Service，服务名 `MySQL80`，✅ 开机自启 |

**验证 + 建库**：

```powershell
Get-Service MySQL80          # 期望 Status = Running

# 建库与专用账号（把 bili_pass_2026 换成你自己的密码）
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u root -p -e "CREATE DATABASE IF NOT EXISTS biliinsight DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER IF NOT EXISTS 'bili'@'localhost' IDENTIFIED BY 'bili_pass_2026'; GRANT ALL PRIVILEGES ON biliinsight.* TO 'bili'@'localhost'; FLUSH PRIVILEGES; SHOW DATABASES;"
```

> 若路径不同：`Get-ChildItem "C:\Program Files\MySQL" -Recurse -Filter mysql.exe`。
> 也可把 `...\MySQL Server 8.0\bin` 加入系统 PATH，之后直接敲 `mysql -u root -p`。

#### B-2 安装 Memurai 代替 Redis

**为什么要 Memurai**：Redis 官方**不提供 Windows 原生版本**。Memurai 是 Windows 原生的
Redis 兼容服务（[Redis 官方合作伙伴](https://redis.io/partners/memurai/)），
免费 Developer 版对本项目完全够用。

**下载**：<https://www.memurai.com/get-memurai> → 选 **Developer Edition** → 下载 `Memurai.msi`

**安装要点**：

| 选项 | 值 |
| --- | --- |
| Install as Windows Service | ✅ 勾选（**开机自启，强烈建议**） |
| Port | 保持默认 **`6379`**（与 Redis 一致，`.env` 无需改动） |
| Add firewall exception | ✅ 勾选 |

> 管理员命令行静默安装（可选）：
> ```powershell
> msiexec /quiet /i Memurai.msi INSTALL_SERVICE=1 PORT=6379 ADD_FIREWALL_RULE=1 ADD_INSTALLFOLDER_TO_PATH=1
> ```

**验证**：

```powershell
Get-Service Memurai                                   # 期望 Status = Running
& "C:\Program Files\Memurai\memurai-cli.exe" ping     # 期望输出 PONG
```

> ⚠️ **命令名注意**：Memurai 的客户端是 **`memurai-cli`**，**不是 `redis-cli`**。
> 想沿用 `redis-cli` 这个名字，可在 `C:\Program Files\Memurai\` 下把
> `memurai-cli.exe` 复制一份改名 `redis-cli.exe`。

**`.env` 无需修改**，默认值即可直连：

```ini
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
```

> ⚠️ **Developer 版有 10 天限制**（到期后服务自动停止，需重启）。
> 答辩前一天用管理员执行 `Restart-Service Memurai` 重置计时即可。

#### B-3 数据来源：真实抓取 vs 模拟数据

> ⚠️ **先读这段，能省很多时间。** 实测风控规律：
> B站风控按**短时间窗口内的请求次数**判定，**与请求间隔关系不大**。
> 日志记录：
> ```
> 冷却后第 1 次请求（dry-run）  -> ✅ 成功，返回 97 条
> 紧接着第 2 次请求（正式抓取） -> ❌ -352 风控
> 即便把间隔从 4 秒调到 8 秒，第 2 次仍被拦
> ```
> **因此不要连续试**——每次被拦都会重置冷却计时，越试越糟。

**最优解：换网络环境（实测有效 ✅）**

风控按 **IP 维度**统计，因此**换一个出口 IP 是最快的解法**。
本项目最终就是靠**手机开热点**抓成功的——新 IP 无风控记录，
第一次请求直接返回 97 条。

```powershell
# 1) 把电脑网络切到手机热点
# 2) 单次请求抓满（注意：1 次请求就能拿 97 条，见下方说明）
python manage.py crawl --partition 科技 --limit 100 --interval 5
```

> 💡 **成本按「请求次数」计，不按「视频条数」计**
> `run_partition()` 只发 **1 次** HTTP 请求，排行榜一次返回约 97 条，
> `--limit` 仅是**本地入库上限**。所以 `--limit 30` 与 `--limit 100`
> 的风控代价**完全相同**，但后者数据量是前者的 3 倍。
> **风控敏感时，一次把 `--limit` 开到接口上限，不要保守取小值。**

**备选：用带指数退避的脚本**（不方便换网络时）

```powershell
# 先等 30 分钟冷却，再尝试；失败自动退避重试（30 分钟 -> 45 分钟）
python scripts\crawl_with_backoff.py --partition 科技 --limit 100 --interval 8

# 冷却期内启动（先等待再试）
python scripts\crawl_with_backoff.py --partition 科技 --limit 100 --initial-wait 1800

# 多分区：逐个抓，前一个成功后再进行下一个
python scripts\crawl_with_backoff.py --partition 科技,数码,游戏 --limit 100
```

脚本会在成功后自动统计真实数据条数，并提示重建向量索引。

**推荐顺序：换网络 > 指数退避 > 长时间等待。** 前者的成功率远高于后两者。

**区分真实与模拟数据**

```powershell
# 查看真实/模拟比例（按分区细分）
python manage.py mark_data_source --status

# 修正历史数据标记（is_demo 是后加的字段，旧数据默认被当成真实数据）
python manage.py mark_data_source --mark-demo
```

抓到真实数据后：
- 看板顶部的提示条会自动变成「混合数据」或消失（全真实时）
- 真实数据的**标题可点击跳转B站核对**，模拟数据仍带标签且链接禁用

#### B-4 后端启动步骤

完成 B-1、B-2 后，**与路径 A 的第 2)~4) 步完全一致**：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver 8000

# 另开终端：celery -A config worker -l info -P solo
# 再开终端：cd frontend; npm install; npm run dev
```

#### B-4 清理 Docker 残留（可选）

实测本机 `C:\Program Files\Docker` 是个**空目录**（上次安装失败的残留），
注册表已无 Docker 卸载项。确定不用 Docker 后可删除（**需管理员**）：

```powershell
Remove-Item "C:\Program Files\Docker" -Recurse -Force
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\docker-desktop" -Recurse -Force
```

### 路径 C：确实想用 Docker（必须先启用 WSL2）

> ⚠️ **务必按此顺序**，否则 Docker 装了也起不来。

```powershell
# 1) 以【管理员】身份打开 PowerShell，启用两个 Windows 功能
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 2) 重启电脑（必须，不可跳过）

# 3) 重启后设置 WSL2 为默认版本
wsl --set-default-version 2
wsl --update

# 4) 安装 Docker Desktop（见 4.6 放行 SmartScreen）
winget install Docker.DockerDesktop

# 5) 启动 Docker Desktop，等托盘图标变绿后验证引擎
docker --version
docker run --rm hello-world          # 能跑通说明引擎正常

# 6) 回到项目根目录启动中间件
cd "E:\deepseek harness\Biliinsight"
docker compose up -d
```

**前置检查**：任务管理器 → 性能 → CPU，右下角需显示 **「虚拟化：已启用」**。
若为"已禁用"，需重启进 **BIOS/UEFI** 打开 `Intel VT-x` / `AMD-V`。
学校机房电脑可能被 BIOS 锁死，这种情况请改用路径 B。

### 启动成功的判断标准

| 检查项 | 命令 / 地址 | 期望结果 |
| --- | --- | --- |
| 后端存活 | <http://localhost:8000/api/health/> | `{"status": "ok", "db": true, "redis": true}` |
| 接口文档 | <http://localhost:8000/api/docs/> | Swagger / Redoc 页面 |
| Django Admin | <http://localhost:8000/admin/> | 可登录 |
| 前端页面 | <http://localhost:8080> | 看板渲染出图表 |
| Celery | Worker 终端 | `celery@xxx ready.` |
| AI 助手 | 页面右下角悬浮球 | 输入问题能返回推荐 |

---

## 六、完整部署步骤

### 6.1 拉取代码

```powershell
git clone <你的 Gitee/GitHub 仓库地址> BiliInsight
cd BiliInsight
```

### 6.2 后端环境

```powershell
cd backend

# 创建虚拟环境（PyCharm 中可用 GUI：Settings → Project → Python Interpreter → Add → Virtualenv）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 若提示"禁止运行脚本"，先执行：
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

> **PyCharm 用户提示**：创建虚拟环境后，在 `Settings → Project: backend → Python Interpreter`
> 选择 `.venv\Scripts\python.exe`，PyCharm 会自动识别依赖。

### 6.3 安装依赖

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**依赖安装失败时的常用镜像源**：

```powershell
# 清华源（PaddlePaddle 建议用官方源，其余可用镜像加速）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# PaddlePaddle 官方源
pip install paddlepaddle==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

### 6.4 配置环境变量

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env` 关键项（完整见 `.env.example`）：

```ini
# ---------- Django ----------
DJANGO_SECRET_KEY=change-me-to-a-random-50-char-string
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# ---------- MySQL ----------
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=biliinsight
MYSQL_USER=bili
MYSQL_PASSWORD=bili_pass_2026

# ---------- Redis ----------
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2

# ---------- AI（二选一，详见第七章）----------
AI_PROVIDER=ollama                      # ollama | dashscope
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=deepseek-r1:8b
DASHSCOPE_API_KEY=                      # 用 dashscope 时必填

# ---------- 爬虫合规 ----------
SPIDER_REQUEST_INTERVAL=2.0             # 请求间隔（秒），请勿低于 1.0
SPIDER_USER_AGENT=Mozilla/5.0 (compatible; BiliInsight/1.0; Educational-Research)
```

### 6.5 初始化数据库

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### 6.6 灌入数据

```powershell
# 方式一：真实爬取（首次建议小批量试跑）
python manage.py crawl --partition 科技 --limit 50

# 方式二：演示数据（答辩/无网环境推荐）
python manage.py seed_demo

# 方式三：异步任务（验证 Celery 链路）
python manage.py shell -c "from apps.spider.tasks import crawl_partition; crawl_partition.delay('科技', 50)"
```

### 6.7 启动全部服务

需要**三个终端**：

```powershell
# 终端 1 —— Django
cd backend; .\.venv\Scripts\Activate.ps1; python manage.py runserver 8000

# 终端 2 —— Celery Worker（Windows 必须 -P solo）
cd backend; .\.venv\Scripts\Activate.ps1; celery -A config worker -l info -P solo

# 终端 3 —— Celery Beat（可选，定时爬虫）
cd backend; .\.venv\Scripts\Activate.ps1; celery -A config beat -l info

# 终端 4 —— Vue
cd frontend; npm run dev
```

> **PyCharm 联合调试**：`Run → Edit Configurations → +  → Compound`，
> 把 `Django Server` 和 `npm run dev` 两个配置加进去，一键同时启动。

### 6.8 前端配置

`frontend/.env.development`：

```ini
VITE_API_BASE_URL=/api
VITE_PROXY_TARGET=http://127.0.0.1:8000
```

`frontend/vite.config.ts` 代理（解决跨域）：

```ts
server: {
  port: 8080,
  proxy: {
    '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  },
}
```

---

## 七、AI 模块配置（RAG + 情感分析）

### 7.1 三种 Provider，按场景切换

| 方案 | 依赖 | 成本 | 联网 | 适用场景 |
| --- | --- | --- | --- | --- |
| **A. DeepSeek 官方 API** | API Key | **极低**（约几厘/次） | 需要 | ⭐ **推荐**：便宜、效果好、OpenAI 兼容 |
| **B. 通义千问（DashScope）** | 阿里云 API Key | 有免费额度 | 需要 | 效果最好，国产框架加分 |
| **C. 本地 Ollama** | 本机 Ollama 服务 | **免费** | **不需要** | 答辩现场零风险备份 |

三者都不可用时自动降级为**检索式回答**（用真实数据组织回答并标注），
保证 AI 功能永不空白。`.env` 中 `AI_PROVIDER` 一键切换。

### 7.1.1 DeepSeek 接入（推荐）

**⚠️ 最容易踩的坑：模型名**

| 项目 | 正确值 |
| --- | --- |
| **API 模型名** | **`deepseek-flash`** |
| 对应模型版本 | DeepSeek-V4.1-Flash（**版本名 ≠ 模型名**） |
| 另一个可选 | `deepseek-v4-pro` |
| ❌ 错误写法 | `deepseek-v4.1-flash`（会报模型不存在） |
| ⚠️ 已退役 | `deepseek-v4-flash`（仅兼容转发，不推荐） |

官方文档原文：

> Use `deepseek-flash` as the model name. The legacy names `deepseek-v4-flash`
> and `deepseek-v4-flash-...` are still accepted, but **the corresponding models
> have been retired**.

**配置步骤**：

1. 申请 API Key：<https://platform.deepseek.com/api_keys>
2. 修改 `.env`：

```ini
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-你的密钥
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

3. 验证：

```powershell
python manage.py shell -c "from apps.ai.llm import get_llm; print(get_llm().provider_name, get_llm().model)"
# 期望输出：deepseek deepseek-flash
```

4. **重启后端**（⚠️ `.env` 只在进程启动时读取一次，不重启不生效）

5. 前端 AI 助手页应显示 Provider 为 `deepseek`

**一键诊断**：配置后若未生效，运行诊断脚本自动排查（会依次检查文件、
环境变量、settings、Provider 判定，并**真实调用一次**验证密钥）：

```powershell
python scripts\diagnose_deepseek.py
```

输出示例：

```
【1】文件层面
  .env 路径      : E:\deepseek harness\Biliinsight\backend\.env
  .env 修改时间  : 2026-09-18 22:26:54
【2】进程环境变量（会覆盖 .env！）
  （无相关环境变量，配置将全部来自 .env，这是正常情况）
【3】Django settings 读到的值
  AI_PROVIDER     : deepseek
  DEEPSEEK_API_KEY: sk-8971...21b5（35 字符）
【4】DeepSeekLLM 实例判定
  available       : True
【5】工厂选择结果
  provider        : deepseek
【6】真实调用测试（会消耗少量额度）
  [OK] 调用成功，模型回复：收到
```

> **实测效果**（2026-09-18，真实调用）：
> ```
> 提问：科技区有什么值得看的视频？用一句话推荐
> provider=deepseek  intent=recommend  retrieved=3  latency=1061ms  fallback=False
>
> 回答：科技区值得看的是《【显卡】深度评测｜第23期》，播放量6,309、
>       点赞228、互动率7.31%，适合关注硬件性能的观众 [3]。
> ```
> 结尾的 `[3]` 是 RAG 引用编号，证明模型是**依据检索到的第 3 条真实资料**
> 回答，而非编造——这是 RAG 抑制幻觉的直接体现。

**实现要点**：

| 要点 | 说明 |
| --- | --- |
| **不用 openai SDK** | DeepSeek 是 OpenAI 兼容格式，用 `requests` 直接 POST 即可，少一个依赖（与项目"降低答辩现场风险"原则一致） |
| **显式关闭思考模式** | 该模型**默认开启 thinking**，会输出思维链。请求体中传 `"thinking": {"type": "disabled"}` 关闭——思维链对终端用户是噪声（与 deepseek-r1 同类问题） |
| **模型名校验** | 误填 `deepseek-v4.1-flash` 时会打 WARNING 提示正确名称，并已用测试固化该约定 |
| **忽略 `reasoning_content`** | 流式解析时只取 `delta.content`，刻意跳过思维链字段 |
| **错误信息透传** | 非 200 响应会把官方错误文本带出来，便于定位（如模型名错误） |

**价格**（Flash 档，非峰值时段为半价）：

```
输入（缓存未命中）  峰值 $0.30 / 百万 tokens
输出                峰值 $1.20 / 百万 tokens
```

本项目的问答单次约 1-2k tokens，**一次问答成本约几厘钱**。

### 7.2 方案 B：通义千问

1. 访问 <https://bailian.console.aliyun.com/> 注册并开通「百炼」；
2. 在「API-KEY 管理」创建 Key；
3. 写入 `.env`：

```ini
AI_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
AI_MODEL=qwen-plus
```

4. 验证：

```powershell
python manage.py shell -c "from apps.ai.llm import get_llm; print(get_llm().invoke('你好，用一句话介绍B站').content)"
```

### 7.3 方案 B：本地 Ollama（零密钥、可离线）

本机已装 Ollama 且已有 `deepseek-r1:8b`（4.87 GB）。

> ⚠️ **重要**：`ollama` **当前不在 PATH 上**，且服务**未运行**。需要两步修复：

```powershell
# 1) 启动 Ollama 服务（找到实际安装路径）
& "D:\develop\ollama\ollama.exe" serve
# 若 ollama.exe 不在该目录，先运行安装包：
#   D:\develop\ollama\OllamaSetup-v0.7.0.exe
# 建议把 Ollama 加入 PATH：把 C:\Users\<你>\AppData\Local\Programs\Ollama 加入系统环境变量

# 2) 另开终端验证
curl http://127.0.0.1:11434/api/tags        # 应返回含 deepseek-r1:8b 的 JSON
ollama run deepseek-r1:8b "你好"             # 能对话即成功
```

`.env`：

```ini
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=deepseek-r1:8b
```

> 💡 8B 模型在 16 GB 内存机器上可流畅运行；若显存不足会回退 CPU，首次响应约 5–20 秒。

### 7.4 RAG 检索链路

```
用户提问 "最近科技区什么视频最火？"
      │
      ▼
[1] Query 向量化（bge-small-zh / text-embedding-v3）
      │
      ▼
[2] ChromaDB 余弦检索 Top-K=8 视频（标题 + 简介 + 标签）
      │
      ▼
[3] 附加弹幕情感分布（PaddleNLP 已离线打标）
      │
      ▼
[4] Prompt 组装（系统提示 + 检索片段 + 用户问题）
      │
      ▼
[5] 大模型生成（qwen-plus 或 deepseek-r1:8b）
      │
      ▼
[6] 流式返回前端（SSE），打字机效果
```

### 7.5 弹幕情感分析

#### 为什么默认用 SnowNLP 而不是 PaddleNLP

⚠️ **实测结论：`paddlenlp` 在 Python 3.13 上无法安装。**

```
ERROR: Could not find a version that satisfies the requirement tool-helpers (from paddlenlp)
ERROR: No matching distribution found for tool-helpers
```

`paddlenlp 2.8.1` 依赖 `tool-helpers`，而该包在 PyPI 上取不到任何可用版本
（其版本约束均为 `>=3.x,<3.13`）。**这是上游依赖问题，不是环境配置错误。**

因此情感分析模块设计为**可插拔**，通过 `SENTIMENT_BACKEND` 一键切换：

| 后端 | 依赖 | Python 要求 | 适用场景 |
|---|---|---|---|
| **`snownlp`**（默认） | 纯 Python，零编译 | **3.8 – 3.13 全支持** | 开箱即用，本机推荐 |
| `paddlenlp`（进阶） | 飞桨 PaddlePaddle | **仅 3.11 / 3.12** | 需更高精度、要在报告里写"国产框架" |

**业务逻辑与实现解耦**：情绪分类、波动图、词云等逻辑都在
`apps/ai/sentiment.py` 的 `SentimentAnalyzer` 抽象接口里，换后端只需改 `.env` 一行：

```ini
SENTIMENT_BACKEND=snownlp     # 或 paddlenlp
```

> 💡 **答辩加分说明**：若报告需要强调"使用国产框架"，有两条路：
> ① 加装 Python 3.12 后启用 PaddleNLP（见 `requirements-paddle.txt`）；
> ② 保留 SnowNLP 做情感分析，**国产框架加分改由 Element Plus（前端 UI）+ 通义千问（AI 助手）承担**——
> 这两者同样是国产且已在项目中实际使用，加分点不丢。

#### 用法

```powershell
# 批量打标
python manage.py analyze_sentiment --batch 500

# 查看某视频情绪分布
python manage.py analyze_sentiment --video BV1xx411c7mD --show-dist
```

输出示例：

```
视频 BV1xx411c7mD 弹幕情感分布：
  正向  62.3%  ████████████░░░░░░░░
  中性  28.1%  █████░░░░░░░░░░░░░░░
  负向   9.6%  ██░░░░░░░░░░░░░░░░░░
主导情绪标签：高燃、搞笑
```

#### 若要用 PaddleNLP（需 Python 3.11/3.12）

```powershell
# 1) 安装 Python 3.12（本机当前只有 3.13）
winget install Python.Python.3.12
# 或手动下载：https://www.python.org/downloads/release/python-3129/

# 2) 用 3.12 建独立虚拟环境
py -3.12 -m venv .venv-paddle
.\.venv-paddle\Scripts\Activate.ps1

# 3) 先装主依赖，再装飞桨（用官方源）
pip install -r requirements.txt
pip install -r requirements-paddle.txt -i https://www.paddlepaddle.org.cn/packages/stable/cpu/

# 4) 切换后端
# 修改 .env:  SENTIMENT_BACKEND=paddlenlp
```


---

## 八、接口文档

Base URL：`http://localhost:8000/api` · 认证：`Authorization: Bearer <access_token>`

### 8.1 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register/` | 注册 |
| POST | `/auth/login/` | 登录，返回 access + refresh |
| POST | `/auth/refresh/` | 刷新 access token |
| GET | `/auth/me/` | 当前用户信息 |

### 8.2 数据

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/videos/` | 视频列表（分页、筛选、排序） |
| GET | `/videos/{bvid}/` | 视频详情 |
| GET | `/videos/{bvid}/danmaku/` | 弹幕列表 |
| GET | `/upusers/` | UP主列表 |
| GET | `/partitions/` | 分区列表 |

### 8.3 分析

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/analytics/overview/` | 总览卡片（视频数/播放总量/UP主数） |
| GET | `/analytics/trend/?days=30` | 播放量趋势 |
| GET | `/analytics/partition-ratio/` | 分区占比饼图 |
| GET | `/analytics/top-upusers/?limit=10` | UP主排行榜 |
| GET | `/analytics/wordcloud/?bvid=` | 弹幕词云数据 |
| GET | `/analytics/sentiment/?bvid=` | 情绪波动序列 |

### 8.4 AI

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/ai/chat/` | AI 助手对话（支持 SSE 流式） |
| POST | `/ai/recommend/` | 基于偏好的视频推荐 |
| POST | `/ai/topic-ideas/` | 创作者选题建议 |
| GET | `/ai/health/` | 检查 AI Provider 连通性 |

### 8.5 运维

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health/` | 健康检查（DB + Redis + AI） |
| POST | `/tasks/crawl/` | 手动触发爬虫任务 |
| GET | `/tasks/{task_id}/` | 查询任务状态 |

---

## 九、目录结构

```
BiliInsight/
├── README.md                       # 本文档
├── rdme.txt                        # 原始设计需求
├── docker-compose.yml              # ✅ MySQL + Redis 一键编排（3307 / 6379）
├── .gitignore
│
├── scripts/
│   └── check-env.ps1               # ✅ 一键环境自检
│
├── docker/
│   └── mysql/init/01-init.sql      # ✅ MySQL 初始化脚本
│
├── backend/                        # Django 后端 —— 阶段一已完成
│   ├── manage.py                   # ✅ 默认加载 config.settings.dev
│   ├── requirements.txt            # ✅ 依赖清单（已在 Python 3.13 实测）
│   ├── requirements-paddle.txt     # ✅ PaddleNLP 可选依赖（需 Python 3.11/3.12）
│   ├── .env / .env.example         # ✅ 环境变量（MYSQL_PORT=3307）
│   │
│   ├── config/                     # ✅ 项目配置
│   │   ├── __init__.py             #    PyMySQL 伪装 + 暴露 celery_app
│   │   ├── settings/
│   │   │   ├── base.py             #    通用配置（数据库/缓存/Celery/日志/DRF）
│   │   │   ├── dev.py              #    开发环境（DEBUG=True，跨域放开）
│   │   │   └── prod.py             #    生产环境（强制 SECRET_KEY + HTTPS 头）
│   │   ├── urls.py                 #    总路由 + handler404 / handler500
│   │   ├── celery.py               #    Celery 应用 + Beat 定时任务
│   │   ├── wsgi.py                 #    WSGI（生产用 waitress）
│   │   └── asgi.py                 #    ASGI（AI 流式响应用）
│   │
│   ├── scripts/
│   │   ├── test_db.py              # ✅ 数据库连通性测试（MySQL + Redis）
│   │   └── grant_test_db.py        # ✅ 授予测试库权限（跑 test 前执行一次）
│   │
│   └── apps/                       # ✅ 6 个业务 app
│       ├── common/                 #    公共组件
│       │   ├── models.py           #      TimeStampedModel 抽象基类
│       │   ├── pagination.py       #      标准分页器（含总页数等元信息）
│       │   ├── response.py         #      统一响应封装 + 业务错误码
│       │   ├── exceptions.py       #      全局异常处理 + 404/500 JSON 化
│       │   ├── views.py            #      健康检查（真实探测 DB + Redis）
│       │   ├── tasks.py            #      Celery 任务（缓存清理 / ping）
│       │   └── tests_404.py        #      5 个单元测试
│       ├── accounts/               #    用户与 JWT（阶段二填充）
│       ├── videos/                 #    ✅ 核心数据模型
│       │   ├── models.py           #      Partition / UpUser / Video / Danmaku
│       │   ├── admin.py            #      Admin 后台配置
│       │   └── migrations/         #      0001_initial（已应用）
│       ├── spider/                 #    ✅ 数据采集（阶段二完成）
│       │   ├── base.py             #      BaseSpider 抽象基类（限速/重试/UA/日志）
│       │   ├── constants.py        #      接口地址 + 15 个分区 tid 表 + 数据实体
│       │   ├── parsers.py          #      纯解析函数（视频JSON + 弹幕protobuf）
│       │   ├── bilibili.py         #      BiliBiliSpider 具体实现
│       │   ├── persistence.py      #      幂等入库（upsert_video/danmaku/upuser）
│       │   ├── tasks.py            #      5 个 Celery 异步任务
│       │   ├── models.py           #      CrawlTask 任务记录
│       │   ├── admin.py            #      任务记录后台
│       │   ├── tests.py            #      25 个离线单元测试 ✅
│       │   ├── migrations/         #      0001_initial（已应用）
│       │   └── management/commands/
│       │       ├── crawl.py        #      manage.py crawl（命令行抓取）
│       │       └── seed_demo.py    #      manage.py seed_demo（离线演示数据）
│       ├── analytics/              #    聚合统计（阶段三填充）
│       └── ai/                     #    ✅ 模型完成，RAG 待阶段五
│           └── models.py           #      ChatSession / ChatMessage
│
└── frontend/                       # Vue 3 前端（阶段四创建）
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.ts
        ├── App.vue
        ├── api/                    # Axios 封装（统一响应拦截）
        ├── router/                 # 路由（懒加载）
        ├── stores/                 # Pinia
        ├── components/
        │   ├── charts/             # ECharts 封装（按需引入）
        │   └── AiAssistant/        # AI 悬浮助手
        └── views/
            ├── Dashboard/          # 数据大屏
            ├── VideoList/
            ├── VideoDetail/
            ├── Sentiment/          # 情感分析
            └── AiChat/             # AI 问答
```

### 阶段一设计要点

| 设计决策 | 理由 |
| --- | --- |
| **不自定义 User 模型** | Django 官方建议项目初期就定；本项目登录需求简单，内置 User 够用，降低迁移风险。将来扩展用 `UserProfile` 一对一附加即可 |
| **`config/__init__.py` 里注册 PyMySQL** | Django 加载 MySQL 后端的时机早于 settings 执行体，必须在此完成 `install_as_MySQLdb()` |
| **`config/__init__.py` 暴露 `celery_app`** | `celery -A config worker` 需要从包属性中找到 app 实例 |
| **`interaction_rate` 冗余存储** | 榜单要按互动率排序，实时计算需全表扫描；入库时算好可显著提速（对应"代码优化"加分项） |
| **弹幕独立成表** | 热门视频弹幕可达数万条，塞进 Video 表会导致主表膨胀 |
| **`handler404/500` 返回 JSON** | 前端 Axios 拦截器需统一结构；Django 默认返回 HTML 页面 |
| **settings 分 base/dev/prod** | 生产强制校验 SECRET_KEY 与 ALLOWED_HOSTS，避免误用开发配置上线 |

> ✅ 标记的为**已完成并实测通过**；未标记的目录为阶段二至五的计划结构。

---

## 十、测试与性能优化

### 10.1 压测（JMeter / Locust）

```powershell
# Locust
pip install locust
locust -f tests/locustfile.py --host http://127.0.0.1:8000

# JMeter（需先安装，见 4.2）——GUI 模式
jmeter -t tests/biliinsight.jmx
```

### 10.2 优化对照表（报告"代码优化"章节直接用）

| 层面 | 优化前 | 优化后 | 手段 |
| --- | --- | --- | --- |
| 数据库 | 视频列表 N+1 查询 | 1 次 JOIN | `select_related('upuser', 'partition')` |
| 数据库 | 热榜全表扫描 | 索引命中 | `bvid`/`partition_id`/`pubdate` 建索引 |
| 缓存 | 每次请求查库 | 命中 Redis | 热榜 5 分钟 TTL，榜单 10 分钟 |
| 后端 | 爬虫阻塞请求 | 异步化 | Celery + Redis Broker |
| 后端 | 同步 AI 推理 | 异步 + SSE | Celery 任务 + 流式响应 |
| 前端 | 全量引入 ECharts | 按需引入 | `echarts/core` + 手动注册组件 |
| 前端 | 路由全量打包 | 懒加载 | `() => import()` 动态导入 |
| 前端 | 长列表卡顿 | 分页/虚拟滚动 | 后端分页 + 组件懒加载 |

> 建议实测并记录**优化前后 QPS / P95 延迟**，截图放进报告。

### 10.3 前端性能评估

用 Chrome DevTools → Lighthouse，目标：

- Performance ≥ 85
- First Contentful Paint < 1.5s
- Largest Contentful Paint < 2.5s

---

## 十一、常见问题排查

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| **点击视频详情后约 2 秒被弹回列表** | 早期实现在"视频不存在"时用 `setTimeout(() => router.replace(...), 1500)` 自动跳回，用户来不及看提示，也无法判断原因 | 已改为**停留展示错误页**（`el-result` + 原因说明 + 手动「返回列表 / 重试」按钮），把控制权交回用户 |
| **页面上的 BV 号在B站搜索不到** | 该条数据由 `seed_demo` 生成，**bvid 是虚构值**。已标记 `is_demo=True`，界面显示「模拟数据」标签并隐藏跳转入口 | 抓真实数据：`python manage.py crawl --partition 科技 --limit 100 --interval 5`；用 `mark_data_source --status` 查看真实/模拟比例。**当前库内已有 97 条真实数据，可按 `data_source` 筛选查看** |
| **重跑 `seed_demo` 后旧链接 404** | 早期 bvid 用 `random` 生成，每次重建都变，前端缓存的旧链接即失效 | 已改为**基于索引的确定性哈希**（`_deterministic_bvid`）。⚠️ 注意 `hash()` 不可用——它对字符串加随机盐（`PYTHONHASHSEED`），必须用 `hashlib` |
| **测试在"已配置真实密钥"的机器上失败** | 测试断言"无 Key 时应不可用"，但本机 `.env` 已配 Key，且环境变量优先级更高 | 测试中显式清空：`with override_settings(DEEPSEEK_API_KEY=""):` |
| **改了 `.env` 但配的 AI Provider 不生效**，状态仍显示 `fallback` / 旧 Provider | **`.env` 只在进程启动时读取一次**。旧的后端进程内存里仍是启动时的旧配置 | **重启后端**（`Ctrl+C` 后重新 `runserver`）。另外 `.env` 中 `DEEPSEEK_MODEL` 必须填 `deepseek-flash`，不是版本名 `deepseek-v4.1-flash` |
| 改了 `.env` 重启后**仍不生效** | **环境变量优先级高于 `.env`**；若进程环境里有同名变量会覆盖文件配置 | 检查是否有同名环境变量：`Get-ChildItem Env: \| Where-Object Name -like "*DEEPSEEK*"`。诊断脚本会报告此情况 |
| **SSE 流式接口整体 500**，日志报 `AssertionError: Hop-by-hop header, 'Connection: keep-alive', not allowed` | `Connection` 是 **HTTP 逐跳头（hop-by-hop）**，WSGI 规范禁止应用层设置，`wsgiref` 会直接断言失败 | 从 `StreamingHttpResponse` 中**移除** `Connection` 头；`Cache-Control` 与 `X-Accel-Buffering` 可保留（后者告诉 Nginx 不要缓冲） |
| 测试中 ChromaDB 报 `error code: 14 unable to open database file` | ChromaDB 无法在**系统临时目录**（`%TEMP%`）打开其 SQLite 文件 | 把向量库目录放在**项目内**（如 `backend/data/`）。测试用 `backend/data/_test_chroma_*` 并在 tearDown 清理 |
| **AI 助手状态显示"索引就绪"，但提问永远回答"没有相关视频"** | **向量化器与索引维度不匹配的静默失败**。本地 TF-IDF+SVD 的输出维度随语料规模变化（297 条→256 维，40 条→39 维）；重建索引后 Web 进程缓存的仍是旧实例，而 `search()` 只在"完全未训练"时才加载磁盘状态，异常又被 `except: return []` 吞掉 | 已修复：集合元数据记录 `embedding_dim` 与语料指纹，检索前校验并自动重载。手工排查：对比 `/api/ai/status/` 的 `dim` 与 `build_index` 输出的维度是否一致。**重建索引后建议重启后端** |
| 在 CMD 里跑 `Activate.ps1` 后 `python manage.py` 报 **`No module named 'django'`** | `Activate.ps1` 是 **PowerShell 脚本**，在 CMD 里执行会**静默失败**（不报错也不生效），于是 `python` 落到全局解释器上 | 用 CMD 的激活脚本 `.venv\Scripts\activate.bat`；或**不激活直接用全路径** `.venv\Scripts\python.exe manage.py runserver`（最不易出错） |
| 不确定虚拟环境是否激活 | 看提示符：激活后前面会有 `(.venv)` | ✅ `(.venv) PS E:\...\backend>`　❌ `E:\...\backend>`（未激活） |
| **接口错误返回 `{"detail": "..."}` 而不是 `{"code":...}`** | DRF 默认错误格式；**`REST_FRAMEWORK` 里漏配 `EXCEPTION_HANDLER`**，自定义处理器从未被调用 | 在 `settings/base.py` 的 `REST_FRAMEWORK` 中加入 `"EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler"` |
| **缓存清理"成功"但一个键都没删** | Django 内置 `RedisCache` **没有 `delete_pattern()`**（该方法属于第三方包 django-redis）；`hasattr` 判断永远为假，静默失效 | 用 `cache_utils.delete_pattern()`（基于 SCAN 自实现），并加测试断言"清理后缓存确实不存在" |
| 缓存键出现 `biliinsight:1:biliinsight:analytics:x` 双前缀 | Django 自动拼接 `KEY_PREFIX:版本号:业务键`，我又手工加了前缀 | 业务代码只写 `"analytics:x"`，前缀交给 Django；用 `cache.make_key()` 查看真实键名 |
| 抓取报 **`接口返回业务错误 code=-352`** | **B站风控拦截**。风险码：`-352` 请求过于频繁 / `-412` 被拦截 / `-509`、`-799` 频率超限 | ⚠️ **切勿立即重试**——风控按请求频率累积，重试会延长封禁。处理优先级：**① 换网络环境（手机热点，实测最快最有效）**；② 等待 10-30 分钟冷却；③ 用 `crawl_with_backoff.py` 指数退避；④ 调整 `SPIDER_REQUEST_INTERVAL`（**实测作用很小**） |
| **调整了 `SPIDER_REQUEST_INTERVAL` 仍被风控** | ⚠️ 实测发现：**风控按"短时间窗口内的请求次数"判定，与请求间隔关系不大**。冷却后第 1 次请求成功，紧接着的第 2 次就被拦——此时把间隔从 4 秒调到 8 秒也无效 | **换出口 IP**（手机热点）是唯一可靠解法，本项目即以此成功。不方便换网络时再用 `scripts/crawl_with_backoff.py`：**长时间等待 + 单次尝试 + 指数退避**（30 分钟 → 45 分钟） |
| **风控场景下怎么抓最多数据** | 单次请求能拿多少与 `--limit` 无关：`run_partition()` **只发 1 次** HTTP 请求，排行榜一次返回约 97 条，`--limit` 仅控制本地入库条数 | **把 `--limit` 开到接口上限（100）**。`--limit 30` 与 `--limit 100` 风控代价完全相同，但数据量差 3 倍 |
| **抓弹幕时 `--limit 50` 却入库了几千条** | `--limit` **不是严格的条数上限**：代码只在**包与包之间**检查 `collected >= limit`，而一包（6 分钟）内的弹幕是**整包入库**的 | 这是设计使然，可放心用。若想"只抓一包就停"以节省请求，就用 `--limit 50`；想抓更多包则调大 |
| **抓弹幕该挑什么样的视频** | 弹幕按 **6 分钟一包** 返回，**请求次数由视频时长决定，与弹幕总量无关** | 挑**短视频**。实测 39,319 条弹幕的视频（165 秒）只要 2 次请求，而 1,190 秒的视频要抓更多包 |
| **前端 `http://127.0.0.1:8080` 打不开，但服务明明在跑** | Vite dev server 默认监听 **IPv6 loopback `[::1]`**，未绑定 IPv4 `127.0.0.1`。`netstat` 可见 `[::1]:8080 LISTENING` | 改用 **`http://localhost:8080`**（会解析到 `::1`）。或在 `vite.config.ts` 设 `server.host: '127.0.0.1'` |
| **`Get-NetTCPConnection` 显示端口未监听，但服务实际可用** | 该 cmdlet 在本机环境下会漏报（实测 3307/6379/8000 均在监听却查不到） | 用 **`netstat -ano \| Select-String "LISTENING"`** 复核。判断服务是否可用，**直接发一次请求比查端口更可靠** |
| **抓完数据后"视频列表更新了，但总览/排行榜/情感分析没变"** | **写入数据后没有清分析缓存**。`/api/videos/` 无缓存所以立刻生效，而 `/api/analytics/*` 带 300-600 秒缓存仍是旧值。看起来像"只同步了一半" | 已在 `_finish_task` 与 `crawl`/`seed_demo`/`mark_data_source` 中统一清理。手工清理：`python -c "…clear_analytics_cache()"`，或直接 `redis-cli FLUSHDB`。**注意：重启后端无效** —— 实测过期缓存能跨进程重启存活 |
| **改了后端代码但接口返回值没变** | 开发服务器若用 `--noreload` 启动，**不会自动加载新代码** | 重启后端。判断方法：看返回 JSON 里有没有新加的字段 |
| **改了 `.vue` 文件后编辑工具报 `ReplaceFileW EIO (Win32 32)`** | Windows 上 `ReplaceFileW` 在 E: 盘该目录会失败（文件未被独占锁定，但原子替换失败） | 改用 Python 脚本读入→替换→`write_text()` 写回（见 `scripts/patch_*.py`）；或用 `Set-Content` 直接覆写 |
| **`Get-NetTCPConnection` 报端口未监听但能访问 / 前端 `127.0.0.1:8080` 打不开** | ① 该 cmdlet 会漏报；② Vite 只绑了 IPv6 `[::1]` | ① 用 `netstat -ano`；② 访问 **`http://localhost:8080`** 而不是 `127.0.0.1:8080` |
| `argparse.ArgumentError: argument --videos/-v: conflicting option string: -v` | Django 的 `BaseCommand` 已内置 `-v/--verbosity`，自定义命令**不能再用 `-v`** | 改用长选项（`--videos`），或换 `-n` 等其他短名 |
| `ValueError: bulk_create() prohibited to prevent data loss due to unsaved related object 'video'` | **`bulk_create` 不回填主键**（Django 已知限制），未保存的实例 `pk` 仍为 `None`，无法作为外键 | 插入后按唯一键（如 `bvid`）**重新查回**带主键的实例，再用它建立关联 |
| 脚本报 `ModuleNotFoundError: No module named 'config'` | 脚本放在 `backend/scripts/` 下，Python 搜索路径不含 `backend/` | 在脚本开头 `sys.path.insert(0, str(Path(__file__).parent.parent))` |
| `ModuleNotFoundError: No module named 'drf_spectacular.urls'` | drf-spectacular **0.28 没有 urls 模块** | 直接引用视图类：`SpectacularAPIView` / `SpectacularSwaggerView` / `SpectacularRedocView` |
| `manage.py test` 报 `(1044, "Access denied ... 'test_biliinsight'")` | `bili` 用户只有 `biliinsight` 库权限，测试库需单独授权 | `python scripts\grant_test_db.py`（用 root 授权，仅授测试库） |
| 测试之间互相污染（删了数据却仍统计出旧值） | 统计结果缓存在 **Redis** 中，而 Redis 在测试方法之间共享、不会被 TestCase 回滚 | 在 `setUp` 中调用 `clear_analytics_cache()` |
| `AttributeError: 'RedisCache' object has no attribute 'client'` | Django 5.x 的 RedisCache 不暴露公开 client 属性 | 底层连接在私有 `cache._cache`（RedisCacheClient），需调用 `.get_client()` |
| DEBUG=True 时 404 返回 HTML 而不是 JSON | Django 仅在 **DEBUG=False** 时使用 `handler404` | 这是预期行为；用 `override_settings(DEBUG=False)` 写测试验证，生产环境自动生效 |
| 下载安装包时提示 **"Microsoft Defender SmartScreen 无法扫描此文件"** | 大文件超出 SmartScreen 云查杀上限，**正常现象非报错** | 点 `···` → **「保留」**，然后按 [4.4](#44-安装包安全验证) 核对数字签名 |
| `Activate.ps1 无法加载，因为在此系统上禁止运行脚本` | PowerShell 执行策略 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `django.db.utils.OperationalError: (2003) Can't connect to MySQL` | MySQL 未启动或端口错 | `Get-Service MySQL80` 确认 Running；`Test-NetConnection 127.0.0.1 -Port 3306` |
| `Access denied for user 'bili'@'localhost'` | 账号未建或密码不符 | 重跑 [B-1](#b-1-安装-mysql-80) 里的建库建号语句，核对 `.env` 中 `MYSQL_PASSWORD` |
| `redis.exceptions.ConnectionError` | Redis/Memurai 未启动 | `Get-Service Memurai`；`& "C:\Program Files\Memurai\memurai-cli.exe" ping` 应返回 PONG |
| 找不到 `redis-cli` 命令 | Memurai 的客户端叫 **`memurai-cli`** | 用 `memurai-cli` 代替，或把 `memurai-cli.exe` 复制改名为 `redis-cli.exe` |
| Docker 卡在 **"Starting the Docker Engine..."** 无限转圈 | **WSL2 / 虚拟机平台未启用** | 按 [路径 C](#路径-c确实想用-docker必须先启用-wsl2) 启用 WSL2 并重启；或改用 [路径 B](#路径-b完全不用-dockermysql--memurai--本机推荐) |
| Docker Desktop 安装完成后无法启动，报 WSL 版本错误 | 未设默认版本 | `wsl --set-default-version 2` + `wsl --update` |
| `mysqlclient` 安装失败 | Windows 缺 C 编译环境 | 本项目已改用 `PyMySQL`，无需编译；确认 `requirements.txt` 未误装 `mysqlclient` |
| Celery 在 Windows 卡住 / `Task received but not executing` | 默认 prefork 池不兼容 Windows | **必须加 `-P solo`**：`celery -A config worker -l info -P solo` |
| Celery Worker 收不到任务 | 未连同一 Broker | 检查 `.env` 的 `CELERY_BROKER_URL` 与 Django 一致，且 Redis/Memurai 在运行 |
| `mysql.exe` 不是内部或外部命令 | MySQL bin 未加入 PATH | 用全路径 `& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"`，或把该目录加入系统 PATH |
| PaddleNLP 下载模型超时 | 默认走外网 | 设置 `$env:HF_ENDPOINT="https://hf-mirror.com"`，或提前离线下载模型 |
| `paddlepaddle` 安装报找不到匹配版本 | 索引源不对 | 用官方源：`-i https://www.paddlepaddle.org.cn/packages/stable/cpu/` |
| Ollama 连接被拒绝 `11434` | 服务未启动 / 不在 PATH | 见 [7.3](#73-方案b本地-ollama零密钥可离线) |
| 前端请求 404 / CORS | 代理未生效 | 确认 `vite.config.ts` 的 `proxy`，请求走 `/api` 前缀而非绝对地址 |
| `npm install` 缓慢或失败 | 默认源在国外 | `npm config set registry https://registry.npmmirror.com` |
| 端口被占用 | 其它程序占用 | `netstat -ano | findstr :8000` 找到 PID 后结束进程 |
| MySQL 安装时 `Initializing database` 失败，日志报 `File '.\???bin.index' not found (OS errno 2)` | **计算机名是中文**（本机为 `清`），MySQL Installer 用计算机名作日志文件前缀，生成 `清-bin` 后 mysqld 无法处理非 ASCII 路径 | 改 `my.ini` 中 4 处为 ASCII：`general_log_file`、`slow_query_log_file`、`log-error`、`log-bin`；删除 `Data` 目录后重新 Execute（详见 [附录 B](#附录-bwindows-中文计算机名导致-mysql-初始化失败)） |
| Memurai 突然停止服务 | **Developer 版有 10 天运行限制** | 管理员执行 `Restart-Service Memurai` 重置；答辩前记得重启一次 |

---

## 十二、数据合规声明

> ⚠️ **务必遵守，否则可能影响评分甚至带来法律风险。**

1. **遵守 robots.txt**：爬虫启动前先拉取并解析目标站点 `robots.txt`；
2. **控制请求频率**：`SPIDER_REQUEST_INTERVAL` **不得低于 1.0 秒**，默认 2.0 秒，禁止并发轰炸；
3. **仅采集公开数据**：不碰登录态、不碰用户隐私字段、不绕过任何风控；
4. **明确用途声明**：所有代码文件头部与 README 均注明 **"仅用于学习研究，禁止商业用途"**；
5. **数据不对外分发**：数据集仅本地留存，仓库中不提交原始爬取数据（`.gitignore` 已排除 `data/`）；
6. **尊重版权**：视频封面、标题等仅作分析展示，不二次分发原始内容。

---

## 十三、团队分工

| 角色 | 职责 | 关键交付 |
| --- | --- | --- |
| **组长 / 后端 & 数据库** | 架构设计、Django API、MySQL 表结构、Redis 缓存、JWT、Git 分支管理 | `backend/apps/*`、ER 图、接口文档 |
| **前端 & 可视化** | Vue3 + Element Plus 页面、ECharts 图表、前后端联调、性能优化 | `frontend/src/*`、Lighthouse 报告 |
| **爬虫 & 算法 & AI** | B站爬虫、Pandas 清洗、Scikit-learn 聚类/推荐、PaddleNLP 情感分析、LangChain RAG | `apps/spider/*`、`apps/ai/*`、算法说明 |

> **2 人组**：一人「后端 + 爬虫 + AI」，一人「前端 + 可视化 + 数据库」。
> **4 人组**：把「爬虫」与「算法/AI」再拆开，各司其职。

### Git 协作流程

```powershell
git checkout -b feature/spider-base        # 从 develop 切功能分支
# ... 开发 ...
git add .; git commit -m "feat(spider): 新增 BaseSpider 抽象基类"
git push origin feature/spider-base        # 提 PR/MR 到 develop
```

分支模型：`main`（可发布）← `develop`（集成）← `feature/*`（功能）

---

## 十四、答辩自查清单

### 交付物

- [ ] 源代码（前后端完整）
- [ ] `README.md`（本文档）
- [ ] Gitee / GitHub 仓库链接 + 完整提交记录
- [ ] 2 分钟演示视频
- [ ] 项目报告（PDF / Word）

### 演示脚本（2 分钟建议节奏）

| 时间 | 内容 |
| --- | --- |
| 0:00–0:20 | 项目背景与架构图（讲清解决什么问题） |
| 0:20–0:50 | **爬虫实时运行**（终端滚动日志 + 数据入库） |
| 0:50–1:20 | **数据大屏**（趋势图、分区占比、词云、UP主排行） |
| 1:20–1:45 | **弹幕情感分析**（情绪波动图 + 关键词云） |
| 1:45–2:00 | **AI 问答互动**（提问 → 流式回答，展示 RAG 命中） |

### 技术自查

- [ ] `requirements.txt` / `package.json` **锁定精确版本号**（防答辩现场崩）
- [ ] `.env.example` 齐全，`.env` 已加入 `.gitignore`
- [ ] 所有服务能一键启动（写完 `start-all.ps1`）
- [ ] AI 助手**双 Provider 已实测**（DashScope 挂了能切 Ollama）
- [ ] 优化前后有**量化对比数据**
- [ ] 爬虫限速参数可见、合规声明完整
- [ ] 数据库有**索引**、Redis **缓存命中**能在日志中看到

---

## 附录 A：本机环境实测原始结论

```
检测时间：2026-09-14
操作系统：Windows 11 (10.0.26100)

【已安装】
Python 3.13.13        D:\develop\python\python.exe
pip 26.0.1
Node.js v24.16.0      D:\develop\nodeJS\node.exe
npm 11.13.0
Git 2.47.1.windows.1
PyCharm 2026.1.5 Professional   D:\develop\pycharm\PyCharm 2026.1.1\bin\pycharm64.exe
Apifox 2.8.32         D:\develop\apifox\Apifox.exe
Ollama 0.7.0 (deepseek-r1:8b, 4.87 GB)   D:\develop\ollama\
IntelliJ IDEA 2025.2.4
JDK 21.0.8 LTS / javac 21.0.8
.NET SDK 9.0.100

【缺失，需安装】
MySQL 8.0             -> https://dev.mysql.com/downloads/installer/          [P0]
Memurai (替代 Redis)  -> https://www.memurai.com/get-memurai                 [P0]
Docker Desktop        -> https://www.docker.com/products/docker-desktop/     [P1，当前不可用，见下]
DBeaver Community     -> https://dbeaver.io/download/                        [P1，可被 MySQL Workbench 替代]
Apache JMeter         -> https://jmeter.apache.org/download_jmeter.cgi      [P2]
Python 3.11 (可选)    -> https://www.python.org/downloads/release/python-3119/  [P2，本机不需要]

【端口占用检测】
3306 / 6379 / 8000 / 8080 / 5173 / 11434  均空闲

【关键兼容性结论】
- paddlepaddle-3.3.1-cp313-cp313-win_amd64.whl 存在 -> Python 3.13 可用，无需降级到 3.11
- Django 5.2 LTS 支持 Python 3.10-3.13
- Node 24 >= 18，满足前端要求
- PyCharm 为 Professional 版 (productCode=PY)，满足 rdme.txt 的强制要求
- winget 存在于 WindowsApps 别名路径，但在受限 shell 中无法调用 -> 请用手动下载

【虚拟化与 Docker 前置检查 —— 重要】
- wsl.exe 存在，但 `wsl --status` 返回 Wsl/EnumerateDistros/Service/E_ACCESSDENIED
- CBS 中 VirtualMachinePlatform 包为 ...Client-Disabled-FOD-Package...  -> 处于 Disabled
- 未检测到 Microsoft-Windows-Subsystem-Linux 已启用
- 结论：Docker Desktop 当前【装上也起不来】，会卡在 "Starting the Docker Engine..."
        => 推荐改用【路径 B：MySQL + Memurai】，无需虚拟化、无需重启
        => 若坚持用 Docker，须先启用 WSL2 并重启（见路径 C）

【Docker 残留】
- C:\Program Files\Docker 存在但为空目录（上次安装失败的残留）
- 注册表 HKLM\SOFTWARE\Docker Inc. 与 Uninstall\Docker Desktop 均不存在（非有效安装）
- 开始菜单 ...\Programs\docker-desktop 存在但为空目录
- 确定不用 Docker 后可按 B-4 清理（需管理员）

【浏览器下载目录】
- Edge savefile 默认目录 = E:\Downloads （不是 C:\Users\11140\Downloads）
```

---

## 附录 B：Windows 中文计算机名导致 MySQL 初始化失败

> 本机实际踩过的坑，完整记录以便复现与排查。

### 现象

MySQL Installer 配置阶段报错：

```
Apply Configuration
  ✅ Writing configuration file
  ✅ Updating Windows Firewall rules
  ✅ Adjusting Windows service
  ❌ Initializing database (may take a long time)
The configuration for MySQL Server 8.0.46 has failed.
```

### 定位过程

查看安装日志 `C:\ProgramData\MySQL\MySQL Installer for Windows\Logs\<用户>-installer.log`：

```
Attempting to run MySQL Server with --initialize-insecure option...
Starting process with command: E:\MySQL\MySQL Server 8.0\bin\mysqld.exe
  --defaults-file="E:\MySQL\MySQL Server 8.0\my.ini" --console --initialize-insecure=on ...
mysqld: File '.\娓?bin.index' not found (OS errno 2 - No such file or directory)
The newly created data directory E:\MySQL\MySQL Server 8.0\Data\ by --initialize is unusable.
Aborting
Database initialization failed.
```

`.\娓?` 是**中文乱码**。再查 `my.ini`，发现 4 行含中文"清"：

```ini
general_log_file="清.log"
slow_query_log_file="清-slow.log"
log-error="清.err"
log-bin="清-bin"          # ← 元凶：mysqld 需创建 清-bin.index
```

### 根因

```powershell
COMPUTERNAME   # 输出：清
```

**计算机名是一个中文字 `清`（U+6E05）**。MySQL Installer 会把**计算机名**作为日志文件名的前缀，
写入 `my.ini`。于是 `log-bin="清-bin"` 让 mysqld 需要创建 `清-bin.index`，
而 mysqld 在 Windows 上对非 ASCII 路径处理有缺陷，直接 `abort`。

**这与用户名、安装路径是否含中文无关**——安装路径 `E:\MySQL\MySQL Server 8.0\` 完全是 ASCII。

### 解决步骤

**1. 修改 `my.ini`，把 4 处中文换成 ASCII**（需管理员）

```powershell
$f = "E:\MySQL\MySQL Server 8.0\my.ini"
$c = Get-Content $f -Raw -Encoding UTF8
$c = $c -replace 'general_log_file="清\.log"',       'general_log_file="mysql-general.log"'
$c = $c -replace 'slow_query_log_file="清-slow\.log"','slow_query_log_file="mysql-slow.log"'
$c = $c -replace 'log-error="清\.err"',              'log-error="mysql.err"'
$c = $c -replace 'log-bin="清-bin"',                 'log-bin="mysql-bin"'
[System.IO.File]::WriteAllText($f, $c, (New-Object System.Text.UTF8Encoding($false)))
(Select-String -Path $f -Pattern '[\u4e00-\u9fff]').Count    # 应为 0
```

**2. 删除失败的数据目录**（需管理员，该目录 ACL 仅授予 `NT AUTHORITY\NetworkService`）

```powershell
Remove-Item "E:\MySQL\MySQL Server 8.0\Data" -Recurse -Force
```

**3. 回到 MySQL Installer 点 `Execute` 重试**（无需回退或重装）

**4. 验证**

```powershell
Get-Service MySQL80      # 期望 Status = Running
```

### 经验总结

1. **Windows 上的 MySQL / MariaDB 对非 ASCII 极其敏感**。计算机名、服务名、安装路径、数据路径
   全部使用 ASCII 最稳妥。
2. **不建议为此改计算机名**——需重启且影响其他软件绑定，改 `my.ini` 是更小代价的修法。
3. **`Data` 目录删不掉是正常的**：安装器将其 ACL 设为仅 `NetworkService` + 管理员，
   普通权限必然 `Access to the path is denied`，必须提权操作。
4. 遇到 MySQL 安装失败，**第一时间看这个日志**：
   `C:\ProgramData\MySQL\MySQL Installer for Windows\Logs\<用户名>-installer.log`，
   里面 `mysqld:` 开头的行就是真正原因。

---

## 附录 C：桌面版打包与分发

> 目标：做一个**能发给老师/同学、双击就能用**的桌面应用，
> 并且**打包后仍然能更新数据**。

### C.1 先回答那个关键疑问：打包后还能更新数据吗？

**能。** 这个问题容易让人犹豫，是因为把"打包"和"数据"混在一起了。
把数据链路拆开看就很清楚：

```
点「立即更新数据」
   ├─ ① 请求 api.bilibili.com      ← 运行时行为，需要网络
   ├─ ② 写入 data\biliinsight.db   ← 运行时行为，SQLite 是外部文件，可写
   └─ ③ 前端读接口重绘图表          ← 运行时行为，服务在同一进程里
```

**打包只冻结「代码 + Python 解释器」，它既不冻结网络，也不冻结数据库。**

还有一个常见误解值得点明：exe 本身是只读的，但**数据库并没有塞进 exe** ——
它是 exe 旁边 `data\` 目录下的一个独立文件，可写可更新。
所以数据层完全不受打包影响。

### C.2 真正的难点：三个外部服务从哪来

开发形态依赖三个独立服务，这对"发给别人安装"完全不现实：

| 组件 | 开发形态 | 桌面形态 | 为什么能这样换 |
| --- | --- | --- | --- |
| 数据库 | MySQL 8.0（3307） | **SQLite** | 业务代码没有用任何 MySQL 专有特性（无 JSONField / ArrayField / 原生 SQL），唯一一处 `SELECT VERSION()` 已做方言适配 |
| 缓存 | Redis（6379） | **LocMemCache** | 业务一直通过 Django cache 抽象访问，换后端不改业务代码 |
| 异步任务 | Celery Worker + Beat | **同步执行** | 桌面单用户不需要任务队列；抓取直接同步跑，前端能拿真实进度 |
| 向量库 | ChromaDB | ChromaDB（不变） | 本来就是嵌入式 PersistentClient |
| 前端 | Vite 开发服务器（8080） | **Django 直接托管 dist** | 新增 SPA 兜底路由 + WhiteNoise |

于是整个应用从"4 个进程 + 2 个中间件"变成**1 个进程**：

```
BiliInsight.exe
  ├─ pywebview 窗口（复用系统自带 WebView2，不额外塞 Chromium）
  ├─ waitress（后台线程，WSGI 服务）
  ├─ Django（应用 + 前端静态文件）
  └─ SQLite + ChromaDB（data\ 目录下）
```

### C.3 与"离线可用"的设计取舍

桌面版带了**一份预置数据集**（40 条真实视频 + 6720 条弹幕 + 情感标注），
首次启动自动导入。这解决了两件现实问题：

1. **拿到手就能看懂**：不是一片空图表，而是完整可浏览的看板；
2. **答辩现场没网也能演示**：有网则再演示「更新数据」。

启动时初始化逻辑（`apps/common/bootstrap.py`）全部**幂等**：

```
migrate            —— Django 自带幂等，已应用的迁移跳过
导入预置数据        —— 只在视频表为空时执行
构建向量索引        —— 只在索引条数与视频数不一致时重建
```

### C.4 文件清单与产物

| 文件 / 目录 | 作用 |
| --- | --- |
| `backend/config/settings/desktop.py` | 桌面版配置（SQLite / LocMemCache / 关闭 Celery / 路径解析） |
| `backend/desktop_main.py` | 启动器：先显示启动画面 → 初始化 → 起 waitress → 切到应用页 |
| `backend/apps/common/bootstrap.py` | 首次启动初始化（建表 / 导入预置数据 / 建索引 / 开 WAL） |
| `backend/apps/common/spa.py` | 托管前端产物：真实文件直出，其余回退 index.html |
| `backend/apps/spider/views.py` | 抓取接口（同步抓排行榜 + 后台补全任务） |
| `backend/build_desktop.spec` | PyInstaller 打包配置 |
| `backend/使用说明.txt` | 随包分发给接收者的说明书 |

**产物**：

```
backend\dist_desktop\BiliInsight\   ← 免安装目录（解压即用）
release\BiliInsight-Desktop-win64.zip  ← 200.7 MB（解压后 416.4 MB）
```

> 分发方式：把 zip 发给对方，解压到**非 C:\Program Files** 的位置，
> 双击 `BiliInsight.exe` 即可。首次启动约 13 秒（导入预置数据 + 建索引）。

构建命令：

```bash
cd backend
python -m PyInstaller build_desktop.spec --noconfirm --clean
```

### C.5 这一轮踩过的坑（都很值得记）

**坑 1：两个只在 `npm run build` 时才暴露的前端错误**

Vite 开发服务器**不做类型检查**，所以开发阶段一切正常，
真正打包时 `vue-tsc` 才报错：

| 报错 | 原因 | 修复 |
| --- | --- | --- |
| `TS1005: ',' expected` | 模板表达式里写了 TS 类型注解：`@row-click="(row: { bvid: string }) => ..."`。Vue 模板不支持类型注解 | 改成脚本里的具名函数 `@row-click="onRowClick"` |
| `TS2307: Cannot find module 'node:url'` | `vite.config.ts` 被纳入类型检查，但 `types` 只有 `vite/client`，缺 Node 类型 | 安装 `@types/node`，并在 `types` 中加入 `"node"` |

**教训：交付前必须真跑一次 `npm run build`，不能只靠 dev server。**

**坑 2：`celery.fixups` 缺失导致 exe 静默退出**

无控制台版本双击毫无反应。加上崩溃日志后才看到真正原因：

```
File "config/celery.py", line 31, in <module>
  app = Celery("biliinsight")
ModuleNotFoundError: No module named 'celery.fixups'
```

`config/__init__.py` 会导入 Celery，而 Celery 内部大量使用
**字符串动态导入**（`kombu.utils.imports.symbol_by_name`），
PyInstaller 的静态分析完全看不到这些路径。

修复：在 spec 里补上 `collect_submodules("celery")` / `kombu` / `billiard`。

**顺带得到一个必要的改进**：给启动器加了"崩溃现场保存" ——
无控制台时把堆栈写进 exe 同级的 `startup-error.log` 并弹 Windows 消息框。
否则这类问题对使用者就是"双击没反应"，对开发者也无从下手。

**坑 3：PyInstaller 6.x 把数据挪进了 `_internal\`**

6.x 的 onedir 结构与 5.x 不同：exe 在根目录，**依赖和数据都在 `_internal\`**。
如果按"exe 同级"去找前端产物和预置数据，打出来的应用会白屏。

修复：路径解析改为多候选探测，优先 `sys._MEIPASS`（PyInstaller 提供的资源根），
再 `_internal\`，最后才是 exe 同级 —— 这样无论 PyInstaller 版本怎么变都不踩空。

**坑 4：换缓存后端后，清缓存又静默失效了**

这是本项目**第二次**踩同一个坑（第一次是 `delete_pattern` 方法不存在）。
桌面版把 Redis 换成 LocMemCache 后，`get_raw_redis_client()` 返回 `None`，
`delete_pattern()` 直接 `return 0` —— 一个键都没删，于是
"点了更新数据但页面数字没变"。

修复：`cache_utils` 增加内存后端兜底，用 `fnmatch` 遍历 LocMemCache 的字典，
删除时走公开的 `cache.delete(业务键)`（不碰私有结构）。

**坑 5：`SO_REUSEADDR` 在 Windows 上会误判端口空闲**

探测端口时用了 `SO_REUSEADDR`。但 Windows 上它的语义与 Unix 不同：
**允许绑定已被监听的端口**。结果"探测通过"但起服务时两个进程抢同一端口，
表现为时好时坏的诡异故障。

修复：改用 `SO_EXCLUSIVEADDRUSE`（Windows 专有，禁止共享端口），
并先 `connect_ex` 探活再尝试绑定。

**坑 6：`请求 0 次` 的假统计**

`run_partition()` 返回的是"本次入库"的局部统计，其中 `requests` 恒为 0；
真正的请求计数在爬虫实例的 `spider.stats` 上。接口直接取局部统计，
于是页面显示"HTTP 请求 0 次"——看着像根本没联网，实际抓回了 97 条。

### C.6 验收记录

**构建**：PyInstaller 6.22.3 / Python 3.13.13 / Windows 11
**体积**：解压后 416.4 MB（6089 个文件），zip 后 200.7 MB
**主要体积来源**：chromadb rust 绑定 60.5 MB、numpy/scipy 39 MB、
snownlp 55 MB、jieba 41 MB —— 都是功能必需的，`onnxruntime`（44 MB）
与 `matplotlib`（30 MB）已确认可排除。

**端到端验收（从 zip 全新解压到独立目录）**：

```
解压耗时            6.8 秒
首次启动            12.6 秒（导入预置数据 40 条 + 建索引）
首页 SPA            HTTP 200
离线数据            视频 40 条 / UP主 40 位 / 弹幕情感 6720 条
AI 检索索引         40 条，ready=True
data 目录           自动生成（SQLite + WAL + ChromaDB）
崩溃日志            无
```

**联网更新数据（真实请求 B站）**：

```
解析 97 条 | 新增 0 | 更新 3 | HTTP 请求 1 次 | 耗时 0.55s | 清缓存 2 键
```

> 没有新增是因为这 3 条本来就在库里（排行榜只取前 3，已被收录）。
> 换更靠后的分区或更大条数就会看到"新增"。

**测试**：完整套件 **204/204 通过**（本轮新增 12 个桌面交付测试：
抓取接口、LocMemCache 兜底、SPA 托管与路径穿越防护）。

### C.7 分发给接收者时要知道的三件事

1. **不要解压到 `C:\Program Files`** —— 那里没有写权限，抓取会失败。
   放桌面、D 盘、E 盘都行。
2. **AI 助手的 API Key 需要自己填**：把 `config.example.json` 复制为
   `config.json` 并填入自己的密钥。
   **密钥绝不能打包进 exe** —— exe 里的字符串可被直接提取，等于公开它。
3. **抓取仍会受 B站 风控**：打包时不改变这一点。提示被限流时等几分钟再试，
   不要连续点。

### C.8 批量准备初始数据（300 条）

桌面版自带的初始数据集需要一定规模才撑得起图表。从 40 条扩到 317 条的
过程中发现了一个**关键规律**，值得单独记下来。

#### 关键发现：不同接口的风控配额完全不同

之前只知道"排行榜接口容易被拦"，这次有了对照：

| 接口 | 用途 | 实测表现 |
| --- | --- | --- |
| `/x/web-interface/ranking/v2` | 分区排行榜 | **最敏感**，连续抓 2-3 个分区就被 `-352` |
| `/x/web-interface/popular` | 全站热门 | **宽松**，连续 5 页（250 条）全部成功 |
| `/x/relation/stat` | UP主 粉丝数 | **宽松**，连续 265 次全部成功 |
| `/x/v2/dm/web/seg.so` | 弹幕分包 | **较敏感**，约 20 次后开始限流 |

**结论：被风控了要先问"是哪个接口被拦"，换接口往往还能继续抓。**
这条比"等 30 分钟再试"有用得多 —— 原先排行榜抓不动时，其实热门接口是通的。

#### 因此新增了 `--popular` 抓取方式

`constants.py` 里一直定义着 `BiliAPI.POPULAR`，但**从未被使用**过
（`run_hot` 走的其实还是 `ranking/v2`，只是不带 rid）。这次把它接上了：

```bash
# 抓全站热门，支持翻页：6 页 ≈ 300 条
python manage.py crawl --popular --limit 300 --pages 6 --interval 3
```

实测 5 页取回 250 条、零风控，比逐个分区抓高效得多。

#### 新增 `scripts/grow_dataset.py` 编排脚本

一次要发六七百个请求（视频 + 粉丝数 + 弹幕），不可能一口气跑完。脚本把
三个阶段串起来，并复用 `patient_crawl.py` 的自适应退避：

```bash
python scripts/grow_dataset.py --target 300 --with-followers --with-danmaku \
    --danmaku-limit 120 --interval 3
```

进度全部存在数据库里（待抓视频 = 目标 - 现有；待补粉丝数 = `follower_count == 0`；
待抓弹幕 = 没有关联 Danmaku），因此随时可中断、可续跑。

#### 途中修掉的一个 Bug

`crawl` 命令里有一段"未指定抓取目标则使用默认分区列表"的逻辑：

```python
if not any([partition, hot, danmaku, batch_danmaku]):
    partition = ",".join(DEFAULT_PARTITIONS)   # 自动跑一遍默认分区
```

新增 `--popular` 时**忘了把它加进这个判断**，于是：

```bash
manage.py crawl --popular    # 抓完热门后，又顺手抓了一遍「科技」分区
```

多花一次风控额度（当时正好被 `-352` 拦住）。这类"参数漏加进判断"的 Bug
不会报错，只会悄悄多发请求，已用测试钉住
（`tests_popular.py::PopularCommandTests`）。

#### 本次数据规模

| 项目 | 数量 | 说明 |
| --- | --- | --- |
| 视频 | **411 条** | 覆盖 70 个细分分区；封面、cid 全部就绪 |
| 弹幕 | **28627 条** | 覆盖 82 个视频；全部完成情感标注 |
| UP主 | **390 位** | 粉丝数 390 位全部补齐 |

预置数据集 `seed/preset_videos.json` 约 **10.8 MB**。
桌面版首次启动导入 + 建索引实测 **约 20 秒**（启动画面有进度提示）；
之后每次启动约 2 秒。

### C.9 长跑脚本的两个稳定性问题

用脚本连续抓数据（十几分钟、几百次请求）时踩到两个坑：

**① 数据库连接被掐断**

```
pymysql.err.OperationalError: (2013, 'Lost connection to MySQL server
during query (WinError 10053)')
```

跑完 265 位粉丝数、弹幕抓到 40/120 时崩了。
原因是风控冷却期间连接空闲几分钟，被服务端/中间设备断开。

修复：**每轮循环前调用 `django.db.close_old_connections()`**
（Django 在 Web 请求周期里会自动做，纯脚本需要自己调）。

**② MySQL 容器根本没在运行**

排查时发现 `error 10053` 的表象下面其实是更基础的问题：
Docker Desktop 没启动，`biliinsight-mysql` 容器是停的，
所以不是"连接超时"而是"连接被拒绝"。

```powershell
# 启动 Docker Desktop（装在 %LOCALAPPDATA%\Programs\DockerDesktop）
Start-Process "C:\Users\<你>\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"
docker compose up -d
docker inspect --format '{{.State.Health.Status}}' biliinsight-mysql
```

**教训：报"连接中断"时先确认服务本身还在不在**，
不要一上来就怀疑超时或网络。数据在 Docker 数据卷里，容器停了就等于库没了。

### C.10 「更新数据」按钮为什么"点了没反应还一直报风控"

这是桌面版试用手感最差的一处，值得单独记。

#### 现象

点一次「立即更新数据」之后，再看板数据没变化；
之后每次点击都弹：

> 被 B站 风控限流：请等待 2-10 分钟后重试（不要连续点击）

#### 根因：接口选错了，而且一次犯了两个错

最初这个按钮调用的是**分区排行榜** `/x/web-interface/ranking/v2`：

| 问题 | 后果 |
| --- | --- |
| 排行榜每次返回的都是**同一批 Top 100** | 抓过一次就全入库了，再点只会"更新 97 条、新增 0 条" —— 看起来像按钮坏了 |
| 排行榜恰恰是**风控最严**的接口 | 点一次就可能 `-352`，之后每次点都失败 |

也就是说：**"没有新数据"和"一直被风控"是两个独立问题，但恰好被同一个接口同时触发。**

#### 修复：换成「全站热门」+ 翻页游标

热门接口 `/x/web-interface/popular` 的两个特性正好对症：

- **支持翻页**（`ps` / `pn`），翻到后面的页几乎全是没见过的视频；
- **风控宽松**，实测连续 5 页 250 条零拦截。

再配合一个**翻页游标**（存在缓存里），每次点击从上一次的下一页继续：

```python
# apps/spider/views.py
start_page = _get_popular_cursor()      # 上次翻到哪了
stats = spider.run_popular(start_page=start_page, max_pages=1)
_set_popular_cursor(stats.last_page + 1)  # 下次从下一页继续
```

还加了一条"跳过已收录页"的策略：**某一页解析出来新增为 0 就继续读下一页**
（最多 10 页；一旦凑够界面填的「条数」就停），这样第一次点击也能拿到新数据。

#### 实测效果

连续点三次按钮：

| 次数 | 新增 | 更新 | 请求数 | 耗时 | 下次页码 |
| --- | --- | --- | --- | --- | --- |
| 第 1 次 | **+20** | 157 | 5 | 16.5s | 第 6 页 |
| 第 2 次 | **+35** | 5 | 1 | 5.1s | 第 7 页 |
| 第 3 次 | **+39** | 1 | 1 | 5.4s | 第 8 页 |

库内视频 317 → 337 → 372 → 411。**每次都有真实新增**，
且第二次起只需 1 次请求、5 秒完成。

#### 界面上的配套改进

- 增加了「**全站热门（推荐）** / **指定分区**」切换，
  并在下方说明为什么推荐热门（分区排行榜每次都是同一批、且容易被限流）。
- 弹窗提示按结果区分：有新增报"成功 + 新增数"；
  没新增则提示"已为你往后翻了一页，再点一次试试"，而不是让人以为坏了。
- 结果行显示"读了 N 页（下次从第 M 页继续）"，让翻页行为可见。

#### 「条数」到底指什么

界面上那个「条数」输入框，含义是**本次希望新增多少条视频**，
不是"读多少页"，也不等于"接口返回多少条"：

```
条数 = 5   → 逐页读，凑够 5 条新的就停（通常 1-2 页，约 3-5 秒）
条数 = 40  → 凑够 40 条新的就停（约 1-4 页）
```

默认值设成 **5**：单次点击更轻、更快，也更容易看清"确实加了新东西"。

> 早期这里默认 40，且内部另有"攒够 20 条才停"的阈值，
> 导致填 5 和填 40 效果差不多 —— 参数不听话。
> 现在 `limit` 直接作为目标条数，语义和界面标签一致。

游标初始值是 **第 5 页**（`_POPULAR_INITIAL_PAGE`）：
预置数据就是从热门榜前几页抓的，从第 5 页起步能少读些已收录内容。

### C.11 「深度更新」：补全粉丝数与弹幕

「立即更新数据」只抓视频列表。有两类字段排行榜接口**不返回**，
必须逐个补，所以单独做了「深度更新」按钮：

| 项目 | 请求成本 | 不补的后果 |
| --- | --- | --- |
| UP主 粉丝数 | 1 位 = 1 次请求 | 新 UP主 在「UP主排行」里显示 0 |
| 弹幕 | 1 个视频 = 1 次请求 | 情感分析、词云没有新数据 |

几十上百次请求不能放在同步接口里（浏览器会超时），
因此后端用**后台线程**跑，前端每 2.5 秒轮询一次进度。

#### 三个实现要点

**① 进度必须真实上报**

第一版补 35 位 UP主 时，进度条在 72 秒里一直停在 `0/35` ——
因为 `run_upuser_followers` 是整段阻塞调用。看着像卡死。

修复：给该方法加 `on_progress` 回调，每补一位就回调一次，
进度条才能一格一格走（实测 1/24 → 23/24）。

**② 被风控时要"停下"，不能"继续磨"**

`run_danmaku` 内部捕获限流后只记日志、**正常返回**（这是有意的：
单包失败不该让整个视频失败）。但调用方看不出被拦了，于是继续循环，
对剩下的几百个视频各发一次注定失败的请求 —— 既拿不到数据，又延长风控。

实测：389 个待抓视频，日志里连续几十条限流警告，程序还在往下跑。

修复：用「**连续 3 个视频一条弹幕都没拿到**」判定为限流并停止
（正常情况每个视频至少能拿到几十条，连续空手基本只能是限流）。

**③ 提前停止要如实说**

不能把"被风控中断"报成"补全完成"。现在会明确输出：

> 已提前停止：弹幕接口被风控。本次补全粉丝数 33 位、新增弹幕 3977 条（已保存），稍后可再点一次继续

#### 默认参数

```python
followers_limit = 300   # 粉丝数：尽量补完（1 次请求/位，约 3 秒一位）
danmaku_limit  = 10     # 弹幕：只补 10 个视频（接口最敏感，见上文配额表）
```

弹幕要补更多，用 `scripts/grow_dataset.py` 挂着跑更合适 —— 它带自适应退避。

---

## 附录 D：大模型提供商（用户自定义 API）

> 目标：让使用者**在界面里**填入自己的大模型 API，
> 而不是被要求去改 `.env` 或配置文件。

### D.1 为什么必须做这个功能

最初大模型配置只认环境变量（`AI_PROVIDER` / `DEEPSEEK_API_KEY`）：

```bash
# .env
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxx
```

在开发机上这完全够用。但**打包成桌面版发给别人之后就彻底不成立了**：

| 障碍 | 现实情况 |
| --- | --- |
| 拿不到你的 `.env` | 分发包里没有这个文件，也不该有 |
| 不会改 | 改环境变量对非开发者是高门槛操作 |
| 改完还要重启 | 没有任何界面提示，改错了也不知道 |
| **不该把 Key 给别人** | 把密钥写进分发包 = 把自己的额度让出去 |

所以这个功能的本质不是"加个设置项"，而是：
**让 AI 能力从"作者专属"变成"使用者可用"。**

### D.2 支持的四种服务商

| 类型 | 默认地址 | 默认模型 | 需要 Key | 说明 |
| --- | --- | --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` | 是 | 官方 OpenAI 兼容接口 |
| 通义千问 | （走官方 SDK） | `qwen-plus` | 是 | 阿里云百炼 |
| 本地 Ollama | `http://127.0.0.1:11434` | `deepseek-r1:8b` | 否 | 完全离线、零费用 |
| **OpenAI 兼容** | 用户自填 | 用户自填 | 视情况 | 覆盖面最广，见下 |

**"OpenAI 兼容"这一类是关键设计。** 它让用户能接入几乎所有主流服务：

```
硅基流动 / 月之暗面 / 智谱 / One-API 中转 / New-API /
vLLM / LM Studio / LocalAI / 公司内网网关 …
```

只要对方支持 `POST {base_url}/chat/completions`，填地址和模型名就能用 ——
**不需要为每个服务商写一套适配代码**。

### D.3 三条安全铁律

| # | 规则 | 为什么 |
| --- | --- | --- |
| 1 | 数据库存**密文** | 桌面版的数据库就在程序目录，备份/排查时会被拷走。明文存 Key 等于把密钥一起发出去 |
| 2 | 接口**永不返回明文** | 只要返回一次，它就会留在浏览器开发者工具、日志、抓包记录里。界面只显示 `sk-8****cdef` |
| 3 | 打码值回写**不覆盖真实 Key** | 界面回显打码值时，用户只改模型名就保存 —— 若后端把打码串当新 Key，真实 Key 就被覆盖成废串，表现为"改个模型名结果连不上了" |

**加密方案**：用 `SECRET_KEY` 派生 Fernet 对称密钥（`apps/ai/crypto.py`）。

- `SECRET_KEY` 本来就是每台机器独有的（桌面版首次启动随机生成并持久化到 `data/secret.key`），
  因此换机器、换安装，加密密钥都不同；
- 数据库文件被单独拷走时，脱离 `SECRET_KEY` 无法解密；
- **诚实说明局限**：这防的是"数据库文件被看到"，防不住"能读到 `SECRET_KEY` 的攻击者"。
  更强的方案需要用户主密码，但那会牺牲"双击即用"，本阶段不做。

**加密失败时 fail-closed**：绝不静默回退成明文存储，而是报错让用户知道保存失败。
宁可存不了，也不能悄悄降级成不安全状态。

### D.4 途中发现的一处真实泄密风险

写测试时断言"本地服务不需要 Key 时不应发送鉴权头"，结果**测试挂了**：

```
AssertionError: 'Authorization' unexpectedly found in
{'Content-Type': 'application/json',
 'Authorization': 'Bearer sk-8971effdb2354caca410adec9da421b5'}
```

根因：`OpenAICompatibleLLM` 继承自 `DeepSeekLLM`，而父类构造函数有这样一行：

```python
self.api_key = api_key or getattr(settings, "DEEPSEEK_API_KEY", "")
#                          ^^^^^^ 空字符串会触发回落
```

于是用户配置**本地 LM Studio**（不需要 Key）时：

```
api_key 传空  ->  回落到 settings.DEEPSEEK_API_KEY
              ->  程序把 DeepSeek 的真实密钥当成 Bearer token
                  发给了 http://127.0.0.1:1234（或某个陌生中转服务）
```

**自己的密钥被发到了用户随便填的地址上** —— 这是真实的安全缺陷，不是测试问题。

修复：`OpenAICompatibleLLM` 绕开父类构造函数，**严格只使用传入值**，
绝不去翻环境变量：

```python
self.api_key = api_key or ""      # 不回落到 settings
BaseLLM.__init__(self)            # 直接调基类完成可用性检查
```

> 这个案例说明：**继承 + "参数为空时回落默认值" 是一种危险组合**。
> 在"要给任意第三方发请求"的类里复用"内置服务商"的构造函数，
> 很容易把内置凭据带到外部地址。

### D.5 配置优先级（重要）

```
① 界面里启用的那条配置（数据库，用户自己填的 Key）   ← 最高
② 调用方显式指定的 provider
③ settings.AI_PROVIDER（.env，开发/部署用）
④ 逐级降级 -> fallback（检索式回答，不会报错）
```

桌面版分发后环境变量那条路等于不存在，使用者唯一能操作的就是界面，
因此**界面配置必须优先级最高**。

**缓存自动失效**：`get_llm()` 的缓存键里带上了配置的 `updated_at`，
任何一次保存都会自动失效 —— 不依赖调用方记得手动清缓存
（这类"改完不生效"的问题一旦出现极难排查）。

### D.6 接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ai/providers/presets/` | 内置服务商预设 |
| GET | `/api/ai/providers/` | 已保存的配置（Key 打码） |
| POST | `/api/ai/providers/` | 新增配置（自动加密 Key） |
| PATCH | `/api/ai/providers/{id}/` | 修改（不传 key 则保持不变） |
| DELETE | `/api/ai/providers/{id}/` | 删除（删活跃项自动接管给剩余项） |
| POST | `/api/ai/providers/{id}/activate/` | 设为当前启用（保证互斥） |
| POST | `/api/ai/providers/{id}/test/` | 测试连通性 |

**为什么"测试连接"要发真实请求**：常见失败原因有三种，
只有真实调用能全部覆盖：

1. 地址不通 / Key 无效 —— ping 也能发现
2. Key 有效但**余额不足** —— 只有真实调用返回 402/403
3. **模型名填错** —— 只有真实调用返回 model not found

第 3 种恰恰最常见（比如把 `deepseek-flash` 写成版本名）。
因此发一个 `max_tokens=16` 的最小请求，成本可忽略。

### D.7 前端交互

入口放在 **AI 助手页 → 右侧「RAG 链路状态」→「模型设置」按钮**。

理由：用户"感觉 AI 不够聪明 / 没接上大模型"的瞬间就在这个页面，
把设置入口放在同一屏，路径最短。

弹窗里提供：

- 已保存配置的表格（名称 / 类型 / 模型 / 打码 Key / 上次测试结果）
- 启用 / 编辑 / 测试连接 / 删除
- 新增表单（选服务商后自动回填地址与模型，并显示该服务商的说明与申请 Key 链接）
- 测试结果直接在下方显示完整原因

`RAG 链路状态` 面板的提示语也按"未配置 / 配置了但连不上 / 已就绪"分三种，
分别给出对应的下一步动作 —— 三种情况让用户做的事完全不同，
混在一起提示等于没提示。

### D.8 兼容与迁移

已有 `.env` / `config.json` 里的 Key 不会失效：
启动时 `bootstrap` 会做**一次性迁移**，把已有 Key 转成一条数据库记录并设为启用。
之后以数据库为准。整个过程幂等，不会重复写入。

### D.9 验收

```
新增测试            28 个（crypto 6 / API 12 / 预设 2 / 工厂 3 /
                          测试接口 3 / 播种 3 / 请求体 2，其中含 1 个安全回归）
完整套件            232/232 通过
真实对话            provider=deepseek retrieved=5 fallback=False
                    （走的是数据库里配置的 Key，而非环境变量）
明文泄露检查        列表接口响应中不含完整 Key ✔
删除活跃配置        自动回落给剩余配置，AI 不中断 ✔
```

---

<p align="center">
  <b>BiliInsight</b> · 仅用于学习研究，禁止商业用途<br>
  <sub>Made with Django · Vue · SQLite · ChromaDB · 可自定义大模型</sub>
</p>
