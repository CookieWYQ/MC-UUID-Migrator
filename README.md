# MC UUID 玩家数据迁移工具

> 一个用于 **Minecraft** 的玩家数据迁移小工具：把「玩家 A 的所有数据」整体迁移成「玩家 B 的」。
> 绿色**单文件 exe**，无需安装 Java / Python，双击即用。

内置第三个功能页「Xaero 地图转移」：把单机世界的路径点与已探索地图，合并到服务器对应的容器里。

---

## 功能特性

### 1. UUID 玩家数据迁移

- **文件名 / 目录名改名**：`playerdata`、`stats`、`advancements`、`maid_backups` 等以 UUID 命名的文件与文件夹
- **文件内容原位替换**：
  - 纯文本 / 二进制文件（等长替换，安全）
  - gzip 压缩的 NBT（`playerdata/*.dat`、`level.dat`、模组数据）
  - `.mca` 区块文件（逐区块解压 → 替换 → 安全重建，覆盖实体藏在区块里的情况）
- **覆盖 UUID 的多种写法**：小写/大写 × 带横线/无横线，以及 16 字节二进制形式（NBT 的 `IntArray[4]` 等）
- 不依赖固定路径或版本号，适用于所有以 UUID 作玩家标识的版本

### 2. 两种工作模式

| 页面 | 用途 |
|---|---|
| 单人存档 | 迁移本地存档目录（全程离线） |
| 多人服务器 | 通过 SFTP 连接主机，远程迁移服务器世界：下载镜像 → 本地替换 → 只回传改动文件 |

多人模式特点：SFTP 单通道复用（避免部分主机上重复开通道导致卡死）、逐操作超时、目录扫描 180s 硬超时看门狗、列目录实时进度、连接测试按钮、密码可留空、服务器信息持久化。

### 3. Xaero 地图转移（与 UUID 无关）

Xaero 的路径点与已探索地图保存在**客户端**，按「世界 / 服务器容器」区分，文件里不含 UUID。
因此「单机世界传上服务器后路径点全没了」——本页用于把两者对接：

- **路径点**：按维度合并到目标容器，自动去重，不产生重复点
- **已探索地图**：只补充目标容器缺失的区块文件，**不覆盖**已有数据
- **多世界 ID 对齐**：可读取服务器 `world/xaeromap.txt` 的 `id:<数字>`，自动用 `mw$<ID>_1.txt` 命名；服务器换 ID 时可一键把旧文件名改名对齐
- 维度自动映射：`dim%0 ↔ null`、`dim%-1 ↔ DIM-1`、`dim%1 ↔ DIM1`

### 4. 其他

- **迁移前自动备份**（见下文「备份与还原」），可整体还原
- **一键替换**：填用户名 + 方向（正版→离线 / 离线→正版），自动算出两个 UUID 并执行
- **内置图形教程**：点击界面右上角「使用教程」，富文本渲染，10 篇已打包进 exe
- 单文件无控制台窗口，图标与依赖（paramiko / cryptography / tkinter）全部打包

---

## 下载

前往 **[Releases](../../releases)** 下载 `UUID玩家数据迁移.exe`，双击运行即可（Windows 64 位）。

---

## 快速上手

### 场景一：本地存档换身份（正版 → 离线）

1. 打开程序，切到 **「单人存档」** 页
2. 「存档根目录」选择存档文件夹（内含 `playerdata`、`region`、`level.dat`）
3. 来源UUID(A) 填原主人、目标UUID(B) 填继承者；或直接在顶部填用户名 → 选「正版→离线」→ 点「一键替换」
4. 点「扫描」预览 → 点「开始迁移」

### 场景二：迁移服务器世界（需先停服）

1. **先停止服务器**（运行中会被服务器写档覆盖）
2. 切到 **「多人服务器」** 页，填 SFTP 地址 / 端口 / 用户名 / 密码 / 远端世界根目录
3. 点 **「测试连接」** 确认能连上、路径正确
4. 填 A / B（或用用户名一键替换）→ 点「开始迁移」→ 等待 下载镜像 / 替换 / 回传
5. 重启服务器验证

### 场景三：找回单机世界的路径点与地图

1. **先退出游戏**
2. 切到 **「Xaero 地图转移」** 页，「客户端目录」选含 `xaero` 文件夹的目录
3. 点「刷新容器列表」→ 源容器选单机世界名，目标容器选 `Multiplayer_<服务器地址>`
4. 勾选「路径点」「已探索地图」→ 点「扫描预览」→ 点「开始转移」

---

