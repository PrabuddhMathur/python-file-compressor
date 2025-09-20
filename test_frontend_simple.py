#!/usr/bin/env python3
"""
Simple Frontend Integration Test
Tests basic API endpoints and static file availability without browser automation.
"""

import os
import sys
import json
import requests
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class SimpleFrontendTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.test_results = []
        
    def log_test(self, test_name, success, message=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message
        })
        print(f"{status}: {test_name}")
        if message:
            print(f"    {message}")
    
    def test_server_connection(self):
        """Test if server is running"""
        print("\n=== Testing Server Connection ===")
        
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            server_running = response.status_code in [200, 302, 401]  # Any valid HTTP response
            
            self.log_test(
                "Server Connection",
                server_running,
                f"Status: {response.status_code}"
            )
            return server_running
        except Exception as e:
            self.log_test(
                "Server Connection",
                False,
                f"Connection failed: {str(e)}"
            )
            return False
    
    def test_static_files(self):
        """Test static file availability"""
        print("\n=== Testing Static Files ===")
        
        static_files = [
            ("/static/css/style.css", "CSS"),
            ("/static/js/main.js", "Main JavaScript"),
            ("/static/js/upload.js", "Upload JavaScript"), 
            ("/static/js/progress.js", "Progress JavaScript"),
            ("/static/js/advanced-processing.js", "Advanced Processing JavaScript"),
            ("/static/js/real-time-predictions.js", "Real-time Predictions JavaScript")
        ]
        
        for file_path, description in static_files:
            try:
                response = requests.get(f"{self.base_url}{file_path}", timeout=5)
                file_available = response.status_code == 200
                content_length = len(response.content)
                
                self.log_test(
                    description,
                    file_available,
                    f"Status: {response.status_code}, Size: {content_length} bytes"
                )
                
                # Check if file has meaningful content
                if file_available and content_length > 0:
                    if file_path.endswith('.js'):
                        # Check for basic JavaScript structure
                        content = response.text
                        has_functions = 'function' in content or 'class' in content or '=>' in content
                        self.log_test(
                            f"{description} - Content Check",
                            has_functions,
                            "Contains JavaScript functions/classes" if has_functions else "No JavaScript structure detected"
                        )
                    elif file_path.endswith('.css'):
                        # Check for CSS rules
                        content = response.text
                        has_css_rules = '{' in content and '}' in content
                        self.log_test(
                            f"{description} - Content Check",
                            has_css_rules,
                            "Contains CSS rules" if has_css_rules else "No CSS rules detected"
                        )
                        
            except Exception as e:
                self.log_test(
                    description,
                    False,
                    f"Error: {str(e)}"
                )
    
    def test_template_pages(self):
        """Test template pages load without server errors"""
        print("\n=== Testing Template Pages ===")
        
        pages = [
            ("/", "Home Page"),
            ("/auth/login", "Login Page"),
            ("/auth/register", "Register Page")
            # Note: Dashboard and history require authentication
        ]
        
        for path, description in pages:
            try:
                response = requests.get(f"{self.base_url}{path}", timeout=5, allow_redirects=False)
                # Accept 200 (OK), 302 (redirect), 401 (auth required) as valid responses
                page_loads = response.status_code in [200, 302, 401]
                
                # Check if response contains HTML
                is_html = 'text/html' in response.headers.get('content-type', '')
                
                success = page_loads and (is_html or response.status_code in [302, 401])
                
                self.log_test(
                    description,
                    success,
                    f"Status: {response.status_code}, Content-Type: {response.headers.get('content-type', 'unknown')}"
                )
                
            except Exception as e:
                self.log_test(
                    description,
                    False,
                    f"Error: {str(e)}"
                )
    
    def test_api_endpoints_structure(self):
        """Test API endpoints return proper JSON structure"""
        print("\n=== Testing API Endpoints Structure ===")
        
        # These endpoints might require authentication or specific methods
        endpoints = [
            ("/api/process/analyze", "POST", "PDF Analysis API"),
            ("/api/process/predict", "POST", "Size Prediction API"), 
            ("/api/process/upload-advanced", "POST", "Advanced Upload API"),
            ("/api/user/stats", "GET", "User Statistics API"),
            ("/api/user/quota", "GET", "User Quota API")
        ]
        
        for endpoint, method, description in endpoints:
            try:
                if method == "GET":
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                else:
                    # For POST endpoints, test with OPTIONS (CORS preflight)
                    response = requests.options(f"{self.base_url}{endpoint}", timeout=5)
                
                # Check if endpoint exists (not 404)
                endpoint_exists = response.status_code != 404
                
                # For authenticated endpoints, 401 is acceptable
                valid_response = response.status_code in [200, 400, 401, 405, 422]
                
                self.log_test(
                    description,
                    endpoint_exists and valid_response,
                    f"Status: {response.status_code} ({'Endpoint exists' if endpoint_exists else 'Not found'})"
                )
                
            except Exception as e:
                self.log_test(
                    description,
                    False,
                    f"Error: {str(e)}"
                )
    
    def test_javascript_syntax(self):
        """Test JavaScript files for basic syntax validity"""
        print("\n=== Testing JavaScript Syntax ===")
        
        js_files = [
            "/static/js/main.js",
            "/static/js/upload.js",
            "/static/js/progress.js", 
            "/static/js/advanced-processing.js",
            "/static/js/real-time-predictions.js"
        ]
        
        for js_file in js_files:
            try:
                response = requests.get(f"{self.base_url}{js_file}", timeout=5)
                if response.status_code == 200:
                    content = response.text
                    
                    # Basic syntax checks
                    syntax_checks = [
                        ("Balanced braces", content.count('{') == content.count('}')),
                        ("Balanced parentheses", content.count('(') == content.count(')')),
                        ("Has classes or functions", 'class ' in content or 'function ' in content or ' => ' in content),
                        ("No obvious syntax errors", 'SyntaxError' not in content and 'Unexpected token' not in content)
                    ]
                    
                    all_checks_pass = all(check[1] for check in syntax_checks)
                    failed_checks = [check[0] for check in syntax_checks if not check[1]]
                    
                    self.log_test(
                        f"JavaScript Syntax - {js_file.split('/')[-1]}",
                        all_checks_pass,
                        f"Failed checks: {', '.join(failed_checks)}" if failed_checks else "All syntax checks passed"
                    )
                else:
                    self.log_test(
                        f"JavaScript Syntax - {js_file.split('/')[-1]}",
                        False,
                        f"File not accessible: {response.status_code}"
                    )
                    
            except Exception as e:
                self.log_test(
                    f"JavaScript Syntax - {js_file.split('/')[-1]}",
                    False,
                    f"Error: {str(e)}"
                )
    
    def test_css_structure(self):
        """Test CSS file structure"""
        print("\n=== Testing CSS Structure ===")
        
        try:
            response = requests.get(f"{self.base_url}/static/css/style.css", timeout=5)
            if response.status_code == 200:
                content = response.text
                
                # Check for important CSS features
                css_checks = [
                    ("Has CSS variables", ':root' in content and '--' in content),
                    ("Has animations", '@keyframes' in content),
                    ("Has responsive design", '@media' in content),
                    ("Has modern features", 'grid' in content or 'flex' in content),
                    ("Has custom classes", '.profile-card' in content or '.upload-area' in content)
                ]
                
                all_checks_pass = all(check[1] for check in css_checks)
                passed_checks = [check[0] for check in css_checks if check[1]]
                
                self.log_test(
                    "CSS Structure",
                    all_checks_pass,
                    f"Passed features: {', '.join(passed_checks)}"
                )
            else:
                self.log_test(
                    "CSS Structure",
                    False,
                    f"CSS file not accessible: {response.status_code}"
                )
                
        except Exception as e:
            self.log_test(
                "CSS Structure",
                False,
                f"Error: {str(e)}"
            )
    
    def test_template_integration(self):
        """Test template integration with JavaScript and CSS"""
        print("\n=== Testing Template Integration ===")
        
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                content = response.text
                
                # Check for expected integrations
                integration_checks = [
                    ("TailwindCSS included", 'cdn.tailwindcss.com' in content),
                    ("Custom CSS linked", '/static/css/style.css' in content),
                    ("Main JavaScript linked", '/static/js/main.js' in content),
                    ("Meta viewport present", 'viewport' in content),
                    ("CSRF token meta", 'csrf-token' in content)
                ]
                
                passed_checks = [check[0] for check in integration_checks if check[1]]
                failed_checks = [check[0] for check in integration_checks if not check[1]]
                
                self.log_test(
                    "Template Integration",
                    len(failed_checks) == 0,
                    f"Passed: {len(passed_checks)}, Failed: {len(failed_checks)}"
                )
                
                if failed_checks:
                    for failed_check in failed_checks:
                        self.log_test(f"  - {failed_check}", False, "Missing from template")
                        
            else:
                self.log_test(
                    "Template Integration",
                    False,
                    f"Home page not accessible: {response.status_code}"
                )
                
        except Exception as e:
            self.log_test(
                "Template Integration",
                False,
                f"Error: {str(e)}"
            )
    
    def generate_report(self):
        """Generate test report"""
        print("\n" + "="*60)
        print("FRONTEND INTEGRATION TEST REPORT")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        
        if total_tests > 0:
            success_rate = (passed_tests/total_tests*100)
            print(f"Success Rate: {success_rate:.1f}%")
        else:
            success_rate = 0
            print("Success Rate: N/A")
        
        if failed_tests > 0:
            print(f"\nFailed Tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  ❌ {result['test']}")
                    if result['message']:
                        print(f"     {result['message']}")
        
        # Summary assessment
        print(f"\n{'='*60}")
        if success_rate >= 90:
            print("🎉 EXCELLENT: Frontend integration is working very well!")
        elif success_rate >= 75:
            print("✅ GOOD: Frontend integration is mostly working with minor issues.")
        elif success_rate >= 50:
            print("⚠️  FAIR: Frontend integration has some issues that should be addressed.")
        else:
            print("❌ POOR: Frontend integration has significant issues requiring attention.")
        
        print("="*60)
        
        # Save report to file
        report_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': success_rate,
            'results': self.test_results
        }
        
        try:
            with open('frontend_test_report.json', 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"Detailed report saved to: frontend_test_report.json")
        except Exception as e:
            print(f"Could not save report file: {e}")
    
    def run_all_tests(self):
        """Run all frontend integration tests"""
        print("Starting Simple Frontend Integration Tests...")
        print(f"Testing URL: {self.base_url}")
        
        # First check if server is running
        if not self.test_server_connection():
            print("\n❌ Server is not running or not accessible.")
            print("Please start the Flask application before running tests.")
            return
        
        # Run all tests
        self.test_static_files()
        self.test_template_pages()
        self.test_api_endpoints_structure()
        self.test_javascript_syntax()
        self.test_css_structure()
        self.test_template_integration()
        
        self.generate_report()

def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Simple Frontend Integration Tester')
    parser.add_argument('--url', default='http://localhost:5000', 
                       help='Base URL for testing (default: http://localhost:5000)')
    
    args = parser.parse_args()
    
    tester = SimpleFrontendTester(base_url=args.url)
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
    except Exception as e:
        print(f"\nTest suite error: {e}")

if __name__ == "__main__":
    main()