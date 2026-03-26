"""
Auto-generated skill wrapper from https://raw.githubusercontent.com/MiniMax-AI/skills/main/skills/minimax-docx/SKILL.md
"""

import subprocess

def register(skills_manager):
    @skills_manager.skill(
        name="remote_minimax_docx_cli",
        description="""【动态解析技能: minimax_docx】Professional DOCX document creation, editing, and formatting using OpenXML SDK (.NET). Three pipelines: (A) create new documents from scratch, (B) fill/edit content in existing documents, (C) apply template formatting with XSD validation gate-check. MUST use this skill whenever the user wants to produce, modify, or format a Word document — including when they say "write a report", "draft a proposal", "make a contract", "fill in this form", "reformat to match this template", or any task whose final output is a .docx file. Even if the user doesn't mention "docx" explicitly, if the task implies a printable/formal document, use this skill.
 只能执行: []""",
        parameters={
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    )
    def remote_cli_runner(command: str) -> str:
        try:
            import os
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            res = subprocess.run(command, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120, **kwargs)
            return res.stdout or f"报错: {res.stderr}"
        except Exception as e:
            return str(e)
