# utils/dns_checker.py
import dns.resolver
import json
import os
from typing import Dict, List, Tuple
import re

class DNSChecker:
    def __init__(self, config_file: str = "config/domain_setup.json"):
        self.config_file = config_file
        self.domain_config = self._load_domain_config()
    
    def _load_domain_config(self) -> Dict:
        """Load domain configuration from JSON file"""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Domain configuration file not found: {self.config_file}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error parsing domain configuration: {e}")
            return {}
    
    def check_spf_record(self, domain: str) -> Tuple[bool, str, str]:
        """Check SPF record for domain"""
        try:
            answers = dns.resolver.resolve(domain, 'TXT')
            
            for answer in answers:
                txt_record = str(answer).strip('"')
                if txt_record.startswith('v=spf1'):
                    expected_spf = self.domain_config.get('dns_records', {}).get('spf', {}).get('value', '')
                    
                    # Check if all required includes are present
                    required_includes = ['sendgrid.net', 'amazonses.com', 'spf.mtasv.net']
                    missing_includes = []
                    
                    for include in required_includes:
                        if f'include:{include}' not in txt_record:
                            missing_includes.append(include)
                    
                    if not missing_includes and '~all' in txt_record:
                        return True, txt_record, "SPF record is correctly configured"
                    else:
                        issues = []
                        if missing_includes:
                            issues.append(f"Missing includes: {', '.join(missing_includes)}")
                        if '~all' not in txt_record:
                            issues.append("Missing ~all mechanism")
                        return False, txt_record, f"SPF issues: {'; '.join(issues)}"
            
            return False, "", "No SPF record found"
            
        except dns.resolver.NXDOMAIN:
            return False, "", "Domain not found"
        except dns.resolver.NoAnswer:
            return False, "", "No TXT records found"
        except Exception as e:
            return False, "", f"Error checking SPF: {str(e)}"
    
    def check_dkim_records(self, domain: str) -> Dict[str, Tuple[bool, str, str]]:
        """Check DKIM records for all ESPs"""
        results = {}
        dkim_config = self.domain_config.get('dns_records', {}).get('dkim', {})
        
        for esp, records in dkim_config.items():
            if not isinstance(records, list):
                continue
                
            for record in records:
                selector_host = record.get('host', '')
                expected_value = record.get('value', '')
                
                try:
                    full_domain = f"{selector_host}.{domain}"
                    answers = dns.resolver.resolve(full_domain, 'CNAME')
                    
                    actual_value = str(answers[0]).rstrip('.')
                    
                    if actual_value == expected_value:
                        results[f"{esp}_{selector_host}"] = (True, actual_value, "DKIM record correctly configured")
                    else:
                        results[f"{esp}_{selector_host}"] = (False, actual_value, f"Expected: {expected_value}")
                        
                except dns.resolver.NXDOMAIN:
                    results[f"{esp}_{selector_host}"] = (False, "", "DKIM record not found")
                except dns.resolver.NoAnswer:
                    results[f"{esp}_{selector_host}"] = (False, "", "No CNAME record found")
                except Exception as e:
                    results[f"{esp}_{selector_host}"] = (False, "", f"Error: {str(e)}")
        
        return results
    
    def check_dmarc_record(self, domain: str) -> Tuple[bool, str, str]:
        """Check DMARC record for domain"""
        try:
            dmarc_domain = f"_dmarc.{domain}"
            answers = dns.resolver.resolve(dmarc_domain, 'TXT')
            
            for answer in answers:
                txt_record = str(answer).strip('"')
                if txt_record.startswith('v=DMARC1'):
                    # Check DMARC policy
                    policy_match = re.search(r'p=(\w+)', txt_record)
                    if policy_match:
                        policy = policy_match.group(1)
                        if policy in ['quarantine', 'reject']:
                            # Check for reporting addresses
                            if 'rua=' in txt_record and 'ruf=' in txt_record:
                                return True, txt_record, "DMARC record correctly configured"
                            else:
                                return False, txt_record, "DMARC missing reporting addresses (rua/ruf)"
                        else:
                            return False, txt_record, f"DMARC policy too lenient: {policy}"
                    else:
                        return False, txt_record, "DMARC policy not found"
            
            return False, "", "No DMARC record found"
            
        except dns.resolver.NXDOMAIN:
            return False, "", "DMARC domain not found"
        except dns.resolver.NoAnswer:
            return False, "", "No DMARC TXT records found"
        except Exception as e:
            return False, "", f"Error checking DMARC: {str(e)}"
    
    def check_mx_record(self, domain: str) -> Tuple[bool, str, str]:
        """Check MX record for domain"""
        try:
            answers = dns.resolver.resolve(domain, 'MX')
            
            mx_records = []
            for answer in answers:
                mx_records.append(f"{answer.preference} {str(answer.exchange).rstrip('.')}")
            
            expected_mx = self.domain_config.get('dns_records', {}).get('mx', {}).get('value', '')
            
            if any(expected_mx in mx for mx in mx_records):
                return True, '; '.join(mx_records), "MX record correctly configured"
            else:
                return False, '; '.join(mx_records), f"Expected MX record not found: {expected_mx}"
                
        except dns.resolver.NXDOMAIN:
            return False, "", "Domain not found"
        except dns.resolver.NoAnswer:
            return False, "", "No MX records found"
        except Exception as e:
            return False, "", f"Error checking MX: {str(e)}"
    
    def check_tracking_cname(self, subdomain: str) -> Tuple[bool, str, str]:
        """Check tracking subdomain CNAME"""
        try:
            answers = dns.resolver.resolve(subdomain, 'CNAME')
            actual_value = str(answers[0]).rstrip('.')
            
            expected_value = self.domain_config.get('dns_records', {}).get('tracking', {}).get('value', '')
            
            if actual_value == expected_value:
                return True, actual_value, "Tracking CNAME correctly configured"
            else:
                return False, actual_value, f"Expected: {expected_value}"
                
        except dns.resolver.NXDOMAIN:
            return False, "", "Tracking subdomain not found"
        except dns.resolver.NoAnswer:
            return False, "", "No CNAME record found"
        except Exception as e:
            return False, "", f"Error checking tracking CNAME: {str(e)}"
    
    def run_full_dns_check(self) -> Dict:
        """Run complete DNS check for all configured records"""
        if not self.domain_config:
            return {'error': 'Domain configuration not loaded'}
        
        primary_domain = self.domain_config.get('primary_domain', '')
        email_subdomain = self.domain_config.get('email_subdomain', '')
        tracking_subdomain = self.domain_config.get('tracking_subdomain', '')
        
        results = {
            'domain': primary_domain,
            'email_subdomain': email_subdomain,
            'tracking_subdomain': tracking_subdomain,
            'checks': {}
        }
        
        # Check SPF
        spf_valid, spf_record, spf_message = self.check_spf_record(email_subdomain)
        results['checks']['spf'] = {
            'valid': spf_valid,
            'record': spf_record,
            'message': spf_message
        }
        
        # Check DKIM
        dkim_results = self.check_dkim_records(email_subdomain)
        results['checks']['dkim'] = {}
        for key, (valid, record, message) in dkim_results.items():
            results['checks']['dkim'][key] = {
                'valid': valid,
                'record': record,
                'message': message
            }
        
        # Check DMARC
        dmarc_valid, dmarc_record, dmarc_message = self.check_dmarc_record(email_subdomain)
        results['checks']['dmarc'] = {
            'valid': dmarc_valid,
            'record': dmarc_record,
            'message': dmarc_message
        }
        
        # Check MX
        mx_valid, mx_record, mx_message = self.check_mx_record(email_subdomain)
        results['checks']['mx'] = {
            'valid': mx_valid,
            'record': mx_record,
            'message': mx_message
        }
        
        # Check tracking CNAME
        tracking_valid, tracking_record, tracking_message = self.check_tracking_cname(tracking_subdomain)
        results['checks']['tracking'] = {
            'valid': tracking_valid,
            'record': tracking_record,
            'message': tracking_message
        }
        
        # Calculate overall score
        total_checks = len(results['checks'])
        valid_checks = sum(1 for check in results['checks'].values() 
                          if isinstance(check, dict) and check.get('valid', False))
        
        # For DKIM, count individual records
        if 'dkim' in results['checks']:
            dkim_checks = results['checks']['dkim']
            total_checks += len(dkim_checks) - 1  # -1 because we already counted dkim once
            valid_checks += sum(1 for check in dkim_checks.values() if check.get('valid', False)) - 1
        
        results['overall_score'] = (valid_checks / total_checks * 100) if total_checks > 0 else 0
        results['total_checks'] = total_checks
        results['valid_checks'] = valid_checks
        
        return results
    
    def generate_dns_setup_instructions(self) -> str:
        """Generate DNS setup instructions based on configuration"""
        if not self.domain_config:
            return "Domain configuration not loaded"
        
        instructions = []
        instructions.append("DNS SETUP INSTRUCTIONS")
        instructions.append("=" * 50)
        instructions.append("")
        
        dns_records = self.domain_config.get('dns_records', {})
        
        # SPF Record
        if 'spf' in dns_records:
            spf = dns_records['spf']
            instructions.append(f"1. SPF Record:")
            instructions.append(f"   Type: {spf['type']}")
            instructions.append(f"   Host: {spf['host']}")
            instructions.append(f"   Value: {spf['value']}")
            instructions.append("")
        
        # DKIM Records
        if 'dkim' in dns_records:
            instructions.append("2. DKIM Records:")
            for esp, records in dns_records['dkim'].items():
                instructions.append(f"   {esp.upper()}:")
                for record in records:
                    instructions.append(f"     Type: {record['type']}")
                    instructions.append(f"     Host: {record['host']}")
                    instructions.append(f"     Value: {record['value']}")
                instructions.append("")
        
        # DMARC Record
        if 'dmarc' in dns_records:
            dmarc = dns_records['dmarc']
            instructions.append(f"3. DMARC Record:")
            instructions.append(f"   Type: {dmarc['type']}")
            instructions.append(f"   Host: {dmarc['host']}")
            instructions.append(f"   Value: {dmarc['value']}")
            instructions.append("")
        
        # MX Record
        if 'mx' in dns_records:
            mx = dns_records['mx']
            instructions.append(f"4. MX Record:")
            instructions.append(f"   Type: {mx['type']}")
            instructions.append(f"   Host: {mx['host']}")
            instructions.append(f"   Value: {mx['value']}")
            instructions.append("")
        
        # Tracking CNAME
        if 'tracking' in dns_records:
            tracking = dns_records['tracking']
            instructions.append(f"5. Tracking CNAME:")
            instructions.append(f"   Type: {tracking['type']}")
            instructions.append(f"   Host: {tracking['host']}")
            instructions.append(f"   Value: {tracking['value']}")
            instructions.append("")
        
        return "\n".join(instructions)
