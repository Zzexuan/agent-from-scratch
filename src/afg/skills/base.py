import os
from abc import ABC, abstractmethod

from afg.config import SkillConfig
from afg.context.counter import TokenCounter
from afg.exceptions import AfgError, ToolError
from afg.observability.logging import get_logger
from afg.tools.decorator import tool

MARKDOWN_SUFFIX = ".md"
FENCE = "---"
NAME_KEY = "name"
DESCRIPTION_KEY = "description"

_LOADERS = {}


class BaseSkill(ABC):
    name = ""
    description = ""

    @abstractmethod
    def load_body(self):
        ...


class FileSkill(BaseSkill):
    def __init__(self, name, description, path):
        self.name = name
        self.description = description
        self._path = path

    def load_body(self) -> str:
        return read_skill_file(self._path)[2]


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def split_frontmatter(text, source):
    lines = text.splitlines()
    if not lines or lines[0].strip() != FENCE:
        raise AfgError("技能文件第 1 行必须是 ---（frontmatter 起点）：" + source)
    end = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == FENCE:
            end = index
            break
    if end < 0:
        raise AfgError("技能文件的 frontmatter 没有收尾的 ---：" + source)
    header = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).strip()
    return header, body


def parse_fields(header, source):
    fields = {}
    for line in header.splitlines():
        text = line.strip()
        if not text:
            continue
        # description 里可能出现 ASCII 冒号（网址、时间），只按第一个冒号切才不会把它切断
        parts = text.split(":", 1)
        if len(parts) != 2:
            raise AfgError("frontmatter 这一行不是 key: value 格式：" + text)
        fields[parts[0].strip()] = parts[1].strip()
    return fields


def read_skill_file(path):
    source = os.path.basename(path)
    header, body = split_frontmatter(read_text(path), source)
    fields = parse_fields(header, source)
    name = fields.get(NAME_KEY, "")
    description = fields.get(DESCRIPTION_KEY, "")
    if not name:
        raise AfgError("技能文件缺少 name：" + source)
    if not description:
        # description 是渐进披露唯一的入口：空了模型就永远不知道该不该加载它
        raise AfgError("技能文件缺少 description：" + source)
    return name, description, body


class SkillLoader:
    def __init__(self, skills_dir):
        self._skills_dir = skills_dir
        self._skills = {}
        self._counter = TokenCounter()
        self._max_body_tokens = SkillConfig().max_body_tokens
        self._scan()

    def _scan(self):
        if not os.path.isdir(self._skills_dir):
            raise AfgError(
                "技能目录不存在：" + self._skills_dir,
                context={"hint": "把 *.md 技能文件放进去，或改 SkillConfig.skills_dir"},
            )
        for file_name in sorted(os.listdir(self._skills_dir)):
            if not file_name.endswith(MARKDOWN_SUFFIX):
                continue
            path = os.path.join(self._skills_dir, file_name)
            name, description, _ = read_skill_file(path)
            self._skills[name] = FileSkill(name, description, path)

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def list_skills(self) -> list[BaseSkill]:
        return list(self._skills.values())

    def get(self, name: str) -> BaseSkill:
        if name not in self._skills:
            raise AfgError(
                "没有这个技能",
                context={"skill": name, "available": self.names()},
            )
        return self._skills[name]

    def inject_index(self) -> str:
        if not self._skills:
            return ""
        lines = ["你可以加载以下技能手册。任务匹配某条描述时，先调 load_skill 取全文，再按手册的流程做事："]
        for name in self._skills:
            lines.append("- " + name + "：" + self._skills[name].description)
        logger = get_logger("skill")
        logger.info("skill.index", count=len(self._skills), names=self.names())
        return "\n".join(lines)

    def load_body(self, name: str) -> str:
        skill = self.get(name)
        body = skill.load_body()
        tokens = self._counter.count(body)
        logger = get_logger("skill")
        logger.info("skill.load", name=name, tokens=tokens, chars=len(body))
        if tokens > self._max_body_tokens:
            # 不静默截断：手册被切掉一半比多花点 token 更危险，宁可留下一条显眼的告警
            logger.warning(
                "skill.body_too_long",
                name=name,
                tokens=tokens,
                limit=self._max_body_tokens,
            )
        return body


def get_loader(skills_dir):
    if skills_dir not in _LOADERS:
        _LOADERS[skills_dir] = SkillLoader(skills_dir)
    return _LOADERS[skills_dir]


@tool
def load_skill(name: str) -> str:
    """加载一个技能的完整操作手册。当任务匹配「可用技能」列表里的某条描述时，先调用这个工具拿到手册全文，再按手册里的流程做事。

    :param name: 技能名，必须是可用技能列表里出现过的名字
    """
    try:
        loader = get_loader(SkillConfig().skills_dir)
        return loader.load_body(name)
    except AfgError as error:
        raise ToolError("加载技能失败：" + str(error), context=error.context)
