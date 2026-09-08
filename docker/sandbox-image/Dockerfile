ARG BASE_IMAGE=sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2
FROM ${BASE_IMAGE}

ARG PYTHON_BIN=/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin/python3
ENV PATH="/opt/skills-venv/bin:/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin:${PATH}" \
    MPLCONFIGDIR=/tmp/matplotlib

COPY requirements-sandbox.txt /tmp/requirements-sandbox.txt

RUN "${PYTHON_BIN}" -m venv /opt/skills-venv \
    && /opt/skills-venv/bin/pip install --no-cache-dir \
       -i https://mirrors.aliyun.com/pypi/simple/ \
       --default-timeout=120 \
       -r /tmp/requirements-sandbox.txt \
    && /opt/skills-venv/bin/python -c \
       "import bs4, lxml, markdownify, matplotlib, numpy, pandas, requests" \
    && mkdir -p /analysis/temp /analysis/tasks /data /tmp/matplotlib \
    && printf '%s\n' 'asu-agent-sandbox:v1' > /opt/skills-venv/.erp-openclaw-image-v1 \
    && rm -f /tmp/requirements-sandbox.txt

