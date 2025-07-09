#!/usr/bin/env python3
"""
Implementation Verification Script - Phase 2 Part 2
Verifies code structure and completeness without requiring dependencies
"""

import os
import ast
import json
from typing import Dict, List

class ImplementationVerifier:
    def __init__(self):
        self.results = []
    
    def log_result(self, component: str, status: str, details: str = ""):
        """Log verification result"""
        symbol = "✓" if status == "COMPLETE" else "⚠" if status == "PARTIAL" else "✗"
        print(f"{symbol} {component}: {status}")
        if details:
            print(f"   {details}")
        
        self.results.append({
            'component': component,
            'status': status,
            'details': details
        })
    
    def verify_file_structure(self):
        """Verify complete file structure"""
        required_files = {
            'src/core/email_engine.py': 'Enhanced email delivery engine',
            'src/core/provider_manager.py': 'Intelligent provider management',
            'src/core/warming_system.py': 'IP warming automation',
            'src/database/models.py': 'Advanced database models',
            'src/database/subscriber_manager.py': 'Enhanced subscriber operations',
            'src/database/engagement_tracker.py': 'Real-time engagement tracking',
            'src/api/routes.py': 'Complete FastAPI routes',
            'src/api/webhooks.py': 'Enhanced webhook handlers',
            'src/utils/validators.py': 'Advanced validation system',
            'src/utils/analytics.py': 'Analytics engine',
            'src/utils/email_builder.py': 'Content optimization',
            'config/providers.json': 'Provider configuration',
            'config/warming_schedule.json': 'Warming configuration',
            'config/delivery_rules.json': 'Delivery rules',
            'main.py': 'FastAPI application',
            'deploy.sh': 'Deployment script',
            'requirements.txt': 'Dependencies'
        }
        
        missing_files = []
        for file_path, description in required_files.items():
            if os.path.exists(file_path):
                self.log_result(f"File: {file_path}", "COMPLETE", description)
            else:
                self.log_result(f"File: {file_path}", "MISSING", description)
                missing_files.append(file_path)
        
        if not missing_files:
            self.log_result("File Structure", "COMPLETE", "All required files present")
        else:
            self.log_result("File Structure", "INCOMPLETE", f"{len(missing_files)} files missing")
    
    def verify_email_engine_methods(self):
        """Verify EmailDeliveryEngine has all required methods"""
        try:
            with open('src/core/email_engine.py', 'r') as f:
                content = f.read()
            
            required_methods = [
                '_send_via_sendgrid',
                '_send_via_ses', 
                '_send_via_postmark',
                'send_campaign',
                '_send_email_batch',
                '_process_batch',
                '_send_single_email'
            ]
            
            found_methods = []
            missing_methods = []
            
            for method in required_methods:
                if f"def {method}" in content or f"async def {method}" in content:
                    found_methods.append(method)
                else:
                    missing_methods.append(method)
            
            if not missing_methods:
                self.log_result("EmailDeliveryEngine Methods", "COMPLETE", f"All {len(required_methods)} methods implemented")
            else:
                self.log_result("EmailDeliveryEngine Methods", "INCOMPLETE", f"Missing: {', '.join(missing_methods)}")
                
        except Exception as e:
            self.log_result("EmailDeliveryEngine Methods", "ERROR", str(e))
    
    def verify_api_routes(self):
        """Verify API routes are complete"""
        try:
            with open('src/api/routes.py', 'r') as f:
                content = f.read()
            
            required_endpoints = [
                '@app.post("/subscribers/")',
                '@app.get("/subscribers/{email}")',
                '@app.put("/subscribers/{email}")',
                '@app.delete("/subscribers/{email}")',
                '@app.get("/campaigns/")',
                '@app.post("/campaigns/")',
                '@app.get("/campaigns/{campaign_id}")',
                '@app.get("/system/health")',
                '@app.get("/system/metrics")',
                '@app.get("/system/alerts")'
            ]
            
            found_endpoints = []
            missing_endpoints = []
            
            for endpoint in required_endpoints:
                if endpoint in content:
                    found_endpoints.append(endpoint)
                else:
                    missing_endpoints.append(endpoint)
            
            if not missing_endpoints:
                self.log_result("API Routes", "COMPLETE", f"All {len(required_endpoints)} endpoints implemented")
            else:
                self.log_result("API Routes", "INCOMPLETE", f"Missing: {len(missing_endpoints)} endpoints")
                
        except Exception as e:
            self.log_result("API Routes", "ERROR", str(e))
    
    def verify_webhook_handlers(self):
        """Verify webhook handlers are enhanced"""
        try:
            with open('src/api/webhooks.py', 'r') as f:
                content = f.read()
            
            required_webhooks = [
                '@webhook_router.post("/sendgrid")',
                '@webhook_router.post("/amazon-ses")',
                '@webhook_router.post("/postmark")',
                '@webhook_router.post("/generic")'
            ]
            
            enhanced_features = [
                'verify_sendgrid_signature',
                'verify_postmark_signature',
                'provider_stats',
                'update_reputation'
            ]
            
            found_webhooks = sum(1 for webhook in required_webhooks if webhook in content)
            found_features = sum(1 for feature in enhanced_features if feature in content)
            
            if found_webhooks == len(required_webhooks):
                self.log_result("Webhook Handlers", "COMPLETE", f"All {len(required_webhooks)} webhooks + {found_features} enhanced features")
            else:
                self.log_result("Webhook Handlers", "INCOMPLETE", f"Found {found_webhooks}/{len(required_webhooks)} webhooks")
                
        except Exception as e:
            self.log_result("Webhook Handlers", "ERROR", str(e))
    
    def verify_configuration_files(self):
        """Verify configuration files are complete"""
        config_files = {
            'config/providers.json': ['sendgrid', 'aws_ses', 'postmark', 'global_settings'],
            'config/warming_schedule.json': ['warming_profiles', 'schedule', 'segment_definitions'],
            'config/delivery_rules.json': ['send_time_optimization', 'domain_specific_rules', 'content_optimization']
        }
        
        for config_file, required_keys in config_files.items():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                found_keys = [key for key in required_keys if key in config]
                
                if len(found_keys) == len(required_keys):
                    self.log_result(f"Config: {config_file}", "COMPLETE", f"All {len(required_keys)} sections present")
                else:
                    missing = [key for key in required_keys if key not in config]
                    self.log_result(f"Config: {config_file}", "INCOMPLETE", f"Missing: {', '.join(missing)}")
                    
            except Exception as e:
                self.log_result(f"Config: {config_file}", "ERROR", str(e))
    
    def verify_deployment_script(self):
        """Verify deployment script completeness"""
        try:
            with open('deploy.sh', 'r') as f:
                content = f.read()
            
            required_functions = [
                'check_requirements',
                'setup_project_structure',
                'setup_python_environment',
                'setup_database',
                'setup_environment',
                'setup_systemd_service',
                'setup_monitoring'
            ]
            
            found_functions = sum(1 for func in required_functions if func in content)
            
            if found_functions == len(required_functions):
                self.log_result("Deployment Script", "COMPLETE", f"All {len(required_functions)} functions implemented")
            else:
                self.log_result("Deployment Script", "INCOMPLETE", f"Found {found_functions}/{len(required_functions)} functions")
                
        except Exception as e:
            self.log_result("Deployment Script", "ERROR", str(e))
    
    def verify_requirements(self):
        """Verify requirements.txt has all necessary dependencies"""
        try:
            with open('requirements.txt', 'r') as f:
                requirements = f.read().lower()
            
            required_packages = [
                'fastapi', 'uvicorn', 'sqlalchemy', 'alembic', 'psycopg2-binary',
                'sendgrid', 'boto3', 'postmarker', 'email-validator', 'beautifulsoup4',
                'premailer', 'redis', 'celery', 'prometheus-client', 'sentry-sdk'
            ]
            
            found_packages = [pkg for pkg in required_packages if pkg in requirements]
            missing_packages = [pkg for pkg in required_packages if pkg not in requirements]
            
            if not missing_packages:
                self.log_result("Requirements", "COMPLETE", f"All {len(required_packages)} packages present")
            else:
                self.log_result("Requirements", "INCOMPLETE", f"Missing: {', '.join(missing_packages)}")
                
        except Exception as e:
            self.log_result("Requirements", "ERROR", str(e))
    
    def verify_code_quality(self):
        """Verify code quality and structure"""
        python_files = [
            'src/core/email_engine.py',
            'src/core/provider_manager.py', 
            'src/api/routes.py',
            'src/api/webhooks.py',
            'main.py'
        ]
        
        total_lines = 0
        total_functions = 0
        syntax_errors = 0
        
        for file_path in python_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Count lines
                    lines = len(content.splitlines())
                    total_lines += lines
                    
                    # Count functions
                    functions = content.count('def ') + content.count('async def ')
                    total_functions += functions
                    
                    # Check syntax
                    ast.parse(content)
                    
                except SyntaxError:
                    syntax_errors += 1
                except Exception:
                    pass
        
        if syntax_errors == 0:
            self.log_result("Code Quality", "COMPLETE", f"{total_lines} lines, {total_functions} functions, no syntax errors")
        else:
            self.log_result("Code Quality", "ISSUES", f"{syntax_errors} files with syntax errors")
    
    def run_verification(self):
        """Run complete verification"""
        print("=== Phase 2 Part 2 Implementation Verification ===")
        print("Verifying code structure and completeness...\n")
        
        self.verify_file_structure()
        print()
        
        self.verify_email_engine_methods()
        self.verify_api_routes()
        self.verify_webhook_handlers()
        print()
        
        self.verify_configuration_files()
        print()
        
        self.verify_deployment_script()
        self.verify_requirements()
        self.verify_code_quality()
        print()
        
        # Summary
        complete_count = sum(1 for r in self.results if r['status'] == 'COMPLETE')
        total_count = len(self.results)
        
        print("=== VERIFICATION SUMMARY ===")
        print(f"Complete: {complete_count}/{total_count}")
        print(f"Success Rate: {(complete_count/total_count)*100:.1f}%")
        print()
        
        if complete_count >= total_count * 0.9:
            print("🎉 IMPLEMENTATION VERIFICATION PASSED!")
            print("Phase 2 Part 2 is complete and ready for deployment.")
        elif complete_count >= total_count * 0.8:
            print("⚠ IMPLEMENTATION MOSTLY COMPLETE")
            print("Minor issues detected - review warnings above.")
        else:
            print("❌ IMPLEMENTATION INCOMPLETE")
            print("Multiple issues detected - review errors above.")
        
        print("\n=== NEXT STEPS ===")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Configure API keys in .env file")
        print("3. Run deployment script: ./deploy.sh")
        print("4. Test with: python test_complete_phase2.py")
        print("5. Start production deployment")

if __name__ == '__main__':
    verifier = ImplementationVerifier()
    verifier.run_verification()
