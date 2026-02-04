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
            # Check cache first
            cache_key = f"jira_project_{project}"
            cached = self.state_manager.get_cached_query(cache_key)

            if cached:
                print(f"Using cached results for Jira project {project}")
                issues.append(cached)
                continue

            # Query for recent issues
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

                # Cache the result
                self.state_manager.cache_query_result(cache_key, issue_data, ttl_seconds=300)

                # Save to history
                self.state_manager.append_history(self.monitor_name, {
                    "project": project,
                    "check_time": datetime.now().isoformat()
                })

                issues.append(issue_data)
            except Exception as e:
                print(f"Error checking Jira project {project}: {e}")

        # Update state
        self.state_manager.update_monitor(
            self.monitor_name,
            {"projects": self.projects, "issue_count": len(issues)}
        )

        return issues


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
            # Default query for recent failures
            self.queries = [
                "((status in ['failure', 'error']) and (created_at >= '2026-02-04'))"
            ]

        state = self.state_manager.get_monitor_state(self.monitor_name)
        results = []
        all_job_ids = set()

        for query in self.queries:
            # Check cache first
            cache_key = f"dci_query_{hash(query)}"
            cached = self.state_manager.get_cached_query(cache_key)

            if cached:
                print(f"Using cached results for DCI query")
                results.append(cached)
                continue

            prompt = f"""
            Search DCI jobs with this query: {query}

            Please provide a summary including:
            1. List of job IDs found
            2. Total number of jobs matching
            3. NEW failures (jobs not seen in previous checks)
            4. Failure patterns or common issues
            5. Jobs that need investigation
            6. Any trends or concerns
            """

            try:
                result = await self.agent.query(prompt)
                result_data = {
                    "query": query,
                    "summary": result,
                    "timestamp": datetime.now().isoformat(),
                }

                # Cache the result
                self.state_manager.cache_query_result(cache_key, result_data, ttl_seconds=300)

                # Save to history
                self.state_manager.append_history(self.monitor_name, {
                    "query": query,
                    "check_time": datetime.now().isoformat()
                })

                results.append(result_data)

                # Store in knowledge graph if available
                if self.knowledge_graph:
                    await self._store_dci_jobs_in_kg(result, query)

                # Track job IDs (would need to parse from result in real implementation)
                # For now, we'll track queries
                all_job_ids.add(hash(query))

            except Exception as e:
                print(f"Error checking DCI with query '{query}': {e}")

        # Get new items since last check
        new_items = self.state_manager.get_new_items(self.monitor_name, all_job_ids)
        if new_items:
            print(f"Found {len(new_items)} new DCI items since last check")

        # Update state
        self.state_manager.update_monitor(
            self.monitor_name,
            {"queries": self.queries, "result_count": len(results)},
            seen_items=all_job_ids
        )

        return results

    async def _store_dci_jobs_in_kg(self, result_text: str, query: str):
        """Parse DCI job results and store in knowledge graph

        This is a helper to extract structured data from agent responses
        and populate the knowledge graph with jobs, components, and relationships.
        """
        # Ask the agent to extract structured data from the result
        extract_prompt = f"""
        From this DCI job query result, extract structured information:

        {result_text}

        Please provide a JSON array of jobs with this structure:
        [{{
            "job_id": "job ID from DCI",
            "status": "failure|error|success",
            "created_at": "ISO timestamp when job was created",
            "remoteci": "lab name",
            "components": [{{"type": "component type", "version": "version", "tags": ["tag1"]}}]
        }}]

        Only include jobs that have clear job IDs. Return ONLY the JSON array, no other text.
        """

        try:
            json_str = await self.agent.query(extract_prompt)
            # Strip markdown code blocks if present
            if "```" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0] if "```json" in json_str else json_str.split("```")[1].split("```")[0]

            jobs_data = json.loads(json_str.strip())

            tx_time = datetime.now()

            for job_data in jobs_data:
                job_id = job_data.get("job_id")
                if not job_id:
                    continue

                # Parse valid_from (when job was created)
                created_str = job_data.get("created_at", "")
                try:
                    valid_from = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    valid_from = tx_time  # Fallback to now if parse fails

                # Insert job entity
                entity_id = f"dci-job-{job_id}"
                self.knowledge_graph.insert_entity(
                    entity_type="dci_job",
                    entity_id=entity_id,
                    valid_from=valid_from,
                    tx_from=tx_time,
                    data={
                        "job_id": job_id,
                        "status": job_data.get("status", "unknown"),
                        "remoteci": job_data.get("remoteci"),
                        "query": query
                    }
                )

                # Insert components and relationships
                for comp_data in job_data.get("components", []):
                    comp_type = comp_data.get("type")
                    comp_version = comp_data.get("version")
                    if not comp_type:
                        continue

                    comp_id = f"component-{comp_type}-{comp_version}" if comp_version else f"component-{comp_type}"

                    # Insert component if not exists (or get existing)
                    try:
                        self.knowledge_graph.insert_entity(
                            entity_type="component",
                            entity_id=comp_id,
                            valid_from=valid_from,  # Component existed when job ran
                            tx_from=tx_time,
                            data={
                                "type": comp_type,
                                "version": comp_version,
                                "tags": comp_data.get("tags", [])
                            }
                        )
                    except Exception:
                        # Component might already exist, that's fine
                        pass

                    # Create relationship
                    self.knowledge_graph.insert_relationship(
                        rel_type="job_uses_component",
                        source_id=entity_id,
                        target_id=comp_id,
                        valid_from=valid_from,
                        tx_from=tx_time,
                        properties={"tags": comp_data.get("tags", [])}
                    )

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
        self.user_task_handles: list[asyncio.Task] = []  # Track user task coroutines
        self.running = False

        # Load user-defined tasks on initialization
        if self.task_file:
            self.user_tasks = self._load_user_tasks(self.task_file)

    def _load_user_tasks(self, task_file: Path) -> list[TaskRunner]:
        """Load user-defined tasks from YAML file"""
        if not task_file or not task_file.exists():
            return []

        try:
            loader = TaskLoader()
            task_defs = loader.load_from_yaml(task_file)

            # Filter enabled tasks and create runners
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
            # Load new task definitions
            new_tasks = self._load_user_tasks(self.task_file)

            # Cancel existing user task coroutines
            for task_handle in self.user_task_handles:
                task_handle.cancel()

            # Wait for all to be cancelled
            if self.user_task_handles:
                await asyncio.gather(*self.user_task_handles, return_exceptions=True)

            # Clear old handles
            self.user_task_handles.clear()

            # Update tasks
            self.user_tasks = new_tasks

            # Restart user tasks
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

        # Clean up expired cache on startup
        removed = self.state_manager.cleanup_expired_cache()
        if removed:
            print(f"Cleaned up {removed} expired cache entries")

        # Schedule built-in monitors
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

        # Schedule user-defined tasks
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

        # Add file watcher if task file is specified
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
