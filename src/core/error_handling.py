# src/core/error_handling.py
import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
import json

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    """Error categories for better classification"""
    EMAIL_DELIVERY = "email_delivery"
    DATABASE = "database"
    ESP_CONNECTION = "esp_connection"
    RATE_LIMITING = "rate_limiting"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    SYSTEM = "system"
    NETWORK = "network"

class EmailDeliveryError(Exception):
    """Base exception for email delivery errors"""
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.EMAIL_DELIVERY, 
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM, details: Optional[Dict] = None):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.timestamp = datetime.utcnow()

class ESPConnectionError(EmailDeliveryError):
    """ESP connection specific errors"""
    def __init__(self, message: str, esp_name: str, status_code: Optional[int] = None, 
                 response_body: Optional[str] = None):
        details = {
            'esp_name': esp_name,
            'status_code': status_code,
            'response_body': response_body
        }
        super().__init__(message, ErrorCategory.ESP_CONNECTION, ErrorSeverity.HIGH, details)

class RateLimitError(EmailDeliveryError):
    """Rate limiting errors"""
    def __init__(self, message: str, esp_name: str, limit_type: str, 
                 current_count: int, limit: int):
        details = {
            'esp_name': esp_name,
            'limit_type': limit_type,
            'current_count': current_count,
            'limit': limit
        }
        super().__init__(message, ErrorCategory.RATE_LIMITING, ErrorSeverity.MEDIUM, details)

class DatabaseError(EmailDeliveryError):
    """Database operation errors"""
    def __init__(self, message: str, operation: str, query: Optional[str] = None):
        details = {
            'operation': operation,
            'query': query
        }
        super().__init__(message, ErrorCategory.DATABASE, ErrorSeverity.HIGH, details)

class ValidationError(EmailDeliveryError):
    """Input validation errors"""
    def __init__(self, message: str, field: str, value: Any, validation_rule: str):
        details = {
            'field': field,
            'value': str(value),
            'validation_rule': validation_rule
        }
        super().__init__(message, ErrorCategory.VALIDATION, ErrorSeverity.LOW, details)

