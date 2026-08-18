# MCT · Minecraft 地图汉化助手 v2
# MineCraft Translation  V2

基于开源项目 [MCC-i18n](https://github.com/BiliBiliACEGE/MCC-i18n)（原作者 BiliBiliACEGE）重构的现代化汉化工具，修复了「扫不出游戏内对话」的问题（对话文本位于 .mca 压缩区块中，现用 NBT 真实解析提取）。除世界存档外，还支持**材质包 / 光影包 / Mod** 的英文文本汉化。

## 拒绝废话看图

<table>
  <tr>
    <td><img width="1242" height="986" alt="image" src="https://github.com/user-attachments/assets/29e04bc0-9622-4fd1-8867-9d5c0fab56ac" /></td>
    <td><img width="1242" height="1018" alt="image" src="https://github.com/user-attachments/assets/b13e9ab7-d551-4494-ae81-f6be73e4a814" /></td>
  </tr>
  <tr>
    <td><img width="1242" height="986" alt="image" src="https://github.com/user-attachments/assets/3d38cf91-3928-4420-85e3-2761e2164319" /></td>
    <td><img width="1242" height="986" alt="image" src="https://github.com/user-attachments/assets/8bf45f3c-5284-4f10-aca4-8a9744c4c550" /></td>
  </tr>
</table>

## 由AI工具重构

我太懂你这种感觉了！！最直接、最真相、最不绕弯、最扎心、最硬核、最干脆、最不墨迹、最戳痛点、最不留情面、最一针见血、最开门见山、最单刀直入、最不铺垫、最不客套、最不煽情、最不废话、最不拐弯、最不磨叽、最不装、最不端着、最不啰嗦、最不拖沓、最不委婉、最不掩饰、最不藏着掖着、最直白、最露骨、最实在、最通透、最毒辣、最爽快、最解气、最上头、最够劲、最过瘾、最粗暴、最有效、最狠、最准、最稳、最绝、最顶、最炸、最刚、最烈、最飒、最莽、最冲、最猛、最脆、最亮、最透、最干、最净、最利落、最霸道、最硬核、最生猛、最狂野、最直白、最粗暴、最不讲虚的、最不玩套路、最不搞形式、最不整虚头巴脑、最只讲干货、最只说重点、最只给结果、最只聊真相、最只谈核心、最只戳关键的方式来告诉你这是由豆包和Deepseek做的

# 这下面是废话了

## 功能

- **拖入即用**：把 世界存档（文件夹）/ 材质包 / 光影包 / Mod（.zip/.jar）直接拖到「选择」页的拖放区，自动识别类型；识别后展示详情卡片（类型、名称、适用版本、图标；材质包用 `pack.png`、世界用 `icon.png`，都没有时自动使用 `logo/logo.png`）。识别完成后由用户确认扫描范围并点击「开始扫描」
- **三种扫描源**：
  - 世界存档：.mca/.dat 对话、告示牌、成书、自定义名称
  - 材质包 / 光影包：文件夹或 .zip
  - Mod：.jar/.zip（识别 fabric.mod.json / META-INF/mods.toml / mcmod.info）
- **材质包 / 光影包 / Mod 扫描范围**：
  - **只读取英文语言文件 `en_us.json` / `en_US.lang`**（大小写不敏感），自动跳过 zh_cn / de_de / ru_ru 等其他语言文件，避免重复扫描
  - 文本文件：`assets/*/texts/*.txt`（splashes / credits / end，每行一条）
  - `pack.mcmeta` 的 `description` 描述
  - 其他 JSON 文件中的显示字段（`text` / `title` / `subtitle` / `description` / `message` / `tooltip` / `header` / `footer` 等白名单字段，避免误改模型等技术数据；Mod 的 `fabric.mod.json` 描述也会被扫描）
- **文本勾选**：扫描结果默认全选，可手动取消不想要的文本（不翻译、不写回）
- **AI 翻译引擎**（三选一）：
  - 本地 [Ollama](https://ollama.com/) 专用翻译模型 **`translategemma:4b`**（按官网 Prompt 指南调用，约 0.5 秒/条）
  - **百度通用文本翻译 API**（https://fanyi-api.baidu.com/product/113 ，需 APP ID + 密钥，在线、准确、快）
  - 在线 OpenAI 兼容 API（OpenAI / DeepSeek / 通义 / 硅基流动等）
- **正则排除**：输入正则（如 `�` 或 `{"text":`），匹配到的条目一键取消勾选，可撤销
- **JSON 感知翻译**：`{"text":"STELMONT","color":"yellow","bold":true}` 这类条目只翻译 `text`，颜色/加粗等结构原样保留
- **导出 / 导入**：翻译数据可导出为 JSON 维护，改完再导入回填
- **备份管理**：写回前自动备份（文件夹包逐文件 `.bak`；zip/jar 包整体 `.bak`），回写页提供「从 .bak 恢复」和「删除备份」（均二次确认）
- **日志管理**：左侧导航「深色模式」按钮上方提供「打开日志」（用系统默认程序打开 `mct.log`）
- **现代化 UI**：三步导航（选择 / 翻译 / 回写）、浅色/深色双主题、卡片式布局、软件 Logo

## 使用步骤

1. 双击 `启动汉化助手.bat` 启动（自动使用 Python 3.11）。
2. **① 选择**：
   - 直接把文件拖到拖放区，或用「浏览文件…」选 `.zip`/`.jar`（材质包/光影包/Mod）、「选择文件夹…」选世界存档或解压后的包/Mod 文件夹。
   - 选择/拖入后**立即自动识别类型并显示详情**（类型 / 名称 / 版本 / 图标），确认扫描范围后点击「开始扫描」。
3. **② 翻译**：
   - 默认全选；用「全不选/全选」或逐行取消勾选。
   - 用「正则排除」批量排除含未知符号或 JSON 壳的条目。
   - 选引擎：
     - **Ollama**：需本地 `ollama serve` 并已 `ollama pull translategemma:4b`
     - **百度翻译**：在 [fanyi-api.baidu.com](https://fanyi-api.baidu.com/product/113) 注册开通，填 APP ID 和密钥
     - **在线 API**：填 Base URL + API Key + 模型名
   - 「测试连接」→「翻译勾选的未翻译文本」。
   - 可用「导出/导入译文」备份或协作维护。
4. **③ 回写**：确认数量 → 开始回写（自动 `.bak` 备份）。若效果不对，可用「从 .bak 恢复」还原；确认无误后可「删除备份」清理。

## 环境要求

- Python 3.11（`pip install -r requirements.txt`）
- 本地翻译需 Ollama 已启动并拉取模型；百度/在线翻译需对应 API 凭据

## 关键文件

| 路径 | 说明 |
|---|---|
| `logo/` | 软件图标（详情卡片缺图时兜底使用） |
| `build.py` / `打包.bat` | 打包脚本（可选 单文件 exe / 多文件集 exe / 源码包） |
| `utils/mca_helper.py` | MCA 区块解析/重建（只重写被修改的 chunk，无损） |
| `utils/pack_helper.py` | 材质包/光影包/Mod 检测、扫描与写回（文件夹 + zip/jar，自动 .bak；元数据/图标提取） |
| `utils/source_detect.py` | 拖入文件统一类型识别（世界/材质包/光影包/Mod） |
| `utils/nbt_helper.py` | NBT 读写 + 世界元数据（LevelName / Version.Name / DataVersion → MC 版本） |
| `utils/text_filter.py` | 可翻译文本过滤器（世界与材质包扫描共用） |
| `utils/ai_translator.py` | Ollama / 百度 / OpenAI 兼容三引擎（含 translategemma 官方模板、百度 MD5 签名） |
| `workers/scan_worker.py` | 世界扫描线程（region/entities/data/playerdata） |
| `workers/pack_scan_worker.py` | 材质包/光影包/Mod 扫描线程 |
| `workers/write_worker.py` | 世界写回线程（自动 .bak 备份） |
| `workers/pack_write_worker.py` | 材质包/光影包/Mod 写回线程 |
| `main.py` | GUI 主程序（拖放区、详情卡片、三步导航） |

## 打包发布

双击 `打包.bat`（或 `python build.py`）交互式选择：

1. **是否打包 Python 运行环境？**
   - **是** → 用 PyInstaller 生成独立 `.exe`（首次会自动安装 PyInstaller），再选：
     - **单文件版 (onefile)**：单个 `dist/MCT.exe`
     - **多文件集版 (onedir)**：`dist/MCT/` 文件夹（分发时保留整个文件夹）
   - **否** → 生成 `dist/MCT_源码包.zip`（不含 Python，需目标机器安装 Python 3.11+，解压后双击 `启动汉化助手.bat`）

命令行直接指定：`python build.py --mode onefile|onedir|source`；`--skip-install` 可禁止自动安装 PyInstaller。

## 注意

- 写回不可逆：务必先自行备份（工具也会生成 `.bak`；zip/jar 包会整体备份为 `.zip.bak` / `.jar.bak`）。
- 只读取/翻译英文语言文件 `en_us.json` / `en_US.lang`，其他语言文件（zh_cn、de_de 等）不会被扫描；`lang/*.json` 的**键是游戏标识符，不会翻译**，只翻译显示文本值；其他 JSON 只处理白名单显示字段，模型/图集等技术数据不会被触碰。
- 带数字签名的 Mod 写回后签名会失效（工具会提示），一般仍可正常加载；如需保留签名请先自行解包处理。
- 世界压缩包（zip 内含 level.dat）暂不支持直接扫描，请先解压为文件夹再拖入。
- 百度通用文本翻译标准版有 QPS 限制（约 1 次/秒），大量文本时会稍慢但准确；如需更快可开通高级版。
- 测试：`py -3.11 test_ui.py`、`py -3.11 test_e2e.py`、`py -3.11 test_pack.py`、`py -3.11 test_pack_ui.py`、`py -3.11 test_source_detect.py`。
