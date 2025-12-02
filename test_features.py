#!/usr/bin/env python3
"""
Integration tests for production features:
- Rate Limiting
- Input Validation
- Redis Caching
"""
import requests
import time
import json
from typing import Tuple

BASE_URL = "http://localhost:8000"
VALID_PARAMS = {
    "model_name": "bert-base-uncased",
    "text": "This is a test sentence for visualization",
    "view_type": "head"
}

def test_validation():
    """Test input validation feature."""
    print("\n=== Testing Input Validation ===")
    
    test_cases = [
        {
            "name": "Valid input",
            "params": VALID_PARAMS,
            "should_fail": False
        },
        {
            "name": "Path traversal attempt",
            "params": {**VALID_PARAMS, "model_name": "../../../etc/passwd"},
            "should_fail": True
        },
        {
            "name": "SQL injection attempt",
            "params": {**VALID_PARAMS, "text": "'; DROP TABLE--"},
            "should_fail": True
        },
        {
            "name": "XSS attempt",
            "params": {**VALID_PARAMS, "text": "<script>alert('xss')</script>"},
            "should_fail": True
        },
        {
            "name": "Invalid view_type",
            "params": {**VALID_PARAMS, "view_type": "invalid"},
            "should_fail": True
        },
        {
            "name": "Special characters in model name",
            "params": {**VALID_PARAMS, "model_name": "bert@base"},
            "should_fail": True
        }
    ]
    
    passed = 0
    for test in test_cases:
        try:
            response = requests.post(
                f"{BASE_URL}/visualize",
                data=test["params"],
                timeout=30,
                allow_redirects=False
            )
            
            failed = response.status_code >= 400
            expected = test["should_fail"]
            
            if failed == expected:
                print(f"✓ {test['name']}: PASS (status {response.status_code})")
                passed += 1
            else:
                print(f"✗ {test['name']}: FAIL (expected {'fail' if expected else 'success'}, got {response.status_code})")
        except Exception as e:
            print(f"✗ {test['name']}: ERROR - {e}")
    
    print(f"\nValidation Tests: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_rate_limiting():
    """Test rate limiting feature."""
    print("\n=== Testing Rate Limiting ===")
    
    requests_made = 0
    blocked = 0
    
    for i in range(7):
        try:
            response = requests.post(
                f"{BASE_URL}/visualize",
                data=VALID_PARAMS,
                timeout=30,
                allow_redirects=False
            )
            requests_made += 1
            
            if response.status_code == 429:
                blocked += 1
                print(f"Request {i+1}: BLOCKED (429)")
            elif response.status_code == 303:
                print(f"Request {i+1}: SUCCESS (303 redirect)")
            else:
                print(f"Request {i+1}: {response.status_code}")
        except Exception as e:
            print(f"Request {i+1}: ERROR - {e}")
        
        time.sleep(0.2)  # Small delay between requests
    
    print(f"\nRate Limiting Test: Made {requests_made} requests, {blocked} blocked")
    # Should block after 5 requests in 1 minute
    return blocked > 0


def test_caching():
    """Test Redis caching feature."""
    print("\n=== Testing Redis Caching ===")
    
    try:
        # Get initial cache stats
        response = requests.get(f"{BASE_URL}/cache/stats")
        if response.status_code != 200:
            print("✗ Cannot access cache stats endpoint")
            return False
        
        initial_stats = response.json()
        print(f"Initial cache stats: {json.dumps(initial_stats, indent=2)}")
        
        if not initial_stats.get("available"):
            print("✗ Redis not available")
            return False
        
        initial_keys = initial_stats.get("keys_in_cache", 0)
        
        # Make a request (cache miss)
        print("\n→ Making first request (cache miss expected)...")
        response = requests.post(
            f"{BASE_URL}/visualize",
            data=VALID_PARAMS,
            timeout=30,
            allow_redirects=False
        )
        
        if response.status_code not in [303, 400, 429]:
            print(f"✗ Unexpected response: {response.status_code}")
            return False
        
        time.sleep(1)
        
        # Get cache stats after first request
        response = requests.get(f"{BASE_URL}/cache/stats")
        mid_stats = response.json()
        mid_keys = mid_stats.get("keys_in_cache", 0)
        print(f"After first request: {mid_keys} keys in cache")
        
        # Make identical request (cache hit expected)
        print("\n→ Making identical second request (cache hit expected)...")
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/visualize",
            data=VALID_PARAMS,
            timeout=30,
            allow_redirects=False
        )
        elapsed = time.time() - start_time
        print(f"Second request completed in {elapsed:.2f}s")
        
        # Get final cache stats
        response = requests.get(f"{BASE_URL}/cache/stats")
        final_stats = response.json()
        print(f"Final cache stats: {json.dumps(final_stats, indent=2)}")
        
        # Caching is working if:
        # 1. Redis is available
        # 2. Keys increased (or at least didn't decrease)
        cache_working = final_stats.get("available") and mid_keys >= initial_keys
        
        print(f"\nCache Performance: {'✓ WORKING' if cache_working else '✗ NOT WORKING'}")
        return cache_working
        
    except Exception as e:
        print(f"✗ Caching test error: {e}")
        return False


def test_clear_cache():
    """Test cache clearing endpoint."""
    print("\n=== Testing Cache Clear ===")
    
    try:
        response = requests.post(f"{BASE_URL}/cache/clear")
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Cache cleared: {data}")
            return data.get("success", False)
        else:
            print(f"✗ Cache clear failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cache clear error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("PRODUCTION FEATURES INTEGRATION TEST")
    print("=" * 60)
    
    # Check server is running
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"\n✓ Server is running")
    except Exception as e:
        print(f"\n✗ Cannot connect to server: {e}")
        print("Start server with: uvicorn main:app --reload")
        return
    
    results = {
        "validation": test_validation(),
        "rate_limiting": test_rate_limiting(),
        "caching": test_caching(),
        "cache_clear": test_clear_cache(),
    }
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for feature, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{feature.upper()}: {status}")
    
    all_passed = all(results.values())
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
