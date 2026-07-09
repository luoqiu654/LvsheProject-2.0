from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from backend.config import PROJECT_ROOT
from backend.core.agents import LegalAgent
from backend.core.rag import LegalRAG, rag as default_rag


SKILLS_ROOT = PROJECT_ROOT / "skills"


@dataclass(frozen=True)
class SkillMetadata:
    """
    Agent Skill 元数据。

    对应 SKILL.md frontmatter 中的内容。
    """

    name: str
    description: str
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, Any] | None = None


@dataclass
class AgentSkill:
    """
    一个完整的 Agent Skill。
    """

    metadata: SkillMetadata
    path: Path
    instructions: str = ""

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description


@dataclass
class SkillExecutionResult:
    """
    Skill 执行结果。
    """

    skill_name: str
    input_text: str
    output_text: str
    used_resources: list[str]


class SkillRegistryError(RuntimeError):
    """Skill 注册表异常。"""


class SkillRegistry:
    """
    Agent Skills 注册表。

    设计原则：
    1. discovery 阶段只读取 name / description 等元数据
    2. activate 阶段才读取完整 instructions
    3. Skill 文件以目录形式组织，每个目录必须有 SKILL.md
    """

    def __init__(self, skills_root: str | Path = SKILLS_ROOT) -> None:
        self.skills_root = Path(skills_root)
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, AgentSkill] = {}
        self.discover()

    def discover(self) -> list[SkillMetadata]:
        """
        发现本地所有 skills。

        只读取 SKILL.md 的 YAML frontmatter 和正文，
        但对外主要暴露 metadata，符合渐进式加载思路。
        """
        self._skills = {}

        for skill_dir in sorted(self.skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            metadata, instructions = self._parse_skill_file(skill_file)

            if metadata.name != skill_dir.name:
                raise SkillRegistryError(
                    f"Skill 名称必须与目录名一致：目录={skill_dir.name}, name={metadata.name}"
                )

            self._skills[metadata.name] = AgentSkill(
                metadata=metadata,
                path=skill_dir,
                instructions=instructions,
            )

        return self.list_metadata()

    def list_metadata(self) -> list[SkillMetadata]:
        return [skill.metadata for skill in self._skills.values()]

    def list_names(self) -> list[str]:
        return sorted(self._skills.keys())

    def get(self, name: str) -> AgentSkill:
        if name not in self._skills:
            available = ", ".join(self.list_names()) or "无"
            raise SkillRegistryError(
                f"Skill 不存在：{name}。当前可用 Skills：{available}"
            )

        return self._skills[name]

    def activate(self, name: str) -> AgentSkill:
        """
        激活 skill。

        当前实现中 instructions 已经解析好；
        这个方法保留为清晰的语义入口。
        """
        return self.get(name)

    def match(self, task: str) -> Optional[AgentSkill]:
        """
        根据用户任务简单匹配最合适的 skill。

        当前是规则 MVP。
        后续可以升级为：
        - embedding 匹配
        - LLM Router
        - LangGraph Router
        """
        text = task.lower()

        if any(keyword in task for keyword in ["审查", "风险", "条款", "合同文本", "甲方", "乙方"]):
            return self._skills.get("contract-risk-review")

        if any(keyword in task for keyword in ["法律依据", "违约", "定金", "租赁", "劳动", "赔偿", "合同"]):
            return self._skills.get("law-search")

        if any(keyword in text for keyword in ["consult", "advice"]) or any(
            keyword in task for keyword in ["咨询", "怎么办", "能不能", "可以吗"]
        ):
            return self._skills.get("legal-consultation")

        return self._skills.get("legal-consultation")

    def _parse_skill_file(self, path: Path) -> tuple[SkillMetadata, str]:
        raw = path.read_text(encoding="utf-8")

        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, flags=re.DOTALL)
        if not match:
            raise SkillRegistryError(f"SKILL.md 缺少 YAML frontmatter：{path}")

        frontmatter_text = match.group(1)
        instructions = match.group(2).strip()

        data = yaml.safe_load(frontmatter_text) or {}

        name = data.get("name")
        description = data.get("description")

        if not name or not description:
            raise SkillRegistryError(f"SKILL.md 必须包含 name 和 description：{path}")

        self._validate_skill_name(name)

        return (
            SkillMetadata(
                name=name,
                description=description,
                license=data.get("license", ""),
                compatibility=data.get("compatibility", ""),
                metadata=data.get("metadata", {}),
            ),
            instructions,
        )

    def _validate_skill_name(self, name: str) -> None:
        """
        Agent Skills 规范风格：
        - 小写字母、数字、短横线
        - 不能以短横线开头或结尾
        - 不允许连续短横线
        """
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise SkillRegistryError(
                f"非法 skill name：{name}。请使用小写字母、数字和单短横线。"
            )


