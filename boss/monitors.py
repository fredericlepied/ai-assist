"""Monitoring scheduler"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from .agent import BossAgent
from .state import StateManager
from .knowledge_graph import KnowledgeGraph
from .tasks import TaskLoader
from .task_runner import TaskRunner
from .task_watcher import TaskFileWatcher
from .monitor_runner import MonitorRunner


class MonitoringScheduler:
    """Schedule and run monitoring tasks"""

    def __init__(
        self,
        agent: BossAgent,
        config,
        state_manager: StateManager,
        knowledge_graph: Optional[KnowledgeGraph] = None,
        monitor_file: Optional[Path] = None,
        task_file: Optional[Path] = None
    ):
        self.agent = agent
        self.config = config
        self.state_manager = state_manager
        self.knowledge_graph = knowledge_graph
        self.monitor_file = monitor_file
        self.task_file = task_file
        self.monitors: list[MonitorRunner] = []
        self.user_tasks: list[TaskRunner] = []
        self.monitor_handles: list[asyncio.Task] = []
        self.user_task_handles: list[asyncio.Task] = []
        self.running = False

        if monitor_file and monitor_file.exists():
            self.monitors = self._load_monitors(monitor_file)

        if task_file and task_file.exists():
            self.user_tasks = self._load_user_tasks(task_file)

    def _load_monitors(self, monitor_file: Path) -> list[MonitorRunner]:
        """Load monitors from YAML file"""
        try:
            loader = TaskLoader()
            monitor_defs = loader.load_monitors_from_yaml(monitor_file)

            runners = []
            for monitor_def in monitor_defs:
                if monitor_def.enabled:
                    runner = MonitorRunner(
                        monitor_def,
                        self.agent,
                        self.state_manager,
                        self.knowledge_graph
                    )
                    runners.append(runner)
                    print(f"Loaded monitor: {monitor_def.name} (interval: {monitor_def.interval})")
                else:
                    print(f"Skipping disabled monitor: {monitor_def.name}")

            return runners
        except Exception as e:
            print(f"Error loading monitors from {monitor_file}: {e}")
            return []

    def _load_user_tasks(self, task_file: Path) -> list[TaskRunner]:
        """Load user-defined tasks from YAML file"""
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

        tasks = []

        for monitor in self.monitors:
            interval = 0 if monitor.monitor_def.is_time_based else monitor.monitor_def.interval_seconds
            task_handle = asyncio.create_task(
                self._schedule_task(
                    monitor.monitor_def.name,
                    monitor.run,
                    interval,
                    task_def=monitor.monitor_def
                )
            )
            tasks.append(task_handle)
            self.monitor_handles.append(task_handle)

        if self.monitors:
            print(f"Scheduled {len(self.monitors)} monitors from YAML")

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

            if not (task_def and task_def.is_time_based):
                await asyncio.sleep(interval)

    def _report_results(self, monitor_name: str, results: list[dict]):
        """Report monitoring results"""
        print(f"\n{'='*60}")
        print(f"{monitor_name} Report")
        print(f"{'='*60}")

        for result in results:
            if "monitor" in result:
                print(f"\nMonitor: {result['monitor']}")

            print(f"Time: {result['timestamp']}")
            print(f"\n{result['summary']}")
            print(f"{'-'*60}")

    def stop(self):
        """Stop the monitoring loop"""
        self.running = False
        print("Stopping monitoring scheduler...")
