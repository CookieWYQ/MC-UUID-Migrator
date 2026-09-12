# 两个关键输入：A 和 B

| 名称 | 含义 | 填什么 |
|---|---|---|
| 来源UUID(A) | 数据现在的主人 | 完整带横线UUID，如 aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa（示例） |
| 目标UUID(B) | 要继承数据的对象 | 如 bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb（示例） |

- 大小写无所谓，但必须有横线（8-4-4-4-12）
- 填错 = 数据给错人

## 怎么查玩家的 UUID

正版：

- 启动器账号资料页
- mcuuid.net 输入游戏名查询
- 自己存档里的 usercache.json（name 与 uuid 对应表）

离线：

- 直接在工具顶部填用户名
- 选方向「正版→离线」或「离线→正版」
- 点「一键替换」自动算出两个 UUID
