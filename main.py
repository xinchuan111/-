from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
# 旧版规范核心：导入 Context 类
from astrbot.api.star import Context, Star, register, StarTools
import astrbot.api.message_components as Comp


def md5_bytes_upper(b: bytes) -> str:
    """计算字节数据的MD5值并转为大写"""
    return hashlib.md5(b).hexdigest().upper()


# 插件注册（4个参数完整，注册名用小写+下划线，避免特殊字符）
@register("meme_echo", "YourName", "群聊表情包命中即复读（命令收录+别名管理）", "1.1.0")
class MemeEcho(Star):
    """
    表情包复读插件（旧版规范适配）
    指令列表：
    /meme add               收录一张表情包（先发命令再发图，或命令同条带图）
    /meme name <KEY> <别名> 绑定别名
    /meme show <KEY|别名>   查看详情
    /meme list              列表（含别名）
    /meme del <KEY|别名>    删除
    /meme reload            重建索引
    """
    # 旧版规范核心：补充 plugin_name 属性
    def __init__(self, context: Context):
        super().__init__(context)
        # 手动赋值 plugin_name（和@register第一个参数一致）
        self.plugin_name = "meme_echo"

    async def initialize(self):
        """插件初始化逻辑（旧版规范中初始化都放这里）"""
        # 插件数据存储目录（现在能正确获取 plugin_name）
        self.data_dir = Path(StarTools.get_data_dir(self.plugin_name))
        self.meme_dir = self.data_dir / "memes"
        self.meme_dir.mkdir(parents=True, exist_ok=True)

        # 索引文件路径
        self.index_path = self.data_dir / "index.json"   # key -> filename
        self.alias_path = self.data_dir / "alias.json"   # alias -> key

        # 内存中的索引和别名映射
        self.index: Dict[str, str] = {}
        self.alias: Dict[str, str] = {}
        # 等待用户发图的临时状态（(group_id, user_id) -> 过期时间戳）
        self.awaiting: Dict[Tuple[str, str], float] = {}

        # 加载或重建索引
        self._load_or_rebuild()
        logger.info(f"✅ meme_echo 插件初始化完成 | 表情包数量={len(self.index)} | 别名数量={len(self.alias)} | 存储目录={self.meme_dir}")

    # ---------- 索引和别名管理 ----------
    def _load_or_rebuild(self) -> None:
        """加载索引，若索引为空则重建"""
        self._load_index()
        if not self.index:
            self._rebuild_index()
        self._load_alias()

    def _load_index(self) -> None:
        """加载表情包索引文件"""
        try:
            if self.index_path.exists():
                data = json.loads(self.index_path.read_text("utf-8"))
                self.index = {str(k).upper(): str(v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"加载索引失败，使用空索引 | 错误：{e}")
            self.index = {}

    def _save_index(self) -> None:
        """保存表情包索引到文件"""
        try:
            self.index_path.write_text(json.dumps(self.index, ensure_ascii=False, indent=2), "utf-8")
        except Exception as e:
            logger.error(f"保存索引失败 | 错误：{e}")

    def _rebuild_index(self) -> None:
        """从表情包目录重建索引"""
        self.index.clear()
        for p in self.meme_dir.glob("*"):
            if not p.is_file():
                continue
            stem = p.stem.upper()
            if len(stem) == 32:  # MD5值长度为32位
                self.index[stem] = p.name
        self._save_index()
        logger.info(f"✅ 重建索引完成 | 共发现 {len(self.index)} 个表情包")

    def _load_alias(self) -> None:
        """加载别名映射文件"""
        try:
            if self.alias_path.exists():
                data = json.loads(self.alias_path.read_text("utf-8"))
                self.alias = {str(a).strip(): str(k).upper() for a, k in data.items()}
        except Exception as e:
            logger.error(f"加载别名失败，使用空别名 | 错误：{e}")
            self.alias = {}

    def _save_alias(self) -> None:
        """保存别名映射到文件"""
        try:
            self.alias_path.write_text(json.dumps(self.alias, ensure_ascii=False, indent=2), "utf-8")
        except Exception as e:
            logger.error(f"保存别名失败 | 错误：{e}")

    # ---------- 工具方法 ----------
    def _extract_first_image(self, event: AstrMessageEvent) -> Optional[Comp.Image]:
        """从消息中提取第一张图片"""
        msg = event.message_obj
        if not msg or not msg.message:
            return None
        for seg in msg.message:
            if isinstance(seg, Comp.Image):
                return seg
        return None

    def _get_group_user_key(self, event: AstrMessageEvent) -> Tuple[str, str]:
        """获取 (group_id, user_id) 作为唯一标识"""
        msg = event.message_obj
        group_id = str(getattr(msg, "group_id", "") or getattr(event, "group_id", "") or "")
        user_id = str(getattr(msg, "user_id", "") or getattr(event, "user_id", "") or getattr(msg, "sender_id", "") or "")
        return (group_id, user_id)

    def _resolve_key(self, key_or_alias: str) -> Optional[str]:
        """从 KEY 或别名解析出真实的 MD5 KEY"""
        s = (key_or_alias or "").strip()
        # 如果是32位十六进制字符串，直接作为KEY
        if len(s) == 32 and all(c in "0123456789abcdefABCDEF" for c in s):
            return s.upper()
        # 否则从别名映射中查找
        return self.alias.get(s)

    def _reverse_alias(self, key: str) -> Optional[str]:
        """从 KEY 反向查找别名"""
        key = key.upper()
        for a, k in self.alias.items():
            if k == key:
                return a
        return None

    def _save_bytes_as_meme(self, data: bytes, ext: str) -> str:
        """将字节数据保存为表情包文件，并更新索引"""
        key = md5_bytes_upper(data)
        ext = (ext or ".png").lower()
        if not ext.startswith("."):
            ext = "." + ext
        filename = f"{key}{ext}"
        dst = self.meme_dir / filename
        if not dst.exists():
            dst.write_bytes(data)
        self.index[key] = filename
        self._save_index()
        return key

    def _delete_key(self, key: str) -> bool:
        """删除指定 KEY 的表情包及关联别名"""
        key = key.upper()
        name = self.index.get(key)
        if not name:
            return False

        # 删除文件
        p = self.meme_dir / name
        try:
            if p.exists():
                p.unlink()
        except Exception as e:
            logger.error(f"删除表情包文件失败 | KEY={key} | 错误：{e}")

        # 删除索引
        self.index.pop(key, None)
        self._save_index()

        # 删除所有指向该 KEY 的别名
        bad_aliases = [a for a, k in self.alias.items() if k == key]
        for a in bad_aliases:
            self.alias.pop(a, None)
        if bad_aliases:
            self._save_alias()
            logger.info(f"删除 {len(bad_aliases)} 个无效别名 | KEY={key}")

        return True

    # ---------- 指令处理 ----------
    @filter.command("meme")
    async def meme_cmd(self, event: AstrMessageEvent):
        """处理 /meme 指令"""
        parts = (event.message_str or "").strip().split()
        action = parts[1].lower() if len(parts) >= 2 else "help"

        # 收录表情包
        if action == "add":
            img = self._extract_first_image(event)
            if img is not None:
                ok, key_or_err = await self._add_from_image_segment(img)
                if ok:
                    alias = self._reverse_alias(key_or_err)
                    hint = f"（别名：{alias}）" if alias else f"\n可用：/meme name {key_or_err} <别名> 绑定别名"
                    yield event.plain_result(f"✅ 已收录表情包：{key_or_err}{hint}")
                else:
                    yield event.plain_result(f"❌ 收录失败：{key_or_err}")
                return

            # 无图片，进入等待发图状态
            gu = self._get_group_user_key(event)
            self.awaiting[gu] = time.time() + 60
            yield event.plain_result("好👌 现在请在 60 秒内发送一张表情包图片（直接发图即可，我会自动收录）")
            return

        # 绑定别名
        if action == "name":
            if len(parts) < 4:
                yield event.plain_result("用法：/meme name <KEY> <别名>")
                return
            key = parts[2].strip().upper()
            alias = " ".join(parts[3:]).strip()

            if key not in self.index:
                yield event.plain_result(f"未找到该 KEY：{key}\n先用 /meme add 收录它")
                return

            self.alias[alias] = key
            self._save_alias()
            yield event.plain_result(f"✅ 已设置别名：{alias} -> {key}")
            return

        # 查看详情
        if action == "show":
            if len(parts) < 3:
                yield event.plain_result("用法：/meme show <KEY|别名>")
                return
            q = " ".join(parts[2:]).strip()
            key = self._resolve_key(q)
            if not key:
                yield event.plain_result(f"未找到：{q}")
                return
            name = self.index.get(key, "")
            alias = self._reverse_alias(key)
            yield event.plain_result(f"KEY: {key}\n别名: {alias or '（无）'}\n文件: {name or '（不存在）'}")
            return

        # 列表展示
        if action == "list":
            keys = sorted(self.index.keys())
            if not keys:
                yield event.plain_result("当前还没有收录任何表情包。用：/meme add")
                return
            lines = []
            # 先展示前10个别名
            for a, k in list(self.alias.items())[:10]:
                lines.append(f"{a} -> {k}")
            # 补充无别名的KEY，凑够10个
            if len(lines) < 10:
                for k in keys:
                    if len(lines) >= 10:
                        break
                    if k in self.alias.values():
                        continue
                    lines.append(k)
            more = "" if len(keys) <= 10 else f"\n…共 {len(keys)} 个，仅显示部分"
            yield event.plain_result("已收录：\n" + "\n".join(lines) + more)
            return

        # 删除表情包
        if action == "del":
            if len(parts) < 3:
                yield event.plain_result("用法：/meme del <KEY|别名>")
                return
            q = " ".join(parts[2:]).strip()
            key = self._resolve_key(q)
            if not key:
                yield event.plain_result(f"未找到：{q}")
                return
            if self._delete_key(key):
                yield event.plain_result(f"✅ 已删除：{q}（KEY={key}）")
            else:
                yield event.plain_result(f"删除失败：{q}")
            return

        # 重建索引
        if action == "reload":
            self._rebuild_index()
            # 清理无效别名
            bad_aliases = [a for a, k in self.alias.items() if k not in self.index]
            for a in bad_aliases:
                self.alias.pop(a, None)
            if bad_aliases:
                self._save_alias()
            yield event.plain_result(f"✅ 已重建索引，当前共 {len(self.index)} 个（清理无效别名 {len(bad_aliases)} 个）")
            return

        # 帮助信息
        yield event.plain_result(
            "用法：\n"
            "/meme add               收录一张表情包\n"
            "/meme name <KEY> <别名> 绑定别名\n"
            "/meme show <KEY|别名>   查看\n"
            "/meme list              列表\n"
            "/meme del <KEY|别名>    删除\n"
            "/meme reload            重建索引"
        )

    # ---------- 群消息监听 ----------
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """监听群消息，处理等待发图和表情包复读"""
        # 处理等待用户发图的逻辑
        gu = self._get_group_user_key(event)
        exp_time = self.awaiting.get(gu)
        if exp_time:
            # 未过期
            if time.time() <= exp_time:
                img = self._extract_first_image(event)
                if img is not None:
                    ok, key_or_err = await self._add_from_image_segment(img)
                    self.awaiting.pop(gu, None)
                    if ok:
                        alias = self._reverse_alias(key_or_err)
                        hint = f"（别名：{alias}）" if alias else f"\n可用：/meme name {key_or_err} <别名> 绑定别名"
                        yield event.plain_result(f"✅ 已收录表情包：{key_or_err}{hint}")
                    else:
                        yield event.plain_result(f"❌ 收录失败：{key_or_err}")
                    event.stop_event()
                    return
            # 已过期，清理状态
            else:
                self.awaiting.pop(gu, None)

        # 表情包复读逻辑
        msg = event.message_obj
        if not msg or not msg.message:
            return
        for seg in msg.message:
            if not isinstance(seg, Comp.Image):
                continue
            # 从图片段中提取文件名（MD5 KEY）
            f = getattr(seg, "file", "") or ""
            key = Path(f).stem.upper()
            # 检查是否在索引中
            name = self.index.get(key)
            if not name:
                continue
            # 检查文件是否存在
            p = self.meme_dir / name
            if not p.exists():
                continue
            # 发送复读的表情包
            yield event.chain_result([Comp.Image.fromFileSystem(str(p))])
            event.stop_event()
            return

    # ---------- 图片下载与收录 ----------
    async def _add_from_image_segment(self, img: Comp.Image):
        """从图片段下载并收录表情包"""
        # 1) 优先从本地路径读取
        path = getattr(img, "path", "") or ""
        if path:
            p = Path(path)
            if p.exists() and p.is_file():
                data = p.read_bytes()
                ext = p.suffix or ".png"
                key = self._save_bytes_as_meme(data, ext)
                return True, key

        # 2) 从URL下载
        url = getattr(img, "url", None) or getattr(img, "src", None)
        if not url:
            return False, "图片段没有 url/path，无法获取原图数据"

        # 检查aiohttp依赖
        try:
            import aiohttp
        except Exception:
            return False, "缺少 aiohttp，无法下载图片。请安装：pip install aiohttp"

        # 下载图片
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(url) as resp:
                    if resp.status != 200:
                        return False, f"下载失败 HTTP {resp.status}"
                    data = await resp.read()
        except Exception as e:
            return False, f"下载异常：{e}"

        # 保存图片
        f = getattr(img, "file", "") or ""
        ext = (Path(f).suffix or ".png")
        key = self._save_bytes_as_meme(data, ext)
        return True, key

    async def terminate(self):
        """插件卸载/停用时的清理逻辑（可选实现）"""
        logger.info("✅ meme_echo 插件已卸载/停用")