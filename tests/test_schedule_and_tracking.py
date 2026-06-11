import unittest
from datetime import datetime, time, timezone

import config
from project_alpha.config.schedule import SessionPhase, get_session_phase
from project_alpha.tracking import CooldownTracker


class ScheduleTests(unittest.TestCase):
    def test_session_phase_matches_project_mission(self):
        self.assertEqual(
            get_session_phase(
                datetime(2026, 6, 8, 9, 16),
                config.WARMUP_START,
                config.SCANNER_START,
                config.MARKET_CLOSE,
            ),
            SessionPhase.WARMUP,
        )
        self.assertEqual(
            get_session_phase(
                datetime(2026, 6, 8, 9, 20),
                config.WARMUP_START,
                config.SCANNER_START,
                config.MARKET_CLOSE,
            ),
            SessionPhase.ACTIVE,
        )
        self.assertEqual(
            get_session_phase(
                datetime(2026, 6, 7, 9, 20),
                time(9, 15),
                time(9, 20),
                time(15, 30),
            ),
            SessionPhase.CLOSED,
        )


class CooldownTests(unittest.TestCase):
    def test_stage_upgrade_bypasses_lower_stage_cooldown(self):
        tracker = CooldownTracker(cooldown_seconds=900)
        now = datetime(2026, 6, 8, 9, 30, tzinfo=timezone.utc)

        tracker.record("ABC", 1, now)

        self.assertTrue(tracker.is_on_cooldown("ABC", 1, now))
        self.assertFalse(tracker.is_on_cooldown("ABC", 2, now))


if __name__ == "__main__":
    unittest.main()

