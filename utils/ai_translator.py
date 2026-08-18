# -*- coding: utf-8 -*-
"""
AI 翻译引擎 - Ollama 本地 / OpenAI 兼容在线 API
统一接口 translate(text) -> str，基于标准库 urllib，无需额外安装依赖。
"""

import hashlib
import json
import random
import time
import urllib.request
import urllib.error
import urllib.parse

from utils.logger import get_logger


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    """POST JSON 并返回解析后的 dict"""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', **headers},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _is_translategemma(model: str) -> bool:
    """判断是否为 TranslateGemma 系列专用翻译模型"""
    return "translategemma" in (model or "").lower()


# TranslateGemma 官方 Prompt 指南：https://ollama.com/library/translategemma:4b
# 要求单条 user 消息，使用固定模板，且待翻译文本前要有两个空行。
TRANSLATEGEMMA_TEMPLATE = (
    "You are a professional English (en) to Chinese Simplified (zh-Hans) translator. "
    "Your goal is to accurately convey the meaning and nuances of the original English text "
    "while adhering to Chinese Simplified grammar, vocabulary, and cultural sensitivities.\n"
    "Produce only the Chinese Simplified translation, without any additional explanations "
    "or commentary. Please translate the following English text into Chinese Simplified:\n\n"
    "{text}"
)


SYSTEM_PROMPT = (
    "你是《我的世界》(Minecraft) 游戏地图的资深汉化翻译，精通游戏术语。"
    "把用户给的英文文本翻译成自然、地道的简体中文。"
    "严格规则：1) 只输出译文本身，不要任何解释、引号或多余文字；"
    "2) 保留原文中的占位符、变量名、@玩家选择器、JSON 结构、颜色代码等游戏技术内容不变；"
    "3) 保留换行 \\n 与标点；4) 保持原文的说话语气与人物身份(如 NPC 名字前缀 <Name:> 原样保留)；"
    "5) 人名、地名、城镇名等专有名词按常见音译处理(如 STELMONT→斯特尔蒙特、Bayville→贝维尔)，"
    "若在对话中作为称呼则可在译文后保留原文便于辨认。"
)


