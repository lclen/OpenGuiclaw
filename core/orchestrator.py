from typing import Optional, Dict, Any, List
import logging
from .profiles import ProfileStore, AgentProfile

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    负责调度和委派不同配置的 agent 实例。
    每个会话可以通过这里获取到一个适合当前任务的 agent，
    也可以让一个 Master Agent 将子任务委派给 Sub-Agent。
    """

    def __init__(self, profiles_dir: str):
        self.profile_store = ProfileStore(profiles_dir)
        self.active_agents: Dict[str, Any] = {} # 存放 profile_id -> Agent 实例的映射

    def get_agent(self, profile_id: str = "default", config_path: str = "config.json"):
        """获取或初始化一个指定 profile_id 的 Agent"""
        
        # 延迟导入以避免循环依赖
        # 这里假设后面对 agent.py 会有改造，或者它包装一层
        from agent import ScreenAgent

        if profile_id in self.active_agents:
            return self.active_agents[profile_id]

        profile = self.profile_store.get(profile_id)
        if not profile:
            logger.warning(f"Profile {profile_id} not found, falling back to default")
            profile = self.profile_store.get("default")
            if not profile:
                raise ValueError("System lacks a 'default' profile.")

        # 初始化具体的 Agent，这里需要对原本的 ScreenAgent 做出改造以接受 profile
        agent = ScreenAgent(config_path=config_path, profile=profile)
        
        # Shared Identity & Memory Loading requirement handled internally by the agent during init.
        
        self.active_agents[profile_id] = agent
        logger.info(f"Initialized agent with profile: {profile.name} ({profile_id})")
        return agent

    def dispatch(self, task: str, target_profile_id: str = "default") -> str:
        """主入口调度"""
        agent = self.get_agent(target_profile_id)
        return agent.run(task)

