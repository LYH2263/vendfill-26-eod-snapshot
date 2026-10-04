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

1. 在「点位」「货道」查看售货机布局与库存。
2. 在「销量」了解近期出货。
3. 打开「补货单」按缺口生成建议补货量。
4. 在「满仓」「汇总」查看已满货道与补货合计（均按当前库存实时计算）。
5. 在「汇总」点「日终导出」，生成一份导出瞬间钉死的口径包（待补总件数 / 满仓货道 / 超占货道）；导出后再改库存不回写该包，货道页与之后新生成的补货单仍跟新库存。
   - 无点位导出失败：`404 LOCATION_NOT_FOUND`
   - 导出成功但冻结包被回刷/篡改：`409 EXPORT_SNAPSHOT_REFRESHED`

## 开发与测试

```bash
docker compose exec api pytest -q
```
