# VendFill 售货机补货

按货道容量、库存与在途量计算缺口，生成不超缺口、非负的补货单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4800 |
| API | http://localhost:9800 |
| API 文档 | http://localhost:9800/docs |
| Postgres | localhost:5449 |

健康检查：`GET http://localhost:9800/api/health`

## 使用说明

1. 在「点位」「货道」查看售货机布局与库存（货道页可 ± 调整库存，实时生效）。
2. 在「销量」了解近期出货。
3. 打开「补货单」按缺口生成建议补货量。
4. 在「满仓」「汇总」查看已满货道与补货合计。
5. 在「日终导出」导出当日口径包。

## 日终口径包（导出即钉死）

`POST /api/exports/eod` 在导出瞬间固化一份口径包：待补总件数、满仓货道、超占货道，
落库为 `payload_json + sha256`。导出之后再改库存，这份包不会被回写；
`GET /api/exports/eod/latest` 永远返回导出瞬间的内容（读取时做哈希校验，绝不按现库存重算）。
货道页与之后新生成的补货单仍跟随最新库存。

失败码严格分开，不得混用：

| 场景 | HTTP | code |
| --- | --- | --- |
| 无点位，导出失败 | 409 | `EOD_NO_LOCATIONS` |
| 导出成功过，但包被回刷 | 500 | `EOD_SNAPSHOT_TAMPERED` |
| 尚未导出过 | 404 | `EOD_EXPORT_NOT_FOUND` |

## 约束（应用层 + 数据库双层）

- `capacity > 0`、`stock >= 0`、`in_transit >= 0`：应用层校验返回 422，数据库 CHECK 约束兜底，直插非法值必败。
- 刻意**不**约束 `stock <= capacity`：合法超占道（库存+在途超过容量）必须仍能存在。
- 老库启动时由 `app/services/migrate.py` 幂等补齐 CHECK 约束（仅 Postgres；新库由 `create_all` 直接带出）。

## 开发与测试

```bash
docker compose exec api pytest -q
```
