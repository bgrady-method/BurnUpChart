"""
Cache manager for browser session persistence with 24-hour expiry.
Uses streamlit-javascript for localStorage integration.
"""

import json
import streamlit as st
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from models import JiraIssue, ComputeResults, FieldCatalogs, AppConfig
import uuid

# Install streamlit-javascript if not already installed
try:
    from streamlit_javascript import st_javascript
    JAVASCRIPT_AVAILABLE = True
except ImportError:
    JAVASCRIPT_AVAILABLE = False
    st.warning("streamlit-javascript not available. Install with: pip install streamlit-javascript")


class CacheManager:
    """Manages browser localStorage cache with 24-hour expiry."""
    
    CACHE_DURATION_HOURS = 24
    
    def __init__(self):
        self.cache_keys = {
            'config': 'burndown_cache_config',
            'raw_issues': 'burndown_cache_raw_issues', 
            'normalized_issues': 'burndown_cache_normalized_issues',
            'field_catalogs': 'burndown_cache_field_catalogs',
            'compute_results': 'burndown_cache_compute_results',
            'timestamp': 'burndown_cache_timestamp'
        }
        # Session state will be initialized by app.py before cache manager is used
        pass
    
    def _execute_js(self, js_code: str) -> Any:
        """Execute JavaScript code and return result."""
        if not JAVASCRIPT_AVAILABLE:
            return None
        
        try:
            # Generate unique key for each JavaScript execution
            st.session_state.js_exec_counter += 1
            unique_key = f"cache_js_{st.session_state.js_exec_counter}_{hash(js_code) % 10000}"
            return st_javascript(js_code, key=unique_key)
        except Exception as e:
            st.error(f"JavaScript execution failed: {e}")
            return None
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid (within 24 hours)."""
        if not JAVASCRIPT_AVAILABLE:
            return False
            
        js_code = f"""
        try {{
            const timestamp = localStorage.getItem('{self.cache_keys["timestamp"]}');
            if (!timestamp) return false;
            
            const cacheTime = new Date(timestamp);
            const now = new Date();
            const diffHours = (now - cacheTime) / (1000 * 60 * 60);
            
            return diffHours < {self.CACHE_DURATION_HOURS};
        }} catch (e) {{
            console.error('Cache validation error:', e);
            return false;
        }}
        """
        
        result = self._execute_js(js_code)
        return result == True
    
    def save_to_cache(self, 
                     config: AppConfig,
                     raw_issues: List[Dict[str, Any]], 
                     normalized_issues: List[JiraIssue],
                     field_catalogs: FieldCatalogs,
                     compute_results: Optional[ComputeResults] = None) -> bool:
        """Save data to browser localStorage with timestamp."""
        if not JAVASCRIPT_AVAILABLE:
            # Just continue silently - caching is optional
            return False
        
        try:
            # Simple localStorage test with detailed debugging
            test_js = """
            try {
                if (typeof Storage === "undefined") {
                    return {success: false, error: "Storage not supported"};
                }
                if (typeof localStorage === "undefined") {
                    return {success: false, error: "localStorage not supported"};
                }
                localStorage.setItem('burndown_test', 'test');
                localStorage.removeItem('burndown_test');
                return {success: true};
            } catch (e) {
                return {success: false, error: e.toString()};
            }
            """
            
            test_result = self._execute_js(test_js)
            
            # If JavaScript execution fails entirely, skip caching silently
            if test_result is None:
                return False
            
            # Check if localStorage is available
            if not test_result or not test_result.get('success'):
                # Only show warning once per session
                if not st.session_state.get('localStorage_warning_shown', False):
                    st.session_state.localStorage_warning_shown = True
                    error_detail = test_result.get('error', 'unknown') if test_result else 'no response'
                    st.info(f"💾 Browser storage not available ({error_detail}) - data won't persist between sessions")
                return False
            
            # Try to save a minimal cache (just the most important data)
            minimal_cache = {
                'config': config.model_dump() if config else {},
                'normalized_issues': [issue.model_dump() for issue in normalized_issues[:20]] if normalized_issues else [],  # Even more limited
                'field_catalogs': field_catalogs.model_dump() if field_catalogs else {},
                'timestamp': datetime.now().isoformat()
            }
            
            success_count = 0
            
            # Save each piece separately with size checking
            for data_key, data_value in minimal_cache.items():
                cache_key = self.cache_keys[data_key]
                try:
                    if data_key == 'timestamp':
                        # Save timestamp directly
                        js_code = f"""
                        try {{
                            localStorage.setItem('{cache_key}', '{data_value}');
                            return true;
                        }} catch (e) {{
                            return false;
                        }}
                        """
                    else:
                        # Serialize and encode other data
                        json_data = json.dumps(data_value, default=str)
                        # Check size before encoding
                        if len(json_data) > 500000:  # Skip very large items
                            continue
                            
                        import base64
                        encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
                        
                        js_code = f"""
                        try {{
                            localStorage.setItem('{cache_key}', '{encoded_data}');
                            return true;
                        }} catch (e) {{
                            return false;
                        }}
                        """
                    
                    result = self._execute_js(js_code)
                    if result:
                        success_count += 1
                        
                except Exception as e:
                    # Silently skip items that fail to serialize
                    continue
            
            if success_count > 0:
                # Only show success message once per session  
                if not st.session_state.get('cache_success_shown', False):
                    st.session_state.cache_success_shown = True
                    st.toast(f"💾 Data cached for 24h", icon="✅")
                return True
            else:
                return False
            
        except Exception as e:
            # Fail silently - caching is optional
            return False
    
    def load_from_cache(self) -> Optional[Dict[str, Any]]:
        """Load data from browser localStorage if valid."""
        if not JAVASCRIPT_AVAILABLE:
            return None
            
        # Check if cache is valid first
        if not self._is_cache_valid():
            return None
        
        try:
            cached_data = {}
            import base64
            
            for data_key, cache_key in self.cache_keys.items():
                js_code = f"localStorage.getItem('{cache_key}')"
                encoded_str = self._execute_js(js_code)
                
                if encoded_str and encoded_str != "null":
                    try:
                        if data_key == 'timestamp':
                            cached_data[data_key] = encoded_str
                        else:
                            # Decode base64 data
                            decoded_json = base64.b64decode(encoded_str.encode('utf-8')).decode('utf-8')
                            cached_data[data_key] = json.loads(decoded_json)
                    except Exception as decode_error:
                        st.warning(f"💾 Failed to decode cached {data_key}: {decode_error}")
                        # Don't return None, just skip this item
                        continue
                else:
                    # Missing non-critical data - continue anyway
                    if data_key not in ['timestamp']:
                        st.info(f"💾 Missing cached {data_key}")
            
            # Convert back to proper types if we have enough data
            if cached_data.get('config') or cached_data.get('normalized_issues'):
                try:
                    # Reconstruct normalized issues
                    if cached_data.get('normalized_issues'):
                        cached_data['normalized_issues'] = [
                            JiraIssue(**issue_data) 
                            for issue_data in cached_data['normalized_issues']
                        ]
                    
                    # Reconstruct other models
                    if cached_data.get('config'):
                        cached_data['config'] = AppConfig(**cached_data['config'])
                    
                    if cached_data.get('field_catalogs'):
                        cached_data['field_catalogs'] = FieldCatalogs(**cached_data['field_catalogs'])
                    
                    if cached_data.get('compute_results'):
                        cached_data['compute_results'] = ComputeResults(**cached_data['compute_results'])
                        
                    return cached_data
                    
                except Exception as reconstitute_error:
                    st.warning(f"💾 Failed to reconstitute cached data: {reconstitute_error}")
                    return None
            
            return None
            
        except Exception as e:
            st.warning(f"💾 Cache load failed: {e}")
            return None
    
    def clear_cache(self) -> bool:
        """Clear all cached data."""
        if not JAVASCRIPT_AVAILABLE:
            return False
        
        js_code = f"""
        {'; '.join([f"localStorage.removeItem('{key}')" for key in self.cache_keys.values()])}
        return true;
        """
        
        result = self._execute_js(js_code)
        if result:
            st.success("🗑️ Cache cleared")
            return True
        else:
            st.error("Failed to clear cache")
            return False
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about current cache."""
        if not JAVASCRIPT_AVAILABLE:
            return {"available": False, "reason": "JavaScript not available"}
        
        js_code = f"""
        try {{
            // First check if localStorage is available
            if (typeof localStorage === "undefined") {{
                return {{"available": false, "reason": "localStorage not supported"}};
            }}
            
            const timestamp = localStorage.getItem('{self.cache_keys["timestamp"]}');
            if (!timestamp) {{
                return {{"available": false, "reason": "no cached data"}};
            }}
            
            const cacheTime = new Date(timestamp);
            const now = new Date();
            const diffHours = (now - cacheTime) / (1000 * 60 * 60);
            const remainingHours = {self.CACHE_DURATION_HOURS} - diffHours;
            
            return {{
                "available": true,
                "timestamp": timestamp,
                "age_hours": Math.round(diffHours * 10) / 10,
                "remaining_hours": Math.round(remainingHours * 10) / 10,
                "valid": remainingHours > 0
            }};
        }} catch (e) {{
            return {{"available": false, "reason": "error", "error": e.toString()}};
        }}
        """
        
        result = self._execute_js(js_code)
        return result or {"available": False, "reason": "execution failed"}


# Singleton instance
cache_manager = CacheManager()