class SkillExecutor:
    """
    Skill 执行器。

    它把标准化 Skill 描述映射到本项目已有能力：
    - law-search -> LegalRAG
    - contract-risk-review -> 合同风险审查规则
    - legal-consultation -> LangGraph LegalAgent
    """

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        rag_engine: Optional[LegalRAG] = None,
        legal_agent: Optional[LegalAgent] = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.rag_engine = rag_engine or default_rag
        self.legal_agent = legal_agent or LegalAgent(rag_engine=self.rag_engine)

    async def execute(
        self,
        skill_name: str,
        input_text: str,
        use_llm: bool = True,
    ) -> SkillExecutionResult:
        skill = self.registry.activate(skill_name)

        if skill.name == "law-search":
            output = await self._execute_law_search(input_text)

        elif skill.name == "contract-risk-review":
            output = await self._execute_contract_risk_review(input_text, use_llm=use_llm)

        elif skill.name == "legal-consultation":
            output = await self._execute_legal_consultation(input_text, use_llm=use_llm)

        else:
            raise SkillRegistryError(f"Skill 尚未接入执行器：{skill.name}")

        resources = self._list_resources(skill.path)

        return SkillExecutionResult(
            skill_name=skill.name,
            input_text=input_text,
            output_text=output,
            used_resources=resources,
        )

    async def execute_best_match(
        self,
        input_text: str,
        use_llm: bool = True,
    ) -> SkillExecutionResult:
        skill = self.registry.match(input_text)

        if skill is None:
            raise SkillRegistryError("没有可用 Skill")

        return await self.execute(
            skill_name=skill.name,
            input_text=input_text,
            use_llm=use_llm,
        )

    async def _execute_law_search(self, input_text: str) -> str:
        answer = await self.rag_engine.answer(
            question=input_text,
            top_k=3,
            use_llm_query_transform=False,
            use_llm_hyde=False,
            use_llm_answer=False,
        )

        if not answer.contexts:
            return "知识库中暂时没有检索到相关资料。"

        lines = ["法律知识库检索结果："]

        for index, item in enumerate(answer.contexts, start=1):
            content = item.enriched_text.strip().replace("\n", " ")
            if len(content) > 280:
                content = content[:280] + "..."

            lines.append(
                f"{index}. 来源：{item.source}；相关度：{item.final_score:.4f}；内容：{content}"
            )

        return "\n".join(lines)

    async def _execute_contract_risk_review(self, input_text: str, use_llm: bool = True) -> str:
        """
        合同风险审查 Skill。

        先用规则引擎做初筛，再调用 LLM 生成专业审查建议。
        """
        # 步骤1：规则引擎初筛
        rule_result = self.legal_agent._tool_contract_risk_check(input_text)

        checklist_path = (
            self.registry.get("contract-risk-review").path
            / "references"
            / "review_checklist.md"
        )

        checklist_note = ""
        if checklist_path.exists():
            checklist_note = (
                "\n\n已参考技能资源："
                f"{checklist_path.relative_to(PROJECT_ROOT)}"
            )

        # 步骤2：调用 LLM 生成专业审查建议
        if use_llm:
            try:
                from backend.core.llm_gateway import gateway as default_gateway

                prompt = f"""你是专业合同法律师。请对以下合同内容进行风险审查，给出专业分析和修改建议。

合同内容：
{input_text}

规则引擎初筛结果：
{rule_result}

请按以下格式输出：
1. 风险概述（总体评价）
2. 具体风险点（按严重程度排序，标注高/中/低风险）
3. 修改建议（针对每个风险点给出具体修改意见）
4. 补充条款建议（如有必要）

注意：不要编造法条编号，结尾提醒复杂情况咨询专业律师。""".strip()

                llm_advice = await default_gateway.chat_text(
                    user_message=prompt,
                    system_message="你是专业、严谨的合同法律师，不会编造法条。",
                    max_tokens=2000,
                    temperature=0.3,
                )
                return f"{llm_advice}{checklist_note}"
            except Exception as exc:
                # LLM 失败时回退到规则结果
                return f"⚠️ LLM 分析失败（{exc}），以下为规则引擎初筛结果：\n\n{rule_result}{checklist_note}"

        return f"{rule_result}{checklist_note}"

    async def _execute_legal_consultation(
        self,
        input_text: str,
        use_llm: bool = True,
    ) -> str:
        result = await self.legal_agent.run(input_text, use_llm=use_llm)

        # 只返回最终回答，调度详情（工具名、步骤等）不混入回答
        # 如果 final_answer 为空或是 fallback（以"结论：我已根据问题调用工具"开头），
        # 尝试用 LLM 重新生成
        final_answer = result.final_answer
        if (
            not final_answer.strip()
            or final_answer.startswith("结论：我已根据问题调用工具")
        ):
            if use_llm:
                try:
                    from backend.core.llm_gateway import gateway as default_gateway

                    tool_context = result.tool_result or ""
                    prompt = (
                        f"你是专业法律顾问。请回答以下问题：\n\n{input_text}\n\n"
                        + (f"参考信息：\n{tool_context}\n\n" if tool_context else "")
                        + "要求：先给结论，再说明依据，最后给出建议。不要编造法条编号。"
                    )
                    final_answer = await default_gateway.chat_text(
                        user_message=prompt,
                        system_message="你是专业、严谨的法律顾问，不会编造法条。",
                        max_tokens=1500,
                        temperature=0.3,
                    )
                except Exception:
                    pass  # 保留原始 final_answer

        return final_answer

    def _list_resources(self, skill_path: Path) -> list[str]:
        resources: list[str] = []

        for subdir in ["references", "scripts", "assets"]:
            path = skill_path / subdir
            if not path.exists():
                continue

            for file in path.rglob("*"):
                if file.is_file():
                    resources.append(str(file.relative_to(PROJECT_ROOT)))

        return sorted(resources)


registry = SkillRegistry()
skill_executor = SkillExecutor(registry=registry)


async def _demo() -> None:
    print("已发现 Skills：")
    for meta in registry.list_metadata():
        print(f"- {meta.name}: {meta.description}")

    samples = [
        "合同一方违约了，我可以要求赔偿吗？",
        "请审查这个合同条款风险：甲方委托乙方开发网站，费用5000元，没有写交付时间和争议解决。",
        "我遇到合同纠纷怎么办？",
    ]

    for text in samples:
        print("=" * 80)
        print("输入：", text)

        result = await skill_executor.execute_best_match(
            input_text=text,
            use_llm=False,
        )

        print("匹配 Skill：", result.skill_name)
        print("使用资源：", result.used_resources)
        print("输出：")
        print(result.output_text)


if __name__ == "__main__":
    asyncio.run(_demo())
