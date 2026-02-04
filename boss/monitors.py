"""Monitoring tasks for Jira and DCI"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from .agent import BossAgent
from .state import StateManager
from .knowledge_graph import KnowledgeGraph
from .tasks import TaskLoader
from .task_runner import TaskRunner
from .task_watcher import TaskFileWatcher


class JiraMonitor:
    """Monitor Jira projects for updates"""

    def __init__(
        self,
        agent: BossAgent,
        projects: list[str],
        state_manager: StateManager,
        knowledge_graph: Optional[KnowledgeGraph] = None
    ):
        self.agent = agent
        self.projects = projects
        self.state_manager = state_manager
        self.knowledge_graph = knowledge_graph
        self.monitor_name = "jira_monitor"

    async def check(self) -> list[dict]:
        """Check for Jira updates"""
        if not self.projects:
            return []

        state = self.state_manager.get_monitor_state(self.monitor_name)
        issues = []

        for project in self.projects:
            cache_key = f"jira_project_{project}"
            cached = self.state_manager.get_cached_query(cache_key)

            if cached:
                print(f"Using cached results for Jira project {project}")
                issues.append(cached)
                continue

            jql = f"project = {project} AND updated >= -1d ORDER BY updated DESC"
            prompt = f"""
            Search for Jira tickets using this JQL query: {jql}

            Please provide:
            1. List of ticket keys (e.g., CILAB-1234)
            2. Number of tickets found
            3. Any critical or high priority tickets
            4. Tickets that need attention
            """

            try:
                result = await self.agent.query(prompt)
                issue_data = {
                    "project": project,
                    "summary": result,
                    "timestamp": datetime.now().isoformat(),
                }

                self.state_manager.cache_query_result(cache_key, issue_data, ttl_seconds=300)

                self.state_manager.append_history(self.monitor_name, {
                    "project": project,
                    "check_time": datetime.now().isoformat()
                })

                if self.knowledge_graph:
                    await self._store_jira_tickets_in_kg(jql, project)

                issues.append(issue_data)
            except Exception as e:
                print(f"Error checking Jira project {project}: {e}")

        self.state_manager.update_monitor(
            self.monitor_name,
            {"projects": self.projects, "issue_count": len(issues)}
        )

        return issues

    async def _store_jira_tickets_in_kg(self, jql: str, project: str):
        """Call Jira MCP tool directly and store structured data in KG"""
        try:
            session = self.agent.sessions.get("dci")
            if not session:
                return

            result = await session.call_tool("search_jira_tickets", {
                "jql": jql,
                "max_results": 20
            })

            if result.content:
                for item in result.content:
                    if hasattr(item, "text"):
                        try:
                            tickets_data = json.loads(item.text)
                            tx_time = datetime.now()

                            tickets = []
                            if isinstance(tickets_data, list):
                                tickets = tickets_data
                            elif isinstance(tickets_data, dict):
                                tickets = tickets_data.get("issues", [])

                            for ticket in tickets:
                                ticket_key = ticket.get("key")
                                if not ticket_key:
                                    continue

                                created_str = ticket.get("fields", {}).get("created", "")
                                try:
                                    valid_from = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                                except (ValueError, AttributeError):
                                    valid_from = tx_time

                                self.knowledge_graph.insert_entity(
                                    entity_type="jira_ticket",
                                    entity_id=ticket_key,
                                    valid_from=valid_from,
                                    tx_from=tx_time,
                                    data={
                                        "key": ticket_key,
                                        "project": project,
                                        "summary": ticket.get("fields", {}).get("summary"),
                                        "status": ticket.get("fields", {}).get("status", {}).get("name"),
                                        "priority": ticket.get("fields", {}).get("priority", {}).get("name"),
                                        "assignee": ticket.get("fields", {}).get("assignee", {}).get("displayName") if ticket.get("fields", {}).get("assignee") else None,
                                    }
                                )
                        except json.JSONDecodeError as e:
                            print(f"Warning: Could not parse Jira response JSON: {e}")
                        except Exception as e:
                            print(f"Warning: Could not process Jira ticket: {e}")

        except Exception as e:
            print(f"Warning: Could not store Jira tickets in knowledge graph: {e}")


class DCIMonitor:
    """Monitor DCI jobs"""

    def __init__(
        self,
        agent: BossAgent,
        queries: list[str],
        state_manager: StateManager,
        knowledge_graph: Optional[KnowledgeGraph] = None
    ):
        self.agent = agent
        self.queries = queries
        self.state_manager = state_manager
        self.knowledge_graph = knowledge_graph
        self.monitor_name = "dci_monitor"

    async def check(self) -> list[dict]:
        """Check for DCI job updates"""
        if not self.queries:
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            self.queries = [
                f"((status in ['failure', 'error']) and (created_at >= '{yesterday}'))"
            ]

        state = self.state_manager.get_monitor_state(self.monitor_name)
        results = []
        all_job_ids = set()

        for query in self.queries:
            cache_key = f"dci_query_{hash(query)}"
            cached = self.state_manager.get_cached_query(cache_key)

            if cached:
                print(f"Using cached results for DCI query")
                results.append(cached)
                continue

            prompt = f"""
            Search DCI jobs with this query: {query}
            Limit results to 20 most recent jobs.

            Please provide a concise summary including:
            1. Total number of jobs matching
            2. Number of failures/errors
            3. Most recent 5 job IDs
            4. Key failure patterns (if any)
            5. Urgent items needing attention
            """

            try:
                result = await self.agent.query(prompt)
                result_data = {
                    "query": query,
                    "summary": result,
                    "timestamp": datetime.now().isoformat(),
                }

                self.state_manager.cache_query_result(cache_key, result_data, ttl_seconds=300)

                self.state_manager.append_history(self.monitor_name, {
                    "query": query,
                    "check_time": datetime.now().isoformat()
                })

                results.append(result_data)

                if self.knowledge_graph and result:
                    await self._store_dci_jobs_in_kg(result, query)

                # Track job IDs (would need to parse from result in real implementation)
                # For now, we'll track queries
                all_job_ids.add(hash(query))

            except Exception as e:
                print(f"Error checking DCI with query '{query}': {e}")

        new_items = self.state_manager.get_new_items(self.monitor_name, all_job_ids)
        if new_items:
            print(f"Found {len(new_items)} new DCI items since last check")

        self.state_manager.update_monitor(
            self.monitor_name,
            {"queries": self.queries, "result_count": len(results)},
            seen_items=all_job_ids
        )

        return results

    async def _store_dci_jobs_in_kg(self, result_text: str, query: str):
        """Call DCI MCP tool directly and store structured data in KG"""
        try:
            session = self.agent.sessions.get("dci")
            if not session:
                return

            # Use 'query' parameter (not 'where') - limit to 20 jobs
            result = await session.call_tool("search_dci_jobs", {
                "query": query,
                "limit": 20,
                "sort": "-created_at"
            })

            if result.content:
                for item in result.content:
                    if hasattr(item, "text"):
                        text_content = item.text.strip()

                        if not text_content:
                            print("Debug: DCI MCP tool returned empty response")
                            continue

                        try:
                            jobs_response = json.loads(text_content)
                            tx_time = datetime.now()

                            if isinstance(jobs_response, dict) and "error" in jobs_response:
                                print(f"DCI API error: {jobs_response['error']}")
                                continue

                            jobs = []
                            if isinstance(jobs_response, list):
                                jobs = jobs_response
                            elif isinstance(jobs_response, dict):
                                # DCI API returns {"hits": [...], "total": {...}}
                                jobs = jobs_response.get("hits", jobs_response.get("jobs", []))

                            if not jobs:
                                total = jobs_response.get("total", {}) if isinstance(jobs_response, dict) else {}
                                total_count = total.get("value", 0) if isinstance(total, dict) else 0
                                if total_count > 0:
                                    print(f"Debug: Found {total_count} matching jobs but 0 returned in hits")
                                continue

                            for job in jobs:
                                job_id = job.get("id")
                                if not job_id:
                                    continue

                                created_str = job.get("created_at", "")
                                try:
                                    valid_from = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                                except (ValueError, AttributeError):
                                    valid_from = tx_time

                                self.knowledge_graph.insert_entity(
                                    entity_type="dci_job",
                                    entity_id=job_id,
                                    valid_from=valid_from,
                                    tx_from=tx_time,
                                    data={
                                        "job_id": job_id,
                                        "status": job.get("status", "unknown"),
                                        "remoteci_id": job.get("remoteci_id"),
                                        "topic_id": job.get("topic_id"),
                                        "state": job.get("state"),
                                    }
                                )

                                for component in job.get("components", []):
                                    comp_id = component.get("id")
                                    if not comp_id:
                                        continue

                                    comp_type = component.get("type")
                                    comp_version = component.get("version")

                                    try:
                                        self.knowledge_graph.insert_entity(
                                            entity_type="dci_component",
                                            entity_id=comp_id,
                                            valid_from=valid_from,
                                            tx_from=tx_time,
                                            data={
                                                "type": comp_type,
                                                "version": comp_version,
                                                "name": component.get("name"),
                                            }
                                        )
                                    except Exception:
                                        pass  # Component might already exist

                                    self.knowledge_graph.insert_relationship(
                                        rel_type="job_uses_component",
                                        source_id=job_id,
                                        target_id=comp_id,
                                        valid_from=valid_from,
                                        tx_from=tx_time,
                                        properties={}
                                    )

                        except json.JSONDecodeError as e:
                            print(f"Warning: Could not parse DCI response JSON: {e}")
                            print(f"Debug: Response text (first 200 chars): {text_content[:200]}")
                        except Exception as e:
                            print(f"Warning: Could not process DCI job: {e}")

        except Exception as e:
            print(f"Warning: Could not store DCI jobs in knowledge graph: {e}")


class MonitoringScheduler:
    """Schedule and run monitoring tasks"""

    def __init__(
        self,
        agent: BossAgent,
        config,
        state_manager: StateManager,
        knowledge_graph: Optional[KnowledgeGraph] = None,
        task_file: Optional[Path] = None
    ):
        self.agent = agent
        self.config = config
        self.state_manager = state_manager
        self.knowledge_graph = knowledge_graph
        self.task_file = task_file
        self.jira_monitor = JiraMonitor(
            agent, config.monitoring.jira_projects, state_manager, knowledge_graph
        )
        self.dci_monitor = DCIMonitor(
            agent, config.monitoring.dci_queries, state_manager, knowledge_graph
        )
        self.user_tasks: list["TaskRunner"] = []
        self.user_task_handles: list[asyncio.Task] = []
        self.running = False

        if self.task_file:
            self.user_tasks = self._load_user_tasks(self.task_file)

    def _load_user_tasks(self, task_file: Path) -> list[TaskRunner]:
        """Load user-defined tasks from YAML file"""
        if not task_file or not task_file.exists():
            return []

        try:
            loader = TaskLoader()
            task_defs = loader.load_from_yaml(task_file)

            runners = []
            for task_def in task_defs:
                if task_def.enabled:
                    runner = TaskRunner(task_def, self.agent, self.state_manager)
                    runners.append(runner)
                    print(f"Loaded task: {task_def.name} (interval: {task_def.interval})")
                else:
                    print(f"Skipping disabled task: {task_def.name}")

            return runners
        except Exception as e:
            print(f"Error loading tasks from {task_file}: {e}")
            return []

    async def reload_tasks(self):
        """Reload task definitions from YAML file"""
        if not self.task_file:
            return

        print("\n" + "="*60)
        print("Reloading task definitions...")
        print("="*60)

        try:
            new_tasks = self._load_user_tasks(self.task_file)

            for task_handle in self.user_task_handles:
                task_handle.cancel()

            if self.user_task_handles:
                await asyncio.gather(*self.user_task_handles, return_exceptions=True)

            self.user_task_handles.clear()

            self.user_tasks = new_tasks

            for task_runner in self.user_tasks:
                interval = 0 if task_runner.task_def.is_time_based else task_runner.task_def.interval_seconds
                task_handle = asyncio.create_task(
                    self._schedule_task(
                        task_runner.task_def.name,
                        task_runner.run,
                        interval,
                        task_def=task_runner.task_def
                    )
                )
                self.user_task_handles.append(task_handle)

            print(f"✓ Reloaded {len(new_tasks)} task(s)")
            print("="*60 + "\n")

        except Exception as e:
            print(f"✗ Failed to reload tasks: {e}")
            print("Keeping existing tasks")
            print("="*60 + "\n")

    async def start(self):
        """Start the monitoring loop"""
        self.running = True
        print("Starting monitoring scheduler...")
        print(f"State directory: {self.state_manager.state_dir}")

        removed = self.state_manager.cleanup_expired_cache()
        if removed:
            print(f"Cleaned up {removed} expired cache entries")

        tasks = [
            self._schedule_task(
                "Jira Monitor",
                self.jira_monitor.check,
                self.config.monitoring.jira_check_interval
            ),
            self._schedule_task(
                "DCI Monitor",
                self.dci_monitor.check,
                self.config.monitoring.dci_check_interval
            ),
        ]

        for task_runner in self.user_tasks:
            # For time-based schedules, interval is just a placeholder
            interval = 0 if task_runner.task_def.is_time_based else task_runner.task_def.interval_seconds
            task_handle = asyncio.create_task(
                self._schedule_task(
                    task_runner.task_def.name,
                    task_runner.run,
                    interval,
                    task_def=task_runner.task_def
                )
            )
            tasks.append(task_handle)
            self.user_task_handles.append(task_handle)

        if self.user_tasks:
            print(f"Scheduled {len(self.user_tasks)} user-defined tasks")

        if self.task_file:
            watcher = TaskFileWatcher(self.task_file, self.reload_tasks)
            tasks.append(asyncio.create_task(watcher.watch()))
            print(f"Watching {self.task_file} for changes...")

        await asyncio.gather(*tasks)

    async def _schedule_task(self, name: str, task_func, interval: int, task_def=None):
        """Schedule a periodic task"""
        while self.running:
            try:
                # For time-based schedules, calculate next run time
                if task_def and task_def.is_time_based:
                    schedule = TaskLoader.parse_time_schedule(task_def.interval)
                    next_run = TaskLoader.calculate_next_run(schedule)
                    now = datetime.now()

                    wait_seconds = (next_run - now).total_seconds()
                    if wait_seconds > 0:
                        print(f"{name}: Next run at {next_run.strftime('%Y-%m-%d %H:%M')}")
                        await asyncio.sleep(wait_seconds)

                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running {name}...")
                results = await task_func()

                # Handle TaskResult from user-defined tasks
                from .task_runner import TaskResult
                if isinstance(results, TaskResult):
                    if results.success:
                        print(f"{name}: ✓ Completed")
                        print(f"\n{results.output}")
                    else:
                        print(f"{name}: ✗ Failed - {results.output}")
                elif results:
                    self._report_results(name, results)
                else:
                    print(f"{name}: No updates")

            except Exception as e:
                print(f"Error in {name}: {e}")

            # For interval-based schedules, sleep for the interval
            if not (task_def and task_def.is_time_based):
                await asyncio.sleep(interval)

    def _report_results(self, monitor_name: str, results: list[dict]):
        """Report monitoring results"""
        print(f"\n{'='*60}")
        print(f"{monitor_name} Report")
        print(f"{'='*60}")

        for result in results:
            if "project" in result:
                print(f"\nProject: {result['project']}")
            elif "query" in result:
                print(f"\nQuery: {result['query']}")

            print(f"Time: {result['timestamp']}")
            print(f"\n{result['summary']}")
            print(f"{'-'*60}")

    def stop(self):
        """Stop the monitoring loop"""
        self.running = False
        print("Stopping monitoring scheduler...")
