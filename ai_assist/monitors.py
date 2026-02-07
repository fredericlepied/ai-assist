"""Monitoring scheduler"""

import asyncio
from datetime import datetime
from pathlib import Path

from .agent import AiAssistAgent
from .file_watchdog import FileWatchdog
from .knowledge_graph import KnowledgeGraph
from .monitor_runner import MonitorRunner
from .schedule_loader import ScheduleLoader
from .schedule_recalculator import ScheduleRecalculator
from .state import StateManager
from .suspend_detector import SuspendDetector
from .task_runner import TaskRunner
from .tasks import TaskLoader


class MonitoringScheduler:
    """Schedule and run monitoring tasks"""

    def __init__(
        self,
        agent: AiAssistAgent,
        config,
        state_manager: StateManager,
        knowledge_graph: KnowledgeGraph | None = None,
        schedule_file: Path | None = None,
    ):
        self.agent = agent
        self.config = config
        self.state_manager = state_manager
        self.knowledge_graph = knowledge_graph

        # Use schedule_file or default location
        if schedule_file:
            self.schedule_file = schedule_file
        else:
            self.schedule_file = Path.home() / ".ai-assist" / "schedules.json"

        self.loader = ScheduleLoader(self.schedule_file)
        self.monitors: list[MonitorRunner] = []
        self.user_tasks: list[TaskRunner] = []
        self.monitor_handles: list[asyncio.Task] = []
        self.user_task_handles: list[asyncio.Task] = []
        self.running = False

        # Suspension detection and recovery
        self.suspend_detector: SuspendDetector | None = None
        self.schedule_recalculator = ScheduleRecalculator()
        self.file_watchdog: FileWatchdog | None = None

        # Load initial schedules
        self.monitors = self._load_monitors()
        self.user_tasks = self._load_user_tasks()

    def _load_monitors(self) -> list[MonitorRunner]:
        """Load monitors from JSON file"""
        if not self.loader:
            return []

        try:
            monitor_defs = self.loader.load_monitors()

            runners = []
            for monitor_def in monitor_defs:
                if monitor_def.enabled:
                    runner = MonitorRunner(monitor_def, self.agent, self.state_manager, self.knowledge_graph)
                    runners.append(runner)
                    print(f"Loaded monitor: {monitor_def.name} (interval: {monitor_def.interval})")
                else:
                    print(f"Skipping disabled monitor: {monitor_def.name}")

            return runners
        except Exception as e:
            print(f"Error loading monitors from {self.schedule_file}: {e}")
            return []

    def _load_user_tasks(self) -> list[TaskRunner]:
        """Load user-defined tasks from JSON file"""
        if not self.loader:
            return []

        try:
            task_defs = self.loader.load_tasks()

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
            print(f"Error loading tasks from {self.schedule_file}: {e}")
            return []

    async def reload_schedules(self):
        """Reload all schedules from JSON file (hot reload)"""
        print("\n" + "=" * 60)
        print("Reloading schedules...")
        print("=" * 60)

        try:
            # Load new schedules
            new_monitors = self._load_monitors()
            new_tasks = self._load_user_tasks()

            # Cancel all existing tasks
            all_handles = self.monitor_handles + self.user_task_handles
            for handle in all_handles:
                handle.cancel()

            if all_handles:
                await asyncio.gather(*all_handles, return_exceptions=True)

            # Clear old handles
            self.monitor_handles.clear()
            self.user_task_handles.clear()

            # Update schedules
            self.monitors = new_monitors
            self.user_tasks = new_tasks

            # Restart monitor tasks
            for monitor in self.monitors:
                interval = 0 if monitor.monitor_def.is_time_based else monitor.monitor_def.interval_seconds
                task_handle = asyncio.create_task(
                    self._schedule_task(monitor.monitor_def.name, monitor.run, interval, task_def=monitor.monitor_def)
                )
                self.monitor_handles.append(task_handle)

            # Restart user tasks
            for task_runner in self.user_tasks:
                interval = 0 if task_runner.task_def.is_time_based else task_runner.task_def.interval_seconds
                task_handle = asyncio.create_task(
                    self._schedule_task(
                        task_runner.task_def.name, task_runner.run, interval, task_def=task_runner.task_def
                    )
                )
                self.user_task_handles.append(task_handle)

            print(f"✓ Reloaded {len(new_monitors)} monitor(s) and {len(new_tasks)} task(s)")
            print("=" * 60 + "\n")

        except Exception as e:
            print(f"✗ Failed to reload schedules: {e}")
            print("Keeping existing schedules")
            print("=" * 60 + "\n")

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
                self._schedule_task(monitor.monitor_def.name, monitor.run, interval, task_def=monitor.monitor_def)
            )
            tasks.append(task_handle)
            self.monitor_handles.append(task_handle)

        if self.monitors:
            print(f"Scheduled {len(self.monitors)} monitors")

        for task_runner in self.user_tasks:
            interval = 0 if task_runner.task_def.is_time_based else task_runner.task_def.interval_seconds
            task_handle = asyncio.create_task(
                self._schedule_task(task_runner.task_def.name, task_runner.run, interval, task_def=task_runner.task_def)
            )
            tasks.append(task_handle)
            self.user_task_handles.append(task_handle)

        if self.user_tasks:
            print(f"Scheduled {len(self.user_tasks)} user-defined tasks")

        # Watch schedules.json for changes using OS-level file watching
        if self.schedule_file and self.schedule_file.exists():
            self.file_watchdog = FileWatchdog(self.schedule_file, self.reload_schedules, debounce_seconds=0.5)
            await self.file_watchdog.start()
            print(f"Watching {self.schedule_file} for changes...")

        # Start suspension detection
        self.suspend_detector = SuspendDetector(
            suspend_threshold_seconds=30.0,
            poll_interval_seconds=5.0,
        )
        suspend_task = asyncio.create_task(self.suspend_detector.watch(self._handle_wake_event))
        tasks.append(suspend_task)
        print("Suspension detection enabled")

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

            except asyncio.CancelledError:
                # Task was cancelled (e.g., during reload) - exit gracefully
                break
            except Exception as e:
                print(f"Error in {name}: {e}")

            if not (task_def and task_def.is_time_based):
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    # Cancelled during sleep - exit gracefully
                    break

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

    async def _handle_wake_event(self, wall_jump_seconds: float, now: datetime | None = None) -> None:
        """Handle system wake event after suspension.

        Args:
            wall_jump_seconds: How many seconds the wall clock jumped
            now: Current time (for testing, defaults to datetime.now())
        """
        if now is None:
            now = datetime.now()

        print("\n" + "=" * 60)
        print(f"⚠️  Suspension detected: {abs(wall_jump_seconds):.0f} seconds")
        print("Checking for missed scheduled runs...")
        print("=" * 60)

        # Collect all scheduled items (monitors + user tasks)
        all_scheduled = []

        for monitor in self.monitors:
            if monitor.monitor_def.is_time_based:
                # Create adapter object with execute method
                adapter = type(
                    "MonitorAdapter",
                    (),
                    {
                        "schedule": monitor.monitor_def.interval,
                        "execute": monitor.run,
                    },
                )()
                all_scheduled.append(adapter)

        for task_runner in self.user_tasks:
            if task_runner.task_def.is_time_based:
                adapter = type(
                    "TaskAdapter",
                    (),
                    {
                        "schedule": task_runner.task_def.interval,
                        "execute": task_runner.run,
                    },
                )()
                all_scheduled.append(adapter)

        # Check for and execute missed runs
        await self.schedule_recalculator.handle_wake_event(wall_jump_seconds, all_scheduled, now=now)

        print("✓ Suspension recovery complete")
        print("=" * 60 + "\n")

    async def stop(self):
        """Stop the monitoring loop"""
        self.running = False
        print("Stopping monitoring scheduler...")

        # Stop file watchdog
        if self.file_watchdog:
            await self.file_watchdog.stop()
