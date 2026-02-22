# meme_echo — AstrBot 表情包命中复读插件（命令收录 + 别名管理）

一个用于 **AstrBot（OneBot v11 / QQ NT 系）** 的插件：  
当机器人在群聊中识别到你已收录的特定表情包（图片）后，会 **立刻发送同一张表情包**。

本插件支持在群里通过命令直接“收录表情包”，并支持为每个表情包设置 **别名**，便于后续管理。

---

## 功能特性

- ✅ 群聊中出现已收录表情包 → **自动复读同一张**
- ✅ **命令收录**：`/meme add` 后发图即可入库（不用进 WebUI）
- ✅ **别名管理**：`/meme name <KEY> <别名>`，之后可用别名查询/删除
- ✅ 本地存储：表情包保存在 `data/plugin_data/<plugin>/memes/`，重启不丢

---

## 工作原理（简述）

在 OneBot v11 / QQ NT 系适配器中，收到的图片消息段通常形如：
Image(file='0B62C72CB050ABAC0AED36E46CA54F1A.png', 
url='https://multimedia.nt.qq.com.cn/download
?...')

插件取 `file` 的文件名主体（`0B62C72C...`）作为 **KEY**，与本地收录库中的 KEY 进行匹配，命中后通过本地文件 `fromFileSystem` 复读，稳定且不依赖临时 `rkey/url`。

---

## 安装方式

### 方式 A：通过 AstrBot WebUI 安装（推荐）
1. 确保仓库根目录包含：
   - `main.py`
   - `metadata.yaml`
2. 在 AstrBot WebUI 插件管理中，输入仓库地址安装并启用。


### 方式 B：手动安装
将本插件放到：/opt/AstrBot/data/plugins/astrbot_plugin_meme_echo/
###使用说明
1) 收录表情包

方式 1：先发命令，再发图

/meme add

机器人提示你在 60 秒内发图；随后直接发送一张表情包图片即可收录。

方式 2：同一条消息带图（若平台支持）
发送 /meme add 并附带图片（部分客户端不方便）。

收录成功后返回

KEY（32 位十六进制）

若已有别名，会显示别名；否则提示你用命令绑定别名

2) 绑定别名
/meme name <KEY> <别名>

示例：

/meme name 0B62C72CB050ABAC0AED36E46CA54F1A 狗头
3) 查询（KEY 或别名）
/meme show <KEY|别名>

示例：

/meme show 狗头
4) 列表（含别名）
/meme list

默认只显示部分（前若干项），优先显示别名映射。

5) 删除（KEY 或别名）
/meme del <KEY|别名>

示例：

/meme del 狗头
6) 重建索引

当你手动改动了 memes/ 目录内容，或想清理无效别名时：

/meme reload
数据存储位置
data/plugin_data/meme_echo/
  ├─ memes/      # 表情包文件（按 KEY 命名）
  ├─ index.json  # KEY -> 文件名
  └─ alias.json  # 别名 -> KEY
