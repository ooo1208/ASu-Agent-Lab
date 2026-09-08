---
name: supplier-price-urls
description: >
  ASu 演示采购报价映射。按 ERP 零件名和供应商查找合成报价页面，
  用于本地采集、比价和来源引用练习。全部数据为合成快照，不能当作真实行情。
---

# 合成供应商报价映射

## 数据边界

本 Skill 对应 Java ERP 的三种合成零件和三家演示供应商，共九张候选报价页。
页面上的价格、历史走势、交期和型号均为合成数据。报告必须写明“合成演示报价，快照日期 2026-09-08”，不能把它们描述成联网查到的真实商品报价。

ERP 中的 `part.supplierId` 表示现有目录供货关系；报价页包含其他供应商的候选报价。不能依据候选报价推定已经有采购记录，应使用 `part_by_supplier` 和 `order_search_details` 查询。

## 读取和匹配

1. 用 `supplier_query(name="示例")`、`part_search(name="陶瓷刹车片")` 等工具获取 ERP 数据。
2. 读取 `data/url_mapping.yaml`。该文件采用 JSON 语法，是有效 YAML；顶层包含 `data_kind`、`as_of`、`quote_base_url` 和 `mappings`。
3. 按 `part_id` 或精确零件名匹配，保留目标供应商的条目。跨供应商比价时保留同一零件的全部候选报价。
4. 通过网页抓取 Skill 读取选中的 URL，提取当前单价、单位、币种、起订量、交期和来源 URL。
5. 分清 ERP 历史采购价与演示候选报价；不要把不同零件的价格直接排名。
6. 未命中或页面无法访问时，说明缺少数据或服务未启动。不要自动编造报价，也不要把本地夹具替换成未经核对的市场结果。

示例：`part_name="陶瓷刹车片"`、`supplier="示例精工供应商"` 对应 `supplier-1-part-1.html`，演示单价为 38.50 CNY / 件。

## 主机启动

在项目根目录运行：

```bash
python src/mcp_server/quote_server.py
```

默认首页为 `http://127.0.0.1:8086/`，映射接口为 `/mapping.json`。静态文件在 `src/mcp_server/html_quote/`，不需要模型或数据库。

可以设置 `QUOTE_HOST`、`QUOTE_PORT` 更改监听地址；`QUOTE_BASE_URL` 是页面访问方实际能够访问的公开基址。只设置基址不会自动改变监听地址，也不会自动重写已同步进沙箱的映射。

## 沙箱网络配置

**沙箱内的 127.0.0.1 指向沙箱自己，不是宿主机。** 默认映射适用于主机侧测试。通过 Docker/OpenSandbox 抓取主机上的报价服务时，需要使用沙箱能够路由到的主机地址。

Docker Desktop 的示例配置（先确认该网络环境支持 `host.docker.internal`）：

```powershell
$env:QUOTE_HOST = '0.0.0.0'
$env:QUOTE_PORT = '8086'
$env:QUOTE_BASE_URL = 'http://host.docker.internal:8086'
python src/mcp_server/quote_server.py --write-mapping
```

`--write-mapping` 会先把宿主机的 `data/url_mapping.yaml` 改为配置后的基址，再启动服务。随后必须把更新后的 Skill 同步进沙箱。也可以先执行 `--mapping-only` 只生成映射；在其他终端启动服务。

Linux、远程沙箱或不同容器网络不能假定上述域名可用，需要配置对应的主机网关、服务域名或反向代理地址，并从沙箱实际发起 HTTP 请求验证。未完成网络验证时，不应把 URL 连接失败当作“供应商没有报价”。

监听所有网卡只用于需要沙箱访问的演示部署；服务只提供明确合成的静态报价页面，不包含 API Key 或 ERP 数据库。
