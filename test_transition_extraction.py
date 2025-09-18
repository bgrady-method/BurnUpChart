import unittest
from datetime import date
from fetch import JiraFetcher


class TestTransitionExtraction(unittest.TestCase):
    """Unit tests for transition date extraction logic."""
    
    def setUp(self):
        self.fetcher = JiraFetcher()
    
    def test_pl56880_done_dev_transition_sept_16(self):
        """Test that PL-56880 Done Dev transition is correctly extracted as Sept 16th."""
        # Mock data structure based on expected Jira changelog format
        mock_issue_data = {
            "key": "PL-56880",
            "summary": "[Layout Engine - Components] Missing Component Wrappers Implementation",
            "status": "In Dev",
            "created": "2025-09-04",
            "changelog": {
                "histories": [
                    {
                        "created": "2025-09-04T10:00:00.000Z",
                        "items": [
                            {
                                "field": "status",
                                "fromString": None,
                                "toString": "To Do"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-10T14:30:00.000Z",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "To Do",
                                "toString": "In Dev"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-16T09:15:00.000Z",  # Expected Sept 16th transition
                        "items": [
                            {
                                "field": "status",
                                "fromString": "In Dev",
                                "toString": "Done Dev"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-16T18:30:00.000Z",  # Later reopened
                        "items": [
                            {
                                "field": "status", 
                                "fromString": "Done Dev",
                                "toString": "In Dev"
                            }
                        ]
                    }
                ]
            }
        }
        
        # Test transition extraction
        transitions = self.fetcher._extract_all_status_transitions(mock_issue_data)
        
        # Verify all transitions are captured
        self.assertIn("To Do", transitions)
        self.assertIn("In Dev", transitions) 
        self.assertIn("Done Dev", transitions)
        
        # Verify specific dates
        self.assertEqual(transitions["To Do"], date(2025, 9, 4))
        self.assertEqual(transitions["In Dev"], date(2025, 9, 10))
        self.assertEqual(transitions["Done Dev"], date(2025, 9, 16))  # Critical test!
        
        print(f"✅ PL-56880 Done Dev transition correctly extracted: {transitions['Done Dev']}")
    
    def test_target_status_extraction(self):
        """Test extracting specific target status transition date."""
        mock_issue_data = {
            "key": "TEST-123",
            "changelog": {
                "histories": [
                    {
                        "created": "2025-09-01T10:00:00.000Z",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "To Do", 
                                "toString": "In Progress"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-05T14:00:00.000Z",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "In Progress",
                                "toString": "Done Dev"
                            }
                        ]
                    }
                ]
            }
        }
        
        # Test specific status extraction
        done_dev_date = self.fetcher.extract_status_transition_date(mock_issue_data, "Done Dev")
        self.assertEqual(done_dev_date, date(2025, 9, 5))
        
        # Test non-existent status
        qa_date = self.fetcher.extract_status_transition_date(mock_issue_data, "QA")
        self.assertIsNone(qa_date)
        
        print(f"✅ Target status extraction working correctly: Done Dev = {done_dev_date}")
    
    def test_first_transition_only(self):
        """Test that only the FIRST transition to a status is captured."""
        mock_issue_data = {
            "key": "TEST-456",
            "changelog": {
                "histories": [
                    {
                        "created": "2025-09-01T10:00:00.000Z",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "To Do",
                                "toString": "In Progress"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-02T11:00:00.000Z",  # First time to Done
                        "items": [
                            {
                                "field": "status", 
                                "fromString": "In Progress",
                                "toString": "Done"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-03T12:00:00.000Z",  # Reopened
                        "items": [
                            {
                                "field": "status",
                                "fromString": "Done", 
                                "toString": "In Progress"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-04T13:00:00.000Z",  # Second time to Done (should ignore)
                        "items": [
                            {
                                "field": "status",
                                "fromString": "In Progress",
                                "toString": "Done"  
                            }
                        ]
                    }
                ]
            }
        }
        
        transitions = self.fetcher._extract_all_status_transitions(mock_issue_data)
        
        # Should only capture the FIRST transition to Done (Sept 2nd, not Sept 4th)
        self.assertEqual(transitions["Done"], date(2025, 9, 2))
        
        print(f"✅ First transition logic working: Done = {transitions['Done']} (Sept 2nd, not Sept 4th)")
    
    def test_empty_changelog(self):
        """Test handling of issues with no changelog."""
        mock_issue_data = {
            "key": "TEST-789",
            "status": "To Do"
            # No changelog field
        }
        
        transitions = self.fetcher._extract_all_status_transitions(mock_issue_data)
        self.assertEqual(transitions, {})
        
        print("✅ Empty changelog handled correctly")
    
    def test_malformed_changelog(self):
        """Test handling of malformed changelog data."""
        mock_issue_data = {
            "key": "TEST-999", 
            "changelog": {
                "histories": [
                    {
                        "created": "2025-09-01T10:00:00.000Z",
                        "items": [
                            {
                                "field": "assignee",  # Not a status change
                                "fromString": "john.doe",
                                "toString": "jane.smith"
                            }
                        ]
                    },
                    {
                        "created": None,  # Missing date
                        "items": [
                            {
                                "field": "status",
                                "toString": "In Progress"
                            }
                        ]
                    },
                    {
                        "created": "2025-09-02T11:00:00.000Z",
                        "items": [
                            {
                                "field": "status",
                                "toString": None  # Missing status
                            }
                        ]
                    }
                ]
            }
        }
        
        transitions = self.fetcher._extract_all_status_transitions(mock_issue_data)
        # Should handle malformed data gracefully
        self.assertEqual(transitions, {})
        
        print("✅ Malformed changelog handled gracefully")


def run_pl56880_tests():
    """Run specific tests for PL-56880 transition extraction."""
    print("🧪 Running PL-56880 transition extraction tests...\n")
    
    # Create test suite
    suite = unittest.TestSuite()
    suite.addTest(TestTransitionExtraction('test_pl56880_done_dev_transition_sept_16'))
    suite.addTest(TestTransitionExtraction('test_target_status_extraction'))
    suite.addTest(TestTransitionExtraction('test_first_transition_only'))
    suite.addTest(TestTransitionExtraction('test_empty_changelog'))
    suite.addTest(TestTransitionExtraction('test_malformed_changelog'))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n📊 Test Results:")
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
    success = run_pl56880_tests()
    if success:
        print("\n🎉 All tests passed! PL-56880 transition extraction should work correctly.")
    else:
        print("\n🚨 Tests failed! Need to fix transition extraction logic.")
