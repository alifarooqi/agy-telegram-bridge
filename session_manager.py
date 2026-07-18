import json
import logging
import os
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.conversation.conversation import Conversation
from config import get_agent_config

logger = logging.getLogger(__name__)

SESSION_FILE = "sessions.json"

class SessionManager:
    """Manages independent, stateful Antigravity Agent sessions per Telegram chat_id.
    
    Persists session mappings (chat_id -> conversation_id) to disk so that
    conversation history is preserved across bot restarts.
    """
    
    def __init__(self, session_file: str = SESSION_FILE):
        self.session_file = session_file
        # Maps chat_id (int) -> Agent instance
        self.active_agents: dict[int, Agent] = {}
        # Maps chat_id (str) -> dict containing 'conversation_id' and 'project_dir'
        self.saved_sessions: dict[str, dict] = self._load_saved_sessions()

    def _load_saved_sessions(self) -> dict[str, dict]:
        """Loads saved session mappings from disk, supporting migration from flat formats."""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        migrated = {}
                        for k, v in data.items():
                            if isinstance(v, str):
                                # Migrate legacy flat conversation_id string to dictionary schema
                                migrated[k] = {"conversation_id": v, "project_dir": None}
                            elif isinstance(v, dict):
                                migrated[k] = {
                                    "conversation_id": v.get("conversation_id"),
                                    "project_dir": v.get("project_dir")
                                }
                            else:
                                migrated[k] = {"conversation_id": None, "project_dir": None}
                        logger.info(f"Loaded {len(migrated)} saved session mappings from {self.session_file}")
                        return migrated
            except Exception as e:
                logger.error(f"Error loading saved sessions: {e}")
        return {}

    def _save_sessions(self):
        """Saves current session mappings to disk."""
        try:
            with open(self.session_file, "w") as f:
                json.dump(self.saved_sessions, f, indent=2)
            logger.info("Saved session mappings to disk.")
        except Exception as e:
            logger.error(f"Error saving sessions to disk: {e}")

    async def get_conversation(self, chat_id: int) -> Conversation:
        """Retrieves or creates a stateful conversation for the given chat_id,
        resuming from a saved conversation ID and workspace directory if available.
        """
        # Check if we have an active agent and if it's still connected
        if chat_id in self.active_agents:
            agent = self.active_agents[chat_id]
            is_active = False
            try:
                if agent.is_started and agent.conversation and agent.conversation.connection:
                    conn = agent.conversation.connection
                    if hasattr(conn, "_ws") and conn._ws and conn._ws.open:
                        is_active = True
            except Exception as e:
                logger.warning(f"Error checking connection status for chat_id {chat_id}: {e}")
            
            if not is_active:
                logger.info(f"Antigravity session for chat_id {chat_id} is disconnected. Restarting session...")
                await self.close_session(chat_id, clear_persistence=False)

        if chat_id not in self.active_agents:
            logger.info(f"Creating/resuming Antigravity session for chat_id: {chat_id}")
            
            # Check for saved conversation_id and project_dir
            chat_key = str(chat_id)
            session_data = self.saved_sessions.get(chat_key, {})
            saved_conv_id = session_data.get("conversation_id")
            project_dir = session_data.get("project_dir")
            
            # Get base configuration and inject saved settings
            config = get_agent_config(project_dir=project_dir)
            if saved_conv_id:
                logger.info(f"Resuming conversation with ID: {saved_conv_id}")
                config = config.model_copy(update={"conversation_id": saved_conv_id})
                
            agent = Agent(config)
            await agent.__aenter__()
            self.active_agents[chat_id] = agent
            
        return self.active_agents[chat_id].conversation

    def record_conversation_id(self, chat_id: int):
        """Inspects the active session for a conversation_id and saves it if new."""
        agent = self.active_agents.get(chat_id)
        if agent and agent.conversation_id:
            conv_id = agent.conversation_id
            chat_key = str(chat_id)
            session_data = self.saved_sessions.setdefault(chat_key, {"conversation_id": None, "project_dir": None})
            if session_data.get("conversation_id") != conv_id:
                logger.info(f"Recording new conversation ID '{conv_id}' for chat_id: {chat_id}")
                session_data["conversation_id"] = conv_id
                self._save_sessions()

    async def set_project_dir(self, chat_id: int, project_dir: str | None) -> None:
        """Sets the working project directory for the session and resets the active session to apply it."""
        chat_key = str(chat_id)
        session_data = self.saved_sessions.setdefault(chat_key, {"conversation_id": None, "project_dir": None})
        session_data["project_dir"] = project_dir
        self._save_sessions()
        
        # Close active agent connection so the next turn starts in the updated workspace
        if chat_id in self.active_agents:
            logger.info(f"Resetting active session for chat_id {chat_id} to apply new workspace: {project_dir}")
            await self.close_session(chat_id, clear_persistence=False)

    async def close_session(self, chat_id: int, clear_persistence: bool = True) -> bool:
        """Closes and removes a specific agent session by chat_id, optionally clearing persistence."""
        agent = self.active_agents.pop(chat_id, None)
        chat_key = str(chat_id)
        
        if clear_persistence:
            removed_saved = self.saved_sessions.pop(chat_key, None) is not None
            if removed_saved:
                self._save_sessions()
        else:
            removed_saved = False
            
        if agent:
            logger.info(f"Closing active Antigravity session for chat_id: {chat_id}")
            try:
                await agent.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error during agent session cleanup for chat_id {chat_id}: {e}")
            return True
            
        return removed_saved

    async def close_all(self):
        """Closes all active sessions. Useful on bot shutdown."""
        logger.info("Closing all active Antigravity sessions")
        for chat_id, agent in list(self.active_agents.items()):
            try:
                await agent.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing session {chat_id}: {e}")
        self.active_agents.clear()
