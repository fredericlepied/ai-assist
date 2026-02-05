"""Monitor runner - executes monitors with knowledge graph integration"""

import json
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from .state import StateManager
from .knowledge_graph import KnowledgeGraph
from .tasks import MonitorDefinition

if TYPE_CHECKING:
    from .agent import AiAssistAgent


class MonitorRunner:
    """Execute a monitor and optionally store results in knowledge graph"""

    def __init__(
        self,
        monitor_def: MonitorDefinition,
        agent: "AiAssistAgent",
        state_manager: StateManager,
        knowledge_graph: Optional[KnowledgeGraph] = None
    ):
        self.monitor_def = monitor_def
        self.agent = agent
        self.state_manager = state_manager
        self.knowledge_graph = knowledge_graph

    async def run(self) -> list[dict]:
        """Execute monitor and return results"""

        cache_key = f"monitor_{self.monitor_def.name}"
        cached = self.state_manager.get_cached_query(cache_key)

        if cached:
            print(f"Using cached results for {self.monitor_def.name}")
            return [cached]

        try:
            output = await self.agent.query(self.monitor_def.prompt)

            result_data = {
                "monitor": self.monitor_def.name,
                "summary": output,
                "timestamp": datetime.now().isoformat(),
            }

            self.state_manager.cache_query_result(cache_key, result_data, ttl_seconds=300)

            self.state_manager.append_history(f"monitor_{self.monitor_def.name}", {
                "check_time": datetime.now().isoformat()
            })

            if self.knowledge_graph and self.monitor_def.knowledge_graph and \
               self.monitor_def.knowledge_graph.get("enabled"):
                await self._store_in_kg()

            self.state_manager.update_monitor(
                f"monitor_{self.monitor_def.name}",
                {"last_run": datetime.now().isoformat()}
            )

            return [result_data]

        except Exception as e:
            print(f"Error running monitor {self.monitor_def.name}: {e}")
            return []

    async def _store_in_kg(self):
        """Store structured data in knowledge graph by calling MCP tool directly"""
        if not self.knowledge_graph or not self.monitor_def.knowledge_graph:
            return

        kg_config = self.monitor_def.knowledge_graph
        mcp_tool = kg_config.get("mcp_tool")

        if not mcp_tool or "__" not in mcp_tool:
            print(f"Warning: Invalid mcp_tool format: {mcp_tool}. Expected 'server__tool'")
            return

        server_name, tool_name = mcp_tool.split("__", 1)
        session = self.agent.sessions.get(server_name)

        if not session:
            print(f"Warning: MCP server '{server_name}' not connected")
            return

        try:
            tool_args = kg_config.get("tool_args", {})
            result = await session.call_tool(tool_name, tool_args)

            if not result.content:
                print(f"Warning: No content returned from {mcp_tool}")
                return

            for item in result.content:
                if not hasattr(item, "text"):
                    continue

                text_content = item.text.strip()
                if not text_content:
                    continue

                if kg_config.get("parse_json"):
                    await self._parse_and_store_json(text_content, kg_config)

        except Exception as e:
            print(f"Warning: Could not store data in knowledge graph: {e}")

    async def _parse_and_store_json(self, text_content: str, kg_config: dict):
        """Parse JSON response and store entities in knowledge graph"""
        try:
            data = json.loads(text_content)
            tx_time = datetime.now()

            entity_type = kg_config.get("entity_type")
            if not entity_type:
                print("Warning: entity_type not specified in knowledge_graph config")
                return

            if isinstance(data, dict) and "error" in data:
                print(f"API error: {data['error']}")
                return

            entities = []
            if isinstance(data, list):
                entities = data
            elif isinstance(data, dict):
                entities = data.get("hits", data.get("issues", data.get("jobs", [])))

            for entity_data in entities:
                await self._store_entity(entity_data, entity_type, kg_config, tx_time)

        except json.JSONDecodeError as e:
            print(f"Warning: Could not parse JSON response: {e}")
        except Exception as e:
            print(f"Warning: Could not process entity: {e}")

    async def _store_entity(self, entity_data: dict, entity_type: str, kg_config: dict, tx_time: datetime):
        """Store a single entity in the knowledge graph"""

        entity_id = entity_data.get("id") or entity_data.get("key")
        if not entity_id:
            return

        created_str = entity_data.get("created_at") or entity_data.get("fields", {}).get("created", "")
        try:
            valid_from = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            valid_from = tx_time

        if entity_type == "jira_ticket":
            data = {
                "key": entity_data.get("key"),
                "project": entity_data.get("fields", {}).get("project", {}).get("key"),
                "summary": entity_data.get("fields", {}).get("summary"),
                "status": entity_data.get("fields", {}).get("status", {}).get("name"),
                "priority": entity_data.get("fields", {}).get("priority", {}).get("name"),
                "assignee": entity_data.get("fields", {}).get("assignee", {}).get("displayName")
                           if entity_data.get("fields", {}).get("assignee") else None,
            }
        elif entity_type == "dci_job":
            data = {
                "job_id": entity_id,
                "status": entity_data.get("status", "unknown"),
                "remoteci_id": entity_data.get("remoteci_id"),
                "topic_id": entity_data.get("topic_id"),
                "state": entity_data.get("state"),
            }

            for component in entity_data.get("components", []):
                comp_id = component.get("id")
                if comp_id:
                    try:
                        self.knowledge_graph.insert_entity(
                            entity_type="dci_component",
                            entity_id=comp_id,
                            valid_from=valid_from,
                            tx_from=tx_time,
                            data={
                                "type": component.get("type"),
                                "version": component.get("version"),
                                "name": component.get("name"),
                            }
                        )
                    except Exception:
                        pass

                    self.knowledge_graph.insert_relationship(
                        rel_type="job_uses_component",
                        source_id=entity_id,
                        target_id=comp_id,
                        valid_from=valid_from,
                        tx_from=tx_time,
                        properties={}
                    )
        else:
            data = entity_data

        self.knowledge_graph.insert_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            valid_from=valid_from,
            tx_from=tx_time,
            data=data
        )
