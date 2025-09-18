"""
Integration test for PL-56880 data pipeline - verifying end-to-end transition date extraction.
Expected: First "Done Dev" transition on September 16th, 2025
"""
import unittest
from datetime import date
from models import JiraIssue, AppConfig
from fetch import JiraFetcher  
from transform import DataTransformer


class TestPL56880Integration(unittest.TestCase):
    """Integration tests for PL-56880 complete data pipeline."""
    
    def setUp(self):
        self.fetcher = JiraFetcher()
        self.transformer = DataTransformer()
        
    def test_pl56880_complete_pipeline(self):
        """Test complete pipeline for PL-56880 with expected Sept 16th Done Dev transition."""
        
        # Mock complete issue data as we expect from MCP
        mock_raw_issue = {
            "key": "PL-56880",
            "summary": "[Layout Engine - Components] Missing Component Wrappers Implementation",
            "status": "In Dev",
            "created": "2025-09-04",
            "story_points": 8.0,
            "type": "Story",
            "assignee": "frontend.dev2",
            "epic": "PL-54667",
            "due": "2025-10-15",
            "labels": ["components", "wrappers"],
            "components": ["Frontend"],
            "changelog": {
                "histories": [
                    {
                        "created": "2025-09-04T10:00:00.000Z",
                        "items": [{
                            "field": "status",
                            "fromString": None,
                            "toString": "To Do"
                        }]
                    },
                    {
                        "created": "2025-09-10T14:30:00.000Z", 
                        "items": [{
                            "field": "status",
                            "fromString": "To Do",
                            "toString": "In Dev"
                        }]
                    },
                    {
                        "created": "2025-09-16T09:15:00.000Z",  # Expected Sept 16th transition
                        "items": [{
                            "field": "status",
                            "fromString": "In Dev",
                            "toString": "Done Dev"
                        }]
                    },
                    {
                        "created": "2025-09-16T18:30:00.000Z",  # Later reopened same day
                        "items": [{
                            "field": "status",
                            "fromString": "Done Dev", 
                            "toString": "In Dev"
                        }]
                    }
                ]
            }
        }
        
        # Test normalization step
        normalized_issue = self.fetcher.normalize_issue(mock_raw_issue)
        
        # Verify basic normalization
        self.assertIsNotNone(normalized_issue)
        self.assertEqual(normalized_issue.key, "PL-56880")
        self.assertEqual(normalized_issue.story_points, 8.0)
        self.assertEqual(normalized_issue.status, "In Dev")
        self.assertEqual(normalized_issue.created_day, date(2025, 9, 4))
        
        # Verify transition data extraction - CRITICAL TEST
        self.assertIn("Done Dev", normalized_issue.target_status_transitions)
        self.assertEqual(
            normalized_issue.target_status_transitions["Done Dev"], 
            date(2025, 9, 16)
        )
        
        print(f"✅ PL-56880 normalized with Done Dev transition: {normalized_issue.target_status_transitions['Done Dev']}")
        
        # Test completion calculation with "Done Dev" as target status
        config = AppConfig(
            target_status="Done Dev",
            t0_override=date(2025, 9, 9),  # Start tracking Sept 9th
            t1_override=date(2025, 11, 11)  # End Nov 11th
        )
        
        # Test daily series computation
        issues = [normalized_issue]
        daily_series = self.transformer.compute_daily_series(issues, config.t0_override, config.t1_override, config)
        
        # Find the day when completion should jump (Sept 16th)
        sept_15_point = None
        sept_16_point = None
        sept_17_point = None
        
        for point in daily_series:
            if point.date == date(2025, 9, 15):
                sept_15_point = point
            elif point.date == date(2025, 9, 16):
                sept_16_point = point
            elif point.date == date(2025, 9, 17):
                sept_17_point = point
        
        # Verify completion behavior
        self.assertIsNotNone(sept_15_point)
        self.assertIsNotNone(sept_16_point)
        self.assertIsNotNone(sept_17_point)
        
        # Sept 15th: Should have 0 completed (before Done Dev transition)
        self.assertEqual(sept_15_point.completed, 0.0)
        
        # Sept 16th: Should have 8.0 completed (when Done Dev transition occurred)
        self.assertEqual(sept_16_point.completed, 8.0)
        
        # Sept 17th: Should still have 8.0 completed (transition already counted)
        self.assertEqual(sept_17_point.completed, 8.0)
        
        # Verify delta on Sept 16th
        self.assertEqual(sept_16_point.delta_completed, 8.0)
        
        print(f"✅ Completion tracking correct:")
        print(f"   Sept 15th: {sept_15_point.completed} points completed")
        print(f"   Sept 16th: {sept_16_point.completed} points completed (delta: {sept_16_point.delta_completed})")
        print(f"   Sept 17th: {sept_17_point.completed} points completed")
        
        # Test scope calculation (should include historical ticket)
        # PL-56880 was created Sept 4th, so should be in scope throughout
        self.assertEqual(sept_15_point.scope, 8.0)  # Includes historical scope
        self.assertEqual(sept_16_point.scope, 8.0)
        self.assertEqual(sept_17_point.scope, 8.0)
        
        print(f"✅ Scope tracking correct: {sept_16_point.scope} points in scope")
        
    def test_pl56880_without_target_status(self):
        """Test PL-56880 without target status - should fall back to done_day."""
        
        mock_raw_issue = {
            "key": "PL-56880", 
            "summary": "Test issue",
            "status": "In Dev",
            "created": "2025-09-04",
            "story_points": 8.0,
            "done_day": "2025-09-16",  # Fallback completion date
            "changelog": {
                "histories": []  # No transition history
            }
        }
        
        normalized_issue = self.fetcher.normalize_issue(mock_raw_issue)
        self.assertEqual(normalized_issue.done_day, date(2025, 9, 16))
        
        # Test with no target status configured
        config = AppConfig(
            target_status="",  # No target status
            t0_override=date(2025, 9, 9),
            t1_override=date(2025, 11, 11)
        )
        
        issues = [normalized_issue]
        daily_series = self.transformer.compute_daily_series(issues, config.t0_override, config.t1_override, config)
        
        # Find Sept 16th point
        sept_16_point = next((p for p in daily_series if p.date == date(2025, 9, 16)), None)
        self.assertIsNotNone(sept_16_point)
        
        # Should still complete on Sept 16th using done_day fallback
        self.assertEqual(sept_16_point.completed, 8.0)
        
        print("✅ Fallback to done_day working correctly")


def run_integration_tests():
    """Run integration tests for PL-56880."""
    print("🧪 Running PL-56880 integration tests...\n")
    
    suite = unittest.TestSuite()
    suite.addTest(TestPL56880Integration('test_pl56880_complete_pipeline'))
    suite.addTest(TestPL56880Integration('test_pl56880_without_target_status'))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n📊 Integration Test Results:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ Failures:")
        for test, traceback in result.failures:
            print(f"   {test}: {traceback}")
    
    if result.errors:
        print("\n💥 Errors:")
        for test, traceback in result.errors:
            print(f"   {test}: {traceback}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_integration_tests()
    if success:
        print("\n🎉 All integration tests passed! PL-56880 pipeline working correctly.")
    else:
        print("\n🚨 Integration tests failed! Pipeline needs debugging.")
