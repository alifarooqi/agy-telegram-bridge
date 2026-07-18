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
        # Maps chat_id (str) -> conversation_id (str)
        self.saved_sessions: dict[str, str] = self._load_saved_sessions()

    def _load_saved_sessions(self) -> dict[str, str]:
        """Loads saved session mappings from disk."""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        logger.info(f"Loaded {len(data)} saved session mappings from {self.session_file}")
                        return data
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
        resuming from a saved conversation ID if available.
        """
        if chat_id not in self.active_agents:
            logger.info(f"Creating/resuming Antigravity session for chat_id: {chat_id}")
            
            # Check for saved conversation_id
            saved_conv_id = self.saved_sessions.get(str(chat_id))
            
            # Get base configuration and inject saved conversation_id if present
            config = get_agent_config()
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
            if self.saved_sessions.get(chat_key) != conv_id:
                logger.info(f"Recording new conversation ID '{conv_id}' for chat_id: {chat_id}")
                self.saved_sessions[chat_key] = conv_id
                self._save_sessions()

    async def close_session(self, chat_id: int) -> bool:
        """Closes and removes a specific agent session by chat_id, clearing its persistence."""
        agent = self.active_agents.pop(chat_id, None)
        chat_key = str(chat_id)
        
        # Remove from saved sessions as well to allow a fresh start
        removed_saved = self.saved_sessions.pop(chat_key, None) is not None
        if removed_saved:
            self._save_sessions()
            
        if agent:
            logger.info(f"Closing active Antigravity session for chat_id: {chat_id}")
            await agent.__aexit__(None, None, None)
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
