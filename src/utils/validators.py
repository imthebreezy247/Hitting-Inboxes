# src/utils/validators.py
import re
from typing import Dict, List, Tuple, Optional
from email_validator import validate_email, EmailNotValidError
from urllib.parse import urlparse
import dns.resolver

class EmailValidator:
    """Advanced email validation with deliverability checks"""
    
    def __init__(self):
        self.disposable_domains = self._load_disposable_domains()
        self.role_based_prefixes = [
            'admin', 'administrator', 'support', 'help', 'info', 'contact',
            'sales', 'marketing', 'noreply', 'no-reply', 'postmaster',
            'webmaster', 'hostmaster', 'abuse', 'security'
        ]
    
    def _load_disposable_domains(self) -> set:
        """Load known disposable email domains"""
        # In production, this would load from a file or API
        return {
            '10minutemail.com', 'tempmail.org', 'guerrillamail.com',
            'mailinator.com', 'yopmail.com', 'temp-mail.org',
            'throwaway.email', 'getnada.com', 'maildrop.cc'
        }
    
    def validate_email_address(self, email: str) -> Dict:
        """Comprehensive email validation"""
        result = {
            'email': email,
            'is_valid': False,
            'normalized_email': None,
            'issues': [],
            'warnings': [],
            'deliverability_score': 0.0
        }
        
        try:
            # Basic format validation
            validated = validate_email(email)
            normalized_email = validated.email.lower()
            result['normalized_email'] = normalized_email
            
            # Extract domain and local parts
            local_part, domain = normalized_email.split('@')
            
            # Check for common issues
            issues = []
            warnings = []
            score = 100.0
            
            # Check for disposable email
            if domain in self.disposable_domains:
                issues.append('Disposable email domain')
                score -= 50
            
            # Check for role-based email
            if local_part in self.role_based_prefixes:
                warnings.append('Role-based email address')
                score -= 10
            
            # Check domain MX records
            mx_valid, mx_message = self._check_mx_records(domain)
            if not mx_valid:
                issues.append(f'MX record issue: {mx_message}')
                score -= 30
            else:
                score += 10
            
            # Check for common typos in popular domains
            typo_suggestion = self._check_domain_typos(domain)
            if typo_suggestion:
                warnings.append(f'Possible typo, did you mean: {typo_suggestion}')
                score -= 5
            
            # Check local part for suspicious patterns
            if self._has_suspicious_local_part(local_part):
                warnings.append('Suspicious local part pattern')
                score -= 5
            
            result['is_valid'] = len(issues) == 0
            result['issues'] = issues
            result['warnings'] = warnings
            result['deliverability_score'] = max(0, min(100, score))
            
        except EmailNotValidError as e:
            result['issues'].append(f'Invalid email format: {str(e)}')
        
        return result
    
    def _check_mx_records(self, domain: str) -> Tuple[bool, str]:
        """Check if domain has valid MX records"""
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            if len(mx_records) > 0:
                return True, "MX records found"
            else:
                return False, "No MX records found"
        except dns.resolver.NXDOMAIN:
            return False, "Domain does not exist"
        except dns.resolver.NoAnswer:
            return False, "No MX records configured"
        except Exception as e:
            return False, f"DNS lookup failed: {str(e)}"
    
    def _check_domain_typos(self, domain: str) -> Optional[str]:
        """Check for common typos in popular email domains"""
        popular_domains = {
            'gmail.com': ['gmai.com', 'gmial.com', 'gmail.co', 'gmaill.com'],
            'yahoo.com': ['yaho.com', 'yahoo.co', 'yahooo.com'],
            'outlook.com': ['outlook.co', 'outlok.com', 'outloo.com'],
            'hotmail.com': ['hotmai.com', 'hotmail.co', 'hotmial.com']
        }
        
        for correct_domain, typos in popular_domains.items():
            if domain in typos:
                return correct_domain
        
        return None
    
    def _has_suspicious_local_part(self, local_part: str) -> bool:
        """Check for suspicious patterns in local part"""
        suspicious_patterns = [
            r'^[0-9]+$',  # Only numbers
            r'^.{1,2}$',  # Too short
            r'(.)\1{3,}',  # Repeated characters
            r'^(test|temp|fake|dummy)',  # Test/fake prefixes
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, local_part, re.IGNORECASE):
                return True
        
        return False
    
    def validate_email_list(self, emails: List[str]) -> Dict:
        """Validate a list of emails"""
        results = {
            'total_emails': len(emails),
            'valid_emails': [],
            'invalid_emails': [],
            'warnings': [],
            'summary': {
                'valid_count': 0,
                'invalid_count': 0,
                'disposable_count': 0,
                'role_based_count': 0,
                'average_deliverability_score': 0.0
            }
        }
        
        total_score = 0.0
        disposable_count = 0
        role_based_count = 0
        
        for email in emails:
            validation_result = self.validate_email_address(email)
            
            if validation_result['is_valid']:
                results['valid_emails'].append({
                    'email': validation_result['normalized_email'],
                    'deliverability_score': validation_result['deliverability_score'],
                    'warnings': validation_result['warnings']
                })
                results['summary']['valid_count'] += 1
                total_score += validation_result['deliverability_score']
            else:
                results['invalid_emails'].append({
                    'email': email,
                    'issues': validation_result['issues']
                })
                results['summary']['invalid_count'] += 1
            
            # Count specific issues
            if 'Disposable email domain' in validation_result['issues']:
                disposable_count += 1
            
            if any('role-based' in warning.lower() for warning in validation_result['warnings']):
                role_based_count += 1
        
        results['summary']['disposable_count'] = disposable_count
        results['summary']['role_based_count'] = role_based_count
        
        if results['summary']['valid_count'] > 0:
            results['summary']['average_deliverability_score'] = total_score / results['summary']['valid_count']
        
        return results