## 命令行用法

```bash
# 本地存档迁移
python uuid_transfer_tool.py --root <存档目录> --a <来源UUID> --b <目标UUID> [--scan]

# 按用户名一键替换（正版 → 离线）
python uuid_transfer_tool.py --root <目录> --by-username <用户名>
# 反向（离线 → 正版）
python uuid_transfer_tool.py --root <目录> --by-username <用户名> --to-online

# 计算某用户名的离线 UUID
python uuid_transfer_tool.py --offline-uuid <用户名>

# SFTP 远程迁移
python uuid_transfer_tool.py --sftp-host <地址> --sftp-port <端口> --sftp-user <用户> \
    --sftp-pass <密码> --sftp-root <远端世界目录> --a <A> --b <B> [--scan]

# Xaero 地图转移
python uuid_transfer_tool.py --xaero-root <客户端目录> --xaero-src <源容器> --xaero-dst <目标容器> [--xaero-scan]
python uuid_transfer_tool.py --xaero-root <客户端目录> --xaero-dst <容器> --xaero-world <服务器world目录> --xaero-align
```

---

## 备份与还原

| 操作 | 备份目录 | 内容 |
|---|---|---|
| UUID 迁移 | `uuid_backup_时间戳_A_to_B` | 所有涉及文件：A 的原文件、B 将被覆盖的文件、将被改写的文件 |
| Xaero 转移 | `xaero_backup_时间戳_源_to_目标` | 会被写入的目标路径点文件 |
| Xaero 对齐 | `xaero_backup_时间戳_容器_align_to_ID` | 被改名文件 + `改名记录.txt` |

- Xaero 的**已探索地图**只补缺失、绝不覆盖，无需备份；**源容器**全程只读
- 还原：把备份目录里的文件按相对路径拷回原位置；`改名记录.txt` 记录了 `旧路径 -> 新路径`，反着改回即可

---

## 从源码构建

环境：Windows + Python 3.10+（开发使用 3.13）

```bat
:: 方式一：一键脚本
build.bat

:: 方式二：手动
python -m pip install pyinstaller paramiko
pyinstaller uuid_transfer_tool.spec --noconfirm
```

产物：`dist\UUID玩家数据迁移.exe`（单文件）。

`uuid_transfer_tool.spec` 说明：`onefile` 模式、`console=False`、`hiddenimports=['paramiko']`、`datas=[('使用教程/*.md', '使用教程')]`（把教程 md 打进 exe）、图标 `uuid_transfer_icon.ico`。

### 教程图片渲染（可选）

教程以 Markdown 编写（`使用教程/*.md`），可导出为长图发布：

```bat
python render_md_images.py
```

产物位于 `使用教程_图片/`（2200px 宽高清 PNG，自动换行、表格自适应、边缘无越界）。

---

## 目录结构

```
.
├── uuid_transfer_tool.py      # 主程序（GUI + 命令行）
├── uuid_transfer_tool.spec    # PyInstaller 打包配置（单文件）
├── build.bat                  # 一键构建脚本
├── render_md_images.py        # 教程 md → 长图渲染器
├── uuid_transfer_icon.ico     # 程序图标
├── uuid_transfer_icon.png     # 图标预览
├── LICENSE
├── 使用教程/                   # 教程 Markdown（构建时打包进 exe）
└── 使用教程_图片/               # 教程长图（发布用）
```

---

## 常见问题

- **迁移后进入游戏看不到数据？** 先确认服务器已停服再执行；若已执行，用备份目录还原后重试。
- **Xaero 路径点还是没出现？** 确认目标容器名与客户端实际连的服务器一致（`Multiplayer_<地址>`），必要时用「读取多世界ID」+「对齐到目标容器」。
- **SFTP 扫描卡住？** 本工具已做单通道复用与超时看门狗；若仍异常，请确认主机面板允许 SFTP，并优先把远端根目录填成世界文件夹（如 `/world`）而非整个服务器根目录。
- **密码必填吗？** 不必。留空会尝试免密方式；需要密码的服务器留空会返回明确的认证失败提示。

---

## 免责声明

- 本工具直接修改玩家数据文件，**请务必先备份**。使用前建议停服 / 退出游戏。
- 仓库与 Release **不包含任何第三方模组文件**（例如 Xaero 系列模组），相关名称仅用于说明兼容性，版权归原作者所有。
- 请遵守所在服务器的规则与相关法律法规使用本工具。

---

## 作者与许可

作者：**CallMeACookieWYQ**
许可：[MIT](LICENSE)
