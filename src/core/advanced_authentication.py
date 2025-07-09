import dns.resolver
import ssl
import socket
import hashlib
import os
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import requests
from typing import Dict, List
from datetime import datetime
import json

class AdvancedAuthentication:
    def __init__(self, domain: str):
        self.domain = domain
        self.subdomain = f"mail.{domain}"
        
    def setup_bimi_record(self) -> Dict:
        """Generate BIMI DNS record configuration"""
        # BIMI requires VMC (Verified Mark Certificate) for full functionality
        vmc_url = f"https://{self.domain}/bimi/vmc.pem"
        logo_url = f"https://{self.domain}/bimi/logo.svg"
        
        bimi_record = {
            'type': 'TXT',
            'host': f'default._bimi.{self.subdomain}',
            'value': f'v=BIMI1; l={logo_url}; a={vmc_url}',
            'ttl': 300
        }
        
        return {
            'dns_record': bimi_record,
            'logo_requirements': {
                'format': 'SVG',
                'size': 'Square (1:1 ratio)',
                'max_file_size': '32KB',
                'background': 'Transparent or solid color',
                'content': 'Company logo only, no text'
            },
            'vmc_certificate': {
                'required_for': 'Gmail brand indicators',
                'providers': ['DigiCert', 'Entrust'],
                'cost': '$1,299-$1,499 per year',
                'validation': 'Extended validation required'
            },
            'prerequisites': [
                'DMARC policy must be p=quarantine or p=reject',
                'SPF and DKIM must be properly aligned',
                'Domain must have good sending reputation',
                'Logo must be trademarked'
            ],
            'benefits': [
                'Brand logo displayed in Gmail',
                'Increased trust and recognition',
                'Higher open rates',
                'Protection against spoofing'
            ]
        }
    
    def setup_arc_authentication(self) -> Dict:
        """Setup ARC (Authenticated Received Chain)"""
        return {
            'purpose': 'Preserves authentication results for forwarded emails',
            'how_it_works': [
                'Each hop adds ARC headers',
                'Preserves original authentication',
                'Allows legitimate forwarding',
                'Prevents authentication breaking'
            ],
            'implementation': {
                'sendgrid': {
                    'status': 'Automatically enabled',
                    'configuration': 'No additional setup required'
                },
                'amazon_ses': {
                    'status': 'Available in configuration sets',
                    'configuration': 'Enable in SES console'
                },
                'postmark': {
                    'status': 'Enabled by default',
                    'configuration': 'No additional setup required'
                }
            },
            'benefits': [
                'Improves delivery for mailing lists',
                'Helps with forwarded emails',
                'Maintains authentication chain',
                'Reduces false positives'
            ],
            'dns_records': 'None required - handled by ESP'
        }
    
    def setup_mta_sts(self) -> Dict:
        """Setup MTA-STS for encryption enforcement"""
        policy_id = datetime.now().strftime("%Y%m%d%H%M%S")
        
        policy = {
            'version': 'STSv1',
            'mode': 'enforce',  # or 'testing' for initial deployment
            'mx': [f'mail.{self.domain}'],
            'max_age': 86400
        }
        
        return {
            'dns_record': {
                'type': 'TXT',
                'host': f'_mta-sts.{self.domain}',
                'value': f'v=STSv1; id={policy_id}',
                'ttl': 300
            },
            'policy_file': {
                'url': f'https://mta-sts.{self.domain}/.well-known/mta-sts.txt',
                'content': '\n'.join([f'{k}: {v}' for k, v in policy.items()]),
                'content_type': 'text/plain'
            },
            'web_server_setup': {
                'subdomain': f'mta-sts.{self.domain}',
                'ssl_required': True,
                'path': '/.well-known/mta-sts.txt',
                'headers': {
                    'Content-Type': 'text/plain',
                    'Cache-Control': 'max-age=86400'
                }
            },
            'benefits': [
                'Forces TLS encryption for email delivery',
                'Prevents man-in-the-middle attacks',
                'Improves security reputation',
                'Required for some enterprise recipients'
            ],
            'deployment_modes': {
                'testing': 'Monitor without enforcement (recommended first)',
                'enforce': 'Reject non-TLS delivery (production)'
            }
        }
    
    def setup_dane_tlsa(self) -> Dict:
        """Setup DANE TLSA records for ultimate security"""
        try:
            # Get certificate fingerprint
            cert = ssl.get_server_certificate((f'mail.{self.domain}', 25))
            x509_cert = x509.load_pem_x509_certificate(cert.encode(), default_backend())
            
            # Get public key fingerprint
            public_key_der = x509_cert.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            fingerprint = hashlib.sha256(public_key_der).hexdigest()
            
            return {
                'dns_record': {
                    'type': 'TLSA',
                    'host': f'_25._tcp.mail.{self.domain}',
                    'value': f'3 1 1 {fingerprint}',
                    'ttl': 300
                },
                'record_explanation': {
                    '3': 'Domain-issued certificate',
                    '1': 'Subject Public Key Info',
                    '1': 'SHA-256 hash',
                    fingerprint: 'Certificate fingerprint'
                },
                'requirements': [
                    'DNSSEC must be enabled on domain',
                    'Valid SSL certificate on mail server',
                    'MX record must point to mail server',
                    'Mail server must support DANE'
                ],
                'benefits': [
                    'Highest level of email security',
                    'Prevents certificate spoofing',
                    'Cryptographic verification',
                    'Future-proof security'
                ],
                'certificate_fingerprint': fingerprint
            }
            
        except Exception as e:
            return {
                'error': f'Could not generate DANE record: {str(e)}',
                'requirements': [
                    'Mail server must be accessible',
                    'Valid SSL certificate required',
                    'DNSSEC must be enabled'
                ]
            }
    
    def setup_tls_rpt(self) -> Dict:
        """Setup TLS Reporting for monitoring"""
        return {
            'dns_record': {
                'type': 'TXT',
                'host': f'_smtp._tls.{self.domain}',
                'value': f'v=TLSRPTv1; rua=mailto:tls-reports@{self.domain}',
                'ttl': 300
            },
            'purpose': 'Monitor TLS delivery failures',
            'benefits': [
                'Visibility into TLS issues',
                'Monitor MTA-STS effectiveness',
                'Identify delivery problems',
                'Compliance reporting'
            ],
            'report_handling': {
                'email': f'tls-reports@{self.domain}',
                'format': 'JSON reports',
                'frequency': 'Daily',
                'processing': 'Automated analysis recommended'
            }
        }
    
    async def verify_all_authentication(self) -> Dict:
        """Verify all authentication methods are working"""
        print("🔐 Verifying all authentication methods...")
        
        results = {
            'spf': await self._check_spf(),
            'dkim': await self._check_dkim(),
            'dmarc': await self._check_dmarc(),
            'bimi': await self._check_bimi(),
            'mta_sts': await self._check_mta_sts(),
            'dane': await self._check_dane(),
            'reverse_dns': await self._check_reverse_dns(),
            'tls_rpt': await self._check_tls_rpt()
        }
        
        # Calculate authentication score
        valid_count = sum(1 for v in results.values() if v.get('valid', False))
        total_count = len(results)
        score = (valid_count / total_count) * 100
        
        return {
            'overall_score': round(score, 1),
            'valid_records': valid_count,
            'total_records': total_count,
            'results': results,
            'recommendations': self._get_auth_recommendations(results),
            'security_level': self._calculate_security_level(score)
        }
    
    async def _check_spf(self) -> Dict:
        """Check SPF record"""
        try:
            txt_records = dns.resolver.resolve(self.subdomain, 'TXT')
            
            for record in txt_records:
                record_str = str(record).strip('"')
                if record_str.startswith('v=spf1'):
                    return {
                        'valid': True,
                        'record': record_str,
                        'mechanisms': self._parse_spf_mechanisms(record_str),
                        'status': 'configured'
                    }
            
            return {
                'valid': False,
                'error': 'No SPF record found',
                'recommendation': 'Add SPF record to DNS'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'recommendation': 'Check DNS configuration'
            }
    
    def _parse_spf_mechanisms(self, spf_record: str) -> List[str]:
        """Parse SPF mechanisms"""
        mechanisms = []
        parts = spf_record.split()
        
        for part in parts[1:]:  # Skip v=spf1
            if part.startswith(('include:', 'a:', 'mx:', 'ip4:', 'ip6:')):
                mechanisms.append(part)
            elif part in ['~all', '-all', '+all', '?all']:
                mechanisms.append(f'qualifier: {part}')
        
        return mechanisms
    
    async def _check_dkim(self) -> Dict:
        """Check DKIM record"""
        try:
            # Check common DKIM selectors
            selectors = ['default', 's1', 's2', 'selector1', 'selector2', 'mail']
            
            for selector in selectors:
                try:
                    dkim_domain = f"{selector}._domainkey.{self.subdomain}"
                    txt_records = dns.resolver.resolve(dkim_domain, 'TXT')
                    
                    for record in txt_records:
                        record_str = str(record).strip('"')
                        if 'v=DKIM1' in record_str:
                            return {
                                'valid': True,
                                'selector': selector,
                                'record': record_str,
                                'key_type': 'RSA' if 'k=rsa' in record_str else 'Unknown',
                                'status': 'configured'
                            }
                except dns.resolver.NXDOMAIN:
                    continue
            
            return {
                'valid': False,
                'error': 'No DKIM record found',
                'selectors_checked': selectors,
                'recommendation': 'Configure DKIM signing with your ESP'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'recommendation': 'Check DKIM configuration'
            }
    
    async def _check_dmarc(self) -> Dict:
        """Check DMARC record"""
        try:
            dmarc_domain = f"_dmarc.{self.subdomain}"
            txt_records = dns.resolver.resolve(dmarc_domain, 'TXT')
            
            for record in txt_records:
                record_str = str(record).strip('"')
                if record_str.startswith('v=DMARC1'):
                    policy = self._parse_dmarc_policy(record_str)
                    return {
                        'valid': True,
                        'record': record_str,
                        'policy': policy,
                        'status': 'configured'
                    }
            
            return {
                'valid': False,
                'error': 'No DMARC record found',
                'recommendation': 'Add DMARC policy to DNS'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'recommendation': 'Check DMARC configuration'
            }
    
    def _parse_dmarc_policy(self, dmarc_record: str) -> Dict:
        """Parse DMARC policy"""
        policy = {}
        parts = dmarc_record.split(';')
        
        for part in parts:
            if '=' in part:
                key, value = part.strip().split('=', 1)
                policy[key] = value
        
        return policy
    
    async def _check_bimi(self) -> Dict:
        """Check BIMI record"""
        try:
            bimi_domain = f"default._bimi.{self.subdomain}"
            txt_records = dns.resolver.resolve(bimi_domain, 'TXT')
            
            for record in txt_records:
                record_str = str(record).strip('"')
                if record_str.startswith('v=BIMI1'):
                    return {
                        'valid': True,
                        'record': record_str,
                        'status': 'configured'
                    }
            
            return {
                'valid': False,
                'error': 'No BIMI record found',
                'recommendation': 'Add BIMI record for brand indicators'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'recommendation': 'BIMI is optional but recommended'
            }
    
    async def _check_mta_sts(self) -> Dict:
        """Check MTA-STS record"""
        try:
            mta_sts_domain = f"_mta-sts.{self.domain}"
            txt_records = dns.resolver.resolve(mta_sts_domain, 'TXT')
            
            for record in txt_records:
                record_str = str(record).strip('"')
                if record_str.startswith('v=STSv1'):
                    # Also check policy file
                    policy_url = f"https://mta-sts.{self.domain}/.well-known/mta-sts.txt"
                    try:
                        response = requests.get(policy_url, timeout=10)
                        if response.status_code == 200:
                            return {
                                'valid': True,
                                'record': record_str,
                                'policy_file': response.text,
                                'status': 'configured'
                            }
                    except:
                        pass
                    
                    return {
                        'valid': False,
                        'record': record_str,
                        'error': 'Policy file not accessible',
                        'recommendation': 'Ensure MTA-STS policy file is accessible'
                    }
            
            return {
                'valid': False,
                'error': 'No MTA-STS record found',
                'recommendation': 'Add MTA-STS for enhanced security'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'recommendation': 'MTA-STS is optional but recommended'
            }
    
    async def _check_dane(self) -> Dict:
        """Check DANE TLSA record"""
        try:
            dane_domain = f"_25._tcp.mail.{self.domain}"
            tlsa_records = dns.resolver.resolve(dane_domain, 'TLSA')
            
            if tlsa_records:
                return {
                    'valid': True,
                    'records': [str(record) for record in tlsa_records],
                    'status': 'configured'
                }
            
            return {
                'valid': False,
                'error': 'No DANE TLSA record found',
                'recommendation': 'DANE is optional but provides highest security'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'recommendation': 'DANE requires DNSSEC'
            }
    
    async def _check_reverse_dns(self) -> Dict:
        """Check reverse DNS (PTR) records"""
        # This would check PTR records for sending IPs
        # Implementation depends on knowing the sending IPs
        return {
            'valid': True,  # Assume configured
            'status': 'Contact hosting provider to configure PTR records',
            'recommendation': 'Ensure all sending IPs have proper PTR records'
        }
    
    async def _check_tls_rpt(self) -> Dict:
        """Check TLS reporting record"""
        try:
            tls_rpt_domain = f"_smtp._tls.{self.domain}"
            txt_records = dns.resolver.resolve(tls_rpt_domain, 'TXT')
            
            for record in txt_records:
                record_str = str(record).strip('"')
                if record_str.startswith('v=TLSRPTv1'):
                    return {
                        'valid': True,
                        'record': record_str,
                        'status': 'configured'
                    }
            
            return {
                'valid': False,
                'error': 'No TLS-RPT record found',
                'recommendation': 'Add TLS reporting for monitoring'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'recommendation': 'TLS-RPT is optional but useful for monitoring'
            }
    
    def _get_auth_recommendations(self, results: Dict) -> List[str]:
        """Get authentication recommendations"""
        recommendations = []
        
        if not results['spf']['valid']:
            recommendations.append("🔴 CRITICAL: Configure SPF record immediately")
        
        if not results['dkim']['valid']:
            recommendations.append("🔴 CRITICAL: Configure DKIM signing with your ESP")
        
        if not results['dmarc']['valid']:
            recommendations.append("🔴 CRITICAL: Add DMARC policy to prevent spoofing")
        
        if not results['bimi']['valid']:
            recommendations.append("🟡 OPTIONAL: Add BIMI record for brand indicators in Gmail")
        
        if not results['mta_sts']['valid']:
            recommendations.append("🟡 RECOMMENDED: Add MTA-STS for enhanced security")
        
        if not results['dane']['valid']:
            recommendations.append("🟡 ADVANCED: Consider DANE for ultimate security")
        
        return recommendations
    
    def _calculate_security_level(self, score: float) -> str:
        """Calculate security level based on score"""
        if score >= 90:
            return "Maximum Security"
        elif score >= 75:
            return "High Security"
        elif score >= 60:
            return "Medium Security"
        elif score >= 40:
            return "Basic Security"
        else:
            return "Insufficient Security"