class OllamaTranslator:
    """本地 Ollama 翻译（默认 translategemma:4b 专用翻译模型）"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "translategemma:4b",
                 timeout: int = 180):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.logger = get_logger()
        self._cache = {}

    def translate(self, text: str) -> str:
        if not text.strip():
            return text
        if text in self._cache:
            return self._cache[text]
        url = f"{self.base_url}/api/chat"
        if _is_translategemma(self.model):
            # 按官方指南：单条 user 消息 + 固定模板 + 空行，并限制输出长度/温度提速
            payload = {
                "model": self.model,
                "stream": False,
                "messages": [{"role": "user", "content": TRANSLATEGEMMA_TEMPLATE.format(text=text)}],
                "options": {"num_predict": 256, "temperature": 0.3},
            }
        else:
            payload = {
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            }
        for attempt in range(2):
            try:
                data = _http_post_json(url, payload, {}, self.timeout)
                content = data.get("message", {}).get("content", "").strip()
                if content:
                    self._cache[text] = content
                    return content
            except Exception as e:
                self.logger.warning(f"Ollama翻译失败(第{attempt+1}次): {e}")
                time.sleep(1)
        raise RuntimeError("Ollama 翻译失败：请确认已启动本地 Ollama 服务")

    def check_connection(self) -> str:
        """测试连接，返回可读信息"""
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            models = [m.get('name', '') for m in data.get('models', [])]
            if self.model in models:
                return f"已连接，模型 {self.model} 可用"
            return f"已连接，但未找到模型 {self.model}。已安装: {', '.join(models) or '无'}"
        except Exception as e:
            return f"连接失败: {e}"


class OpenAITranslator:
    """OpenAI 兼容在线 API（支持 OpenAI / DeepSeek / 通义 / 硅基流动 等）"""

    def __init__(self, base_url: str = "https://api.openai.com/v1",
                 api_key: str = "", model: str = "gpt-4o-mini",
                 timeout: int = 120):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.logger = get_logger()
        self._cache = {}

    def translate(self, text: str) -> str:
        if not text.strip():
            return text
        if text in self._cache:
            return self._cache[text]
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        for attempt in range(2):
            try:
                data = _http_post_json(
                    url, payload,
                    {"Authorization": f"Bearer {self.api_key}"},
                    self.timeout,
                )
                content = data["choices"][0]["message"]["content"].strip()
                if content:
                    self._cache[text] = content
                    return content
            except Exception as e:
                self.logger.warning(f"API翻译失败(第{attempt+1}次): {e}")
                time.sleep(1)
        raise RuntimeError("在线 API 翻译失败：请检查 API Key 与网络")

    def check_connection(self) -> str:
        """测试连接，返回可读信息"""
        try:
            url = f"{self.base_url}/models"
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {self.api_key}"})
            with urllib.request.urlopen(req, timeout=10):
                return f"连接成功，模型 {self.model}（可尝试翻译验证）"
        except Exception as e:
            return f"连接失败: {e}"


class BaiduTranslator:
    """
    百度通用文本翻译 API（https://fanyi-api.baidu.com/product/113）
    经典接口 /api/trans/vip/translate，MD5 签名：appid + q + salt + 密钥
    需要在百度翻译开放平台申请 APP ID 与密钥，并开通通用文本翻译服务。
    """

    API_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"

    def __init__(self, appid: str, secret_key: str,
                 from_lang: str = "en", to_lang: str = "zh", timeout: int = 30):
        self.appid = appid.strip()
        self.secret_key = secret_key.strip()
        self.from_lang = from_lang
        self.to_lang = to_lang
        self.timeout = timeout
        self.logger = get_logger()
        self._cache = {}

    def _sign(self, q: str, salt: str) -> str:
        raw = f"{self.appid}{q}{salt}{self.secret_key}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def translate(self, text: str) -> str:
        if not text or not text.strip():
            return text
        if text in self._cache:
            return self._cache[text]
        if not self.appid or not self.secret_key:
            raise RuntimeError("百度翻译未配置 APP ID 或密钥")
        salt = str(random.randint(32768, 655360))
        sign = self._sign(text, salt)
        data = urllib.parse.urlencode({
            "q": text, "from": self.from_lang, "to": self.to_lang,
            "appid": self.appid, "salt": salt, "sign": sign,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                if "error_code" in payload:
                    raise RuntimeError(
                        f"百度翻译错误 {payload['error_code']}: {payload.get('error_msg', '')}")
                result = "\n".join(
                    item.get("dst", "") for item in payload.get("trans_result", []))
                if result:
                    self._cache[text] = result
                    return result
                raise RuntimeError("返回结果为空")
            except Exception as e:
                self.logger.warning(f"百度翻译失败(第{attempt+1}次): {e}")
                time.sleep(1)
        raise RuntimeError("百度翻译失败：请检查 APP ID/密钥、服务开通状态与网络")

    def check_connection(self) -> str:
        """测试连接，返回可读信息"""
        try:
            r = self.translate("hello")
            return f"连接成功，测试：hello → {r}"
        except Exception as e:
            return f"连接失败: {e}"


def build_translator(engine: str, cfg: dict):
    """按配置构建翻译器实例"""
    if engine == "ollama":
        return OllamaTranslator(
            base_url=cfg.get("ollama_url", "http://localhost:11434"),
            model=cfg.get("ollama_model", "translategemma:4b"),
        )
    if engine == "baidu":
        return BaiduTranslator(
            appid=cfg.get("baidu_appid", ""),
            secret_key=cfg.get("baidu_secret", ""),
            from_lang=cfg.get("baidu_from", "en"),
            to_lang=cfg.get("baidu_to", "zh"),
        )
    return OpenAITranslator(
        base_url=cfg.get("api_url", "https://api.openai.com/v1"),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("api_model", "gpt-4o-mini"),
    )