class ContentValidator:
    """Validate email content for deliverability"""
    
    def __init__(self):
        self.spam_trigger_words = [
            'free', 'guarantee', 'no obligation', 'winner', 'urgent',
            'act now', 'limited time', 'click here', 'buy now', 'special offer',
            'congratulations', "you've won", 'cash bonus', 'risk free',
            'make money', 'work from home', 'increase sales', 'double your income'
        ]
    
    def validate_subject_line(self, subject: str) -> Dict:
        """Validate email subject line"""
        result = {
            'subject': subject,
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'spam_score': 0.0
        }
        
        # Length check
        if len(subject) < 10:
            result['warnings'].append('Subject line is very short')
        elif len(subject) > 60:
            result['warnings'].append('Subject line is too long (may be truncated)')
        
        # Spam word check
        spam_words_found = [word for word in self.spam_trigger_words 
                           if word.lower() in subject.lower()]
        if spam_words_found:
            result['warnings'].append(f'Spam trigger words: {", ".join(spam_words_found)}')
            result['spam_score'] += len(spam_words_found) * 0.5
        
        # Excessive punctuation
        exclamation_count = subject.count('!')
        if exclamation_count > 1:
            result['warnings'].append('Too many exclamation marks')
            result['spam_score'] += exclamation_count * 0.2
        
        # All caps check
        if subject.isupper() and len(subject) > 5:
            result['warnings'].append('Subject line is all caps')
            result['spam_score'] += 1.0
        
        # Excessive capitalization
        caps_ratio = sum(1 for c in subject if c.isupper()) / len(subject) if subject else 0
        if caps_ratio > 0.5:
            result['warnings'].append('Too many capital letters')
            result['spam_score'] += 0.5
        
        # Set validity based on spam score
        if result['spam_score'] > 3.0:
            result['is_valid'] = False
            result['issues'].append('High spam score - likely to be filtered')
        
        return result
    
    def validate_content(self, html_content: str, text_content: str = None) -> Dict:
        """Validate email content"""
        from bs4 import BeautifulSoup
        
        result = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'spam_score': 0.0,
            'metrics': {}
        }
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        text_length = len(soup.get_text().strip())
        
        # Basic metrics
        result['metrics'] = {
            'text_length': text_length,
            'html_length': len(html_content),
            'link_count': len(soup.find_all('a')),
            'image_count': len(soup.find_all('img'))
        }
        
        # Text length check
        if text_length < 200:
            result['warnings'].append('Very short content')
            result['spam_score'] += 0.5
        
        # Link density check
        if result['metrics']['link_count'] > 0:
            link_density = result['metrics']['link_count'] / (text_length / 100)
            if link_density > 5:
                result['warnings'].append('High link density')
                result['spam_score'] += 1.0
        
        # Image-to-text ratio
        if result['metrics']['image_count'] > 0:
            image_ratio = result['metrics']['image_count'] / (text_length / 100)
            if image_ratio > 1:
                result['warnings'].append('High image-to-text ratio')
                result['spam_score'] += 0.5
        
        # Check for required elements
        if not soup.find('a', string=re.compile('unsubscribe', re.I)):
            result['issues'].append('Missing unsubscribe link')
        
        # Check for images without alt text
        images_without_alt = [img for img in soup.find_all('img') if not img.get('alt')]
        if images_without_alt:
            result['warnings'].append(f'{len(images_without_alt)} images missing alt text')
        
        # Spam word check in content
        content_text = soup.get_text().lower()
        spam_words_found = [word for word in self.spam_trigger_words if word in content_text]
        if spam_words_found:
            result['warnings'].append(f'Spam trigger words in content: {", ".join(spam_words_found[:5])}')
            result['spam_score'] += len(spam_words_found) * 0.3
        
        # Set validity
        if result['spam_score'] > 5.0:
            result['is_valid'] = False
            result['issues'].append('High spam score - content needs revision')
        
        return result

class URLValidator:
    """Validate URLs in email content"""
    
    def validate_url(self, url: str) -> Dict:
        """Validate a single URL"""
        result = {
            'url': url,
            'is_valid': False,
            'issues': [],
            'warnings': []
        }
        
        try:
            parsed = urlparse(url)
            
            # Basic structure check
            if not parsed.scheme or not parsed.netloc:
                result['issues'].append('Invalid URL structure')
                return result
            
            # Protocol check
            if parsed.scheme not in ['http', 'https']:
                result['warnings'].append('Non-standard protocol')
            
            # HTTPS recommendation
            if parsed.scheme == 'http':
                result['warnings'].append('Consider using HTTPS')
            
            # Domain validation
            domain = parsed.netloc.lower()
            
            # Check for suspicious domains
            suspicious_patterns = [
                r'bit\.ly', r'tinyurl\.com', r'short\.link',  # URL shorteners
                r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+',  # IP addresses
                r'[a-z0-9]{10,}\.com'  # Random-looking domains
            ]
            
            for pattern in suspicious_patterns:
                if re.search(pattern, domain):
                    result['warnings'].append('Potentially suspicious domain')
                    break
            
            result['is_valid'] = len(result['issues']) == 0
            
        except Exception as e:
            result['issues'].append(f'URL parsing error: {str(e)}')
        
        return result
