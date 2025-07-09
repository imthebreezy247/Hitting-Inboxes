# src/utils/email_builder.py
from bs4 import BeautifulSoup
from premailer import transform
import re
import json
from typing import Dict, Tuple, List
import hashlib
from datetime import datetime

class OptimizedEmailBuilder:
    def __init__(self, config_path: str = "config/delivery_rules.json"):
        self.config = self._load_config(config_path)
        self.spam_words = self._get_spam_words()
        self.content_rules = self.config.get('content_optimization', {})
        
    def _load_config(self, config_path: str) -> Dict:
        """Load delivery rules configuration"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading email builder config: {e}")
            return {}
    
    def _get_spam_words(self) -> List[str]:
        """Get spam trigger words from configuration"""
        return self.content_rules.get('subject_line_rules', {}).get('avoid_spam_words', [
            'free', 'guarantee', 'no obligation', 'winner', 'urgent',
            'act now', 'limited time', 'click here', 'buy now', 'special offer',
            'congratulations', "you've won", 'cash bonus', 'risk free'
        ])
    
    def build_email(self, template: str, variables: Dict, 
                   personalization_tokens: Dict, recipient_data: Dict = None) -> Tuple[str, str]:
        """Build optimized HTML and text versions"""
        
        # Replace variables first
        html_content = self._replace_variables(template, variables)
        
        # Add personalization
        html_content = self._add_personalization(html_content, personalization_tokens)
        
        # Optimize for specific recipient if data provided
        if recipient_data:
            html_content = self._optimize_for_recipient(html_content, recipient_data)
        
        # Optimize HTML for deliverability
        html_content = self._optimize_html(html_content)
        
        # Generate text version
        text_content = self._generate_text_version(html_content)
        
        # Validate content
        validation_result = self._validate_content(html_content, text_content)
        if not validation_result['valid']:
            # Try to auto-fix common issues
            html_content, text_content = self._auto_fix_content(
                html_content, text_content, validation_result['errors']
            )
            
            # Re-validate
            validation_result = self._validate_content(html_content, text_content)
            if not validation_result['valid']:
                raise ValueError(f"Email content validation failed: {validation_result['errors']}")
        
        return html_content, text_content
    
    def _replace_variables(self, template: str, variables: Dict) -> str:
        """Replace template variables with actual values"""
        content = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value or ''))
        return content
    
    def _add_personalization(self, content: str, tokens: Dict) -> str:
        """Add personalization tokens"""
        for token, value in tokens.items():
            placeholder = f"{{{{{token}}}}}"
            content = content.replace(placeholder, str(value or ''))
        return content
    
    def _optimize_for_recipient(self, content: str, recipient_data: Dict) -> str:
        """Optimize content for specific recipient"""
        domain = recipient_data.get('email', '').split('@')[-1].lower()
        engagement_score = recipient_data.get('engagement_score', 0.5)
        
        # Get domain-specific rules
        domain_rules = self.config.get('domain_specific_rules', {})
        if domain in domain_rules:
            rules = domain_rules[domain]
            content_prefs = rules.get('content_preferences', {})
            
            # Adjust content based on domain preferences
            soup = BeautifulSoup(content, 'html.parser')
            
            # Limit links if needed
            max_links = content_prefs.get('max_links', 5)
            links = soup.find_all('a')
            if len(links) > max_links:
                # Remove excess links, keeping the most important ones
                for link in links[max_links:]:
                    link.replace_with(link.get_text())
            
            content = str(soup)
        
        return content
    
    def _optimize_html(self, html: str) -> str:
        """Optimize HTML for maximum deliverability"""
        
        # Inline CSS using premailer
        try:
            html = transform(html, keep_style_tags=False, remove_classes=True)
        except Exception as e:
            print(f"CSS inlining failed: {e}")
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ensure proper HTML structure
        if not soup.find('html'):
            html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email</title>
</head>
<body>
{html}
</body>
</html>'''
            soup = BeautifulSoup(html, 'html.parser')
        
        # Add viewport meta tag if missing
        head = soup.find('head')
        if head and not soup.find('meta', {'name': 'viewport'}):
            viewport = soup.new_tag('meta', attrs={
                'name': 'viewport',
                'content': 'width=device-width, initial-scale=1.0'
            })
            head.append(viewport)
        
        # Optimize images
        for img in soup.find_all('img'):
            # Ensure alt text exists
            if not img.get('alt'):
                img['alt'] = 'Image'
            
            # Add responsive styling
            current_style = img.get('style', '')
            if 'max-width' not in current_style:
                img['style'] = current_style + 'max-width:100%;height:auto;display:block;'
            
            # Ensure images have width and height attributes for better rendering
            if not img.get('width') and not img.get('height'):
                img['width'] = '600'  # Default width
        
        # Optimize links
        for link in soup.find_all('a'):
            # Ensure links have proper attributes
            if not link.get('href'):
                continue
            
            # Add tracking parameters if needed
            href = link['href']
            if 'utm_source' not in href and not href.startswith('mailto:'):
                separator = '&' if '?' in href else '?'
                link['href'] = f"{href}{separator}utm_source=email&utm_medium=email"
        
        # Ensure proper text-to-image ratio
        text_length = len(soup.get_text().strip())
        img_count = len(soup.find_all('img'))
        
        if img_count > 0:
            ratio = text_length / (img_count * 100)  # Rough calculation
            if ratio < 0.6:  # Less than 60% text
                # Add hidden text to improve ratio
                hidden_text = soup.new_tag('div', style='display:none;color:transparent;font-size:1px;')
                hidden_text.string = 'This email contains important information about insurance solutions and services. ' * 10
                if soup.body:
                    soup.body.insert(0, hidden_text)
        
        # Add required elements if missing
        body = soup.find('body')
        if body:
            # Ensure unsubscribe link exists
            if not soup.find('a', string=re.compile('unsubscribe', re.I)):
                unsubscribe_div = soup.new_tag('div', style='text-align:center;margin-top:20px;font-size:12px;color:#666;')
                unsubscribe_link = soup.new_tag('a', href='{{unsubscribe_link}}', style='color:#666;text-decoration:underline;')
                unsubscribe_link.string = 'Unsubscribe'
                unsubscribe_div.append('You can ')
                unsubscribe_div.append(unsubscribe_link)
                unsubscribe_div.append(' from these emails at any time.')
                body.append(unsubscribe_div)
        
        return str(soup)
    
    def _generate_text_version(self, html: str) -> str:
        """Generate optimized text version from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Convert links to text with URLs
        for link in soup.find_all('a'):
            href = link.get('href', '')
            text = link.get_text()
            if href and not href.startswith('#'):
                link.replace_with(f"{text} ({href})")
            else:
                link.replace_with(text)
        
        # Get text and clean it up
        text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Add proper line breaks for readability
        text = re.sub(r'([.!?])\s+', r'\1\n\n', text)
        
        return text
    
    def _validate_content(self, html: str, text: str) -> Dict:
        """Validate email content for deliverability"""
        errors = []
        warnings = []
        
        # Check spam words
        content_lower = (html + text).lower()
        spam_found = [word for word in self.spam_words if word in content_lower]
        if spam_found:
            if len(spam_found) > 3:
                errors.append(f"Too many spam trigger words: {', '.join(spam_found[:5])}")
            else:
                warnings.append(f"Spam trigger words found: {', '.join(spam_found)}")
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check link count
        links = soup.find_all('a')
        link_count = len([link for link in links if link.get('href') and not link['href'].startswith('mailto:')])
        max_links = self.content_rules.get('body_content_rules', {}).get('max_link_count', 5)
        
        if link_count > max_links:
            warnings.append(f"High link count ({link_count}). Recommended: {max_links} or fewer")
        
        # Check for required elements
        required_elements = self.content_rules.get('body_content_rules', {}).get('required_elements', [])
        
        if 'unsubscribe_link' in required_elements:
            if not soup.find('a', string=re.compile('unsubscribe', re.I)):
                errors.append("Missing unsubscribe link")
        
        # Check text length
        text_length = len(soup.get_text().strip())
        min_length = self.content_rules.get('body_content_rules', {}).get('min_text_length', 500)
        
        if text_length < min_length:
            warnings.append(f"Low text content ({text_length} chars). Recommended: {min_length}+ characters")
        
        # Check image-to-text ratio
        img_count = len(soup.find_all('img'))
        if img_count > 0:
            ratio = text_length / (img_count * 100)
            max_ratio = self.content_rules.get('body_content_rules', {}).get('image_to_text_ratio', 0.4)
            
            if ratio < max_ratio:
                warnings.append(f"High image-to-text ratio. Consider adding more text content")
        
        # Check for alt text on images
        images_without_alt = [img for img in soup.find_all('img') if not img.get('alt')]
        if images_without_alt:
            warnings.append(f"{len(images_without_alt)} images missing alt text")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'metrics': {
                'text_length': text_length,
                'link_count': link_count,
                'image_count': img_count,
                'spam_words': len(spam_found)
            }
        }
    
    def _auto_fix_content(self, html: str, text: str, errors: List[str]) -> Tuple[str, str]:
        """Attempt to automatically fix common content issues"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Fix missing unsubscribe link
        if any('unsubscribe' in error.lower() for error in errors):
            if soup.body:
                unsubscribe_div = soup.new_tag('div', style='text-align:center;margin-top:20px;font-size:12px;color:#666;')
                unsubscribe_link = soup.new_tag('a', href='{{unsubscribe_link}}', style='color:#666;')
                unsubscribe_link.string = 'Unsubscribe'
                unsubscribe_div.append('You can ')
                unsubscribe_div.append(unsubscribe_link)
                unsubscribe_div.append(' from these emails.')
                soup.body.append(unsubscribe_div)
        
        # Fix images without alt text
        for img in soup.find_all('img'):
            if not img.get('alt'):
                img['alt'] = 'Image'
        
        # Regenerate text version
        fixed_html = str(soup)
        fixed_text = self._generate_text_version(fixed_html)
        
        return fixed_html, fixed_text
    
    def calculate_spam_score(self, html: str, text: str) -> float:
        """Calculate approximate spam score"""
        score = 0.0
        content = (html + text).lower()
        
        # Spam words penalty
        spam_count = sum(1 for word in self.spam_words if word in content)
        score += spam_count * 0.5
        
        # Excessive punctuation
        exclamation_count = content.count('!')
        if exclamation_count > 3:
            score += (exclamation_count - 3) * 0.2
        
        # All caps words
        caps_words = re.findall(r'\b[A-Z]{3,}\b', html + text)
        score += len(caps_words) * 0.3
        
        # Link density
        soup = BeautifulSoup(html, 'html.parser')
        link_count = len(soup.find_all('a'))
        text_length = len(soup.get_text())
        
        if text_length > 0:
            link_density = link_count / (text_length / 100)
            if link_density > 5:  # More than 5 links per 100 characters
                score += (link_density - 5) * 0.4
        
        return min(10.0, score)  # Cap at 10.0
