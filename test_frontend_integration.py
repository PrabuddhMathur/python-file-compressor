#!/usr/bin/env python3
"""
Frontend Integration Test Suite
Tests the advanced PDF compression frontend components and API integration.
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class FrontendIntegrationTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.driver = None
        self.test_results = []
        
        # Setup Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(10)
        except Exception as e:
            print(f"Warning: Could not initialize Chrome driver: {e}")
            print("Skipping browser-based tests, running API tests only")
    
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
    
    def test_api_endpoints(self):
        """Test API endpoints availability"""
        print("\n=== Testing API Endpoints ===")
        
        endpoints = [
            "/api/process/analyze",
            "/api/process/predict", 
            "/api/process/upload-advanced",
            "/api/user/stats",
            "/api/user/quota"
        ]
        
        for endpoint in endpoints:
            try:
                # Test with OPTIONS method first (CORS preflight)
                response = requests.options(f"{self.base_url}{endpoint}", timeout=5)
                api_available = response.status_code in [200, 405]  # 405 is OK for OPTIONS
                
                self.log_test(
                    f"API Endpoint {endpoint}",
                    api_available,
                    f"Status: {response.status_code}"
                )
            except Exception as e:
                self.log_test(
                    f"API Endpoint {endpoint}",
                    False,
                    f"Connection error: {str(e)}"
                )
    
    def test_static_files(self):
        """Test static file availability"""
        print("\n=== Testing Static Files ===")
        
        static_files = [
            "/static/css/style.css",
            "/static/js/main.js",
            "/static/js/upload.js", 
            "/static/js/progress.js",
            "/static/js/advanced-processing.js",
            "/static/js/real-time-predictions.js"
        ]
        
        for file_path in static_files:
            try:
                response = requests.get(f"{self.base_url}{file_path}", timeout=5)
                file_available = response.status_code == 200
                
                self.log_test(
                    f"Static File {file_path}",
                    file_available,
                    f"Status: {response.status_code}, Size: {len(response.content)} bytes"
                )
            except Exception as e:
                self.log_test(
                    f"Static File {file_path}",
                    False,
                    f"Error: {str(e)}"
                )
    
    def test_page_loads(self):
        """Test main pages load correctly"""
        if not self.driver:
            print("\n=== Skipping Page Load Tests (No browser driver) ===")
            return
            
        print("\n=== Testing Page Loads ===")
        
        pages = [
            ("Home Page", "/"),
            ("Dashboard", "/dashboard"),
            ("History", "/history"),
            ("Login", "/auth/login"),
            ("Register", "/auth/register")
        ]
        
        for page_name, path in pages:
            try:
                self.driver.get(f"{self.base_url}{path}")
                
                # Wait for page to load
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Check for error indicators
                error_elements = self.driver.find_elements(By.CLASS_NAME, "error")
                has_error = len(error_elements) > 0
                
                # Check page title
                title = self.driver.title
                has_title = bool(title and "PDF Compressor" in title)
                
                success = not has_error and has_title
                message = f"Title: '{title}'"
                if has_error:
                    message += f", Errors found: {len(error_elements)}"
                
                self.log_test(page_name, success, message)
                
            except TimeoutException:
                self.log_test(page_name, False, "Page load timeout")
            except Exception as e:
                self.log_test(page_name, False, f"Error: {str(e)}")
    
    def test_javascript_components(self):
        """Test JavaScript components initialization"""
        if not self.driver:
            print("\n=== Skipping JavaScript Tests (No browser driver) ===")
            return
            
        print("\n=== Testing JavaScript Components ===")
        
        try:
            # Navigate to dashboard
            self.driver.get(f"{self.base_url}/dashboard")
            
            # Wait for page load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "uploadForm"))
            )
            
            # Test if main utilities are loaded
            utils_loaded = self.driver.execute_script("return typeof Utils !== 'undefined';")
            self.log_test("Utils JavaScript loaded", utils_loaded)
            
            api_loaded = self.driver.execute_script("return typeof API !== 'undefined';")
            self.log_test("API JavaScript loaded", api_loaded)
            
            # Test advanced components
            try:
                advanced_processing_loaded = self.driver.execute_script(
                    "return typeof AdvancedProcessing !== 'undefined';"
                )
                self.log_test("AdvancedProcessing component loaded", advanced_processing_loaded)
            except:
                self.log_test("AdvancedProcessing component loaded", False, "Script execution failed")
            
            try:
                predictions_loaded = self.driver.execute_script(
                    "return typeof RealTimePredictions !== 'undefined';"
                )
                self.log_test("RealTimePredictions component loaded", predictions_loaded)
            except:
                self.log_test("RealTimePredictions component loaded", False, "Script execution failed")
            
        except Exception as e:
            self.log_test("JavaScript Components", False, f"Error: {str(e)}")
    
    def test_ui_elements(self):
        """Test UI elements are present and functional"""
        if not self.driver:
            print("\n=== Skipping UI Tests (No browser driver) ===")
            return
            
        print("\n=== Testing UI Elements ===")
        
        try:
            # Navigate to dashboard
            self.driver.get(f"{self.base_url}/dashboard")
            
            # Test upload area
            upload_area = self.driver.find_elements(By.ID, "dropArea")
            self.log_test("Upload area present", len(upload_area) > 0)
            
            # Test compression profiles
            profile_cards = self.driver.find_elements(By.CLASS_NAME, "profile-card")
            self.log_test(
                "Compression profiles present", 
                len(profile_cards) >= 4,
                f"Found {len(profile_cards)} profile cards"
            )
            
            # Test advanced mode toggle
            advanced_toggle = self.driver.find_elements(By.ID, "toggleAdvancedMode")
            self.log_test("Advanced mode toggle present", len(advanced_toggle) > 0)
            
            # Test prediction card (should be hidden initially)
            prediction_card = self.driver.find_elements(By.ID, "predictionCard")
            self.log_test("Prediction card present", len(prediction_card) > 0)
            
            # Test file input
            file_input = self.driver.find_elements(By.ID, "fileInput")
            self.log_test("File input present", len(file_input) > 0)
            
        except Exception as e:
            self.log_test("UI Elements", False, f"Error: {str(e)}")
    
    def test_css_styles(self):
        """Test CSS styles are applied correctly"""
        if not self.driver:
            print("\n=== Skipping CSS Tests (No browser driver) ===")
            return
            
        print("\n=== Testing CSS Styles ===")
        
        try:
            # Navigate to dashboard
            self.driver.get(f"{self.base_url}/dashboard")
            
            # Test if TailwindCSS is loaded (check for common classes)
            body_classes = self.driver.execute_script(
                "return document.body.className;"
            )
            tailwind_loaded = "bg-gray" in body_classes or "min-h-screen" in body_classes
            self.log_test("TailwindCSS loaded", tailwind_loaded)
            
            # Test custom CSS is applied
            upload_area = self.driver.find_element(By.ID, "dropArea")
            upload_area_style = self.driver.execute_script(
                "return window.getComputedStyle(arguments[0]).borderStyle;", 
                upload_area
            )
            custom_css_loaded = "dashed" in upload_area_style
            self.log_test("Custom CSS applied", custom_css_loaded)
            
            # Test profile card hover effects (check transition property)
            profile_cards = self.driver.find_elements(By.CLASS_NAME, "profile-card")
            if profile_cards:
                transition_style = self.driver.execute_script(
                    "return window.getComputedStyle(arguments[0]).transition;",
                    profile_cards[0]
                )
                has_transitions = transition_style and transition_style != "all 0s ease 0s"
                self.log_test("CSS transitions applied", has_transitions)
            
        except Exception as e:
            self.log_test("CSS Styles", False, f"Error: {str(e)}")
    
    def test_responsive_design(self):
        """Test responsive design"""
        if not self.driver:
            print("\n=== Skipping Responsive Tests (No browser driver) ===")
            return
            
        print("\n=== Testing Responsive Design ===")
        
        viewports = [
            ("Desktop", 1920, 1080),
            ("Tablet", 768, 1024), 
            ("Mobile", 375, 667)
        ]
        
        try:
            self.driver.get(f"{self.base_url}/dashboard")
            
            for viewport_name, width, height in viewports:
                try:
                    self.driver.set_window_size(width, height)
                    time.sleep(1)  # Allow for responsive adjustments
                    
                    # Check if upload area is still visible
                    upload_area = self.driver.find_element(By.ID, "dropArea")
                    is_displayed = upload_area.is_displayed()
                    
                    # Check if navigation is accessible
                    nav_elements = self.driver.find_elements(By.TAG_NAME, "nav")
                    nav_visible = len(nav_elements) > 0 and nav_elements[0].is_displayed()
                    
                    responsive_working = is_displayed and nav_visible
                    self.log_test(
                        f"Responsive - {viewport_name} ({width}x{height})",
                        responsive_working
                    )
                    
                except Exception as e:
                    self.log_test(
                        f"Responsive - {viewport_name}",
                        False,
                        f"Error: {str(e)}"
                    )
                    
        except Exception as e:
            self.log_test("Responsive Design", False, f"Error: {str(e)}")
    
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
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if failed_tests > 0:
            print(f"\nFailed Tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  ❌ {result['test']}")
                    if result['message']:
                        print(f"     {result['message']}")
        
        print("\n" + "="*60)
        
        # Save report to file
        report_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': passed_tests/total_tests*100,
            'results': self.test_results
        }
        
        with open('frontend_test_report.json', 'w') as f:
            json.dump(report_data, f, indent=2)
        
        print(f"Detailed report saved to: frontend_test_report.json")
    
    def run_all_tests(self):
        """Run all frontend integration tests"""
        print("Starting Frontend Integration Tests...")
        
        self.test_api_endpoints()
        self.test_static_files()
        self.test_page_loads()
        self.test_javascript_components()
        self.test_ui_elements()
        self.test_css_styles()
        self.test_responsive_design()
        
        self.generate_report()
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Frontend Integration Tester')
    parser.add_argument('--url', default='http://localhost:5000', 
                       help='Base URL for testing (default: http://localhost:5000)')
    parser.add_argument('--headless', action='store_true', default=True,
                       help='Run browser tests in headless mode')
    
    args = parser.parse_args()
    
    tester = FrontendIntegrationTester(base_url=args.url)
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
    except Exception as e:
        print(f"\nTest suite error: {e}")
    finally:
        tester.cleanup()

if __name__ == "__main__":
    main()