class ErrorHandler:
    """
    Centralized error handling and logging system
    Provides structured error logging, alerting, and recovery mechanisms
    """
    
    def __init__(self):
        self.error_counts = {}
        self.circuit_breakers = {}
        self.alert_thresholds = {
            ErrorSeverity.CRITICAL: 1,  # Alert immediately
            ErrorSeverity.HIGH: 5,      # Alert after 5 occurrences
            ErrorSeverity.MEDIUM: 10,   # Alert after 10 occurrences
            ErrorSeverity.LOW: 50       # Alert after 50 occurrences
        }
    
    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Handle and log errors with structured information
        
        Args:
            error: The exception that occurred
            context: Additional context information
            
        Returns:
            Dict with error details and recommended actions
        """
        context = context or {}
        
        # Determine error type and details
        if isinstance(error, EmailDeliveryError):
            error_info = self._handle_email_delivery_error(error, context)
        else:
            error_info = self._handle_generic_error(error, context)
        
        # Log the error
        self._log_error(error_info)
        
        # Update error counts and check for alerts
        self._update_error_counts(error_info)
        self._check_alert_thresholds(error_info)
        
        # Update circuit breakers if needed
        self._update_circuit_breakers(error_info)
        
        return error_info
    
    def _handle_email_delivery_error(self, error: EmailDeliveryError, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle EmailDeliveryError and its subclasses"""
        error_info = {
            'error_id': self._generate_error_id(),
            'timestamp': error.timestamp.isoformat(),
            'category': error.category.value,
            'severity': error.severity.value,
            'message': str(error),
            'details': error.details,
            'context': context,
            'traceback': traceback.format_exc(),
            'recommended_actions': self._get_recommended_actions(error)
        }
        
        return error_info
    
    def _handle_generic_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle generic exceptions"""
        # Try to categorize the error based on its type and message
        category, severity = self._categorize_generic_error(error)
        
        error_info = {
            'error_id': self._generate_error_id(),
            'timestamp': datetime.utcnow().isoformat(),
            'category': category.value,
            'severity': severity.value,
            'message': str(error),
            'error_type': type(error).__name__,
            'details': {},
            'context': context,
            'traceback': traceback.format_exc(),
            'recommended_actions': self._get_generic_recommended_actions(error)
        }
        
        return error_info
    
    def _categorize_generic_error(self, error: Exception) -> tuple[ErrorCategory, ErrorSeverity]:
        """Categorize generic errors"""
        error_message = str(error).lower()
        error_type = type(error).__name__
        
        # Database errors
        if any(keyword in error_message for keyword in ['database', 'sql', 'connection']):
            return ErrorCategory.DATABASE, ErrorSeverity.HIGH
        
        # Network errors
        if any(keyword in error_message for keyword in ['network', 'timeout', 'connection refused']):
            return ErrorCategory.NETWORK, ErrorSeverity.MEDIUM
        
        # Authentication errors
        if any(keyword in error_message for keyword in ['auth', 'unauthorized', 'forbidden']):
            return ErrorCategory.AUTHENTICATION, ErrorSeverity.HIGH
        
        # Validation errors
        if error_type in ['ValueError', 'TypeError', 'ValidationError']:
            return ErrorCategory.VALIDATION, ErrorSeverity.LOW
        
        # Default to system error
        return ErrorCategory.SYSTEM, ErrorSeverity.MEDIUM
    
    def _get_recommended_actions(self, error: EmailDeliveryError) -> List[str]:
        """Get recommended actions based on error type"""
        actions = []
        
        if isinstance(error, ESPConnectionError):
            actions.extend([
                f"Check {error.details.get('esp_name')} API status",
                "Verify API credentials",
                "Check network connectivity",
                "Consider switching to backup ESP"
            ])
        
        elif isinstance(error, RateLimitError):
            actions.extend([
                f"Reduce sending rate for {error.details.get('esp_name')}",
                "Implement exponential backoff",
                "Distribute load across multiple ESPs",
                "Review rate limiting configuration"
            ])
        
        elif isinstance(error, DatabaseError):
            actions.extend([
                "Check database connectivity",
                "Verify database schema",
                "Review query performance",
                "Check disk space and resources"
            ])
        
        elif isinstance(error, ValidationError):
            actions.extend([
                f"Fix validation for field: {error.details.get('field')}",
                "Review input data format",
                "Update validation rules if needed"
            ])
        
        return actions
    
    def _get_generic_recommended_actions(self, error: Exception) -> List[str]:
        """Get recommended actions for generic errors"""
        actions = ["Review error details and traceback"]
        
        error_message = str(error).lower()
        
        if 'timeout' in error_message:
            actions.extend([
                "Increase timeout values",
                "Check network connectivity",
                "Review system performance"
            ])
        
        elif 'memory' in error_message:
            actions.extend([
                "Check system memory usage",
                "Optimize memory-intensive operations",
                "Consider increasing available memory"
            ])
        
        elif 'permission' in error_message:
            actions.extend([
                "Check file/directory permissions",
                "Verify user access rights",
                "Review security settings"
            ])
        
        return actions
    
    def _log_error(self, error_info: Dict[str, Any]):
        """Log error with appropriate level"""
        severity = error_info['severity']
        message = f"[{error_info['error_id']}] {error_info['message']}"
        
        extra_info = {
            'error_id': error_info['error_id'],
            'category': error_info['category'],
            'severity': severity,
            'details': error_info['details'],
            'context': error_info['context']
        }
        
        if severity == ErrorSeverity.CRITICAL.value:
            logger.critical(message, extra=extra_info)
        elif severity == ErrorSeverity.HIGH.value:
            logger.error(message, extra=extra_info)
        elif severity == ErrorSeverity.MEDIUM.value:
            logger.warning(message, extra=extra_info)
        else:
            logger.info(message, extra=extra_info)
    
    def _update_error_counts(self, error_info: Dict[str, Any]):
        """Update error counts for monitoring"""
        category = error_info['category']
        severity = error_info['severity']
        
        key = f"{category}_{severity}"
        
        if key not in self.error_counts:
            self.error_counts[key] = {
                'count': 0,
                'first_occurrence': error_info['timestamp'],
                'last_occurrence': error_info['timestamp']
            }
        
        self.error_counts[key]['count'] += 1
        self.error_counts[key]['last_occurrence'] = error_info['timestamp']
    
    def _check_alert_thresholds(self, error_info: Dict[str, Any]):
        """Check if error counts exceed alert thresholds"""
        severity = ErrorSeverity(error_info['severity'])
        category = error_info['category']
        
        key = f"{category}_{severity.value}"
        count = self.error_counts.get(key, {}).get('count', 0)
        threshold = self.alert_thresholds.get(severity, 10)
        
        if count >= threshold and count % threshold == 0:
            self._send_alert(error_info, count)
    
    def _send_alert(self, error_info: Dict[str, Any], count: int):
        """Send alert for high error counts"""
        alert_message = (
            f"ALERT: {error_info['category']} errors reached {count} occurrences\n"
            f"Latest error: {error_info['message']}\n"
            f"Severity: {error_info['severity']}\n"
            f"Recommended actions: {', '.join(error_info['recommended_actions'])}"
        )
        
        # In production, this would send to monitoring system, Slack, email, etc.
        logger.critical(f"ALERT TRIGGERED: {alert_message}")
    
    def _update_circuit_breakers(self, error_info: Dict[str, Any]):
        """Update circuit breaker status based on errors"""
        if error_info['category'] == ErrorCategory.ESP_CONNECTION.value:
            esp_name = error_info['details'].get('esp_name')
            if esp_name:
                if esp_name not in self.circuit_breakers:
                    self.circuit_breakers[esp_name] = {
                        'failure_count': 0,
                        'last_failure': None,
                        'state': 'closed'  # closed, open, half-open
                    }
                
                breaker = self.circuit_breakers[esp_name]
                breaker['failure_count'] += 1
                breaker['last_failure'] = datetime.utcnow()
                
                # Open circuit breaker after 5 failures
                if breaker['failure_count'] >= 5 and breaker['state'] == 'closed':
                    breaker['state'] = 'open'
                    logger.warning(f"Circuit breaker opened for ESP: {esp_name}")
    
    def _generate_error_id(self) -> str:
        """Generate unique error ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of recent errors"""
        return {
            'error_counts': self.error_counts,
            'circuit_breakers': self.circuit_breakers,
            'alert_thresholds': {k.value: v for k, v in self.alert_thresholds.items()}
        }
    
    def reset_error_counts(self):
        """Reset error counts (useful for testing or daily resets)"""
        self.error_counts.clear()
        logger.info("Error counts reset")

# Global error handler instance
error_handler = ErrorHandler()

def handle_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function to handle errors"""
    return error_handler.handle_error(error, context)
