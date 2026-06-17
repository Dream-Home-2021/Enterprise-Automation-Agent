# ---------------------------------------------------------------------------
# MCP Python Sandbox — 隔离数据分析容器
# ---------------------------------------------------------------------------
# 安全约束：
#   - 网络隔离（network_mode=none）
#   - CPU ≤ 0.5 核
#   - Memory ≤ 512MB
#   - 代码执行超时 ≤ 10s
# ---------------------------------------------------------------------------

FROM python:3.11-slim

# 安装数据分析核心库
RUN pip install --no-cache-dir \
    pandas==2.2.3 \
    numpy==2.1.3 \
    openpyxl==3.1.5 \
    matplotlib==3.9.3 \
    seaborn==0.13.2 \
    scipy==1.14.1 \
    scikit-learn==1.5.2

# 创建工作目录
WORKDIR /workspace

# 非 root 用户（安全加固）
RUN groupadd -r sandbox && useradd -r -g sandbox -d /workspace sandbox
RUN chown sandbox:sandbox /workspace
USER sandbox

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "print('healthy')" || exit 1

# 容器默认保持运行（由 client.py 管理 exec）
CMD ["sleep", "infinity"]
