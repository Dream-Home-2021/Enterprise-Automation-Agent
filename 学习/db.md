运行单个测试 + 查看数据变化：


python -m pytest test/test_redis_pg.py::test_pg_session_crud -v -s
每次改动都要ctrl +s保存，不然运行的还是之前的代码，巨抽象
运行所有测试 + 每个测试前后打印数据库状态：


conda run -n langgraph python test/test_redis_pg.py
单独查看数据库当前状态：


conda run -n langgraph python test/db_query.py
只看某张表：


conda run -n langgraph python test/db_query.py sessions
conda run -n langgraph python test/db_query.py profiles
conda run -n langgraph python test/db_query.py prefs
conda run -n langgraph python test/db_query.py redis


📁 文件 1: test/test_long_term_memory.py — 长期记忆测试用例
参考 test_redis_pg.py 的书写风格，按 8 个功能组 拆分，共 25 个测试用例：

组	功能	测试用例数	运行方式
组 1	extract_from_conversation 即时提取偏好	6	-k "test_profile_extract"
组 2	batch_process_pending 批量后台提取	3	-k "test_profile_batch"
组 3	_save_vectors_async 向量存储	3	-k "test_profile_vector"
组 4	start/stop_background_extractor 后台定时任务	2	-k "test_profile_background"
组 5	完整生命周期（端到端）	2	-k "test_profile_lifecycle"
组 6	错误隔离（所有操作 try/except）	4	-k "test_profile_error"
组 7	长期记忆读取（load_user_memory / inject / vector search）	5	-k "test_memory_read"
组 8	generate_summary 摘要生成	2	-k "test_generate_summary"
运行方式：


# 全部
python -m pytest test/test_long_term_memory.py -v -s

# 只看即时提取
python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_extract"

# 只看批量处理
python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_batch"
关键设计：

使用 TEST_USER_1/2/3 (88801/88802/88803) 避免污染正式数据
autouse fixture 每个测试后自动清理测试用户数据
_show_memory_state() 辅助函数打印测试后的完整数据状态
所有测试遵循 test_redis_pg.py 的 asyncio + pytest.mark.asyncio 风格
📁 文件 2: test/query_postgres_data.py — PostgreSQL 数据查询工具
比原有的 db_query.py 更全面，支持按表/用户/会话多维度查询：


# 查看所有表数据 + 行数统计
python test/query_postgres_data.py

# 按表查询
python test/query_postgres_data.py sessions
python test/query_postgres_data.py preferences
python test/query_postgres_data.py profile
python test/query_postgres_data.py summaries
python test/query_postgres_data.py vectors

# 按用户查询（全部数据）
python test/query_postgres_data.py user 1
python test/query_postgres_data.py user 999

# 按会话查询（session + summaries + vectors 关联）
python test/query_postgres_data.py session <uuid>

# 只看行数统计
python test/query_postgres_data.py counts

# 查看 PGVector 索引信息
python test/query_postgres_data.py indexes